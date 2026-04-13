"""
Loop tests with a scripted mock backend.

These run without any LLM — the MockBackend returns whatever AssistantMessages
you queue. That's enough to verify:
  - the loop terminates on stop / max_iterations / user_abort / error
  - tool dispatch wires through correctly
  - tool results get fed back into the next model call
  - the disclosure approver actually gates execution
"""

from __future__ import annotations

import asyncio
import sys
from collections import deque
from pathlib import Path
from typing import Any

# Make the package importable when running this file directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from faust.agent.backends import AssistantMessage, LLMBackend, ToolCall
from faust.agent.config import AgentConfig
from faust.agent.dispatch import Dispatcher
from faust.agent.events import Final, Thinking, ToolCallExecuted, ToolCallProposed
from faust.agent.loop import AgentLoop
from faust.tools.registry import Tool, ToolRegistry


class MockBackend(LLMBackend):
    """Returns pre-queued AssistantMessages in order. Records every call."""

    def __init__(self, responses: list[AssistantMessage]) -> None:
        self.responses: deque[AssistantMessage] = deque(responses)
        self.call_log: list[list[dict[str, Any]]] = []

    async def complete(self, messages, tools):
        self.call_log.append(messages.copy())
        if not self.responses:
            raise RuntimeError("MockBackend exhausted")
        return self.responses.popleft()


def make_loop(
    responses: list[AssistantMessage],
    tools: list[Tool] | None = None,
    approver=None,
    max_iterations: int = 5,
) -> tuple[AgentLoop, MockBackend]:
    backend = MockBackend(responses)
    registry = ToolRegistry()
    for t in tools or []:
        registry.register(t)
    dispatcher = Dispatcher(registry, approver=approver)
    cfg = AgentConfig(max_iterations=max_iterations)
    return AgentLoop(backend, dispatcher, cfg), backend


def _add(args):
    return args["a"] + args["b"]


ADD_TOOL = Tool(
    name="add",
    description="add two ints",
    parameters_schema={
        "type": "object",
        "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
        "required": ["a", "b"],
    },
    fn=_add,
    sensitivity="passive",
)


DISRUPTIVE_TOOL = Tool(
    name="deauth",
    description="disruptive tool for disclosure tests",
    parameters_schema={"type": "object", "properties": {}},
    fn=lambda _args: "deauth_sent",
    sensitivity="disruptive",
)


async def collect(loop, prompt):
    return [e async for e in loop.run(prompt)]


# ------------- Tests -------------

async def test_terminates_on_no_tool_calls():
    loop, _ = make_loop([
        AssistantMessage(content="Hi there.", finish_reason="stop"),
    ])
    events = await collect(loop, "hello")
    assert isinstance(events[0], Thinking) and events[0].text == "Hi there."
    assert isinstance(events[-1], Final) and events[-1].reason == "end_turn"
    print("✓ terminates on no tool calls")


