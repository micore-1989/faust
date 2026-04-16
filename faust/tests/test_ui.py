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

from faust.agent.events import (
    CatalogBuildStarted,
    Final,
    ParameterizingDone,
    ParameterizingStep,
    PlanningStarted,
    Thinking,
    ToolCallExecuted,
    ToolCallProposed,
)
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
            assert "--bg-primary" in r.text  # semantic bg alias (spec §4.1)
            assert "--accent-crimson" in r.text  # Goethe palette accent
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


async def test_bridge_maps_phase_marker_events():
    """Spec §2.4: phase-marker dataclasses get custom WS message shapes.
    CatalogBuildStarted + PlanningStarted → `planning_started`;
    ParameterizingStep → `parameterizing_step`;
    ParameterizingDone → suppressed (internal signal only)."""
    bridge = EventBridge()
    q = bridge.subscribe()

    # CatalogBuildStarted → planning_started {phase: catalog, skill_count}
    await bridge.push_event(CatalogBuildStarted(skill_count=12))
    msg = await q.get()
    assert msg == {
        "type": "planning_started",
        "phase": "catalog",
        "skill_count": 12,
    }

    # PlanningStarted(phase=plan) → planning_started {phase, attempt}
    await bridge.push_event(PlanningStarted(phase="plan"))
    msg = await q.get()
    assert msg == {"type": "planning_started", "phase": "plan", "attempt": 0}

    # PlanningStarted(phase=replan, attempt=2) → planning_started with attempt
    await bridge.push_event(PlanningStarted(phase="replan", attempt=2))
    msg = await q.get()
    assert msg == {"type": "planning_started", "phase": "replan", "attempt": 2}

    # ParameterizingStep → parameterizing_step
    await bridge.push_event(ParameterizingStep(
        step=2, of=5, skill="wifi_scan", intent="find APs",
    ))
    msg = await q.get()
    assert msg == {
        "type": "parameterizing_step",
        "step": 2,
        "of": 5,
        "skill": "wifi_scan",
        "intent": "find APs",
    }

    # ParameterizingDone → suppressed (queue stays empty).
    await bridge.push_event(ParameterizingDone(step=2, of=5))
    # Follow up with a known event to prove the queue is still live.
    await bridge.push_event(Final(reason="end_turn"))
    msg = await q.get()
    assert msg["type"] == "final", (
        f"ParameterizingDone leaked onto the wire as: {msg}"
    )

    bridge.unsubscribe(q)
    print("✓ bridge maps phase-marker events per spec §2.4")


async def test_bridge_push_raw():
    bridge = EventBridge()
    q = bridge.subscribe()

    await bridge.push_raw({"type": "link_status", "state": "connected"})
    msg = await q.get()
    assert msg["type"] == "link_status"
    assert msg["state"] == "connected"

    bridge.unsubscribe(q)
    print("✓ bridge push_raw works")


class _StubTrustCache:
    def __init__(self) -> None:
        self.invalidations = 0

    def invalidate(self) -> None:
        self.invalidations += 1


class _StubJournal:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def record(self, **kwargs) -> None:
        self.records.append(kwargs)


async def test_scope_change_updates_state():
    """scope_change with valid payload flips SimulatorState.scope."""
    bridge = EventBridge()
    server = UIServer(bridge, port=0)
    await server._handle_incoming({
        "type": "scope_change",
        "template": "recon",
        "description": None,
    })
    assert server.state.scope.template == "recon"
    assert server.state.scope.description is None
    print("✓ scope_change updates SimulatorState.scope")


async def test_scope_change_emits_state_message():
    """Clients see an updated `state` message carrying the new scope."""
    bridge = EventBridge()
    server = UIServer(bridge, port=0)
    q = bridge.subscribe()

    await server._handle_incoming({
        "type": "scope_change",
        "template": "pentesting",
        "description": "corp red-team 2026",
    })

    msg = await asyncio.wait_for(q.get(), timeout=1.0)
    assert msg["type"] == "state"
    assert msg["scope"] == {
        "template": "pentesting",
        "description": "corp red-team 2026",
    }
    bridge.unsubscribe(q)
    print("✓ scope_change broadcasts updated state")


