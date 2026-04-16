"""
Pivot-hint DSL + injection tests.

Covers:
  - evaluate_when: operators, path resolution, malformed conditions
  - matching_suggestions: filters hints correctly
  - TwoPassAgent: a skill with matching pivot_hints injects suggestions into
    the NEXT step's Pass 2 context, then clears them

Run with: python -m faust.tests.test_pivots
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
from faust.agent.pivots import evaluate_when, matching_suggestions
from faust.agent.twopass import TwoPassAgent
from faust.tools.registry import Tool, ToolRegistry, ToolResult


# ── Unit: evaluate_when ──────────────────────────────────────────

def test_equality_operators():
    s = {"captured": True, "count": 3, "target": "aa:bb"}
    assert evaluate_when("summary.captured == true", s)
    assert evaluate_when("summary.count == 3", s)
    assert evaluate_when("summary.target == \"aa:bb\"", s)
    assert not evaluate_when("summary.count == 5", s)
    print("✓ == operator")


def test_inequality_and_range():
    s = {"n": 10}
    assert evaluate_when("summary.n >= 10", s)
    assert evaluate_when("summary.n <= 10", s)
    assert evaluate_when("summary.n > 5", s)
    assert evaluate_when("summary.n < 20", s)
    assert evaluate_when("summary.n != 99", s)
    assert not evaluate_when("summary.n > 100", s)
    print("✓ numeric comparison operators")


def test_truthy_path():
    s = {"attacked": True, "clean": False, "name": "x", "empty": "", "missing": None}
    assert evaluate_when("summary.attacked", s)
    assert evaluate_when("summary.name", s)
    assert not evaluate_when("summary.clean", s)
    assert not evaluate_when("summary.empty", s)
    assert not evaluate_when("summary.missing", s)
    assert not evaluate_when("summary.nonexistent", s)
    print("✓ truthy-path implicit check")


def test_dotted_path():
    s = {"top": {"nested": {"leaf": 42}}}
    assert evaluate_when("summary.top.nested.leaf == 42", s)
    assert not evaluate_when("summary.top.nested.leaf == 1", s)
    # Missing path → evaluates to None, so == with anything truthy is False.
    assert not evaluate_when("summary.missing.path == 1", s)
    print("✓ dotted-path resolution including missing paths")


def test_malformed_never_raises():
    # Bad operators, missing keys, None summary — all return False, no raise.
    assert not evaluate_when("summary.x === 1", {"x": 1})
    assert not evaluate_when("bad syntax", {})
    assert not evaluate_when("summary.x == bad json here", {"x": 1})
    assert not evaluate_when("summary.x == 1", None)
    print("✓ malformed conditions return False silently")


def test_matching_suggestions_filters():
    hints = [
        {"when": "summary.a == 1", "suggest": "a hit"},
        {"when": "summary.b == 1", "suggest": "b hit"},
        {"when": "summary.c >= 10", "suggest": "c hit"},
    ]
    got = matching_suggestions(hints, {"a": 1, "b": 2, "c": 15})
    assert got == ["a hit", "c hit"]
    print("✓ matching_suggestions returns only hits")


def test_empty_hints_return_empty():
    assert matching_suggestions(None, {"a": 1}) == []
    assert matching_suggestions([], {"a": 1}) == []
    assert matching_suggestions([{"when": "summary.a == 1", "suggest": "x"}], None) == []
    print("✓ empty / None cases produce empty list")


# ── Integration: hints reach Pass 2 context ─────────────────────

class MockBackend(LLMBackend):
    def __init__(self, responses: list[AssistantMessage]) -> None:
        self.responses: deque[AssistantMessage] = deque(responses)
        self.calls: list[dict[str, Any]] = []

    async def complete(self, messages, tools):
        self.calls.append({"messages": list(messages)})
        if not self.responses:
            raise RuntimeError("MockBackend exhausted")
        return self.responses.popleft()


def _plan_response(steps):
    return AssistantMessage(
        content="",
        tool_calls=[ToolCall(
            id="p", name="submit_plan",
            arguments={"reasoning": "test", "steps": steps, "safety_notes": []},
        )],
        finish_reason="tool_calls",
    )


def _tool_response(name):
    return AssistantMessage(
        content="",
        tool_calls=[ToolCall(id="t", name=name, arguments={})],
        finish_reason="tool_calls",
    )


async def test_matching_hint_reaches_next_step():
    """A skill whose summary matches its pivot_hint should inject the suggest
    string into the NEXT step's parameterize prompt."""
    registry = ToolRegistry()
    # Skill A returns a summary that trips its pivot hint.
    def fn_a(args):
        return ToolResult(
            result={"full": "data"},
            summary={"captured": True, "hash_file": "x.22000"},
        )
    registry.register(Tool(
        name="cap", description="capture hash",
        parameters_schema={"type": "object", "properties": {}},
        fn=fn_a, sensitivity="passive",
        pivot_hints=[
            {"when": "summary.captured == true",
             "suggest": "Hash at summary.hash_file — wpa_crack next."},
        ],
    ))
    # Skill B is the next step; we want to see the hint in its prompt.
    registry.register(Tool(
        name="crack", description="crack hash",
        parameters_schema={"type": "object", "properties": {}},
        fn=lambda args: "cracked",
        sensitivity="passive",
    ))

    backend = MockBackend([
        _plan_response([
            {"skill": "cap", "intent": "capture"},
            {"skill": "crack", "intent": "crack"},
        ]),
        _tool_response("cap"),
        _tool_response("crack"),
    ])
    agent = TwoPassAgent(backend, Dispatcher(registry), AgentConfig())
    async for _ in agent.run("capture then crack"):
        pass

    # calls[0] = planner. calls[1] = parameterize cap. calls[2] = parameterize crack.
    # The hint should appear in calls[2]'s user message.
    crack_user = backend.calls[2]["messages"][1]["content"]
    assert "Hash at summary.hash_file" in crack_user, (
        f"expected hint in crack parameterize prompt, got:\n{crack_user}"
    )
    # And the hint should be tagged with the source skill.
    assert "cap:" in crack_user
    print("✓ matching hint appears in next step's Pass 2 context")