async def test_dispatches_tool_call_and_feeds_result_back():
    loop, backend = make_loop(
        [
            AssistantMessage(
                content="",
                tool_calls=[ToolCall(id="c1", name="add", arguments={"a": 3, "b": 4})],
                finish_reason="tool_calls",
            ),
            AssistantMessage(content="The answer is 7.", finish_reason="stop"),
        ],
        tools=[ADD_TOOL],
    )
    events = await collect(loop, "what is 3 + 4?")

    proposed = [e for e in events if isinstance(e, ToolCallProposed)]
    executed = [e for e in events if isinstance(e, ToolCallExecuted)]
    assert len(proposed) == 1 and proposed[0].tool_name == "add"
    assert len(executed) == 1 and executed[0].result == 7 and executed[0].error is None

    # Second backend call must include the role:tool message with the result.
    second_call_messages = backend.call_log[1]
    tool_msgs = [m for m in second_call_messages if m["role"] == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "c1"
    assert "7" in tool_msgs[0]["content"]

    assert isinstance(events[-1], Final) and events[-1].reason == "end_turn"
    print("✓ dispatches tool call and feeds result back")


async def test_max_iterations_cap():
    # Backend keeps requesting tools forever.
    infinite = [
        AssistantMessage(
            content="",
            tool_calls=[ToolCall(id=f"c{i}", name="add", arguments={"a": 1, "b": 1})],
            finish_reason="tool_calls",
        )
        for i in range(10)
    ]
    loop, _ = make_loop(infinite, tools=[ADD_TOOL], max_iterations=3)
    events = await collect(loop, "loop forever")
    assert isinstance(events[-1], Final) and events[-1].reason == "max_iterations"
    # Should have made exactly max_iterations tool calls.
    assert sum(1 for e in events if isinstance(e, ToolCallExecuted)) == 3
    print("✓ max_iterations cap halts runaway loops")


async def test_user_rejection_aborts_loop():
    async def reject_disruptive(name, args, sens):
        return sens != "disruptive"

    loop, _ = make_loop(
        [
            AssistantMessage(
                content="",
                tool_calls=[ToolCall(id="c1", name="deauth", arguments={})],
                finish_reason="tool_calls",
            ),
        ],
        tools=[DISRUPTIVE_TOOL],
        approver=reject_disruptive,
    )
    events = await collect(loop, "deauth that AP")
    executed = [e for e in events if isinstance(e, ToolCallExecuted)]
    assert len(executed) == 1 and executed[0].error == "user_rejected"
    assert isinstance(events[-1], Final) and events[-1].reason == "user_abort"
    print("✓ user rejection aborts the loop cleanly")


async def test_unknown_tool_returns_error_to_model():
    loop, backend = make_loop(
        [
            AssistantMessage(
                content="",
                tool_calls=[ToolCall(id="c1", name="hallucinated_tool", arguments={})],
                finish_reason="tool_calls",
            ),
            AssistantMessage(content="Sorry, can't do that.", finish_reason="stop"),
        ],
        tools=[],
    )
    events = await collect(loop, "do the thing")
    executed = [e for e in events if isinstance(e, ToolCallExecuted)]
    assert len(executed) == 1
    assert "unknown tool" in (executed[0].error or "")
    # Error must be fed back to the model, not just dropped.
    assert any(
        m["role"] == "tool" and "unknown tool" in m["content"]
        for m in backend.call_log[1]
    )
    print("✓ unknown tool errors are surfaced to the model")


async def test_tool_exception_does_not_crash_loop():
    def boom(_args):
        raise ValueError("boom")
    boom_tool = Tool(
        name="boom",
        description="always fails",
        parameters_schema={"type": "object", "properties": {}},
        fn=boom,
        sensitivity="passive",
    )
    loop, _ = make_loop(
        [
            AssistantMessage(
                content="",
                tool_calls=[ToolCall(id="c1", name="boom", arguments={})],
                finish_reason="tool_calls",
            ),
            AssistantMessage(content="Acknowledged the failure.", finish_reason="stop"),
        ],
        tools=[boom_tool],
    )
    events = await collect(loop, "trigger the bug")
    executed = [e for e in events if isinstance(e, ToolCallExecuted)]
    assert "ValueError: boom" in (executed[0].error or "")
    assert isinstance(events[-1], Final) and events[-1].reason == "end_turn"
    print("✓ tool exceptions surface as events without crashing the loop")


async def test_backend_error_emits_final_error():
    class BrokenBackend(LLMBackend):
        async def complete(self, messages, tools):
            raise ConnectionError("endpoint down")
    cfg = AgentConfig()
    loop = AgentLoop(BrokenBackend(), Dispatcher(ToolRegistry()), cfg)
    events = await collect(loop, "anything")
    assert isinstance(events[-1], Final) and events[-1].reason == "error"
    assert "endpoint down" in (events[-1].error or "")
    print("✓ backend errors emit Final(reason='error')")


async def main():
    await test_terminates_on_no_tool_calls()
    await test_dispatches_tool_call_and_feeds_result_back()
    await test_max_iterations_cap()
    await test_user_rejection_aborts_loop()
    await test_unknown_tool_returns_error_to_model()
    await test_tool_exception_does_not_crash_loop()
    await test_backend_error_emits_final_error()
    print("\nall tests passed")


if __name__ == "__main__":
    asyncio.run(main())
