"""
preferred_args plumbing tests.

Covers:
  - Plan.from_dict back-compat with plans that lack the preferred_args key.
  - Plan.from_dict drops unknown step keys silently (forward-compat).
  - TwoPassAgent seeds the parameterizer with preferred_args values.
  - Schema filter: keys absent from the tool's schema are dropped silently.
  - Parameterizer's tool-call output overrides on key conflict.
  - Fallback when the parameterizer emits no tool_call: dispatch seeded args.

Run with: python -m faust.tests.test_preferred_args
"""

from __future__ import annotations

import asyncio
import sys
from collections import deque
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from faust.agent.backends import AssistantMessage, LLMBackend, ToolCall
from faust.agent.config import AgentConfig
from faust.agent.dispatch import Dispatcher
from faust.agent.events import ToolCallProposed
from faust.agent.plan import Plan, PlanStep
from faust.agent.twopass import TwoPassAgent
from faust.tools.registry import Tool, ToolRegistry


# ── Helpers ────────────────────────────────────────────────────

class MockBackend(LLMBackend):
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


def _wifi_registry() -> ToolRegistry:
    """wifi_scan with a schema that permits channel + interface args."""
    reg = ToolRegistry()
    reg.register(Tool(
        name="wifi_scan",
        description="Scan WiFi",
        parameters_schema={
            "type": "object",
            "properties": {
                "channel": {"type": "integer"},
                "interface": {"type": "string"},
            },
        },
        fn=lambda args: {"ok": True, "echo": args},
        sensitivity="passive",
    ))
    return reg


def _plan_msg_with_preferred(
    skill: str, intent: str, preferred: dict[str, Any]
) -> AssistantMessage:
    return AssistantMessage(
        content="",
        tool_calls=[ToolCall(
            id="p",
            name="submit_plan",
            arguments={
                "reasoning": "test",
                "steps": [{
                    "skill": skill,
                    "intent": intent,
                    "preferred_args": preferred,
                }],
                "safety_notes": [],
            },
        )],
        finish_reason="tool_calls",
    )


def _tool_msg(name: str, args: dict[str, Any]) -> AssistantMessage:
    return AssistantMessage(
        content="",
        tool_calls=[ToolCall(id="t", name=name, arguments=args)],
        finish_reason="tool_calls",
    )


def _no_tool_msg() -> AssistantMessage:
    return AssistantMessage(content="I am unsure", finish_reason="stop")


async def _collect(agent: TwoPassAgent, prompt: str):
    return [e async for e in agent.run(prompt)]


def _dispatched_args(events) -> dict[str, Any]:
    """Grab the arguments that went to the Dispatcher."""
    for e in events:
        if isinstance(e, ToolCallProposed):
            return e.arguments
    raise AssertionError("no ToolCallProposed event emitted")


# ── PlanStep/Plan serialization tests ──────────────────────────

async def test_plan_from_dict_back_compat():
    """Legacy plans without preferred_args still deserialize; default = {}."""
    plan = Plan.from_dict({
        "reasoning": "x",
        "steps": [{"skill": "wifi_scan", "intent": "y"}],
    })
    assert len(plan.steps) == 1
    assert plan.steps[0].preferred_args == {}
    print("✓ Plan.from_dict without preferred_args defaults to {}")


async def test_plan_from_dict_drops_unknown_keys():
    """Future planner fields don't crash deserialization."""
    plan = Plan.from_dict({
        "reasoning": "x",
        "steps": [{
            "skill": "wifi_scan",
            "intent": "y",
            "future_field": 42,
        }],
    })
    assert plan.steps[0].skill == "wifi_scan"
    assert plan.steps[0].intent == "y"
    assert not hasattr(plan.steps[0], "future_field")
    print("✓ Plan.from_dict silently drops unknown step keys")


async def test_plan_from_dict_none_preferred_args_coerced():
    """preferred_args: null → {} (survives JSON round-trips)."""
    plan = Plan.from_dict({
        "reasoning": "x",
        "steps": [{"skill": "wifi_scan", "intent": "y", "preferred_args": None}],
    })
    assert plan.steps[0].preferred_args == {}
    print("✓ preferred_args None coerces to empty dict")


# ── Pass 2 plumbing tests ──────────────────────────────────────

async def test_preferred_args_flow_through():
    """Plan says channel=36; parameterizer returns interface=wlan1mon;
    dispatched args should union both."""
    registry = _wifi_registry()
    backend = MockBackend([
        _plan_msg_with_preferred("wifi_scan", "scan", {"channel": 36}),
        _tool_msg("wifi_scan", {"interface": "wlan1mon"}),
    ])
    agent = TwoPassAgent(backend, Dispatcher(registry), AgentConfig())
    events = await _collect(agent, "scan channel 36")

    args = _dispatched_args(events)
    assert args == {"channel": 36, "interface": "wlan1mon"}, f"got {args}"
    print("✓ preferred_args seeded; parameterizer extras merge in")


async def test_preferred_args_filtered_to_schema():
    """Keys not in the tool's schema are dropped silently."""
    registry = _wifi_registry()
    backend = MockBackend([
        _plan_msg_with_preferred(
            "wifi_scan", "scan",
            {"channel": 36, "bogus_key": "nope"},
        ),
        _tool_msg("wifi_scan", {}),
    ])
    agent = TwoPassAgent(backend, Dispatcher(registry), AgentConfig())
    events = await _collect(agent, "scan")

    args = _dispatched_args(events)
    assert args == {"channel": 36}, f"got {args}"
    assert "bogus_key" not in args
    print("✓ schema filter drops hallucinated preferred_args keys")


async def test_preferred_args_overridden_by_parameterizer():
    """Parameterizer's concrete value wins over the preferred seed."""
    registry = _wifi_registry()
    backend = MockBackend([
        _plan_msg_with_preferred("wifi_scan", "scan", {"channel": 6}),
        _tool_msg("wifi_scan", {"channel": 36}),
    ])
    agent = TwoPassAgent(backend, Dispatcher(registry), AgentConfig())
    events = await _collect(agent, "scan")

    args = _dispatched_args(events)
    assert args["channel"] == 36, f"parameterizer should win; got {args}"
    print("✓ parameterizer overrides preferred_args on key conflict")


async def test_preferred_args_fallback_when_no_tool_call():
    """If the parameterizer emits no tool_call, dispatch seeded args alone."""
    registry = _wifi_registry()
    backend = MockBackend([
        _plan_msg_with_preferred("wifi_scan", "scan", {"channel": 36}),
        _no_tool_msg(),
    ])
    agent = TwoPassAgent(backend, Dispatcher(registry), AgentConfig())
    events = await _collect(agent, "scan")

    args = _dispatched_args(events)
    assert args == {"channel": 36}, f"expected seeded args, got {args}"
    print("✓ fallback dispatches seeded preferred_args, not empty dict")


# ── Runner ─────────────────────────────────────────────────────

async def main():
    await test_plan_from_dict_back_compat()
    await test_plan_from_dict_drops_unknown_keys()
    await test_plan_from_dict_none_preferred_args_coerced()
    await test_preferred_args_flow_through()
    await test_preferred_args_filtered_to_schema()
    await test_preferred_args_overridden_by_parameterizer()
    await test_preferred_args_fallback_when_no_tool_call()
    print("\nall preferred_args tests passed")


if __name__ == "__main__":
    asyncio.run(main())
