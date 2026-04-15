"""
UI server tests.

Verifies: server starts, static files serve, event bridge serializes
and fans out correctly. No browser or display needed.

Run with: python -m faust.tests.test_ui
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx

from faust.agent.events import Final, Thinking, ToolCallExecuted, ToolCallProposed
from faust.ui.bridge import EventBridge
from faust.ui.server import UIServer


PORT = 8091


async def test_static_files_served():
    bridge = EventBridge()
    server = UIServer(bridge, port=PORT)
    await server.start()
    try:
        async with httpx.AsyncClient() as client:
            # Index page.
            r = await client.get(f"http://localhost:{PORT}/")
            assert r.status_code == 200
            assert "faust" in r.text.lower() or "shell" in r.text
            print(f"  GET / → {r.status_code}, {len(r.text)} bytes")

            # CSS.
            r = await client.get(f"http://localhost:{PORT}/style.css")
            assert r.status_code == 200
            assert "--bg:" in r.text  # our primary background variable
            print(f"  GET /style.css → {r.status_code}")

            # JS.
            r = await client.get(f"http://localhost:{PORT}/app.js")
            assert r.status_code == 200
            assert "WebSocket" in r.text
            print(f"  GET /app.js → {r.status_code}")
    finally:
        await server.stop()
    print("✓ static files served")


async def test_bridge_serializes_events():
    bridge = EventBridge()
    q = bridge.subscribe()

    await bridge.push_event(Thinking(text="hello world"))
    msg = await q.get()
    assert msg["type"] == "thinking"
    assert msg["text"] == "hello world"

    await bridge.push_event(ToolCallProposed(
        call_id="c1", tool_name="wifi_scan",
        arguments={"interface": "wlan1mon"}, sensitivity="passive",
    ))
    msg = await q.get()
    assert msg["type"] == "tool_call_proposed"
    assert msg["tool_name"] == "wifi_scan"
    assert msg["sensitivity"] == "passive"

    await bridge.push_event(ToolCallExecuted(
        call_id="c1", tool_name="wifi_scan",
        result={"networks": []}, duration_ms=150,
    ))
    msg = await q.get()
    assert msg["type"] == "tool_call_executed"
    assert msg["duration_ms"] == 150

    await bridge.push_event(Final(reason="end_turn", text="done"))
    msg = await q.get()
    assert msg["type"] == "final"
    assert msg["reason"] == "end_turn"

    bridge.unsubscribe(q)
    print("✓ bridge serializes all event types")


async def test_bridge_fan_out():
    bridge = EventBridge()
    q1 = bridge.subscribe()
    q2 = bridge.subscribe()

    await bridge.push_event(Thinking(text="broadcast"))
    m1 = await q1.get()
    m2 = await q2.get()
    assert m1 == m2
    assert m1["text"] == "broadcast"

    bridge.unsubscribe(q1)
    bridge.unsubscribe(q2)
    print("✓ bridge fans out to multiple subscribers")


async def test_bridge_unsubscribe():
    bridge = EventBridge()
    q = bridge.subscribe()
    bridge.unsubscribe(q)

    # Should not raise — no subscribers.
    await bridge.push_event(Thinking(text="nobody home"))
    print("✓ bridge handles unsubscribe cleanly")


async def test_bridge_push_raw():
    bridge = EventBridge()
    q = bridge.subscribe()

    await bridge.push_raw({"type": "link_status", "state": "connected"})
    msg = await q.get()
    assert msg["type"] == "link_status"
    assert msg["state"] == "connected"

    bridge.unsubscribe(q)
    print("✓ bridge push_raw works")


async def main():
    await test_static_files_served()
    await test_bridge_serializes_events()
    await test_bridge_fan_out()
    await test_bridge_unsubscribe()
    await test_bridge_push_raw()
    print("\nall UI tests passed")


if __name__ == "__main__":
    asyncio.run(main())
