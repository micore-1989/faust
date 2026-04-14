"""
Dual-backend cascade tests.

Verifies:
  - Planner uses the deep backend when provided
  - Falls back to fast backend when deep backend fails
  - Fallback injects a safety_note so the user knows
  - TwoPassAgent wires the cascade through correctly
  - Pass 2 (parameterize) ALWAYS uses the fast backend, never deep
  - make_deep_backend returns None when disabled

Run with: python -m faust.tests.test_cascade
"""

from __future__ import annotations

import asyncio
import sys
from collections import deque
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from faust.agent.backends import AssistantMessage, LLMBackend, ToolCall, make_deep_backend
from faust.agent.catalog import build_catalog
from faust.agent.config import AgentConfig
from faust.agent.dispatch import Dispatcher
from faust.agent.plan import Plan
from faust.agent.planner import Planner
from faust.agent.twopass import TwoPassAgent
from faust.tools.registry import Tool, ToolRegistry


class TaggedBackend(LLMBackend):
    """Mock backend that tags every call with an identifier + scripted response."""

    def __init__(self, name: str, responses: list[AssistantMessage]) -> None:
        self.name = name
        self.responses: deque[AssistantMessage] = deque(responses)
        self.call_count = 0

    async def complete(self, messages, tools):
        self.call_count += 1
        if not self.responses:
            raise RuntimeError(f"{self.name} exhausted")
        return self.responses.popleft()


class FailingBackend(LLMBackend):
    """Raises on every call. Used to test fallback."""

    def __init__(self, exc: Exception = ConnectionError("deep down")) -> None:
        self.exc = exc
        self.call_count = 0

    async def complete(self, messages, tools):
        self.call_count += 1
        raise self.exc


def _plan_msg(reasoning: str, skill: str, intent: str) -> AssistantMessage:
    return AssistantMessage(
        content="",
        tool_calls=[ToolCall(
            id="p",
            name="submit_plan",
            arguments={"reasoning": reasoning,
                       "steps": [{"skill": skill, "intent": intent}],
                       "safety_notes": []},
        )],
        finish_reason="tool_calls",
    )


def _tool_msg(name: str, args: dict) -> AssistantMessage:
    return AssistantMessage(
        content="",
        tool_calls=[ToolCall(id="t", name=name, arguments=args)],
        finish_reason="tool_calls",
    )


def _mk_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(Tool(
        name="wifi_scan",
        description="Scan WiFi",
        parameters_schema={"type": "object", "properties": {}},
        fn=lambda a: "scan_result",
        sensitivity="passive",
    ))
    return reg


# ── Planner tests ──────────────────────────────────────────────

async def test_planner_uses_deep_when_provided():
    fast = TaggedBackend("fast", [])  # should not be touched
    deep = TaggedBackend("deep", [_plan_msg("deep reasoning", "wifi_scan", "scan")])
    planner = Planner(fast, deep_backend=deep)

    catalog = build_catalog(_mk_registry())
    plan = await planner.plan("scan", catalog)

    assert deep.call_count == 1
    assert fast.call_count == 0
    assert plan.reasoning == "deep reasoning"
    assert not any("unavailable" in n for n in plan.safety_notes)
    print("✓ planner uses deep backend when provided")


async def test_planner_falls_back_to_fast_on_deep_failure():
    fast = TaggedBackend("fast", [_plan_msg("fast reasoning", "wifi_scan", "scan")])
    deep = FailingBackend()
    planner = Planner(fast, deep_backend=deep)

    catalog = build_catalog(_mk_registry())
    plan = await planner.plan("scan", catalog)

    assert deep.call_count == 1
    assert fast.call_count == 1
    assert plan.reasoning == "fast reasoning"
    # Must surface a safety note so the user knows they got the degraded planner.
    assert any("deep planner unavailable" in n for n in plan.safety_notes)
    print("✓ planner falls back to fast backend on deep failure")


async def test_planner_uses_fast_only_when_no_deep():
    fast = TaggedBackend("fast", [_plan_msg("only planner", "wifi_scan", "scan")])
    planner = Planner(fast)  # no deep_backend

    catalog = build_catalog(_mk_registry())
    plan = await planner.plan("scan", catalog)

    assert fast.call_count == 1
    assert plan.reasoning == "only planner"
    assert plan.safety_notes == []
    print("✓ planner works with only fast backend (no deep)")


# ── TwoPassAgent tests ─────────────────────────────────────────

