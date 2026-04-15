"""
Planner hallucination-retry tests.

Small models sometimes invent plausible-sounding skill names that don't
exist in the registry (e.g. nfc_clone when the real skills are rfid_clone
or nfc_write). The Planner validates step names against the catalog and
retries ONCE with an error hint before surfacing a bad plan to the user.

Run with: python -m faust.tests.test_planner_retry
"""

from __future__ import annotations

import asyncio
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from faust.agent.backends import AssistantMessage, LLMBackend, ToolCall
from faust.agent.catalog import CatalogEntry
from faust.agent.planner import Planner


class CapturedBackend(LLMBackend):
    """Records each call's messages + returns scripted responses."""

    def __init__(self, responses: list[AssistantMessage]) -> None:
        self.responses: deque[AssistantMessage] = deque(responses)
        self.calls: list[list[dict]] = []

    async def complete(self, messages, tools):
        self.calls.append(list(messages))
        if not self.responses:
            raise RuntimeError("CapturedBackend exhausted")
        return self.responses.popleft()


def _catalog() -> list[CatalogEntry]:
    return [
        CatalogEntry(name="nfc_read", description="Read NFC tag",
                     category="nfc", sensitivity="passive"),
        CatalogEntry(name="nfc_write", description="Write NFC tag",
                     category="nfc", sensitivity="active"),
        CatalogEntry(name="rfid_clone", description="Clone LF RFID",
                     category="rfid", sensitivity="active"),
        CatalogEntry(name="wifi_scan", description="Scan WiFi",
                     category="wifi", sensitivity="passive"),
    ]


def _plan_msg(skill: str, intent: str = "do it") -> AssistantMessage:
    return AssistantMessage(
        content="",
        tool_calls=[ToolCall(
            id="p",
            name="submit_plan",
            arguments={
                "reasoning": "test",
                "steps": [{"skill": skill, "intent": intent}],
                "safety_notes": [],
            },
        )],
        finish_reason="tool_calls",
    )


# ── Tests ───────────────────────────────────────────────────────

async def test_valid_plan_passes_unchanged():
    """No hallucination → no retry, plan returned as-is."""
    backend = CapturedBackend([_plan_msg("nfc_read")])
    planner = Planner(backend)
    plan = await planner.plan("read the tag", _catalog())

    assert plan.steps[0].skill == "nfc_read"
    assert len(backend.calls) == 1, "should NOT have retried"
    assert not any("unknown" in n.lower() for n in plan.safety_notes)
    print("✓ valid plan passes through without retry")


async def test_hallucinated_skill_triggers_retry_and_recovers():
    """Bad skill name → retry with hint → good plan on second try."""
    backend = CapturedBackend([
        _plan_msg("nfc_clone"),   # hallucination
        _plan_msg("rfid_clone"),  # fixed on retry
    ])
    planner = Planner(backend)
    plan = await planner.plan("clone the keycard", _catalog())

    assert plan.steps[0].skill == "rfid_clone"
    assert len(backend.calls) == 2, "should have retried exactly once"
    # No safety note on successful retry.
    assert not any("unknown" in n.lower() for n in plan.safety_notes)

    # The retry call should include the hint with the bad skill name.
    retry_messages = backend.calls[1]
    hint_text = retry_messages[-1]["content"]
    assert "nfc_clone" in hint_text
    assert "rfid_clone" in hint_text  # valid alternative listed
    print("✓ hallucinated skill triggers retry, recovers with valid plan")


async def test_repeated_hallucination_surfaces_safety_note():
    """Model hallucinates both times → return bad plan + safety_note."""
    backend = CapturedBackend([
        _plan_msg("nfc_clone"),      # bad
        _plan_msg("magical_skill"),  # still bad
    ])
    planner = Planner(backend)
    plan = await planner.plan("clone the keycard", _catalog())

    assert len(backend.calls) == 2
    # The last plan was bad, safety_note must flag it.
    assert any("unknown skills after retry" in n for n in plan.safety_notes)
    # Show the bad skill name in the note.
    assert any("magical_skill" in n for n in plan.safety_notes)
    print("✓ repeated hallucination surfaces safety note with details")


async def test_empty_plan_no_retry():
    """Planner returning 0 steps shouldn't trigger retry — it's fine."""
    empty_plan = AssistantMessage(
        content="",
        tool_calls=[ToolCall(
            id="p",
            name="submit_plan",
            arguments={"reasoning": "no skills match", "steps": [], "safety_notes": []},
        )],
        finish_reason="tool_calls",
    )
    backend = CapturedBackend([empty_plan])
    planner = Planner(backend)
    plan = await planner.plan("make me a sandwich", _catalog())

    assert plan.steps == []
    assert len(backend.calls) == 1, "should not retry on empty plan"
    print("✓ empty plan (no applicable skills) does not retry")


async def test_retry_hint_lists_common_aliases():
    """Retry hint should teach the model about common mistake patterns."""
    backend = CapturedBackend([
        _plan_msg("wifi_crack"),   # bad
        _plan_msg("wpa_crack"),    # good on retry (should work even though wpa_crack isn't in our test catalog... wait it isn't)
    ])
    # Add wpa_crack to the catalog for this test.
    catalog = _catalog() + [
        CatalogEntry(name="wpa_crack", description="Crack WPA",
                     category="analysis", sensitivity="active"),
    ]
    planner = Planner(backend)
    plan = await planner.plan("crack the handshake", catalog)

    assert plan.steps[0].skill == "wpa_crack"
    # Retry call's hint should mention wpa_crack as the valid alternative.
    retry_hint = backend.calls[1][-1]["content"]
    assert "wpa_crack" in retry_hint
    print("✓ retry hint lists valid alternatives for common aliases")


async def main():
    await test_valid_plan_passes_unchanged()
    await test_hallucinated_skill_triggers_retry_and_recovers()
    await test_repeated_hallucination_surfaces_safety_note()
    await test_empty_plan_no_retry()
    await test_retry_hint_lists_common_aliases()
    print("\nall planner retry tests passed")


if __name__ == "__main__":
    asyncio.run(main())
