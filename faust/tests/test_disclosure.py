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

from faust.agent.disclosure import DisclosureApprover
from faust.agent.dispatch import Dispatcher
from faust.agent.journal import GENESIS_HASH, Journal
from faust.tools.registry import Sensitivity, Tool, ToolRegistry


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

    print("\nall disclosure tests passed")


if __name__ == "__main__":
    asyncio.run(main())
