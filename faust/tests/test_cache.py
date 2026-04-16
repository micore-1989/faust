"""
ResultCache tests.

Covers:
  - TTL per sensitivity class
  - key derivation stability
  - expiry / eviction
  - prompt-section rendering
  - integration with TwoPassAgent: stored after success, visible to planner,
    disruptive never stored

Run with: python -m faust.tests.test_cache
"""
from __future__ import annotations

import asyncio
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from faust.agent.backends import AssistantMessage, LLMBackend, ToolCall
from faust.agent.cache import ResultCache
from faust.agent.config import AgentConfig
from faust.agent.dispatch import Dispatcher
from faust.agent.twopass import TwoPassAgent
from faust.tools.registry import Tool, ToolRegistry, ToolResult


# ── Unit tests ──────────────────────────────────────────────────

def test_store_and_retrieve_passive():
    c = ResultCache()
    c.store("wifi_scan", {"band": "all"}, {"networks_found": 8}, "passive")
    entries = c.fresh_entries()
    assert len(entries) == 1
    assert entries[0].skill == "wifi_scan"
    assert entries[0].summary == {"networks_found": 8}
    print("✓ passive summary stored and retrievable")


def test_disruptive_never_cached():
    c = ResultCache()
    c.store("wifi_deauth", {"bssid": "x"}, {"frames_sent": 5}, "disruptive")
    assert c.fresh_entries() == []
    print("✓ disruptive summaries are never cached")


def test_none_summary_skipped():
    c = ResultCache()
    c.store("legacy_skill", {}, None, "passive")
    assert c.fresh_entries() == []
    print("✓ None summary is a no-op")


def test_stable_key_regardless_of_arg_order():
    c = ResultCache()
    c.store("wifi_scan", {"band": "all", "interface": "wlan1mon"}, {"a": 1}, "passive")
    c.store("wifi_scan", {"interface": "wlan1mon", "band": "all"}, {"a": 2}, "passive")
    # Same args (different insertion order) → overwrite, not duplicate.
    assert len(c.fresh_entries()) == 1
    assert c.fresh_entries()[0].summary == {"a": 2}
    print("✓ key is stable across args insertion order")


def test_different_args_produce_different_keys():
    c = ResultCache()
    c.store("wifi_scan", {"band": "2.4"}, {"x": 1}, "passive")
    c.store("wifi_scan", {"band": "5"},   {"x": 2}, "passive")
    entries = c.fresh_entries()
    assert len(entries) == 2
    print("✓ different args produce distinct cache entries")


def test_expired_entries_evicted_on_read():
    c = ResultCache(ttl_override={"passive": 1})
    c.store("x", {}, {"v": 1}, "passive")
    # Force expiry by backdating stored_at.
    entry = next(iter(c.entries.values()))
    entry.stored_at = time.monotonic() - 10
    alive = c.fresh_entries()
    assert alive == []
    assert c.entries == {}, "expired entry should be evicted"
    print("✓ expired entries are evicted lazily on read")


def test_render_empty_when_no_entries():
    c = ResultCache()
    assert c.render_prompt_section() == ""
    print("✓ empty cache renders to empty string")


def test_render_includes_skill_summary_and_age():
    c = ResultCache()
    c.store("wifi_scan", {}, {"networks_found": 5, "best_handshake_target": "aa:bb"},
            "passive")
    section = c.render_prompt_section()
    assert "Known recent results" in section
    assert "wifi_scan" in section
    assert "networks_found" in section
    assert "best_handshake_target" in section
    assert "s ago" in section  # age marker
    print("✓ render_prompt_section includes skill, summary, age")


# ── Integration with TwoPassAgent ───────────────────────────────

class MockBackend(LLMBackend):
    def __init__(self, responses):
        self.responses = deque(responses)
        self.calls: list[dict[str, Any]] = []

    async def complete(self, messages, tools):
        self.calls.append({"messages": list(messages)})
        if not self.responses:
            raise RuntimeError("MockBackend exhausted")
        return self.responses.popleft()


def _plan(steps):
    return AssistantMessage(
        content="",
        tool_calls=[ToolCall(id="p", name="submit_plan",
                             arguments={"reasoning": "r", "steps": steps, "safety_notes": []})],
        finish_reason="tool_calls",
    )


