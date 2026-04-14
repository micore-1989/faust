"""
Planner — Pass 1 of the two-pass architecture.

Sends a minimal planning prompt to the backend (Mephisto's hailo-ollama in
prod, local Ollama in dev) with the skill catalog as the ONLY context.

The model's output is constrained via a single `submit_plan` tool. The
model's only valid action is to call this tool with a structured plan —
guaranteed valid JSON, no parsing fragility.

The catalog tells the model WHAT each skill does, not HOW to call it.
Pass 2 (executor) handles parameter generation with the full schema.
"""

from __future__ import annotations

import json
from typing import Any

from .backends import LLMBackend
from .catalog import CatalogEntry, render_catalog
from .plan import Plan, PlanStep


PLANNER_SYSTEM_PROMPT = """You are the planning layer of faust, an AI-native pentesting handheld.

Your job: given a user request and a catalog of available skills, produce a
step-by-step execution plan. You do NOT execute anything yourself — Faust
(the operator unit) will execute each step, and ask the user for parameter
details and confirmation.

Rules:
  - Use ONLY skills listed in the catalog. Never invent skill names.
  - Keep plans SHORT. Most tasks are 1-3 steps. Avoid filler steps.
  - Order steps so earlier results inform later parameters (scan before attack).
  - Every skill marked [disruptive] MUST have `critical: true` in your plan.
  - Every skill marked [active] that writes/emulates should have `critical: true`.
  - Include a `safety_notes` entry for any plan that touches RF transmission,
    card cloning, or credential capture — warn about scope and authorization.
  - If the user's request cannot be satisfied by the available skills, return
    a plan with ZERO steps and explain why in `reasoning`.
  - Plans are declarative. The `intent` field describes WHAT each step should
    accomplish (e.g. "find clients with RSSI stronger than -40 dBm").
    Concrete parameters are generated later — don't include them in intent.

You MUST respond by calling the `submit_plan` tool. No other output is valid.
"""


SUBMIT_PLAN_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "submit_plan",
        "description": (
            "Submit an execution plan for operator review. This is the ONLY "
            "valid action. The plan will be shown to the user and executed "
            "step-by-step by Faust."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reasoning": {
                    "type": "string",
                    "description": (
                        "One paragraph explaining why these steps, in this "
                        "order. Written for the operator, not for yourself."
                    ),
                },
                "steps": {
                    "type": "array",
                    "description": "Ordered list of skill invocations.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "skill": {
                                "type": "string",
                                "description": (
                                    "Name of a skill from the catalog. "
                                    "Must match exactly."
                                ),
                            },
                            "intent": {
                                "type": "string",
                                "description": (
                                    "What this step should accomplish. "
                                    "Describe the goal, not the parameters."
                                ),
                            },
                            "critical": {
                                "type": "boolean",
                                "description": (
                                    "True if this step has safety/legal "
                                    "weight — deauth, emulation, transmit, "
                                    "credential capture, HID injection, etc."
                                ),
                            },
                        },
                        "required": ["skill", "intent"],
                    },
                },
                "safety_notes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Warnings to surface to the operator — scope, "
                        "authorization, RF compliance, legal weight."
                    ),
                },
            },
            "required": ["reasoning", "steps"],
        },
    },
}


class Planner:
    """Produces an execution plan given a user request + skill catalog.

    Supports dual-backend cascade: a deep backend (e.g. Qwen 7B on CPU)
    for planning, falling back to the main backend if it fails.
    """

    def __init__(
        self,
        backend: LLMBackend,
        deep_backend: LLMBackend | None = None,
    ) -> None:
        self.backend = backend
        self.deep_backend = deep_backend

    async def plan(
        self,
        user_input: str,
        catalog: list[CatalogEntry],
        history: list[dict[str, Any]] | None = None,
    ) -> Plan:
        """Run Pass 1 — returns the structured Plan.

        Tries the deep backend first (if configured). On timeout/connection
        error, falls back to the main backend with a safety_note appended
        so the user knows they got the less-capable planner.
        """
        catalog_text = render_catalog(catalog)

        system = PLANNER_SYSTEM_PROMPT + "\n\n" + catalog_text

        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_input})

        # Try the deep backend first if available.
        fallback_note: str | None = None
        backend_to_use = self.backend
        if self.deep_backend is not None:
            try:
                msg = await self.deep_backend.complete(
                    messages=messages,
                    tools=[SUBMIT_PLAN_TOOL],
                )
                return self._extract_plan(msg)
            except Exception as e:
                fallback_note = (
                    f"deep planner unavailable ({type(e).__name__}); "
                    f"used fast planner — plan may be less thorough"
                )

        msg = await backend_to_use.complete(
            messages=messages,
            tools=[SUBMIT_PLAN_TOOL],
        )
        plan = self._extract_plan(msg)
        if fallback_note:
            plan.safety_notes.insert(0, fallback_note)
        return plan

    def _extract_plan(self, msg: Any) -> Plan:
        """Parse a submit_plan tool-call into a Plan. Handles malformed output."""

        # The model should have called submit_plan. If it didn't, fall back
        # to an empty plan with the model's text as reasoning.
        for tc in msg.tool_calls:
            if tc.name == "submit_plan":
                args = tc.arguments
                # Coerce strings into the dataclass structure.
                try:
                    return Plan.from_dict(args)
                except Exception as e:
                    return Plan(
                        reasoning=f"planner returned malformed plan: {e}",
                        steps=[],
                        safety_notes=[f"raw args: {json.dumps(args, default=str)[:200]}"],
                    )

        return Plan(
            reasoning=msg.content or "planner produced no structured plan",
            steps=[],
            safety_notes=[],
        )