async def test_twopass_agent_routes_planning_to_deep():
    """Pass 1 goes to deep, Pass 2 goes to fast."""
    deep = TaggedBackend("deep", [_plan_msg("from deep", "wifi_scan", "scan nets")])
    fast = TaggedBackend("fast", [_tool_msg("wifi_scan", {"x": "v"})])

    agent = TwoPassAgent(
        fast, Dispatcher(_mk_registry()), AgentConfig(),
        deep_backend=deep,
    )
    events = [e async for e in agent.run("scan networks")]

    # Deep got exactly one call (the planner), fast got exactly one (parameterize).
    assert deep.call_count == 1, f"deep should get 1 call, got {deep.call_count}"
    assert fast.call_count == 1, f"fast should get 1 call, got {fast.call_count}"

    final = events[-1]
    assert final.reason == "end_turn"
    print("✓ TwoPassAgent routes planning to deep, parameterize to fast")


async def test_twopass_agent_without_deep_uses_fast_for_both():
    fast = TaggedBackend("fast", [
        _plan_msg("fast-only", "wifi_scan", "scan"),
        _tool_msg("wifi_scan", {}),
    ])

    agent = TwoPassAgent(
        fast, Dispatcher(_mk_registry()), AgentConfig(),
        # No deep backend.
    )
    events = [e async for e in agent.run("scan")]

    # Fast gets 2 calls (planner + parameterize).
    assert fast.call_count == 2, f"fast should get 2 calls, got {fast.call_count}"
    assert events[-1].reason == "end_turn"
    print("✓ TwoPassAgent without deep uses fast for both passes")


async def test_twopass_agent_fallback_propagates_through():
    """If deep backend fails, Pass 1 falls back to fast. Pass 2 still works."""
    deep = FailingBackend()
    fast = TaggedBackend("fast", [
        _plan_msg("fell back", "wifi_scan", "scan"),
        _tool_msg("wifi_scan", {}),
    ])

    agent = TwoPassAgent(
        fast, Dispatcher(_mk_registry()), AgentConfig(),
        deep_backend=deep,
    )
    events = [e async for e in agent.run("scan")]

    assert deep.call_count == 1, "deep was tried once"
    assert fast.call_count == 2, "fast did both planner (fallback) and parameterize"

    # PlanProposed should carry the fallback safety_note.
    from faust.agent.events import PlanProposed
    plan_event = next(e for e in events if isinstance(e, PlanProposed))
    assert any("deep planner unavailable" in n for n in plan_event.safety_notes)
    print("✓ end-to-end fallback: deep fails → fast plans → execution continues")


# ── Factory tests ──────────────────────────────────────────────

async def test_make_deep_backend_disabled():
    cfg = AgentConfig(planning_enabled=False)
    assert make_deep_backend(cfg) is None
    print("✓ make_deep_backend returns None when planning_enabled=False")


async def test_make_deep_backend_enabled():
    cfg = AgentConfig(planning_enabled=True)
    db = make_deep_backend(cfg)
    assert db is not None
    await db.aclose()
    print("✓ make_deep_backend returns a backend when enabled")


async def test_make_deep_backend_mephisto_default():
    """When backend=mephisto and no explicit endpoint, use MEPHISTO_PLANNING_ENDPOINT."""
    cfg = AgentConfig(
        backend="mephisto",
        llm_endpoint="http://localhost:11434/v1",  # default, not overridden
        planning_enabled=True,
        planning_endpoint="",
    )
    db = make_deep_backend(cfg)
    assert db is not None
    assert "8081" in db.endpoint, f"expected port 8081, got {db.endpoint}"
    await db.aclose()
    print("✓ make_deep_backend routes to 8081 for mephisto backend")


async def test_effective_planning_endpoint_fallback():
    cfg = AgentConfig(
        llm_endpoint="http://localhost:11434/v1",
        planning_endpoint="",
    )
    assert cfg.effective_planning_endpoint() == "http://localhost:11434/v1"

    cfg2 = AgentConfig(
        llm_endpoint="http://localhost:11434/v1",
        planning_endpoint="http://custom:8081/v1",
    )
    assert cfg2.effective_planning_endpoint() == "http://custom:8081/v1"
    print("✓ effective_planning_endpoint falls back to llm_endpoint when unset")


async def main():
    await test_planner_uses_deep_when_provided()
    await test_planner_falls_back_to_fast_on_deep_failure()
    await test_planner_uses_fast_only_when_no_deep()
    await test_twopass_agent_routes_planning_to_deep()
    await test_twopass_agent_without_deep_uses_fast_for_both()
    await test_twopass_agent_fallback_propagates_through()
    await test_make_deep_backend_disabled()
    await test_make_deep_backend_enabled()
    await test_make_deep_backend_mephisto_default()
    await test_effective_planning_endpoint_fallback()
    print("\nall cascade tests passed")


if __name__ == "__main__":
    asyncio.run(main())