async def test_non_matching_hint_not_injected():
    """A hint whose `when` does NOT match should not reach the next step."""
    registry = ToolRegistry()
    registry.register(Tool(
        name="scan", description="scan",
        parameters_schema={"type": "object", "properties": {}},
        fn=lambda args: ToolResult(result={}, summary={"captured": False}),
        sensitivity="passive",
        pivot_hints=[
            {"when": "summary.captured == true", "suggest": "DO NOT SHOW"},
        ],
    ))
    registry.register(Tool(
        name="next", description="next",
        parameters_schema={"type": "object", "properties": {}},
        fn=lambda args: "ok",
        sensitivity="passive",
    ))

    backend = MockBackend([
        _plan_response([
            {"skill": "scan", "intent": "scan"},
            {"skill": "next", "intent": "next"},
        ]),
        _tool_response("scan"),
        _tool_response("next"),
    ])
    agent = TwoPassAgent(backend, Dispatcher(registry), AgentConfig())
    async for _ in agent.run("do both"):
        pass
    next_user = backend.calls[2]["messages"][1]["content"]
    assert "DO NOT SHOW" not in next_user
    print("✓ non-matching hint never reaches next step")


async def test_hints_cleared_after_one_step():
    """After consumption, pending_hints is cleared — hints don't leak
    forward to the step AFTER the one that was supposed to consume them."""
    registry = ToolRegistry()
    registry.register(Tool(
        name="scan", description="scan",
        parameters_schema={"type": "object", "properties": {}},
        fn=lambda args: ToolResult(result={}, summary={"x": 1}),
        sensitivity="passive",
        pivot_hints=[{"when": "summary.x == 1", "suggest": "ONE-SHOT HINT"}],
    ))
    # Two plain steps after the scan.
    for name in ("mid", "last"):
        registry.register(Tool(
            name=name, description=name,
            parameters_schema={"type": "object", "properties": {}},
            fn=lambda args: "ok",
            sensitivity="passive",
        ))

    backend = MockBackend([
        _plan_response([
            {"skill": "scan", "intent": "s"},
            {"skill": "mid", "intent": "m"},
            {"skill": "last", "intent": "l"},
        ]),
        _tool_response("scan"),
        _tool_response("mid"),
        _tool_response("last"),
    ])
    agent = TwoPassAgent(backend, Dispatcher(registry), AgentConfig())
    async for _ in agent.run("three steps"):
        pass
    mid_user = backend.calls[2]["messages"][1]["content"]
    last_user = backend.calls[3]["messages"][1]["content"]
    assert "ONE-SHOT HINT" in mid_user, "hint must reach the step immediately after scan"
    assert "ONE-SHOT HINT" not in last_user, "hint must NOT leak to the step after that"
    print("✓ hints are consumed once and cleared")


async def test_skill_without_hints_works_unchanged():
    """Backward-compat: a skill without pivot_hints must not break anything."""
    registry = ToolRegistry()
    registry.register(Tool(
        name="plain", description="plain",
        parameters_schema={"type": "object", "properties": {}},
        fn=lambda args: {"just": "a dict"},
        sensitivity="passive",
    ))
    backend = MockBackend([
        _plan_response([{"skill": "plain", "intent": "p"}]),
        _tool_response("plain"),
    ])
    agent = TwoPassAgent(backend, Dispatcher(registry), AgentConfig())
    events = [e async for e in agent.run("run plain")]
    assert events[-1].reason == "end_turn"
    print("✓ skills without pivot_hints still run cleanly")


async def _main():
    test_equality_operators()
    test_inequality_and_range()
    test_truthy_path()
    test_dotted_path()
    test_malformed_never_raises()
    test_matching_suggestions_filters()
    test_empty_hints_return_empty()
    await test_matching_hint_reaches_next_step()
    await test_non_matching_hint_not_injected()
    await test_hints_cleared_after_one_step()
    await test_skill_without_hints_works_unchanged()
    print("\nall pivot tests passed")


if __name__ == "__main__":
    asyncio.run(_main())