async def test_scope_change_creates_journal_entry():
    """Journal sees a `scope.set` entry with previous + new scope."""
    bridge = EventBridge()
    server = UIServer(bridge, port=0)
    journal = _StubJournal()
    trust = _StubTrustCache()
    server.set_disclosure(trust_cache=trust, journal=journal)

    # Seed with an initial scope so the journal sees a non-null previous.
    server.state.set_scope("recon", None)

    await server._handle_incoming({
        "type": "scope_change",
        "template": "self-test",
        "description": None,
    })

    assert len(journal.records) == 1
    entry = journal.records[0]
    assert entry["tool_name"] == "scope.set"
    assert entry["decision"] == "auto"
    assert entry["arguments"]["previous"] == {
        "template": "recon", "description": None,
    }
    assert entry["arguments"]["new"] == {
        "template": "self-test", "description": None,
    }
    print("✓ scope_change journals prev+new as scope.set entry")


async def test_scope_change_invalidates_trust():
    """TrustCache.invalidate() fires on every scope_change."""
    bridge = EventBridge()
    server = UIServer(bridge, port=0)
    trust = _StubTrustCache()
    server.set_disclosure(trust_cache=trust)

    await server._handle_incoming({
        "type": "scope_change",
        "template": "recon",
        "description": None,
    })
    assert trust.invalidations == 1

    await server._handle_incoming({
        "type": "scope_change",
        "template": "pentesting",
        "description": "next engagement",
    })
    assert trust.invalidations == 2
    print("✓ scope_change invalidates TrustCache")


async def test_scope_change_rejects_pentesting_without_description():
    """Pentesting requires a non-empty description; server replies with
    error and leaves state/scope untouched."""
    bridge = EventBridge()
    server = UIServer(bridge, port=0)
    q = bridge.subscribe()
    trust = _StubTrustCache()
    journal = _StubJournal()
    server.set_disclosure(trust_cache=trust, journal=journal)

    # Missing description.
    await server._handle_incoming({
        "type": "scope_change",
        "template": "pentesting",
        "description": "",
    })
    msg = await asyncio.wait_for(q.get(), timeout=1.0)
    assert msg["type"] == "error"
    assert "pentesting" in msg["message"].lower()
    # Scope unchanged, cache not invalidated, no journal entry.
    assert server.state.scope.template is None
    assert trust.invalidations == 0
    assert journal.records == []

    # Whitespace-only description also rejected.
    await server._handle_incoming({
        "type": "scope_change",
        "template": "pentesting",
        "description": "   ",
    })
    msg = await asyncio.wait_for(q.get(), timeout=1.0)
    assert msg["type"] == "error"

    # Invalid template also rejected.
    await server._handle_incoming({
        "type": "scope_change",
        "template": "bogus",
        "description": None,
    })
    msg = await asyncio.wait_for(q.get(), timeout=1.0)
    assert msg["type"] == "error"
    assert "invalid scope" in msg["message"].lower()

    bridge.unsubscribe(q)
    print("✓ scope_change validates template + required description")


