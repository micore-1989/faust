"""
Disclosure layer tests — journal + approver.

Tests:
  - Journal: append, chain integrity, tamper detection
  - Approver: passive auto-approves, active/disruptive route to confirmation UI
  - Integration: approver + dispatcher + journal end-to-end

Run with: python -m faust.tests.test_disclosure
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from faust.agent.disclosure import (
    DisclosureApprover,
    TrustCache,
    scope_key_from_state,
)
from faust.agent.dispatch import Dispatcher
from faust.agent.journal import GENESIS_HASH, Journal
from faust.tools.registry import Sensitivity, Tool, ToolRegistry
from faust.ui.state import ScopeState


# ------------- Helpers -------------

def _tmp_journal() -> tuple[Journal, str]:
    """Create a journal in a temp file. Returns (journal, path)."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)  # Journal will create it.
    return Journal(path), path


def _cleanup(journal: Journal, path: str) -> None:
    journal.close()
    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(path + suffix)
        except FileNotFoundError:
            pass


# ------------- Journal tests -------------

async def test_journal_append_and_read():
    j, path = _tmp_journal()
    try:
        e = j.record("echo", {"text": "hi"}, "passive", "auto")
        assert e.seq == 1
        assert e.tool_name == "echo"
        assert e.prev_hash == GENESIS_HASH
        assert len(e.row_hash) == 64

        entries = j.entries()
        assert len(entries) == 1
        assert entries[0].arguments == {"text": "hi"}
    finally:
        _cleanup(j, path)
    print("✓ journal append and read")


async def test_journal_chain_integrity():
    j, path = _tmp_journal()
    try:
        j.record("echo", {"text": "1"}, "passive", "auto")
        j.record("scan", {"iface": "wlan0"}, "active", "approved")
        j.record("deauth", {"bssid": "aa:bb:cc"}, "disruptive", "rejected")

        assert j.verify_chain() is None
        assert j.count() == 3

        entries = j.entries()
        assert entries[1].prev_hash == entries[0].row_hash
        assert entries[2].prev_hash == entries[1].row_hash
    finally:
        _cleanup(j, path)
    print("✓ journal chain integrity verified")


async def test_journal_tamper_detection():
    j, path = _tmp_journal()
    try:
        j.record("echo", {"text": "1"}, "passive", "auto")
        j.record("scan", {"iface": "wlan0"}, "active", "approved")
        j.record("deauth", {"bssid": "aa:bb:cc"}, "disruptive", "rejected")

        # Tamper: modify the middle row's tool_name.
        j._conn.execute(
            "UPDATE journal SET tool_name = 'tampered' WHERE seq = 2"
        )
        j._conn.commit()

        # Chain should break at seq 2.
        broken_at = j.verify_chain()
        assert broken_at == 2
    finally:
        _cleanup(j, path)
    print("✓ journal tamper detection works")


async def test_journal_tamper_detection_prev_hash():
    j, path = _tmp_journal()
    try:
        j.record("a", {}, "passive", "auto")
        j.record("b", {}, "passive", "auto")

        # Tamper: change prev_hash of row 2.
        j._conn.execute(
            "UPDATE journal SET prev_hash = 'deadbeef' WHERE seq = 2"
        )
        j._conn.commit()

        broken_at = j.verify_chain()
        assert broken_at == 2
    finally:
        _cleanup(j, path)
    print("✓ journal detects prev_hash tampering")


async def test_journal_empty_chain_valid():
    j, path = _tmp_journal()
    try:
        assert j.verify_chain() is None
        assert j.count() == 0
    finally:
        _cleanup(j, path)
    print("✓ empty journal chain is valid")


async def test_journal_records_result_and_error():
    j, path = _tmp_journal()
    try:
        j.record("scan", {}, "passive", "auto",
                 result_summary="found 3 networks", duration_ms=150)
        j.record("deauth", {}, "disruptive", "approved",
                 error="interface not in monitor mode", duration_ms=5)

        entries = j.entries()
        assert entries[0].result_summary == "found 3 networks"
        assert entries[0].duration_ms == 150
        assert entries[1].error == "interface not in monitor mode"
        assert j.verify_chain() is None
    finally:
        _cleanup(j, path)
    print("✓ journal records result_summary, error, and duration_ms")


# ------------- Approver tests -------------

