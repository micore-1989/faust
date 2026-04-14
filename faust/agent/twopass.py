"""
TwoPassAgent — split reasoning (on Mephisto) from execution (on Faust).

Architecture:

  Pass 1 — Planner (Mephisto, minimal context)
    Input : user prompt + skill catalog (name + description + category + sensitivity)
    Output: structured Plan via submit_plan tool
    Context: never sees parameter schemas — just the catalog

  Plan approval
    Plan surfaces to the user via PlanProposed event
    PlanApprover callback (UI or CLI) approves / rejects the whole plan
    Rejection aborts with Final(reason="user_abort")

  Pass 2 — Per-step execution (Mephisto parameterizes, Faust dispatches)
    For each PlanStep:
      - Load JUST that skill's full schema (one tool only)
      - LLM call with: step intent + previous step results + one tool schema
      - Model returns a single tool_call with concrete arguments
      - Disclosure layer gates (same approver as single-pass)
      - Faust dispatches, emits events, records in journal
      - Result feeds into context for next step

This matches the "Mephisto advises, Faust executes" rule. Mephisto's per-call
context is constant-size regardless of how many skills exist. Faust holds the
authoritative registry and is the only thing that invokes tools.

Coexists with AgentLoop — you can run either. Env: FAUST_MODE=twopass selects this.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, AsyncIterator, Awaitable, Callable

from .backends import AssistantMessage, LLMBackend
from .catalog import build_catalog
from .config import AgentConfig
from .dispatch import Dispatcher
from .events import (
    Event,
    Final,
    PlanProposed,
    Thinking,
    ToolCallExecuted,
    ToolCallProposed,
)
from .plan import Plan, PlanStep
from .planner import Planner
from ..skills.scoper import SkillScoper


# PlanApprover is like Approver but scopes to the plan as a whole.
# Returns True to execute, False to abort.
PlanApprover = Callable[[Plan], Awaitable[bool] | bool]


async def _auto_approve_plan(plan: Plan) -> bool:
    return True


EXECUTOR_SYSTEM_PROMPT = """You are the execution layer of faust.

You are being asked to generate parameters for a SINGLE tool call. The plan
has already been agreed with the operator. Your job is narrow: produce the
correct arguments for the given tool, based on the step's intent and any
results from earlier steps.

Rules:
  - Call the provided tool exactly once. No freeform response.
  - If earlier steps produced relevant data (MAC addresses, SSIDs, coordinates),
    use those in your parameters — don't invent values.
  - If required parameters cannot be determined, make safe defaults where
    possible, or leave optional fields empty.