async def test_pursuit_start_message_spawns_background_task():
    """pursuit_start hands off to a background task so the runner can
    operate asynchronously without blocking the server's receive loop."""
    import aiohttp
    import json as _json
    import tempfile
    from pathlib import Path
    from faust.pursuits.models import Pursuit, ParamSpec, PursuitYield, PursuitResultPartial
    from faust.pursuits.registry import PURSUITS
    from faust.pursuits.storage import PursuitStorage

    PORT_LOCAL = PORT + 10
    bridge = EventBridge()
    server = UIServer(bridge, port=PORT_LOCAL)

    # Register a test pursuit that signals start + completion quickly.
    test_pursuit = Pursuit(
        id="_test_fast_pursuit",
        title="Fast Test Pursuit", description="quick", duration_hint="0",
        tools_used=[], parameters=[],
    )
    PURSUITS[test_pursuit.id] = test_pursuit

    async def fast_impl(params, dispatcher, stop_event):
        yield PursuitYield(progress=0.5, activity="halfway")
        yield PursuitYield(progress=1.0)
        yield PursuitResultPartial(summary="done")

    class _Disp:
        async def dispatch(self, tool, args):
            return {"executed": True}

    with tempfile.TemporaryDirectory() as tmp:
        storage = PursuitStorage(path=Path(tmp) / "p.jsonl")
        server.set_pursuits(
            dispatcher=_Disp(),
            storage=storage,
            implementations={test_pursuit.id: fast_impl},
        )

        await server.start()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"http://localhost:{PORT_LOCAL}/ws") as ws:
                    await asyncio.wait_for(ws.receive(), timeout=1.0)  # drain state
                    await ws.send_str(_json.dumps({
                        "type": "pursuit_start",
                        "pursuit_id": test_pursuit.id,
                        "params": {},
                    }))
                    # Drain messages until we see a pursuit_complete.
                    saw_complete = False
                    for _ in range(30):
                        raw = await asyncio.wait_for(ws.receive(), timeout=2.0)
                        if raw.type != aiohttp.WSMsgType.TEXT:
                            continue
                        msg = _json.loads(raw.data)
                        if msg.get("type") == "pursuit_complete":
                            saw_complete = True
                            break
                    assert saw_complete, "client should observe pursuit_complete"
        finally:
            await server.stop()
            PURSUITS.pop(test_pursuit.id, None)
    print("✓ pursuit_start spawns bg task; client sees pursuit_complete")


async def test_pursuit_start_background_task_does_not_block_receive_loop():
    """The Pursuits analog of the prompt deadlock guard: a long-running
    Pursuit must not block the receive loop from processing pursuit_stop."""
    import aiohttp
    import json as _json
    import tempfile
    from pathlib import Path
    from faust.pursuits.models import Pursuit, PursuitYield, PursuitResultPartial
    from faust.pursuits.registry import PURSUITS
    from faust.pursuits.storage import PursuitStorage

    PORT_LOCAL = PORT + 11
    bridge = EventBridge()
    server = UIServer(bridge, port=PORT_LOCAL)

    test_pursuit = Pursuit(
        id="_test_blocking_pursuit",
        title="Blocking Test Pursuit", description="long-running",
        duration_hint="∞", tools_used=[], parameters=[],
    )
    PURSUITS[test_pursuit.id] = test_pursuit

    stopped_cleanly = asyncio.Event()

    async def blocking_impl(params, dispatcher, stop_event):
        # Simulate a real Pursuit's loop: yield a progress tick then wait.
        yield PursuitYield(progress=0.1, activity="started, waiting")
        try:
            # Wait for stop — yield occasionally so the runner can check.
            for _ in range(100):
                await asyncio.sleep(0.02)
                yield PursuitYield(progress=0.2, activity="tick")
            yield PursuitResultPartial(summary="should not finish naturally")
        finally:
            stopped_cleanly.set()

    class _Disp:
        async def dispatch(self, tool, args):
            return {"executed": True}

    with tempfile.TemporaryDirectory() as tmp:
        storage = PursuitStorage(path=Path(tmp) / "p.jsonl")
        server.set_pursuits(
            dispatcher=_Disp(),
            storage=storage,
            implementations={test_pursuit.id: blocking_impl},
        )

        await server.start()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"http://localhost:{PORT_LOCAL}/ws") as ws:
                    await asyncio.wait_for(ws.receive(), timeout=1.0)  # drain state

                    await ws.send_str(_json.dumps({
                        "type": "pursuit_start",
                        "pursuit_id": test_pursuit.id,
                        "params": {},
                    }))
                    # Let the task get going.
                    await asyncio.sleep(0.1)

                    # THIS is the invariant under test: the receive loop
                    # must still process pursuit_stop while the bg task
                    # is running.
                    await ws.send_str(_json.dumps({
                        "type": "pursuit_stop",
                        "pursuit_id": test_pursuit.id,
                    }))

                    # The impl's finally-block runs when the runner aclose's
                    # the generator. If the receive loop were blocked, stop
                    # would never arrive and this event would never set.
                    await asyncio.wait_for(stopped_cleanly.wait(), timeout=3.0)
        finally:
            await server.stop()
            PURSUITS.pop(test_pursuit.id, None)
    print("✓ pursuit_start bg task does not block receive loop (stop delivered)")


