"""
Skill scoper tests.

Tests the scoper interface with NoopScoper and (if sentence-transformers is
installed) the real LocalEmbeddingScoper. Also verifies the agent loop
correctly filters tool_schemas when a scoper is attached.

Run with: python -m faust.tests.test_scoper
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from collections import deque
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from faust.agent.backends import AssistantMessage, LLMBackend, ToolCall
from faust.agent.config import AgentConfig
from faust.agent.dispatch import Dispatcher
from faust.agent.loop import AgentLoop
from faust.skills.scoper import (
    LocalEmbeddingScoper,
    NoopScoper,
    SkillScoper,
    make_scoper,
)
from faust.tools.registry import Tool, ToolRegistry


# ── Fixtures ─────────────────────────────────────────────────────

VALID_SKILL_TEMPLATE = """\
---
name: {name}
description: {description}
parameters_schema:
  type: object
  properties: {{}}
sensitivity: passive
---

{body}
"""


def _write_skill(root: Path, dirname: str, name: str, description: str, body: str) -> None:
    d = root / dirname
    d.mkdir()
    (d / "SKILL.md").write_text(
        VALID_SKILL_TEMPLATE.format(name=name, description=description, body=body)
    )


def _make_registry_from_names(names: list[str]) -> ToolRegistry:
    reg = ToolRegistry()
    for n in names:
        reg.register(Tool(
            name=n,
            description=f"test tool {n}",
            parameters_schema={"type": "object", "properties": {}},
            fn=lambda args, _n=n: f"{_n}_result",
            sensitivity="passive",
        ))
    return reg


class RecordingBackend(LLMBackend):
    """Records the tools passed on each call, returns a scripted response."""

    def __init__(self, responses: list[AssistantMessage]) -> None:
        self.responses = deque(responses)
        self.tools_seen: list[list[str]] = []

    async def complete(self, messages, tools):
        # Extract tool names the loop actually sent.
        names = [t["function"]["name"] for t in tools or []]
        self.tools_seen.append(names)
        if not self.responses:
            raise RuntimeError("RecordingBackend exhausted")
        return self.responses.popleft()


# ── NoopScoper ───────────────────────────────────────────────────

async def test_noop_scoper_returns_all():
    scoper = NoopScoper(["a", "b", "c", "d", "e"])
    assert await scoper.top_k("anything", k=3) == ["a", "b", "c"]
    assert await scoper.top_k("anything", k=0) == ["a", "b", "c", "d", "e"]
    assert await scoper.top_k("anything", k=100) == ["a", "b", "c", "d", "e"]
    assert scoper.all_skills() == ["a", "b", "c", "d", "e"]
    print("✓ NoopScoper returns all skills")


async def test_make_scoper_falls_back_without_st():
    """If sentence-transformers is missing OR the embedding scoper fails,
    make_scoper should return a NoopScoper, never raise."""
    with tempfile.TemporaryDirectory() as tmp:
        # Pass a non-existent skills_dir to force the embedding scoper to
        # hit some failure mode. It should fall back to Noop gracefully.
        scoper = make_scoper(
            Path(tmp) / "nonexistent",
            ["a", "b"],
            prefer_embedding=True,
        )
        # Either NoopScoper (fell back) or LocalEmbeddingScoper with 0 skills.
        assert isinstance(scoper, SkillScoper)
        # Either way, it shouldn't crash.
        result = await scoper.top_k("any query", k=2)
        assert isinstance(result, list)
    print("✓ make_scoper falls back gracefully")


async def test_prefer_embedding_false_returns_noop():
    with tempfile.TemporaryDirectory() as tmp:
        scoper = make_scoper(
            Path(tmp), ["x", "y"], prefer_embedding=False,
        )
        assert isinstance(scoper, NoopScoper)
    print("✓ prefer_embedding=False returns NoopScoper")


# ── LocalEmbeddingScoper (requires sentence-transformers) ────────

def _has_sentence_transformers() -> bool:
    try:
        import sentence_transformers  # noqa: F401
        return True
    except ImportError:
        return False


async def test_embedding_scoper_ranks_relevantly():
    if not _has_sentence_transformers():
        print("⊘ embedding scoper test skipped (sentence-transformers not installed)")
        return

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_skill(root, "wifi-scan", "wifi_scan",
                     "Scan nearby WiFi networks and clients",
                     "WiFi reconnaissance via monitor mode")
        _write_skill(root, "ble-scan", "ble_scan",
                     "Scan Bluetooth Low Energy devices",
                     "BLE device enumeration")
        _write_skill(root, "nfc-read", "nfc_read",
                     "Read NFC and RFID tags using PN532",
                     "NFC tag reading via 13.56 MHz")
        _write_skill(root, "ir-capture", "ir_capture",
                     "Capture and replay infrared remote codes",
                     "IR TV remote capture via TSOP38238")

        scoper = LocalEmbeddingScoper(root)

        # WiFi-related query should rank wifi_scan first.
        top = await scoper.top_k("scan the wireless network for access points", k=2)
        assert "wifi_scan" in top, f"expected wifi_scan in top 2, got {top}"

        # Bluetooth query should rank ble_scan first.
        top = await scoper.top_k("find bluetooth speakers nearby", k=2)
        assert "ble_scan" in top, f"expected ble_scan in top 2, got {top}"

        # IR query should rank ir_capture first.
        top = await scoper.top_k("record the remote control signal from the TV", k=2)
        assert "ir_capture" in top, f"expected ir_capture in top 2, got {top}"

    print("✓ embedding scoper ranks by semantic relevance")


async def test_embedding_scoper_caches():
    if not _has_sentence_transformers():
        print("⊘ embedding cache test skipped (sentence-transformers not installed)")
        return

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_skill(root, "a", "tool_a", "description a", "body a")
        _write_skill(root, "b", "tool_b", "description b", "body b")

        # First instantiation builds the cache.
        scoper1 = LocalEmbeddingScoper(root)
        assert (root / ".embeddings.npz").exists()

        # Second instantiation should load from cache — same ranking.
        scoper2 = LocalEmbeddingScoper(root)
        q = "description a"
        assert await scoper1.top_k(q, k=1) == await scoper2.top_k(q, k=1)

    print("✓ embedding scoper caches to disk")


async def test_embedding_cache_invalidates_on_change():
    if not _has_sentence_transformers():
        print("⊘ cache invalidation test skipped (sentence-transformers not installed)")
        return

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_skill(root, "a", "tool_a", "original description", "body")

        scoper1 = LocalEmbeddingScoper(root)
        first_embeddings = scoper1._embeddings.copy()

        # Rewrite the skill with different content.
        (root / "a" / "SKILL.md").write_text(
            VALID_SKILL_TEMPLATE.format(
                name="tool_a",
                description="totally different description about lasers",
                body="laser body",
            )
        )

        # New scoper should rebuild, not load stale cache.
        scoper2 = LocalEmbeddingScoper(root)
        import numpy as np
        assert not np.allclose(first_embeddings, scoper2._embeddings), \
            "cache should have invalidated on content change"

    print("✓ cache invalidates when SKILL.md content changes")


# ── Loop integration ─────────────────────────────────────────────

async def test_loop_uses_scoper_to_filter_tools():
    """Loop with a scoper should only send the top-K skills to the backend."""
    registry = _make_registry_from_names(
        ["wifi_scan", "wifi_deauth", "ble_scan", "nfc_read", "ir_capture",
         "rfid_clone", "wardrive", "nfc_emulate", "subghz_replay", "ble_spam"]
    )

    class FixedScoper(SkillScoper):
        async def top_k(self, query, k=8):
            return ["wifi_scan", "ble_scan"]  # ignore k and query
        def all_skills(self):
            return ["wifi_scan", "ble_scan"]

    backend = RecordingBackend([
        AssistantMessage(content="done", finish_reason="stop"),
    ])
    dispatcher = Dispatcher(registry)
    cfg = AgentConfig()
    loop = AgentLoop(
        backend, dispatcher, cfg,
        scoper=FixedScoper(),
        scoper_k=2,
    )

    events = [e async for e in loop.run("find wifi networks")]
    assert backend.tools_seen, "backend should have been called"
    sent_names = set(backend.tools_seen[0])
    assert sent_names == {"wifi_scan", "ble_scan"}, \
        f"expected only scoped tools, got {sent_names}"
    print("✓ loop with scoper sends only top-K tools to backend")


async def test_loop_without_scoper_sends_all_tools():
    """Loop with scoper=None should send every registered tool (old behavior)."""
    registry = _make_registry_from_names(["a", "b", "c", "d", "e"])
    backend = RecordingBackend([
        AssistantMessage(content="done", finish_reason="stop"),
    ])
    dispatcher = Dispatcher(registry)
    cfg = AgentConfig()
    loop = AgentLoop(backend, dispatcher, cfg)  # no scoper

    events = [e async for e in loop.run("anything")]
    assert set(backend.tools_seen[0]) == {"a", "b", "c", "d", "e"}
    print("✓ loop without scoper sends all tools (backward-compatible)")


async def main():
    # Interface tests (no ML deps required).
    await test_noop_scoper_returns_all()
    await test_make_scoper_falls_back_without_st()
    await test_prefer_embedding_false_returns_noop()

    # Embedding scoper tests (skipped if sentence-transformers not installed).
    await test_embedding_scoper_ranks_relevantly()
    await test_embedding_scoper_caches()
    await test_embedding_cache_invalidates_on_change()

    # Loop integration.
    await test_loop_uses_scoper_to_filter_tools()
    await test_loop_without_scoper_sends_all_tools()

    print("\nall scoper tests passed")


if __name__ == "__main__":
    asyncio.run(main())
