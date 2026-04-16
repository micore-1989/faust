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

  Feedforward summary channel
    Each step's result can come with a compact `summary` dict (skill opts in
    by returning ToolResult(result=..., summary=...)). The executor prefers
    the summary over the full result when building Pass 2 context for later
    steps and when building the re-plan prompt. Keeps prompts small,
    structured, and parseable by the 1.5B parameterizer.

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
from .cache import ResultCache
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
from .pivots import matching_suggestions
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
  - Prior step summaries often name the canonical target via opinion fields:
      * `best_handshake_target` (from wifi_scan) → use as `bssid`
      * `first_hash_file` (from pcap_inspect / capture skills) → use as
        `hash_file` for crack steps
      * `rogue_bssid` (from rogue_ap_detector) → target for counter-ops
      * `attacker_mac` (from deauth_detector) → source to block / track
    Cite these directly instead of parsing them out of the full result.
  - If a required parameter cannot be determined from the summaries and the
    tool schema shows no `default`, leave the field absent — the tool will
    validate or error cleanly. Never invent MACs, IPs, hashes, or file paths.
  - If a parameter has a `default` in the schema, you MAY omit it; the
    registry will fill it. Only include it if you have a reason to override.
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
        cache: ResultCache | None = None,
    ) -> None:
        self.backend = backend
        self.deep_backend = deep_backend
        self.dispatcher = dispatcher
        self.config = config
        self.scoper = scoper
        self.plan_approver = plan_approver or _auto_approve_plan
        self.planner = Planner(backend, deep_backend=deep_backend)
        # Session-lived short-TTL cache of successful skill summaries.
        # The planner sees a "Known recent results" section so follow-up
        # prompts can skip re-scanning.
        self.cache = cache if cache is not None else ResultCache()

    async def run(
        self,
        user_input: str,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[Event]:
        """Run plan → approve → execute pipeline. Yields events.

        `conversation_history` carries forward prior turns as OpenAI-style
        messages (user + assistant pairs). The planner sees it so follow-up
        prompts like "attack the one we found" reference earlier results.
        Capped to config.conversation_memory_turns to protect token budget.
        """
        # ── Pass 1: build catalog, plan ─────────────────────────────
        allowed_names: list[str] | None = None
        if self.scoper is not None:
            allowed_names = await self.scoper.top_k(user_input, k=self.config.scoper_k)

        catalog = build_catalog(self.dispatcher.registry, allowed_names=allowed_names)
        if not catalog:
            yield Final(reason="error", error="no skills available")
            return

        history = self._trim_history(conversation_history)
        cache_section = self.cache.render_prompt_section()

        try:
            plan = await self.planner.plan(
                user_input, catalog, history=history,
                cache_section=cache_section,
            )
        except Exception as e:
            yield Final(reason="error", error=f"planner failed: {type(e).__name__}: {e}")
            return

        plan_id = f"plan-{uuid.uuid4().hex[:8]}"
        yield PlanProposed.from_plan(plan, plan_id=plan_id)

        if not plan.steps:
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
        # Hints produced by matching pivot_hints on the most recent step's
        # summary. Consumed by the next _parameterize_step, then cleared.
        pending_hints: list[str] = []
        replans_used = 0
        # Worklist of steps remaining — can be rewritten by a re-plan.
        remaining: list[PlanStep] = list(plan.steps)
        step_idx = 0

        while remaining:
            step = remaining.pop(0)
            call_id = f"{plan_id}-step{step_idx}"
            step_idx += 1

            tool = self.dispatcher.registry.get(step.skill)
            if tool is None:
                yield ToolCallExecuted(
                    call_id=call_id,
                    tool_name=step.skill,
                    error=f"unknown skill in plan: {step.skill}",
                )
                yield Final(
                    reason="error",
                    error=f"plan references missing skill: {step.skill}",
                )
                return

            try:
                tool_call = await self._parameterize_step(
                    user_input=user_input,
                    plan=plan,
                    step=step,
                    tool_schema=tool.to_openai_schema(),
                    step_results=step_results,
                    pending_hints=pending_hints,
                )
                pending_hints = []
            except Exception as e:
                yield Final(
                    reason="error",
                    error=f"parameter generation failed: {type(e).__name__}: {e}",
                )
                return

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

            step_results.append({
                "skill": step.skill,
                "intent": step.intent,
                "executed": result.executed,
                "result": result.result,
                "summary": result.summary,
                "error": result.error,
            })

            # ── Cache the summary so follow-up turns can skip re-scans ──
            # TTL depends on sensitivity (disruptive = never cached).
            if result.error is None and result.summary is not None:
                self.cache.store(
                    skill=step.skill,
                    args=tool_call.get("arguments", {}),
                    summary=result.summary,
                    sensitivity=tool.sensitivity,
                )

            # ── Pivot hints ────────────────────────────────────────
            # If the skill's frontmatter declared pivot_hints and this
            # step's summary matches any of them, queue the suggestions
            # for the next step's parameter-generation prompt. Cheap
            # reactive planning without paying a full re-plan.
            if result.error is None and result.summary is not None and tool.pivot_hints:
                matched = matching_suggestions(tool.pivot_hints, result.summary)
                if matched:
                    pending_hints.extend(f"{step.skill}: {s}" for s in matched)

            if result.error == "user_rejected":
                yield Final(reason="user_abort")
                return

            # ── Re-plan on surprise ────────────────────────────────
            # Step errored (but wasn't user-rejected). Invoke planner with
            # current state. If planner produces different remaining steps,
            # swap them in. Guard against infinite loops via replan_max.
            if (
                result.error is not None
                and self.config.replan_enabled
                and replans_used < self.config.replan_max
                and remaining  # only worth re-planning if there's still work
            ):
                replans_used += 1
                # Surface what each completed step actually learned, not just
                # its name — lets the re-planner reason about real results
                # instead of guessing.
                completed_lines = []
                for r in step_results:
                    if r.get("error"):
                        completed_lines.append(
                            f"  - {r['skill']} → ERROR: {str(r['error'])[:80]}"
                        )
                    elif r.get("summary") is not None:
                        completed_lines.append(
                            f"  - {r['skill']} → {json.dumps(r['summary'], default=str)}"
                        )
                    elif r.get("executed"):
                        completed_lines.append(f"  - {r['skill']} → completed")
                completed = "\n".join(completed_lines) or "  (none)"

                replan_prompt = (
                    f"ORIGINAL REQUEST: {user_input}\n\n"
                    f"The plan encountered an error at step `{step.skill}`: "
                    f"{result.error}\n\n"
                    f"Steps completed so far (with their outcomes):\n"
                    f"{completed}\n\n"
                    f"Remaining steps that were planned: "
                    f"{[s.skill for s in remaining]}\n\n"
                    f"Given what you now know from the outcomes above, revise "
                    f"the plan. Return only the REMAINING steps to accomplish "
                    f"the original request — do not repeat completed steps. If "
                    f"the request is no longer achievable, return an empty "
                    f"plan explaining why."
                )
                try:
                    new_plan = await self.planner.plan(
                        replan_prompt, catalog, history=history,
                        cache_section=self.cache.render_prompt_section(),
                    )
                except Exception:
                    # Re-plan failed — fall through to original remaining steps.
                    continue

                # Yield a new PlanProposed so the UI surfaces the revision.
                new_plan_id = f"{plan_id}-replan{replans_used}"
                yield PlanProposed.from_plan(new_plan, plan_id=new_plan_id)

                # Approve the revised plan with the same approver.
                if new_plan.steps:
                    approval = self.plan_approver(new_plan)
                    if hasattr(approval, "__await__"):
                        approved = await approval  # type: ignore[misc]
                    else:
                        approved = approval
                    if not approved:
                        yield Final(reason="user_abort", text="revised plan rejected")
                        return

                # Swap remaining with new plan's steps.
                remaining = list(new_plan.steps)

        yield Final(reason="end_turn")

    def _trim_history(
        self,
        history: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]] | None:
        """Cap history by turns AND by character budget.

        One turn = one {user, assistant} pair. We keep at most
        config.conversation_memory_turns pairs, and within that truncate
        each message so total content stays under config.conversation_memory_chars.
        """
        if not history or not self.config.conversation_memory:
            return None

        max_turns = max(0, self.config.conversation_memory_turns)
        # A turn is 2 messages (user + assistant).
        keep = history[-(max_turns * 2):] if max_turns > 0 else []
        if not keep:
            return None

        # Hard cap on total chars.
        budget = self.config.conversation_memory_chars
        # Truncate from the most recent backward so recent context survives.
        trimmed: list[dict[str, Any]] = []
        used = 0
        for msg in reversed(keep):
            c = str(msg.get("content", ""))
            remaining = budget - used
            if remaining <= 0:
                break
            if len(c) > remaining:
                c = c[: remaining - 3] + "..."
            trimmed.insert(0, {"role": msg.get("role", "user"), "content": c})
            used += len(c)

        return trimmed or None

    async def _parameterize_step(
        self,
        user_input: str,
        plan: Plan,
        step: PlanStep,
        tool_schema: dict[str, Any],
        step_results: list[dict[str, Any]],
        pending_hints: list[str] | None = None,
    ) -> dict[str, Any]:
        """Pass 2 LLM call — generate parameters for one step, given one schema."""
        history_summary = ""
        if step_results:
            lines = []
            for r in step_results:
                if r.get("error"):
                    lines.append(f"- {r['skill']}: error: {r['error']}")
                elif r.get("summary") is not None:
                    # Prefer the skill's own compact summary — structured,
                    # bounded, guaranteed-parseable. Keeps Pass 2 context small.
                    lines.append(
                        f"- {r['skill']}: {json.dumps(r['summary'], default=str)}"
                    )
                elif r.get("executed"):
                    # Legacy path: crude truncation of the full result.
                    # Shreds JSON at the boundary but the big model can cope.
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
        if pending_hints:
            step_context += (
                f"\nHints from the previous step (domain knowledge baked "
                f"into its SKILL.md). Use these to inform your parameter "
                f"choices when relevant:\n"
                + "\n".join(f"  - {h}" for h in pending_hints)
                + "\n"
            )
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