async def test_passive_auto_approves():
    j, path = _tmp_journal()
    try:
        approver = DisclosureApprover(j)
        result = await approver("echo", {"text": "hi"}, "passive")
        assert result is True
        assert j.count() == 1
        assert j.entries()[0].decision == "auto"
    finally:
        _cleanup(j, path)
    print("✓ passive tool auto-approves and journals")


async def test_active_routes_to_confirm():
    confirmations: list[tuple[str, Sensitivity]] = []

    async def fake_confirm(name: str, args: dict[str, Any], sens: Sensitivity) -> bool:
        confirmations.append((name, sens))
        return True

    j, path = _tmp_journal()
    try:
        approver = DisclosureApprover(j, confirm=fake_confirm)
        result = await approver("scan", {"iface": "wlan0"}, "active")
        assert result is True
        assert len(confirmations) == 1
        assert confirmations[0] == ("scan", "active")
        assert j.entries()[0].decision == "approved"
    finally:
        _cleanup(j, path)
    print("✓ active tool routes to confirmation UI")


async def test_disruptive_routes_to_confirm():
    async def fake_confirm(name: str, args: dict[str, Any], sens: Sensitivity) -> bool:
        return True

    j, path = _tmp_journal()
    try:
        approver = DisclosureApprover(j, confirm=fake_confirm)
        result = await approver("deauth", {"bssid": "aa:bb:cc"}, "disruptive")
        assert result is True
        assert j.entries()[0].decision == "approved"
    finally:
        _cleanup(j, path)
    print("✓ disruptive tool routes to confirmation UI")


async def test_rejection_journaled():
    async def reject_all(name: str, args: dict[str, Any], sens: Sensitivity) -> bool:
        return False

    j, path = _tmp_journal()
    try:
        approver = DisclosureApprover(j, confirm=reject_all)
        result = await approver("deauth", {}, "disruptive")
        assert result is False
        assert j.entries()[0].decision == "rejected"
    finally:
        _cleanup(j, path)
    print("✓ rejection is journaled")


async def test_sync_confirm_callback():
    """ConfirmationUI can be sync — approver handles both."""
    def sync_confirm(name: str, args: dict[str, Any], sens: Sensitivity) -> bool:
        return True

    j, path = _tmp_journal()
    try:
        approver = DisclosureApprover(j, confirm=sync_confirm)
        result = await approver("scan", {}, "active")
        assert result is True
    finally:
        _cleanup(j, path)
    print("✓ sync confirmation callback works")


# ------------- Integration: approver + dispatcher -------------

async def test_disclosure_dispatcher_integration():
    """Full pipeline: approver → dispatcher → journal, with a real tool."""
    j, path = _tmp_journal()
    try:
        registry = ToolRegistry()
        registry.register(Tool(
            name="echo",
            description="echo",
            parameters_schema={"type": "object", "properties": {}},
            fn=lambda args: "echoed",
            sensitivity="passive",
        ))
        registry.register(Tool(
            name="scan",
            description="scan",
            parameters_schema={"type": "object", "properties": {}},
            fn=lambda args: "scan_result",
            sensitivity="active",
        ))

        async def approve_active(name: str, args: dict, sens: Sensitivity) -> bool:
            return True

        approver = DisclosureApprover(j, confirm=approve_active)
        dispatcher = Dispatcher(registry, approver=approver)

        # Passive: auto-approved, executes.
        r1 = await dispatcher.dispatch("echo", {})
        assert r1.executed and r1.result == "echoed"

        # Active: confirmed, executes.
        r2 = await dispatcher.dispatch("scan", {})
        assert r2.executed and r2.result == "scan_result"

        # Journal should have 2 entries (one per approval).
        assert j.count() == 2
        assert j.verify_chain() is None
    finally:
        _cleanup(j, path)
    print("✓ disclosure + dispatcher integration")


async def test_disclosure_dispatcher_rejection():
    """Rejected tool: journaled, not executed."""
    j, path = _tmp_journal()
    try:
        registry = ToolRegistry()
        registry.register(Tool(
            name="deauth",
            description="deauth",
            parameters_schema={"type": "object", "properties": {}},
            fn=lambda args: "should_not_run",
            sensitivity="disruptive",
        ))

        async def reject_all(name: str, args: dict, sens: Sensitivity) -> bool:
            return False

        approver = DisclosureApprover(j, confirm=reject_all)
        dispatcher = Dispatcher(registry, approver=approver)

        result = await dispatcher.dispatch("deauth", {"bssid": "aa:bb:cc"})
        assert not result.executed or result.error == "user_rejected"

        # Journal records the rejection.
        entries = j.entries()
        assert len(entries) == 1
        assert entries[0].decision == "rejected"
    finally:
        _cleanup(j, path)
    print("✓ disclosure + dispatcher rejection")


