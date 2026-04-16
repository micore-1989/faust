"""
Stage 11 journal tests.

Exercises:
  - serialize_entry / query_journal filter composition
  - JournalNotes sidecar round-trip
  - server's `journal_query` WS handler + `journal_update_notes` handler
  - tool-invocation journaling via the disclosure layer (end-to-end
    through the Journal that ships today)

Run with: python -m faust.tests.test_journal
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from faust.agent.journal import Journal
from faust.agent.journal_notes import JournalNotes
from faust.agent.journal_query import query_journal, serialize_entry
from faust.agent.disclosure import DisclosureApprover
from faust.ui.bridge import EventBridge
from faust.ui.server import UIServer


# ──────────────────────────────────────────────────────────────
# serialize_entry + query_journal
# ──────────────────────────────────────────────────────────────

async def test_journal_entry_creation_on_tool_executed():
    """The disclosure layer records an entry (pre-execution) and
    amends it post-execution — both land in the journal as a single
    row the UI can serialize."""
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "journal.db")
        journal = Journal(db)
        approver = DisclosureApprover(journal, confirm=None)

        # Passive skills auto-approve + record pre-execution.
        approved = await approver("wifi_scan", {"interface": "wlan1mon"}, "passive")
        assert approved is True

        approver.record_outcome(
            tool_name="wifi_scan",
            arguments={"interface": "wlan1mon"},
            sensitivity="passive",
            result_summary="3 networks seen",
            error=None,
            duration_ms=1400,
        )

        entries = journal.entries()
        assert len(entries) == 2, "pre-call record + outcome record"

        outcome = entries[-1]
        wire = serialize_entry(outcome, notes="")
        assert wire["tool_name"] == "wifi_scan"
        assert wire["type"] == "tool_invocation"
        assert wire["category"] == "wifi_ble"
        assert wire["sensitivity"] == "passive"
        assert wire["duration_ms"] == 1400
        assert wire["result_summary"] == "3 networks seen"
        journal.close()
    print("✓ tool_executed creates journal entry via disclosure layer")


async def test_journal_query_filters_by_group():
    entries = [
        {"id": "1", "timestamp": 1.0, "tool_name": "wifi_scan", "category": "wifi_ble", "sensitivity": "passive", "type": "tool_invocation"},
        {"id": "2", "timestamp": 2.0, "tool_name": "nfc_read",  "category": "nfc",      "sensitivity": "passive", "type": "tool_invocation"},
        {"id": "3", "timestamp": 3.0, "tool_name": "ble_scan",  "category": "wifi_ble", "sensitivity": "passive", "type": "tool_invocation"},
    ]
    out = query_journal(entries, {"group": "wifi_ble"})
    assert [e["id"] for e in out] == ["3", "1"], "newest first, only wifi_ble"
    print("✓ query_journal filters by sigil group")


async def test_journal_query_filters_by_sensitivity():
    entries = [
        {"id": "1", "timestamp": 1.0, "tool_name": "wifi_scan",   "sensitivity": "passive",    "category": "wifi_ble", "type": "tool_invocation"},
        {"id": "2", "timestamp": 2.0, "tool_name": "wifi_deauth", "sensitivity": "disruptive", "category": "wifi_ble", "type": "tool_invocation"},
        {"id": "3", "timestamp": 3.0, "tool_name": "ble_scan",    "sensitivity": "passive",    "category": "wifi_ble", "type": "tool_invocation"},
    ]
    out = query_journal(entries, {"sensitivity": "disruptive"})
    assert [e["id"] for e in out] == ["2"]
    print("✓ query_journal filters by sensitivity")


async def test_journal_query_filters_by_time_range():
    now = 1_000_000.0
    entries = [
        # 5 days ago
        {"id": "old", "timestamp": now - 5 * 24 * 3600, "tool_name": "wifi_scan", "sensitivity": "passive", "category": "wifi_ble", "type": "tool_invocation"},
        # 2 hours ago
        {"id": "recent", "timestamp": now - 2 * 3600,   "tool_name": "wifi_scan", "sensitivity": "passive", "category": "wifi_ble", "type": "tool_invocation"},
        # 10 days ago
        {"id": "stale",  "timestamp": now - 10 * 24 * 3600, "tool_name": "wifi_scan", "sensitivity": "passive", "category": "wifi_ble", "type": "tool_invocation"},
    ]
    out24 = query_journal(entries, {"time_range": "24h"}, now=now)
    assert [e["id"] for e in out24] == ["recent"]

    out7 = query_journal(entries, {"time_range": "7d"}, now=now)
    assert sorted(e["id"] for e in out7) == ["old", "recent"]
    print("✓ query_journal filters by time_range")


async def test_journal_update_notes_via_sidecar():
    """The sidecar persists a single entry's operator notes and survives
    a fresh JournalNotes instance pointed at the same file."""
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "notes.json")
        notes = JournalNotes(path)
        assert notes.get(42) == ""
        notes.set(42, "saw a new access point")
        notes.set("100", "deauthed only the lab device")

        reopen = JournalNotes(path)
        assert reopen.get(42) == "saw a new access point"
        assert reopen.get("100") == "deauthed only the lab device"
        assert reopen.get(999) == ""
    print("✓ journal notes sidecar round-trips via JSON file")


# ──────────────────────────────────────────────────────────────
# Server WS handlers: journal_query + journal_update_notes
# ──────────────────────────────────────────────────────────────

async def test_server_journal_query_returns_entries_with_filters_applied():
    """End-to-end through the server's WS handler: put an entry in the
    journal, send {type: journal_query, filters: {group: wifi_ble}},
    assert the reply carries exactly that entry."""
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "journal.db")
        journal = Journal(db)
        notes = JournalNotes(str(Path(tmp) / "notes.json"))

        bridge = EventBridge()
        q = bridge.subscribe()
        server = UIServer(bridge, port=0)
        server.set_disclosure(trust_cache=None, journal=journal, journal_notes=notes)

        journal.record(
            tool_name="wifi_scan", arguments={"interface": "wlan1mon"},
            sensitivity="passive", decision="auto", result_summary="3 nets",
            duration_ms=1200,
        )
        journal.record(
            tool_name="nfc_read", arguments={}, sensitivity="passive",
            decision="auto", result_summary="none",
        )

        await server._handle_incoming({"type": "journal_query", "filters": {"group": "wifi_ble"}})
        msg = await asyncio.wait_for(q.get(), timeout=1.0)
        assert msg["type"] == "journal_entries"
        assert msg["filters"] == {"group": "wifi_ble"}
        assert len(msg["entries"]) == 1
        assert msg["entries"][0]["tool_name"] == "wifi_scan"
        assert msg["entries"][0]["category"] == "wifi_ble"

        bridge.unsubscribe(q)
        journal.close()
    print("✓ server journal_query applies filters + serializes entries")


async def test_server_journal_update_notes_persists_and_broadcasts():
    """journal_update_notes hits the sidecar + emits a confirmation."""
    with tempfile.TemporaryDirectory() as tmp:
        notes_path = Path(tmp) / "notes.json"
        notes = JournalNotes(str(notes_path))
        bridge = EventBridge()
        q = bridge.subscribe()
        server = UIServer(bridge, port=0)
        server.set_disclosure(trust_cache=None, journal=None, journal_notes=notes)

        await server._handle_incoming({
            "type": "journal_update_notes",
            "id": "7",
            "notes": "re-tested after firmware update",
        })
        msg = await asyncio.wait_for(q.get(), timeout=1.0)
        assert msg["type"] == "journal_entry_updated"
        assert msg["id"] == "7"
        assert msg["notes"] == "re-tested after firmware update"

        reopen = JournalNotes(str(notes_path))
        assert reopen.get("7") == "re-tested after firmware update"
        bridge.unsubscribe(q)
    print("✓ server journal_update_notes persists to sidecar")


async def test_server_journal_query_without_journal_returns_empty():
    """Dev / test servers without a wired journal reply with an empty
    list so the client's state.journalEntries doesn't stall in an
    undefined state."""
    bridge = EventBridge()
    q = bridge.subscribe()
    server = UIServer(bridge, port=0)
    # No set_disclosure call: journal + notes are None.
    await server._handle_incoming({"type": "journal_query", "filters": {}})
    msg = await asyncio.wait_for(q.get(), timeout=1.0)
    assert msg["type"] == "journal_entries"
    assert msg["entries"] == []
    bridge.unsubscribe(q)
    print("✓ journal_query without journal returns empty entries")


async def test_demo_sequence_completes_without_error():
    """Integration guard: the Stage 11 demo sequence must complete end
    to end without raising. We fast-forward by monkeypatching
    asyncio.sleep so we don't pay the real ~40 s walltime in CI."""
    import tempfile
    from unittest.mock import patch

    from faust.ui.run import push_demo_events
    from faust.ui.server import UIServer

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "journal.db"
        journal = Journal(str(db))
        notes = JournalNotes(str(db) + ".notes.json")

        bridge = EventBridge()
        # Drain into a subscriber queue so push_event / push_raw don't
        # block on a full unbounded queue (EventBridge uses asyncio.Queue).
        q = bridge.subscribe()

        server = UIServer(bridge, port=0)
        server.set_disclosure(trust_cache=None, journal=journal, journal_notes=notes)
        server.state.power = server.state.power.__class__("on")

        async def _drain(queue):
            while True:
                try:
                    await asyncio.wait_for(queue.get(), timeout=0.05)
                except asyncio.TimeoutError:
                    return

        # Fast-forward every asyncio.sleep inside the demo.
        real_sleep = asyncio.sleep

        async def _fast_sleep(delay, *args, **kwargs):
            # Let a small yield happen so other tasks (like bridge fanout)
            # get a chance to run, but don't wait the real wall time.
            await real_sleep(0, *args, **kwargs)

        with patch("faust.ui.run.asyncio.sleep", _fast_sleep):
            await asyncio.wait_for(push_demo_events(bridge, server), timeout=10.0)

        # The demo should have journaled at least a scope.set + two tool
        # invocations + the hmc-demo pursuit, i.e. ≥4 rows.
        rows = journal.entries()
        tool_names = [r.tool_name for r in rows]
        assert "scope.set" in tool_names
        assert "wifi_scan" in tool_names
        assert "wifi_deauth" in tool_names
        assert "pursuit.hmc-demo" in tool_names

        # Drain the bridge so the test doesn't leave dangling awaiters.
        await _drain(q)
        bridge.unsubscribe(q)
        journal.close()
    print("✓ demo sequence completes without error (fast-forwarded)")


async def main() -> None:
    await test_journal_entry_creation_on_tool_executed()
    await test_journal_query_filters_by_group()
    await test_journal_query_filters_by_sensitivity()
    await test_journal_query_filters_by_time_range()
    await test_journal_update_notes_via_sidecar()
    await test_server_journal_query_returns_entries_with_filters_applied()
    await test_server_journal_update_notes_persists_and_broadcasts()
    await test_server_journal_query_without_journal_returns_empty()
    await test_demo_sequence_completes_without_error()
    print("\nall journal tests passed")


if __name__ == "__main__":
    asyncio.run(main())
