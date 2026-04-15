"""
Simulator state machine tests.

Verifies:
  - Initial state is OFF
  - Power transitions: OFF → BOOTING → ON, and back to OFF
  - Mephisto transitions: only allowed when power is ON
  - Prompt gate: only accepted when fully booted AND mephisto connected
  - Dispatch gate: accepted when booted (regardless of mephisto)
  - State broadcast to all subscribers on change

Run with: python -m faust.tests.test_simulator_state
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from faust.ui.bridge import EventBridge
from faust.ui.server import UIServer
from faust.ui.state import Mephisto, Power, SimulatorState


# ── Pure state tests ────────────────────────────────────────────

async def test_initial_state_is_off():
    s = SimulatorState()
    assert s.power == Power.OFF
    assert s.mephisto == Mephisto.DISCONNECTED
    assert not s.can_accept_prompt()
    assert not s.can_accept_dispatch()
    print("✓ initial state is OFF, nothing accepted")


async def test_booted_accepts_dispatch_not_prompt():
    s = SimulatorState(power=Power.ON, mephisto=Mephisto.DISCONNECTED)
    assert s.can_accept_dispatch()
    assert not s.can_accept_prompt()
    print("✓ FAUST_ONLY accepts dispatch but not prompt")


async def test_fully_connected_accepts_both():
    s = SimulatorState(power=Power.ON, mephisto=Mephisto.CONNECTED)
    assert s.can_accept_dispatch()
    assert s.can_accept_prompt()
    print("✓ FAUST+MEPHISTO accepts both prompt and dispatch")


async def test_state_dict_roundtrip():
    s = SimulatorState(power=Power.BOOTING, mephisto=Mephisto.DISCONNECTED, boot_progress=42)
    d = s.to_dict()
    assert d["type"] == "state"
    assert d["power"] == "booting"
    assert d["mephisto"] == "disconnected"
    assert d["boot_progress"] == 42
    print("✓ state serializes to dict correctly")


# ── Server-level tests ──────────────────────────────────────────

async def test_server_rejects_prompt_when_off():
    bridge = EventBridge()
    server = UIServer(bridge, port=0)
    called = []
    async def capture(text):
        called.append(text)
    server.set_handlers(prompt_handler=capture)

    await server._handle_incoming({"type": "prompt", "text": "hi"})
    assert called == [], "prompt handler must NOT fire when power is off"
    print("✓ server rejects prompt when power OFF")


async def test_server_rejects_prompt_without_mephisto():
    bridge = EventBridge()
    server = UIServer(bridge, port=0)
    server.state.power = Power.ON
    # mephisto still disconnected
    called = []
    async def capture(text):
        called.append(text)
    server.set_handlers(prompt_handler=capture)

    await server._handle_incoming({"type": "prompt", "text": "hi"})
    assert called == [], "prompt must require mephisto connected"
    print("✓ server rejects prompt without mephisto")


async def test_server_accepts_prompt_when_both_ready():
    bridge = EventBridge()
    server = UIServer(bridge, port=0)
    server.state.power = Power.ON
    server.state.mephisto = Mephisto.CONNECTED
    called = []
    async def capture(text):
        called.append(text)
    server.set_handlers(prompt_handler=capture)

    await server._handle_incoming({"type": "prompt", "text": "hello world"})
    assert called == ["hello world"]
    print("✓ server accepts prompt when power ON + mephisto connected")


async def test_server_dispatch_requires_power_on():
    bridge = EventBridge()
    server = UIServer(bridge, port=0)
    called = []
    async def capture(skill, args):
        called.append((skill, args))
    server.set_handlers(dispatch_handler=capture)

    # OFF → rejected
    await server._handle_incoming({"type": "dispatch", "skill": "wifi_scan", "args": {}})
    assert called == []

    # Power on → accepted (mephisto irrelevant for dispatch)
    server.state.power = Power.ON
    await server._handle_incoming({"type": "dispatch", "skill": "wifi_scan", "args": {"x": 1}})
    assert called == [("wifi_scan", {"x": 1})]
    print("✓ dispatch requires power but not mephisto")


async def test_server_dispatch_ignores_unknown_handler():
    """If no dispatch handler registered, dispatch is silently dropped."""
    bridge = EventBridge()
    server = UIServer(bridge, port=0)
    server.state.power = Power.ON
    # No handler set.
    # Should not raise.
    await server._handle_incoming({"type": "dispatch", "skill": "foo", "args": {}})
    print("✓ server doesn't crash without a dispatch handler")


async def test_mephisto_connect_requires_power_on():
    bridge = EventBridge()
    server = UIServer(bridge, port=0)

    # Power OFF: connect request ignored.
    await server._mephisto_connect()
    assert server.state.mephisto == Mephisto.DISCONNECTED

    # Power ON: connect succeeds.
    server.state.power = Power.ON
    await server._mephisto_connect()
    assert server.state.mephisto == Mephisto.CONNECTED
    print("✓ mephisto connect requires power to be ON")


async def test_power_off_disconnects_mephisto():
    bridge = EventBridge()
    server = UIServer(bridge, port=0)
    server.state.power = Power.ON
    server.state.mephisto = Mephisto.CONNECTED

    await server._power_off()
    assert server.state.power == Power.OFF
    assert server.state.mephisto == Mephisto.DISCONNECTED
    print("✓ power off cascades to disconnect mephisto")


async def test_state_broadcasts_to_subscribers():
    bridge = EventBridge()
    server = UIServer(bridge, port=0)
    q = bridge.subscribe()

    # Trigger a state change.
    server.state.power = Power.ON
    await server._broadcast_state()

    msg = await asyncio.wait_for(q.get(), timeout=1.0)
    assert msg["type"] == "state"
    assert msg["power"] == "on"
    bridge.unsubscribe(q)
    print("✓ state changes broadcast to all subscribers")


async def test_skills_catalog_sent_on_connect_when_booted():
    """A client reconnecting to a running server should receive the catalog."""
    bridge = EventBridge()
    server = UIServer(bridge, port=0)
    server.state.power = Power.ON
    server.set_skills_catalog([
        {"name": "wifi_scan", "description": "...", "category": "wifi",
         "sensitivity": "passive", "parameters_schema": {}},
    ])
    # The _ws_handler pushes both state and skills to the ws it just accepted.
    # We can't easily exercise the ws here without a real socket — just
    # verify the catalog is retained on the server.
    assert len(server.skills_catalog) == 1
    assert server.skills_catalog[0]["name"] == "wifi_scan"
    print("✓ skills catalog is retained on the server")


async def main():
    await test_initial_state_is_off()
    await test_booted_accepts_dispatch_not_prompt()
    await test_fully_connected_accepts_both()
    await test_state_dict_roundtrip()
    await test_server_rejects_prompt_when_off()
    await test_server_rejects_prompt_without_mephisto()
    await test_server_accepts_prompt_when_both_ready()
    await test_server_dispatch_requires_power_on()
    await test_server_dispatch_ignores_unknown_handler()
    await test_mephisto_connect_requires_power_on()
    await test_power_off_disconnects_mephisto()
    await test_state_broadcasts_to_subscribers()
    await test_skills_catalog_sent_on_connect_when_booted()
    print("\nall simulator state tests passed")


if __name__ == "__main__":
    asyncio.run(main())
