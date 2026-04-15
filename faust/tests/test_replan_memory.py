"""
Tests for re-plan on surprise + cross-turn conversation memory.

Run with: python -m faust.tests.test_replan_memory
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
from faust.agent.events import Final, PlanProposed, ToolCallExecuted, ToolCallProposed
from faust.agent.twopass import TwoPassAgent
from faust.tools.registry import Tool, ToolRegistry


# ── Mock backend ───────────────────────────────────────────────

class MockBackend(LLMBackend):
    def __init__(self, responses: list[AssistantMessage]) -> None:
        self.responses: deque[AssistantMessage] = deque(responses)
        self.calls: list[list[dict[str, Any]]] = []

    async def complete(self, messages, tools):
        self.calls.append(list(messages))
        if not self.responses:
            raise RuntimeError("MockBackend exhausted")
        return self.responses.popleft()


def _mk_registry_with(skills_and_fns: list[tuple[str, Any]]) -> ToolRegistry:
    reg = ToolRegistry()
    for name, fn in skills_and_fns:
        reg.register(Tool(
            name=name,
            description=f"test {name}",
            parameters_schema={"type": "object", "properties": {}},
            fn=fn,
            sensitivity="passive",
        ))
    return reg


def _plan(steps: list[str], reasoning: str = "r") -> AssistantMessage:
    return AssistantMessage(
        content="",
        tool_calls=[ToolCall(id="p", name="submit_plan", arguments={
            "reasoning": reasoning,
            "steps": [{"skill": s, "intent": f"do {s}"} for s in steps],
            "safety_notes": [],
        })],
        finish_reason="tool_calls",
    )


def _tool(name: str, args: dict | None = None) -> AssistantMessage:
    return AssistantMessage(
        content="",
        tool_calls=[ToolCall(id="t", name=name, arguments=args or {})],
        finish_reason="tool_calls",
    )


async def collect(agent, prompt, history=None):
    return [e async for e in agent.run(prompt, conversation_history=history)]


# ── Re-plan tests ──────────────────────────────────────────────

async def test_replan_fires_on_step_error():
    """If a step errors mid-plan, planner is re-invoked with current state."""
    def bad(args):
        raise ValueError("simulated hardware failure")

    def good(args):
        return {"ok": True}

    reg = _mk_registry_with([("fail_tool", bad), ("good_tool", good)])

    backend = MockBackend([
        _plan(["fail_tool", "good_tool"], "plan A"),  # original plan
        _tool("fail_tool"),                           # parameterize fail_tool
        _plan(["good_tool"], "revised after failure"),  # re-plan
        _tool("good_tool"),                           # parameterize good_tool
    ])
    cfg = AgentConfig(scoper_enabled=False, replan_enabled=True)
    agent = TwoPassAgent(backend, Dispatcher(reg), cfg)

    events = await collect(agent, "do things")

    # Two PlanProposed events: original + revised.
    plans = [e for e in events if isinstance(e, PlanProposed)]
    assert len(plans) == 2, f"expected 2 plans, got {len(plans)}"
    assert "revised" in plans[1].reasoning

    # Both tools dispatched (fail then good).
    executed = [e for e in events if isinstance(e, ToolCallExecuted)]
    assert len(executed) == 2
    assert executed[0].error is not None
    assert executed[1].error is None

    # Final is end_turn (good_tool worked).
    assert events[-1].reason == "end_turn"
    print("✓ re-plan fires on step error and recovers")


async def test_replan_capped_at_replan_max():
    """Consecutive errors — only one re-plan total."""
    def bad(args):
        raise ValueError("perma-broken")

    reg = _mk_registry_with([("fail_a", bad), ("fail_b", bad), ("fail_c", bad)])

    # Plan has 3 steps. Step 1 errors → re-plan (1st). Re-plan returns
    # [fail_b, fail_c]. fail_b errors → replan_max reached, no more re-plan.
    backend = MockBackend([
        _plan(["fail_a", "fail_b", "fail_c"], "p1"),
        _tool("fail_a"),
        _plan(["fail_b", "fail_c"], "replan 1"),  # uses the quota
        _tool("fail_b"),
        _tool("fail_c"),  # step 3's parameterize — no further replan
    ])
    cfg = AgentConfig(scoper_enabled=False, replan_enabled=True, replan_max=1)
    agent = TwoPassAgent(backend, Dispatcher(reg), cfg)

    events = await collect(agent, "do it")

    plans = [e for e in events if isinstance(e, PlanProposed)]
    assert len(plans) == 2, f"got {len(plans)} plans, expected 2"
    # All 3 steps attempted (1 original + 2 from replan).
    executed = [e for e in events if isinstance(e, ToolCallExecuted)]
    assert len(executed) == 3
    assert all(e.error is not None for e in executed)
    print("✓ re-plan respects replan_max cap (one replan total)")


async def test_replan_disabled_by_config():
    """replan_enabled=False → step errors don't trigger re-plan."""
    def bad(args):
        raise ValueError("oops")

    def good(args):
        return {"ok": True}

    reg = _mk_registry_with([("fail", bad), ("good", good)])

    backend = MockBackend([
        _plan(["fail", "good"]),
        _tool("fail"),
        _tool("good"),  # step 2's parameterize — should still be called
    ])
    cfg = AgentConfig(scoper_enabled=False, replan_enabled=False)
    agent = TwoPassAgent(backend, Dispatcher(reg), cfg)

    events = await collect(agent, "do it")

    plans = [e for e in events if isinstance(e, PlanProposed)]
    # Only the original plan — no replan emitted.
    assert len(plans) == 1, f"got {len(plans)} plans"
    # Both steps attempted in the original plan sequence.
    executed = [e for e in events if isinstance(e, ToolCallExecuted)]
    assert len(executed) == 2
    print("✓ re-plan disabled by config respects the flag")