"""


class TwoPassAgent:
    """Two-pass orchestration: plan then execute step-by-step."""

    def __init__(
        self,
        backend: LLMBackend,
        dispatcher: Dispatcher,
        config: AgentConfig,
        scoper: SkillScoper | None = None,
        plan_approver: PlanApprover | None = None,
        deep_backend: LLMBackend | None = None,
    ) -> None:
        self.backend = backend
        self.deep_backend = deep_backend
        self.dispatcher = dispatcher
        self.config = config
        self.scoper = scoper
        self.plan_approver = plan_approver or _auto_approve_plan
        self.planner = Planner(backend, deep_backend=deep_backend)

    async def run(self, user_input: str) -> AsyncIterator[Event]:
        """Run plan → approve → execute pipeline. Yields events."""
        # ── Pass 1: build catalog, plan ─────────────────────────────
        allowed_names: list[str] | None = None
        if self.scoper is not None:
            allowed_names = await self.scoper.top_k(user_input, k=self.config.scoper_k)

        catalog = build_catalog(self.dispatcher.registry, allowed_names=allowed_names)
        if not catalog:
            yield Final(reason="error", error="no skills available")
            return

        try:
            plan = await self.planner.plan(user_input, catalog)
        except Exception as e:
            yield Final(reason="error", error=f"planner failed: {type(e).__name__}: {e}")
            return

        plan_id = f"plan-{uuid.uuid4().hex[:8]}"
        yield PlanProposed.from_plan(plan, plan_id=plan_id)

        if not plan.steps:
            # Planner decided no skills apply or returned empty plan.
            yield Final(
                reason="end_turn",
                text=plan.reasoning or "No applicable skills for this request.",
            )
            return

        # ── Plan approval ───────────────────────────────────────────
        approval = self.plan_approver(plan)
        if hasattr(approval, "__await__"):
            approved = await approval  # type: ignore[misc]
        else:
            approved = approval
        if not approved:
            yield Final(reason="user_abort", text="plan rejected by operator")
            return

        # ── Pass 2: execute each step ───────────────────────────────
        step_results: list[dict[str, Any]] = []

        for idx, step in enumerate(plan.steps):
            tool = self.dispatcher.registry.get(step.skill)
            if tool is None:
                yield ToolCallExecuted(
                    call_id=f"{plan_id}-step{idx}",
                    tool_name=step.skill,
                    error=f"unknown skill in plan: {step.skill}",
                )
                yield Final(
                    reason="error",
                    error=f"plan references missing skill: {step.skill}",
                )
                return

            # Per-step LLM call: ONE tool schema + intent + history.
            try:
                tool_call = await self._parameterize_step(
                    user_input=user_input,
                    plan=plan,
                    step=step,
                    tool_schema=tool.to_openai_schema(),
                    step_results=step_results,
                )
            except Exception as e:
                yield Final(
                    reason="error",
                    error=f"parameter generation failed: {type(e).__name__}: {e}",
                )
                return

            call_id = f"{plan_id}-step{idx}"
            yield ToolCallProposed(
                call_id=call_id,
                tool_name=step.skill,
                arguments=tool_call.get("arguments", {}),
                sensitivity=tool.sensitivity,
            )

            result = await self.dispatcher.dispatch(
                step.skill,
                tool_call.get("arguments", {}),
            )

            yield self.dispatcher.make_executed_event(
                call_id=call_id,
                tool_name=step.skill,
                result=result,
            )

            # Record for next step's context.
            step_results.append({
                "skill": step.skill,
                "intent": step.intent,
                "executed": result.executed,
                "result": result.result,
                "error": result.error,
            })

            if result.error == "user_rejected":
                yield Final(reason="user_abort")
                return

        yield Final(reason="end_turn")

    async def _parameterize_step(
        self,
        user_input: str,
        plan: Plan,
        step: PlanStep,
        tool_schema: dict[str, Any],
        step_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Pass 2 LLM call — generate parameters for one step, given one schema."""
        history_summary = ""
        if step_results:
            lines = []
            for r in step_results:
                if r.get("error"):
                    lines.append(f"- {r['skill']}: error: {r['error']}")
                elif r.get("executed"):
                    result_repr = json.dumps(r.get("result"), default=str)[:800]
                    lines.append(f"- {r['skill']}: {result_repr}")
            history_summary = "\n".join(lines)

        step_context = (
            f"Plan reasoning: {plan.reasoning}\n\n"
            f"Original user request: {user_input}\n\n"
            f"Current step intent: {step.intent}\n"
        )
        if history_summary:
            step_context += f"\nEarlier step results:\n{history_summary}\n"
        step_context += f"\nCall the `{step.skill}` tool with appropriate parameters."

        messages = [
            {"role": "system", "content": EXECUTOR_SYSTEM_PROMPT},
            {"role": "user", "content": step_context},
        ]

        msg = await self.backend.complete(
            messages=messages,
            tools=[tool_schema],
        )

        # The model should have called the tool. If it didn't, return empty args.
        for tc in msg.tool_calls:
            if tc.name == step.skill:
                return {"name": tc.name, "arguments": tc.arguments}

        # Fallback: empty args, let the tool validate or error.
        return {"name": step.skill, "arguments": {}}
