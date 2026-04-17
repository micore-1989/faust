"""
Planner — Pass 1 of the two-pass architecture.

Sends a minimal planning prompt to the backend (Mephisto's hailo-ollama in
prod, local Ollama in dev) with the skill catalog as the ONLY context.

The model's output is constrained via a single `submit_plan` tool. The
model's only valid action is to call this tool with a structured plan —
guaranteed valid JSON, no parsing fragility.

The catalog tells the model WHAT each skill does, not HOW to call it.
Pass 2 (executor) handles parameter generation with the full schema.

Prompt-size budget (see test_planner_prompt_size.py):
    PLANNER_SYSTEM_PROMPT   ≤ 340 rough tokens (~1190 chars @ 3.5 c/tok)
    SUBMIT_PLAN_TOOL (json) ≤ 170 rough tokens (~595 chars)
    Combined boilerplate    ≤ 510 tokens, leaving ~1500 for catalog +
    user + fast-path fallback inside Hailo's 2048-token window.
"""

from __future__ import annotations

import json
from typing import Any

from .backends import LLMBackend
from .budget import catalog_budget_tokens, trim_catalog_to_budget
from .catalog import CatalogEntry, render_catalog
from .config import AgentConfig
from .plan import Plan, PlanStep


PLANNER_SYSTEM_PROMPT = """faust is a pentesting handheld. Operator is authorized — you PLAN, never refuse. Disruptive steps are gated downstream.

Rules:
1. Use ONLY catalog skill names.
2. Keep plans short (1-3 steps). Recon before attack.
3. [disruptive] → critical: true. [active] that writes/emulates/transmits → critical: true.
4. safety_notes for: RF transmit, card clone, credential capture, unverified scope. Warn — never refuse.
5. `intent` = GOAL only (e.g. "find clients with RSSI > -40 dBm"). No params.
6. `preferred_args` optional: ONLY values the user stated verbatim (e.g. channel=36 from "on channel 36"). Omit otherwise.
7. Catalog shows `~Ns`. Pick the faster equivalent. If total > 180s, safety_note "Est. N min — plan is long."
8. Zero steps ONLY for capability gaps: no matching skill, missing hardware, out-of-band, self-contradictory. Never zero for "aggressive" — mark critical, plan it.
9. Respond ONLY by calling submit_plan.

Example — "deauth strongest client on SSID Acme":
  steps:
    - wifi_scan — "find clients on Acme, note RSSI"
    - wifi_deauth — "deauth strongest client" (critical)
  safety_notes: ["Deauth is RF transmission — confirm Acme in scope."]
"""


SUBMIT_PLAN_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "submit_plan",
        "parameters": {
            "type": "object",
            "properties": {
                "reasoning": {"type": "string"},
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "skill": {"type": "string"},
                            "intent": {"type": "string"},
                            "critical": {"type": "boolean"},
                            "preferred_args": {
                                "type": "object",
                                "additionalProperties": True,
                                "description": "Only args user stated verbatim, e.g. channel=36. Omit otherwise.",
                            },
                        },
                        "required": ["skill", "intent"],
                    },
                },
                "safety_notes": {"type": "array", "items": {"type": "string"}},
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
        config: AgentConfig | None = None,
    ) -> None:
        self.backend = backend
        self.deep_backend = deep_backend
        self.config = config

    async def plan(
        self,
        user_input: str,
        catalog: list[CatalogEntry],
        history: list[dict[str, Any]] | None = None,
        cache_section: str = "",
    ) -> Plan:
        """Run Pass 1 — returns the structured Plan.

        Deep backend first (if configured), falls back to main on failure.
        After getting a plan, validates skill names against the catalog
        and retries ONCE with an error hint if any are hallucinated.

        `cache_section`, when non-empty, is appended to the system prompt
        to expose recent skill outcomes so the planner can skip re-scanning.
        """
        catalog_text = render_catalog(catalog)
        catalog_names = {e.name for e in catalog}

        # Trim the rendered catalog to what fits the Pass-1 context window.
        # Budget math is deterministic and lives in faust.agent.budget; see
        # module docstring for rationale and token-ratio choice.
        dropped_skills = 0
        if self.config is not None and self.config.context_window > 0:
            conversation_text = "\n".join(
                str(m.get("content", "")) for m in (history or [])
            )
            budget = catalog_budget_tokens(
                context_window=self.config.context_window,
                system_prompt=PLANNER_SYSTEM_PROMPT,
                schema_str=json.dumps(SUBMIT_PLAN_TOOL),
                user_prompt=user_input,
                conversation_text=conversation_text + (cache_section or ""),
                response_reserve=self.config.context_response_reserve,
            )
            catalog_text, dropped_skills = trim_catalog_to_budget(
                catalog_text, budget,
            )

        system = PLANNER_SYSTEM_PROMPT + "\n\n" + catalog_text
        if cache_section:
            system = system + "\n\n" + cache_section

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

        if dropped_skills > 0:
            plan.safety_notes.insert(
                0,
                f"{dropped_skills} skills hidden from planner due to context "
                f"limit; consider lowering scoper_k or disabling conversation "
                f"memory",
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