def _tc(name):
    return AssistantMessage(
        content="",
        tool_calls=[ToolCall(id="t", name=name, arguments={})],
        finish_reason="tool_calls",
    )


async def test_passive_skill_result_reaches_next_turn_planner():
    """After a passive skill runs, its summary must appear in the planner's
    system prompt on the NEXT invocation via the 'Known recent results' section."""
    registry = ToolRegistry()
    registry.register(Tool(
        name="scan", description="scan",
        parameters_schema={"type": "object", "properties": {}},
        fn=lambda a: ToolResult(result={}, summary={"found": 5}),
        sensitivity="passive",
    ))
    backend = MockBackend([
        _plan([{"skill": "scan", "intent": "s"}]),
        _tc("scan"),
        # Second turn: planner call only (empty plan → no execution).
        _plan([]),
    ])
    agent = TwoPassAgent(backend, Dispatcher(registry), AgentConfig())
    async for _ in agent.run("first turn"):
        pass
    async for _ in agent.run("second turn"):
        pass
    # Second-turn planner is calls[2].
    system = backend.calls[2]["messages"][0]["content"]
    assert "Known recent results" in system
    assert "scan" in system
    assert "found" in system
    print("✓ passive result cached and injected into next-turn planner prompt")


async def test_disruptive_skill_not_cached():
    """A disruptive skill's summary must NOT appear in the next planner prompt."""
    registry = ToolRegistry()
    registry.register(Tool(
        name="attack", description="attack",
        parameters_schema={"type": "object", "properties": {}},
        fn=lambda a: ToolResult(result={}, summary={"frames_sent": 100}),
        sensitivity="disruptive",
    ))
    backend = MockBackend([
        _plan([{"skill": "attack", "intent": "a"}]),
        _tc("attack"),
        _plan([]),
    ])
    agent = TwoPassAgent(backend, Dispatcher(registry), AgentConfig())
    async for _ in agent.run("attack"):
        pass
    async for _ in agent.run("next"):
        pass
    system = backend.calls[2]["messages"][0]["content"]
    assert "frames_sent" not in system
    # A clean cache produces no "Known recent results" section at all.
    assert "Known recent results" not in system
    print("✓ disruptive result is not cached and not leaked to planner")


async def test_cache_updated_across_multiple_steps():
    """After a multi-step plan, every passive/active step should be cached."""
    registry = ToolRegistry()
    for name, sens in [("scan_a", "passive"), ("scan_b", "active"), ("attack", "disruptive")]:
        registry.register(Tool(
            name=name, description=name,
            parameters_schema={"type": "object", "properties": {}},
            fn=(lambda a, _n=name: ToolResult(result={}, summary={"src": _n})),
            sensitivity=sens,
        ))
    backend = MockBackend([
        _plan([
            {"skill": "scan_a", "intent": "a", "critical": False},
            {"skill": "scan_b", "intent": "b", "critical": False},
            {"skill": "attack", "intent": "c", "critical": True},
        ]),
        _tc("scan_a"), _tc("scan_b"), _tc("attack"),
    ])
    agent = TwoPassAgent(backend, Dispatcher(registry), AgentConfig())
    async for _ in agent.run("chain"):
        pass
    cached_skills = {e.skill for e in agent.cache.fresh_entries()}
    assert cached_skills == {"scan_a", "scan_b"}, (
        f"expected passive+active cached, got {cached_skills}"
    )
    print("✓ passive+active cached, disruptive excluded")


async def _main():
    test_store_and_retrieve_passive()
    test_disruptive_never_cached()
    test_none_summary_skipped()
    test_stable_key_regardless_of_arg_order()
    test_different_args_produce_different_keys()
    test_expired_entries_evicted_on_read()
    test_render_empty_when_no_entries()
    test_render_includes_skill_summary_and_age()
    await test_passive_skill_result_reaches_next_turn_planner()
    await test_disruptive_skill_not_cached()
    await test_cache_updated_across_multiple_steps()
    print("\nall cache tests passed")


if __name__ == "__main__":
    asyncio.run(_main())
