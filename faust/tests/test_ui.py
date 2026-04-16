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
from faust.ui.state import Mephisto, Power


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


async def test_prompt_handler_does_not_deadlock_on_approval():
    """Regression: the WS receive loop must stay free while a prompt
    handler is awaiting plan_approval. Otherwise the approval message
    can never arrive and the agent blocks forever.

    Reproduces the Apr-2026 bug where _handle_incoming was awaited inline
    in the receive loop; prompt → wait_for_plan_approval → deadlock.
    """
    import json as _json

    bridge = EventBridge()
    server = UIServer(bridge, port=PORT + 1)

    handler_finished = asyncio.Event()
    got_approved: dict[str, Any] = {}

    async def prompt_handler(text: str) -> None:
        # Simulate what TwoPassAgent does: block on plan approval.
        resp = await server.wait_for_plan_approval()
        got_approved["value"] = bool(resp.get("approved"))
        handler_finished.set()

    server.set_handlers(prompt_handler=prompt_handler)
    # Skip the canned boot sequence — force booted state directly so the
    # server accepts prompts immediately.
    server.state.power = Power.ON
    server.state.mephisto = Mephisto.CONNECTED

    await server.start()

    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(f"http://localhost:{PORT + 1}/ws") as ws:
                # Drain the initial state push so it doesn't clog the test.
                await asyncio.wait_for(ws.receive(), timeout=1.0)

                # Fire the prompt — handler will block on plan_approval.
                await ws.send_str(_json.dumps({"type": "prompt", "text": "hi"}))
                await asyncio.sleep(0.05)  # let the receive loop dispatch it

                # Now send the approval. With the bug, this message never
                # reaches _handle_incoming because the receive loop was
                # blocked awaiting the prompt handler. With the fix, the
                # prompt handler runs as a background task and the receive
                # loop stays free to process this message.
                await ws.send_str(_json.dumps({
                    "type": "plan_approval",
                    "plan_id": "x",
                    "approved": True,
                }))

                # Handler should complete within a reasonable window.
                await asyncio.wait_for(handler_finished.wait(), timeout=3.0)
                assert got_approved.get("value") is True
    finally:
        await server.stop()

    print("✓ prompt handler does not deadlock when awaiting plan_approval")


async def main():
    await test_static_files_served()
    await test_bridge_serializes_events()
    await test_bridge_fan_out()
    await test_bridge_unsubscribe()
    await test_bridge_push_raw()
    await test_prompt_handler_does_not_deadlock_on_approval()
    print("\nall UI tests passed")


if __name__ == "__main__":
    asyncio.run(main())
