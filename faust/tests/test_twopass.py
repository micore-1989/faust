"""
TwoPassAgent tests.

Exercises the plan → approve → per-step execute pipeline using a scripted
mock backend. The mock records every call so we can assert:
  - Pass 1 call includes catalog but NOT full schemas
  - Pass 1 uses only the submit_plan tool
  - Pass 2 calls include only ONE tool schema per call
  - Results feed forward in Pass 2 context
  - Plan rejection aborts cleanly
  - Empty plan returns end_turn with reasoning as text

Run with: python -m faust.tests.test_twopass
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import deque
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from faust.agent.backends import AssistantMessage, LLMBackend, ToolCall
from faust.agent.config import AgentConfig
from faust.agent.dispatch import Dispatcher
from faust.agent.events import (
    Final,
    PlanProposed,
    ToolCallExecuted,
    ToolCallProposed,
)
from faust.agent.plan import Plan
from faust.agent.twopass import TwoPassAgent
from faust.tools.registry import Tool, ToolRegistry


# ── Mock backend ────────────────────────────────────────────────

class MockBackend(LLMBackend):
    """Scripts a sequence of AssistantMessages and records every call."""

    def __init__(self, responses: list[AssistantMessage]) -> None:
        self.responses: deque[AssistantMessage] = deque(responses)
        self.calls: list[dict[str, Any]] = []

    async def complete(self, messages, tools):
        self.calls.append({
            "messages": list(messages),
            "tool_names": [t["function"]["name"] for t in (tools or [])],
        })
        if not self.responses:
            raise RuntimeError("MockBackend exhausted")
        return self.responses.popleft()


# ── Helpers ─────────────────────────────────────────────────────

def _mk_registry(skills: list[tuple[str, str]]) -> ToolRegistry:
    reg = ToolRegistry()
    for name, description in skills:
        reg.register(Tool(
            name=name,
            description=description,
            parameters_schema={
                "type": "object",
                "properties": {"x": {"type": "string"}},
            },
            fn=lambda args, _n=name: f"{_n}_result",
            sensitivity="passive",
        ))
    return reg


def _plan_response(reasoning: str, steps: list[dict[str, Any]]) -> AssistantMessage:
    return AssistantMessage(
        content="",
        tool_calls=[ToolCall(
            id="p1",
            name="submit_plan",
            arguments={"reasoning": reasoning, "steps": steps, "safety_notes": []},
        )],
        finish_reason="tool_calls",
    )


def _tool_response(tool_name: str, args: dict[str, Any]) -> AssistantMessage:
    return AssistantMessage(
        content="",
        tool_calls=[ToolCall(id="t1", name=tool_name, arguments=args)],
        finish_reason="tool_calls",
    )


async def collect(agent, prompt):
    return [e async for e in agent.run(prompt)]


# ── Tests ───────────────────────────────────────────────────────

async def test_plan_only_sees_catalog_not_schemas():
    """Pass 1 should call backend with ONLY the submit_plan tool, never real skills."""
    registry = _mk_registry([
        ("wifi_scan", "Scan WiFi networks"),
        ("ble_scan", "Scan BLE devices"),
    ])
    backend = MockBackend([
        _plan_response("scan wifi then ble", [
            {"skill": "wifi_scan", "intent": "find networks"},
            {"skill": "ble_scan", "intent": "find devices"},
        ]),
        _tool_response("wifi_scan", {"x": "v1"}),
        _tool_response("ble_scan", {"x": "v2"}),
    ])
    agent = TwoPassAgent(backend, Dispatcher(registry), AgentConfig())

    await collect(agent, "scan everything")

    # First backend call is the planner — tools should be [submit_plan].
    assert backend.calls[0]["tool_names"] == ["submit_plan"], (
        f"planner call sent wrong tools: {backend.calls[0]['tool_names']}"
    )
    # System prompt should include the catalog.
    sys_content = backend.calls[0]["messages"][0]["content"]
    assert "wifi_scan" in sys_content
    assert "ble_scan" in sys_content
    assert "## Available skills" in sys_content
    print("✓ Pass 1 sends only catalog + submit_plan tool")


async def test_each_step_sees_exactly_one_tool_schema():
    """Pass 2 per-step calls should each send exactly ONE tool schema."""
    registry = _mk_registry([
        ("wifi_scan", "Scan WiFi"),
        ("ble_scan", "Scan BLE"),
        ("nfc_read", "Read NFC"),
    ])
    backend = MockBackend([
        _plan_response("three-step plan", [
            {"skill": "wifi_scan", "intent": "find nets"},
            {"skill": "ble_scan", "intent": "find devices"},
            {"skill": "nfc_read", "intent": "read tag"},
        ]),
        _tool_response("wifi_scan", {}),
        _tool_response("ble_scan", {}),
        _tool_response("nfc_read", {}),
    ])
    agent = TwoPassAgent(backend, Dispatcher(registry), AgentConfig())

    await collect(agent, "do all the scans")

    # calls[0] is the planner; calls[1..3] are the three step parameterize calls.
    assert backend.calls[1]["tool_names"] == ["wifi_scan"]
    assert backend.calls[2]["tool_names"] == ["ble_scan"]
    assert backend.calls[3]["tool_names"] == ["nfc_read"]
    print("✓ Pass 2 per-step calls each see exactly one tool schema")


async def test_step_results_feed_forward():
    """Step 2's parameterize context should contain step 1's result."""
    registry = _mk_registry([
        ("wifi_scan", "Scan WiFi"),
        ("wifi_deauth", "Deauth a client"),
    ])
    backend = MockBackend([
        _plan_response("scan then deauth", [
            {"skill": "wifi_scan", "intent": "find clients"},
            {"skill": "wifi_deauth", "intent": "deauth strongest client"},
        ]),
        _tool_response("wifi_scan", {}),
        _tool_response("wifi_deauth", {"x": "deauth_arg"}),
    ])
    agent = TwoPassAgent(backend, Dispatcher(registry), AgentConfig())

    await collect(agent, "scan and deauth")

    # calls[2] is the parameterize call for wifi_deauth.
    user_msg = backend.calls[2]["messages"][1]["content"]
    assert "wifi_scan" in user_msg, "step 2 should see step 1's result"
    assert "wifi_scan_result" in user_msg
    print("✓ step results feed forward into next step's context")


async def test_plan_proposed_event_emitted_before_execution():
    registry = _mk_registry([("wifi_scan", "Scan WiFi")])
    backend = MockBackend([
        _plan_response("quick scan", [{"skill": "wifi_scan", "intent": "scan"}]),
        _tool_response("wifi_scan", {}),
    ])
    agent = TwoPassAgent(backend, Dispatcher(registry), AgentConfig())
    events = await collect(agent, "scan")

    # Order must be: PlanProposed → ToolCallProposed → ToolCallExecuted → Final
    types = [type(e).__name__ for e in events]
    assert types[0] == "PlanProposed"
    assert types[-1] == "Final"
    # PlanProposed must come before any ToolCallProposed.
    plan_idx = types.index("PlanProposed")
    tool_idx = types.index("ToolCallProposed")
    assert plan_idx < tool_idx
    print("✓ PlanProposed emitted before tool calls")


async def test_plan_rejection_aborts():
    registry = _mk_registry([("wifi_scan", "Scan WiFi")])
    backend = MockBackend([
        _plan_response("scan", [{"skill": "wifi_scan", "intent": "scan"}]),
        # No tool responses — execution should never happen.
    ])

    async def reject_plan(plan):
        return False

    agent = TwoPassAgent(
        backend, Dispatcher(registry), AgentConfig(),
        plan_approver=reject_plan,
    )
    events = await collect(agent, "scan")

    # No ToolCall events should appear.
    types = [type(e).__name__ for e in events]
    assert "ToolCallProposed" not in types
    assert types[-1] == "Final"
    assert events[-1].reason == "user_abort"
    print("✓ plan rejection aborts before any execution")


async def test_empty_plan_ends_cleanly():
    """If the planner returns zero steps, finish with reasoning as text."""
    registry = _mk_registry([("wifi_scan", "Scan WiFi")])
    backend = MockBackend([
        _plan_response("no applicable skills for that request", []),
    ])
    agent = TwoPassAgent(backend, Dispatcher(registry), AgentConfig())
    events = await collect(agent, "make me a sandwich")

    types = [type(e).__name__ for e in events]
    assert "PlanProposed" in types
    assert "ToolCallProposed" not in types
    final = events[-1]
    assert final.reason == "end_turn"
    assert "no applicable" in final.text
    print("✓ empty plan ends cleanly with reasoning as final text")


async def test_missing_skill_in_plan_errors():
    """If the planner references a skill that isn't in the registry, fail loudly."""
    registry = _mk_registry([("wifi_scan", "Scan WiFi")])
    backend = MockBackend([
        _plan_response("scan + hallucinated", [
            {"skill": "wifi_scan", "intent": "real scan"},
            {"skill": "hallucinated_tool", "intent": "doesn't exist"},
        ]),
        _tool_response("wifi_scan", {}),
        # Never reached for hallucinated_tool.
    ])
    agent = TwoPassAgent(backend, Dispatcher(registry), AgentConfig())
    events = await collect(agent, "anything")

    # Should see the first step execute, then error on the second.
    types = [type(e).__name__ for e in events]
    assert "ToolCallExecuted" in types
    final = events[-1]
    assert final.reason == "error"
    assert "hallucinated_tool" in (final.error or "")
    print("✓ plan referencing unknown skill errors cleanly")


async def test_planner_non_tool_response_returns_empty_plan():
    """If the model doesn't call submit_plan, we get an empty plan, not a crash."""
    registry = _mk_registry([("wifi_scan", "Scan")])
    backend = MockBackend([
        AssistantMessage(content="I'm confused", finish_reason="stop"),
    ])
    agent = TwoPassAgent(backend, Dispatcher(registry), AgentConfig())
    events = await collect(agent, "anything")

    # PlanProposed with empty steps + Final end_turn.
    plan_event = next(e for e in events if isinstance(e, PlanProposed))
    assert plan_event.steps == []
    assert events[-1].reason == "end_turn"
    print("✓ planner without submit_plan call returns empty plan cleanly")


async def main():
    await test_plan_only_sees_catalog_not_schemas()
    await test_each_step_sees_exactly_one_tool_schema()
    await test_step_results_feed_forward()
    await test_plan_proposed_event_emitted_before_execution()
    await test_plan_rejection_aborts()
    await test_empty_plan_ends_cleanly()
    await test_missing_skill_in_plan_errors()
    await test_planner_non_tool_response_returns_empty_plan()
    print("\nall two-pass tests passed")


if __name__ == "__main__":
    asyncio.run(main())