async def test_replan_does_not_fire_on_user_rejection():
    """User rejection should abort, not re-plan."""
    async def reject_all(name, args, sens):
        return False

    reg = _mk_registry_with([("t1", lambda a: "ok"), ("t2", lambda a: "ok")])

    backend = MockBackend([
        _plan(["t1", "t2"]),
        _tool("t1"),
    ])
    # Wire up dispatcher with a rejecting approver.
    dispatcher = Dispatcher(reg, approver=reject_all)
    cfg = AgentConfig(scoper_enabled=False, replan_enabled=True)
    agent = TwoPassAgent(backend, dispatcher, cfg)

    events = await collect(agent, "do it")

    plans = [e for e in events if isinstance(e, PlanProposed)]
    assert len(plans) == 1, "user rejection should NOT trigger a re-plan"
    assert events[-1].reason == "user_abort"
    print("✓ user rejection aborts cleanly without re-plan")


# ── Cross-turn memory tests ────────────────────────────────────

async def test_history_passed_to_planner():
    """Conversation history should reach the planner in Pass 1."""
    reg = _mk_registry_with([("t1", lambda a: "ok")])
    backend = MockBackend([_plan(["t1"]), _tool("t1")])
    cfg = AgentConfig(scoper_enabled=False,
                      conversation_memory=True,
                      conversation_memory_turns=2)
    agent = TwoPassAgent(backend, Dispatcher(reg), cfg)

    history = [
        {"role": "user", "content": "scan wifi"},
        {"role": "assistant", "content": "Plan: scanned. Found TargetNet, -42dBm, WPA2."},
    ]
    await collect(agent, "attack the one we found", history=history)

    # Pass 1 (first backend call) system+messages should include history.
    plan_messages = backend.calls[0]
    user_roles = [m["role"] for m in plan_messages]
    # At least: system, user(history), assistant(history), user(current)
    assert user_roles.count("user") >= 2, f"roles={user_roles}"
    assert any("TargetNet" in m.get("content", "") for m in plan_messages)
    print("✓ conversation history reaches the planner")


async def test_history_respects_turn_cap():
    """Only the most recent N turns should pass through."""
    reg = _mk_registry_with([("t1", lambda a: "ok")])
    backend = MockBackend([_plan(["t1"]), _tool("t1")])
    cfg = AgentConfig(
        scoper_enabled=False,
        conversation_memory=True,
        conversation_memory_turns=1,  # keep only last 1 turn
    )
    agent = TwoPassAgent(backend, Dispatcher(reg), cfg)

    # 3 prior turns, oldest-to-newest.
    history = []
    for i in range(3):
        history.append({"role": "user", "content": f"old prompt {i}"})
        history.append({"role": "assistant", "content": f"old response {i}"})

    await collect(agent, "current", history=history)

    messages = backend.calls[0]
    joined = "\n".join(str(m.get("content", "")) for m in messages)
    # Only the newest turn should be preserved.
    assert "old response 2" in joined, "newest turn should be kept"
    assert "old prompt 0" not in joined, "oldest turn should be dropped"
    assert "old response 0" not in joined
    print("✓ history respects conversation_memory_turns cap")


async def test_history_respects_char_budget():
    """Huge messages should be truncated so we don't blow context budget."""
    reg = _mk_registry_with([("t1", lambda a: "ok")])
    backend = MockBackend([_plan(["t1"]), _tool("t1")])
    cfg = AgentConfig(
        scoper_enabled=False,
        conversation_memory=True,
        conversation_memory_turns=1,
        conversation_memory_chars=200,  # very small budget
    )
    agent = TwoPassAgent(backend, Dispatcher(reg), cfg)

    big = "X" * 10_000
    history = [
        {"role": "user", "content": f"please consider this: {big}"},
        {"role": "assistant", "content": f"here's a long report: {big}"},
    ]
    await collect(agent, "now", history=history)

    messages = backend.calls[0]
    # Sum up all history content we actually sent.
    history_chars = sum(
        len(str(m.get("content", "")))
        for m in messages
        if m.get("role") in ("user", "assistant")
        and m.get("content") != "now"  # exclude the current user prompt
    )
    assert history_chars <= 250, f"history exceeded budget: {history_chars} chars"
    print(f"✓ history respects char budget ({history_chars} ≤ 200)")


async def test_memory_disabled_sends_no_history():
    reg = _mk_registry_with([("t1", lambda a: "ok")])
    backend = MockBackend([_plan(["t1"]), _tool("t1")])
    cfg = AgentConfig(scoper_enabled=False, conversation_memory=False)
    agent = TwoPassAgent(backend, Dispatcher(reg), cfg)

    history = [{"role": "user", "content": "should not appear"}]
    await collect(agent, "current", history=history)

    messages = backend.calls[0]
    joined = "\n".join(str(m.get("content", "")) for m in messages)
    assert "should not appear" not in joined
    print("✓ conversation_memory=False disables history entirely")


async def main():
    # Re-plan
    await test_replan_fires_on_step_error()
    await test_replan_capped_at_replan_max()
    await test_replan_disabled_by_config()
    await test_replan_does_not_fire_on_user_rejection()
    # Cross-turn memory
    await test_history_passed_to_planner()
    await test_history_respects_turn_cap()
    await test_history_respects_char_budget()
    await test_memory_disabled_sends_no_history()
    print("\nall replan+memory tests passed")


if __name__ == "__main__":
    asyncio.run(main())