# ------------- TrustCache tests -------------

class CountingApprover:
    """Inner approver that counts invocations and can be scripted to
    return varying results per call."""

    def __init__(self, results: list[bool] | None = None, default: bool = True) -> None:
        self._results = list(results) if results else []
        self._default = default
        self.calls: list[tuple[str, dict[str, Any], Sensitivity]] = []

    async def __call__(
        self, tool_name: str, arguments: dict[str, Any], sens: Sensitivity,
    ) -> bool:
        self.calls.append((tool_name, arguments, sens))
        if self._results:
            return self._results.pop(0)
        return self._default


class FakeClock:
    """Deterministic monotonic-like clock for TrustCache tests."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def __call__(self) -> float:
        return self.now


class TestTrustCache:
    """Groups all TrustCache behavior tests per task spec. Methods use
    `self` so pytest resolves them under the class path
    `test_disclosure.py::TestTrustCache`."""

    async def test_first_call_runs_inner(self):
        """Empty cache — first call must delegate to inner approver."""
        inner = CountingApprover()
        clock = FakeClock()
        tc = TrustCache(inner=inner, scope_key_source=lambda: "recon", time_source=clock)

        ok = await tc("wifi_deauth", {"bssid": "aa"}, "disruptive")
        assert ok is True
        assert len(inner.calls) == 1
        assert tc.last_decision_was_cached is False
        print("✓ TrustCache first call runs inner approver")

    async def test_cached_within_window_skips_inner(self):
        """Second call within window with same scope — inner NOT invoked."""
        inner = CountingApprover()
        clock = FakeClock()
        tc = TrustCache(inner=inner, window_s=600,
                        scope_key_source=lambda: "recon", time_source=clock)

        await tc("wifi_deauth", {"bssid": "aa"}, "disruptive")
        clock.advance(30)  # 30s later, still in window
        ok = await tc("wifi_deauth", {"bssid": "bb"}, "disruptive")

        assert ok is True
        assert len(inner.calls) == 1, "inner should have been called exactly once"
        assert tc.last_decision_was_cached is True
        print("✓ TrustCache within window skips inner approver")

    async def test_cached_across_scope_boundary_runs_inner(self):
        """Scope key changes between calls — cache must miss."""
        inner = CountingApprover()
        clock = FakeClock()
        scope: dict[str, str] = {"key": "recon"}
        tc = TrustCache(
            inner=inner, window_s=600,
            scope_key_source=lambda: scope["key"],
            time_source=clock,
        )

        await tc("wifi_deauth", {}, "disruptive")
        scope["key"] = "pentesting:corp-engagement-042"  # scope changes
        clock.advance(10)
        await tc("wifi_deauth", {}, "disruptive")

        assert len(inner.calls) == 2
        assert tc.last_decision_was_cached is False
        print("✓ TrustCache across scope boundary invokes inner")

    async def test_cached_after_window_expiry_runs_inner(self):
        """Advancing the injected clock past the window forces a re-check."""
        inner = CountingApprover()
        clock = FakeClock()
        tc = TrustCache(inner=inner, window_s=600,
                        scope_key_source=lambda: "recon", time_source=clock)

        await tc("wifi_deauth", {}, "disruptive")
        clock.advance(601)  # just past window
        await tc("wifi_deauth", {}, "disruptive")

        assert len(inner.calls) == 2
        assert tc.last_decision_was_cached is False
        print("✓ TrustCache after window expiry re-runs inner")

    async def test_invalidate_clears_cache(self):
        """invalidate() drops the cache — next call goes through inner."""
        inner = CountingApprover()
        clock = FakeClock()
        tc = TrustCache(inner=inner, scope_key_source=lambda: "recon",
                        time_source=clock)

        await tc("wifi_deauth", {}, "disruptive")
        tc.invalidate()
        await tc("wifi_deauth", {}, "disruptive")

        assert len(inner.calls) == 2
        print("✓ TrustCache invalidate() drops the cache")

    async def test_rejection_not_cached(self):
        """Inner rejected → cache untouched. Second call must hit inner again."""
        inner = CountingApprover(results=[False, True])
        clock = FakeClock()
        tc = TrustCache(inner=inner, scope_key_source=lambda: "recon",
                        time_source=clock)

        ok1 = await tc("wifi_deauth", {}, "disruptive")
        ok2 = await tc("wifi_deauth", {}, "disruptive")

        assert ok1 is False and ok2 is True
        assert len(inner.calls) == 2, "rejection must not populate the cache"
        print("✓ TrustCache rejection does not populate cache")

    async def test_scope_key_derivation(self):
        """scope_key_from_state: None → 'none', recon → 'recon', pentesting
        gets description tacked on so engagements don't share trust."""
        assert scope_key_from_state(ScopeState()) == "none"
        assert scope_key_from_state(ScopeState(template="recon")) == "recon"
        assert scope_key_from_state(ScopeState(template="self-test")) == "self-test"
        k1 = scope_key_from_state(
            ScopeState(template="pentesting", description="engagement A")
        )
        k2 = scope_key_from_state(
            ScopeState(template="pentesting", description="engagement B")
        )
        assert k1 == "pentesting:engagement A"
        assert k2 == "pentesting:engagement B"
        assert k1 != k2, "different pentesting descriptions must get different keys"
        print("✓ scope_key_from_state derives 4 key shapes correctly")

    async def test_last_decision_was_cached_flag(self):
        """Flag is False after a fresh call, True after a cache hit, and
        flips back to False when the cache misses again."""
        inner = CountingApprover()
        clock = FakeClock()
        tc = TrustCache(inner=inner, scope_key_source=lambda: "recon",
                        time_source=clock)

        await tc("wifi_deauth", {}, "disruptive")
        assert tc.last_decision_was_cached is False

        clock.advance(1)
        await tc("wifi_deauth", {}, "disruptive")
        assert tc.last_decision_was_cached is True

        tc.invalidate()
        await tc("wifi_deauth", {}, "disruptive")
        assert tc.last_decision_was_cached is False
        print("✓ last_decision_was_cached tracks fresh vs remembered")


