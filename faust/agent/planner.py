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

        Deep backend first (if configured), falls back to main on failure.
        After getting a plan, validates skill names against the catalog
        and retries ONCE with an error hint if any are hallucinated.
        """
        catalog_text = render_catalog(catalog)
        catalog_names = {e.name for e in catalog}

        system = PLANNER_SYSTEM_PROMPT + "\n\n" + catalog_text

        base_messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        if history:
            base_messages.extend(history)
        base_messages.append({"role": "user", "content": user_input})

        plan, fallback_note = await self._call_planner(base_messages)

        # Validate skill names; retry once if any are hallucinated.
        invalid = [s.skill for s in plan.steps if s.skill not in catalog_names]
        if invalid and plan.steps:
            hint = _hallucination_hint(invalid, catalog_names)
            retry_messages = list(base_messages) + [
                {"role": "user", "content": hint},
            ]
            try:
                retry_plan, _ = await self._call_planner(retry_messages)
                retry_invalid = [
                    s.skill for s in retry_plan.steps if s.skill not in catalog_names
                ]
                if not retry_invalid:
                    plan = retry_plan
                else:
                    # Model still hallucinated. Surface via safety note but
                    # use the retry plan (often more structured).
                    plan = retry_plan
                    plan.safety_notes.insert(
                        0,
                        f"planner referenced unknown skills after retry: "
                        f"{sorted(set(retry_invalid))}",
                    )
            except Exception as e:
                # Retry failed entirely (network glitch, backend exhausted, etc.)
                # Keep the original plan but warn the user about the bad skills.
                plan.safety_notes.insert(
                    0,
                    f"planner references unknown skills {sorted(set(invalid))}; "
                    f"retry failed ({type(e).__name__}) — plan may fail at execution",
                )

        if fallback_note:
            plan.safety_notes.insert(0, fallback_note)
        return plan

    async def _call_planner(
        self, messages: list[dict[str, Any]]
    ) -> tuple[Plan, str | None]:
        """Single planner invocation. Tries deep backend, falls back to fast.

        Returns (plan, fallback_note) — fallback_note is non-None when the
        deep backend failed and we used fast instead.
        """
        fallback_note: str | None = None
        if self.deep_backend is not None:
            try:
                msg = await self.deep_backend.complete(
                    messages=messages,
                    tools=[SUBMIT_PLAN_TOOL],
                )
                return self._extract_plan(msg), None
            except Exception as e:
                fallback_note = (
                    f"deep planner unavailable ({type(e).__name__}); "
                    f"used fast planner — plan may be less thorough"
                )

        msg = await self.backend.complete(
            messages=messages,
            tools=[SUBMIT_PLAN_TOOL],
        )
        return self._extract_plan(msg), fallback_note

    def _extract_plan(self, msg: Any) -> Plan:
        """Parse a submit_plan tool-call into a Plan. Handles malformed output."""
        for tc in msg.tool_calls:
            if tc.name == "submit_plan":
                args = tc.arguments
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


def _hallucination_hint(invalid: list[str], catalog_names: set[str]) -> str:
    """Build a retry hint telling the model what it got wrong."""
    bad = sorted(set(invalid))
    valid = sorted(catalog_names)
    return (
        f"Your previous plan referenced skills that do not exist: {bad}. "
        f"Valid skills (use EXACTLY these names, no others): {valid}. "
        f"Some common mistakes:\n"
        f"  - 'nfc_clone' is not a skill — for 13.56 MHz tags, use nfc_read + nfc_write; "
        f"for 125 kHz LF cards, use rfid_clone.\n"
        f"  - 'wifi_crack' is not a skill — use wpa_crack against a captured handshake.\n"
        f"Revise your submit_plan call using only skills from the catalog."
    )