async def test_pursuit_stop_signals_run():
    """pursuit_stop finds the active run and sets its stop_event."""
    from faust.pursuits.registry import PURSUITS
    from faust.pursuits.models import Pursuit
    from faust.ui.state import PursuitRunMeta, Power

    bridge = EventBridge()
    server = UIServer(bridge, port=0)
    server.state.power = Power.ON

    # Pretend there's an active run with a stop event.
    stop_ev = asyncio.Event()
    meta = PursuitRunMeta(
        run_id="run-abc",
        pursuit_id="wardrive",
        started_at=1.0,
        stop_event=stop_ev,
    )
    server.state.active_pursuits[meta.run_id] = meta

    await server._handle_incoming({
        "type": "pursuit_stop",
        "pursuit_id": "wardrive",
    })
    assert stop_ev.is_set()
    print("✓ pursuit_stop trips the matching run's stop_event")


async def test_pursuit_start_validates_params_against_pursuit_spec():
    """Invalid params (wrong enum, wrong type) surface as an error
    message and do NOT spawn a runner task."""
    bridge = EventBridge()
    server = UIServer(bridge, port=0)
    q = bridge.subscribe()

    class _Disp:
        async def dispatch(self, tool, args):
            raise AssertionError("should not be reached")

    server.set_pursuits(dispatcher=_Disp(), storage=None, implementations={})

    # Invalid enum value for wardrive.
    await server._handle_incoming({
        "type": "pursuit_start",
        "pursuit_id": "wardrive",
        "params": {"frequency_band": "bogus"},
    })
    msg = await asyncio.wait_for(q.get(), timeout=1.0)
    assert msg["type"] == "error"
    assert "invalid pursuit params" in msg["message"]
    assert server.state.active_pursuits == {}

    # Wrong type for int param.
    await server._handle_incoming({
        "type": "pursuit_start",
        "pursuit_id": "wardrive",
        "params": {"duration_minutes": "thirty"},
    })
    msg = await asyncio.wait_for(q.get(), timeout=1.0)
    assert msg["type"] == "error"
    assert server.state.active_pursuits == {}

    bridge.unsubscribe(q)
    print("✓ pursuit_start validates params before spawning runner")


async def test_pursuit_start_rejects_unknown_pursuit_id():
    """Unknown pursuit_id produces an error message and spawns nothing."""
    bridge = EventBridge()
    server = UIServer(bridge, port=0)
    q = bridge.subscribe()

    class _Disp:
        async def dispatch(self, tool, args):
            raise AssertionError("should not be reached")

    server.set_pursuits(dispatcher=_Disp(), storage=None, implementations={})

    await server._handle_incoming({
        "type": "pursuit_start",
        "pursuit_id": "totally-fake",
        "params": {},
    })
    msg = await asyncio.wait_for(q.get(), timeout=1.0)
    assert msg["type"] == "error"
    assert "unknown pursuit" in msg["message"]
    assert server.state.active_pursuits == {}

    bridge.unsubscribe(q)
    print("✓ pursuit_start rejects unknown pursuit_id")


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
    await test_bridge_maps_phase_marker_events()
    await test_bridge_push_raw()
    await test_scope_change_updates_state()
    await test_scope_change_emits_state_message()
    await test_scope_change_creates_journal_entry()
    await test_scope_change_invalidates_trust()
    await test_scope_change_rejects_pentesting_without_description()
    await test_pursuit_start_rejects_unknown_pursuit_id()
    await test_pursuit_start_validates_params_against_pursuit_spec()
    await test_pursuit_stop_signals_run()
    await test_pursuit_start_message_spawns_background_task()
    await test_pursuit_start_background_task_does_not_block_receive_loop()
    await test_prompt_handler_does_not_deadlock_on_approval()
    print("\nall UI tests passed")


if __name__ == "__main__":
    asyncio.run(main())