async def test_trust_cache_preserves_disclosure_seam():
    """Spec §16.4 + CLAUDE.md rule 3: TrustCache must not bypass
    DisclosureApprover on a cache miss — it delegates, so the journal sees
    the call as usual."""
    j, path = _tmp_journal()
    try:
        async def always_approve(name, args, sens):
            return True

        inner = DisclosureApprover(j, confirm=always_approve)
        tc = TrustCache(inner=inner, scope_key_source=lambda: "recon")

        await tc("wifi_deauth", {"bssid": "aa"}, "disruptive")
        # Cache hit — journal should NOT get a second entry, because the
        # caller is responsible for journaling the "remembered" decision.
        await tc("wifi_deauth", {"bssid": "bb"}, "disruptive")

        entries = j.entries()
        assert len(entries) == 1
        assert entries[0].decision == "approved"
    finally:
        _cleanup(j, path)
    print("✓ TrustCache wraps DisclosureApprover (does not bypass it)")


async def main():
    # Journal tests
    await test_journal_append_and_read()
    await test_journal_chain_integrity()
    await test_journal_tamper_detection()
    await test_journal_tamper_detection_prev_hash()
    await test_journal_empty_chain_valid()
    await test_journal_records_result_and_error()

    # Approver tests
    await test_passive_auto_approves()
    await test_active_routes_to_confirm()
    await test_disruptive_routes_to_confirm()
    await test_rejection_journaled()
    await test_sync_confirm_callback()

    # Integration tests
    await test_disclosure_dispatcher_integration()
    await test_disclosure_dispatcher_rejection()

    # TrustCache tests
    tc_tests = TestTrustCache()
    await tc_tests.test_first_call_runs_inner()
    await tc_tests.test_cached_within_window_skips_inner()
    await tc_tests.test_cached_across_scope_boundary_runs_inner()
    await tc_tests.test_cached_after_window_expiry_runs_inner()
    await tc_tests.test_invalidate_clears_cache()
    await tc_tests.test_rejection_not_cached()
    await tc_tests.test_scope_key_derivation()
    await tc_tests.test_last_decision_was_cached_flag()
    await test_trust_cache_preserves_disclosure_seam()

    print("\nall disclosure tests passed")


if __name__ == "__main__":
    asyncio.run(main())
