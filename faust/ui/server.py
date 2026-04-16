"""
UI web server.

Serves the three-zone Faust shell as static HTML/CSS/JS and bridges agent
events to the browser via WebSocket. Holds the authoritative simulator
state (power/mephisto) so reconnecting clients render correctly.

Architecture:
  - aiohttp serves static files from faust/ui/static/
  - WebSocket at /ws streams JSON events AND state transitions
  - EventBridge fans out agent events to all WebSocket clients
  - Server-side state machine (state.SimulatorState) controls boot flow
  - Direct skill dispatch bypasses the agent and hits the Dispatcher directly

Message types from client:
  {"type": "power",       "action": "on"|"off"}
  {"type": "mephisto",    "action": "connect"|"disconnect"}
  {"type": "prompt",      "text": "..."}                     (requires FAUST_MEPHISTO)
  {"type": "dispatch",    "skill": "...", "args": {...}}     (requires booted)
  {"type": "confirmation","call_id": "...", "approved": true}
  {"type": "plan_approval","plan_id": "...", "approved": true}

Message types to client (beyond agent events):
  {"type": "state",       "power": "...", "mephisto": "..."}
  {"type": "boot_log",    "line": "..."}
  {"type": "skills",      "skills": [{name, description, category, ...}]}
  {"type": "error",       "message": "..."}
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from aiohttp import web

from ..pursuits.registry import apply_defaults, get_pursuit, validate_params
from ..pursuits.runner import run_pursuit
from .bridge import EventBridge
from .state import (
    BOOT_DURATION_MS,
    BOOT_LOG,
    Mephisto,
    Power,
    PursuitRunMeta,
    SimulatorState,
)


STATIC_DIR = Path(__file__).parent / "static"


# Callbacks installed by the runner so the server can trigger agent work.
PromptHandler = Callable[[str], Any]          # -> awaitable; accepts user prompt
DispatchHandler = Callable[[str, dict], Any]  # -> awaitable; accepts (skill, args)
StateHandler = Callable[[SimulatorState], Any]  # -> awaitable; reacts to state change


class UIServer:
    """Async web server for the Faust touchscreen UI."""

    def __init__(
        self,
        bridge: EventBridge,
        host: str = "0.0.0.0",
        port: int = 8080,
    ) -> None:
        self.bridge = bridge
        self.host = host
        self.port = port
        self.state = SimulatorState()
        self.skills_catalog: list[dict[str, Any]] = []  # set by runner

        self._app = web.Application()
        self._runner: web.AppRunner | None = None
        self._confirmation_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._plan_approval_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._prompt_handler: PromptHandler | None = None
        self._dispatch_handler: DispatchHandler | None = None
        self._state_handler: StateHandler | None = None
        # Wired by run.py so the scope_change handler can invalidate trust
        # and journal the transition. Both optional for dev/test setups.
        self._trust_cache: Any = None
        self._journal: Any = None
        # Wired by run.py for pursuit_start handling. Dispatcher runs inside
        # the Pursuit implementation; storage records the terminal result.
        self._dispatcher: Any = None
        self._pursuit_storage: Any = None
        self._pursuit_implementations: dict[str, Any] | None = None
        self._boot_task: asyncio.Task | None = None
        # Long-running handlers (prompt, dispatch) must not block the WS
        # receive loop — otherwise plan_approval / confirmation messages
        # can never arrive and the agent deadlocks on its own approval
        # gate. We track fire-and-forget tasks here so we can log their
        # exceptions and cancel them on shutdown.
        self._background_tasks: set[asyncio.Task] = set()

        # Routes.
        self._app.router.add_get("/ws", self._ws_handler)
        self._app.router.add_get("/", self._index_handler)
        self._app.router.add_static("/", STATIC_DIR, show_index=False)

    async def _index_handler(self, request: web.Request) -> web.FileResponse:
        return web.FileResponse(STATIC_DIR / "index.html")

    # ── Lifecycle ──────────────────────────────────────────────────

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()

    async def stop(self) -> None:
        if self._boot_task is not None:
            self._boot_task.cancel()
        for task in list(self._background_tasks):
            task.cancel()
        if self._runner is not None:
            await self._runner.cleanup()

    # ── Handlers for the runner to install ─────────────────────────

    def set_handlers(
        self,
        prompt_handler: PromptHandler | None = None,
        dispatch_handler: DispatchHandler | None = None,
        state_handler: StateHandler | None = None,
    ) -> None:
        if prompt_handler is not None:
            self._prompt_handler = prompt_handler
        if dispatch_handler is not None:
            self._dispatch_handler = dispatch_handler
        if state_handler is not None:
            self._state_handler = state_handler

    def set_disclosure(
        self,
        trust_cache: Any = None,
        journal: Any = None,
    ) -> None:
        """Install the server-side disclosure dependencies needed by the
        scope_change handler. Safe to call with either / both as None in
        dev/test environments."""
        self._trust_cache = trust_cache
        self._journal = journal

    def set_pursuits(
        self,
        dispatcher: Any = None,
        storage: Any = None,
        implementations: dict[str, Any] | None = None,
    ) -> None:
        """Install the server-side pursuit dependencies needed by the
        pursuit_start handler. Tests inject a fake dispatcher + stub
        storage + their own implementations dict; production wiring in
        run.py passes the real dispatcher and PursuitStorage."""
        self._dispatcher = dispatcher
        self._pursuit_storage = storage
        self._pursuit_implementations = implementations

    def set_skills_catalog(self, skills: list[dict[str, Any]]) -> None:
        """Installed by the runner after loading skills. Sent to clients
        once state reaches FAUST_ONLY so the grid can render."""
        self.skills_catalog = skills

    # ── Queue accessors ────────────────────────────────────────────

    async def wait_for_confirmation(self) -> dict[str, Any]:
        return await self._confirmation_queue.get()

    async def wait_for_plan_approval(self) -> dict[str, Any]:
        return await self._plan_approval_queue.get()

    # ── State mutations ────────────────────────────────────────────

    async def _broadcast_state(self) -> None:
        """Push current state to all subscribed clients."""
        await self.bridge.push_raw(self.state.to_dict())
        if self._state_handler is not None:
            maybe = self._state_handler(self.state)
            if hasattr(maybe, "__await__"):
                await maybe  # type: ignore[misc]

    async def _power_on(self) -> None:
        if self.state.power != Power.OFF:
            return
        self.state.power = Power.BOOTING
        self.state.boot_progress = 0
        await self._broadcast_state()

        async def _boot_sequence():
            try:
                speed = 0.85  # slightly faster than real-time for UX snappiness
                prev_t = 0
                for t_ms, line in BOOT_LOG:
                    # Sleep by the DELTA, not the absolute time.
                    delta_s = max(0, t_ms - prev_t) / 1000 * speed
                    prev_t = t_ms
                    await asyncio.sleep(delta_s)
                    await self.bridge.push_raw({"type": "boot_log", "line": line})
                    self.state.boot_progress = int(100 * t_ms / BOOT_DURATION_MS)
                await asyncio.sleep(0.3)
                self.state.power = Power.ON
                self.state.boot_progress = 100
                await self._broadcast_state()
                # Also push the skills catalog so the UI can render the grid.
                if self.skills_catalog:
                    await self.bridge.push_raw({
                        "type": "skills",
                        "skills": self.skills_catalog,
                    })
            except asyncio.CancelledError:
                pass

        self._boot_task = asyncio.create_task(_boot_sequence())

    async def _power_off(self) -> None:
        if self._boot_task is not None and not self._boot_task.done():
            self._boot_task.cancel()
        self.state.power = Power.OFF
        self.state.mephisto = Mephisto.DISCONNECTED
        self.state.boot_progress = 0
        # Re-arm the first-dock ceremony for the next boot.
        self.state.first_dock_this_boot = True
        await self._broadcast_state()

    async def _mephisto_connect(self) -> None:
        if self.state.power != Power.ON:
            return
        self.state.mephisto = Mephisto.CONNECTED
        # The ceremony must fire exactly once per boot (§10.13): broadcast
        # the state with first_dock_this_boot=True, then immediately clear
        # the flag so subsequent reconnects in the same boot are silent.
        was_first = self.state.first_dock_this_boot
        await self._broadcast_state()
        if was_first:
            self.state.first_dock_this_boot = False

    async def _mephisto_disconnect(self) -> None:
        self.state.mephisto = Mephisto.DISCONNECTED
        await self._broadcast_state()

    # ── Scope management ──────────────────────────────────────────

    _VALID_SCOPE_TEMPLATES = {None, "recon", "self-test", "pentesting"}

    async def _handle_scope_change(self, payload: dict[str, Any]) -> None:
        """Validate + apply a scope change. Invalidates TrustCache and
        journals the transition so auditors see when scope flipped (spec
        §10.10)."""
        template = payload.get("template")
        description = payload.get("description")

        if template not in self._VALID_SCOPE_TEMPLATES:
            await self.bridge.push_raw({
                "type": "error",
                "message": f"invalid scope template: {template!r}",
            })
            return
        if template == "pentesting" and not (description or "").strip():
            await self.bridge.push_raw({
                "type": "error",
                "message": "pentesting scope requires a non-empty description",
            })
            return

        previous = self.state.set_scope(template, description)

        if self._trust_cache is not None:
            self._trust_cache.invalidate()

        if self._journal is not None:
            self._journal.record(
                tool_name="scope.set",
                arguments={
                    "previous": previous,
                    "new": {"template": template, "description": description},
                },
                sensitivity="passive",
                decision="auto",
            )

        await self._broadcast_state()

    # ── Pursuit management ────────────────────────────────────────

    async def _handle_pursuit_start(self, payload: dict[str, Any]) -> None:
        """Validate a pursuit_start payload and spawn the Pursuit runner as
        a background task.

        The task is backgrounded at the receive-loop level (same pattern as
        prompt/dispatch) so the loop stays free to process pursuit_stop and
        confirmation messages while the Pursuit is running — otherwise the
        stop message could never arrive. Guarded by
        test_pursuit_start_background_task_does_not_block_receive_loop.
        """
        pursuit_id = payload.get("pursuit_id", "")
        raw_params = payload.get("params", {}) or {}

        try:
            pursuit = get_pursuit(pursuit_id)
        except KeyError:
            await self.bridge.push_raw({
                "type": "error",
                "message": f"unknown pursuit: {pursuit_id!r}",
            })
            return

        errors = validate_params(pursuit, raw_params)
        if errors:
            await self.bridge.push_raw({
                "type": "error",
                "message": "invalid pursuit params: " + "; ".join(errors),
            })
            return

        if self._dispatcher is None:
            await self.bridge.push_raw({
                "type": "error",
                "message": "pursuit subsystem not wired on this server",
            })
            return

        merged = apply_defaults(pursuit, raw_params)
        run_id = uuid.uuid4().hex
        stop_event = asyncio.Event()

        meta = PursuitRunMeta(
            run_id=run_id,
            pursuit_id=pursuit_id,
            started_at=time.time(),
            stop_event=stop_event,
        )
        self.state.active_pursuits[run_id] = meta

        async def _runner_coro() -> None:
            try:
                await run_pursuit(
                    pursuit,
                    merged,
                    self._dispatcher,
                    self.bridge,
                    stop_event,
                    run_id=run_id,
                    implementations=self._pursuit_implementations,
                    journal=self._journal,
                    storage=self._pursuit_storage,
                )
            finally:
                # Pruning the active-pursuit entry happens here rather than
                # in a task.add_done_callback so the state is consistent
                # *before* the task reports done.
                self.state.active_pursuits.pop(run_id, None)

        meta.task = self._spawn_background(_runner_coro())
        await self._broadcast_state()

    async def _handle_pursuit_stop(self, payload: dict[str, Any]) -> None:
        """Find the active run by pursuit_id (or run_id) and signal its
        stop_event. If no match, reply with an error."""
        pursuit_id = payload.get("pursuit_id")
        run_id = payload.get("run_id")

        target: PursuitRunMeta | None = None
        if run_id:
            target = self.state.active_pursuits.get(run_id)
        if target is None and pursuit_id:
            # Stop the newest run of that pursuit_id.
            for meta in reversed(list(self.state.active_pursuits.values())):
                if meta.pursuit_id == pursuit_id:
                    target = meta
                    break

        if target is None or target.stop_event is None:
            await self.bridge.push_raw({
                "type": "error",
                "message": f"no active pursuit to stop: {pursuit_id or run_id!r}",
            })
            return

        target.stop_event.set()

    # ── WebSocket handler ──────────────────────────────────────────

    async def _ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        q = self.bridge.subscribe()
        send_task: asyncio.Task | None = None

        try:
            # Push current state + skills on connect (so a refresh "resumes").
            # The skills send is unconditional when powered on, even if the
            # catalog is empty: an empty list is still a deterministic answer
            # the client can act on (render zero tiles) rather than stalling
            # on "no message arrived yet." The earlier `and self.skills_catalog`
            # guard caused demo mode and the startup-race window to silently
            # skip this send, leaving the dashboard permanently empty.
            await ws.send_json(self.state.to_dict())
            if self.state.power == Power.ON:
                await ws.send_json({"type": "skills", "skills": self.skills_catalog})

            async def _send_loop() -> None:
                while True:
                    data = await q.get()
                    await ws.send_json(data)

            send_task = asyncio.create_task(_send_loop())

            async for msg in ws:
                if msg.type != web.WSMsgType.TEXT:
                    if msg.type == web.WSMsgType.ERROR:
                        break
                    continue
                try:
                    payload = json.loads(msg.data)
                except json.JSONDecodeError:
                    continue

                # prompt + dispatch may block on approval/confirmation gates
                # that are themselves serviced by this same receive loop —
                # dispatch them as background tasks to avoid deadlock. Fast
                # message types (power, mephisto, confirmation, plan_approval)
                # keep inline ordering.
                if payload.get("type") in ("prompt", "dispatch", "pursuit_start"):
                    self._spawn_background(self._handle_incoming(payload))
                else:
                    await self._handle_incoming(payload)
        finally:
            if send_task is not None:
                send_task.cancel()
            self.bridge.unsubscribe(q)

        return ws

    def _spawn_background(self, coro) -> asyncio.Task:
        """Run a handler concurrently with the WS receive loop.

        Tracks the task so stop() can cancel it, and logs any unhandled
        exception so fire-and-forget doesn't swallow errors silently.
        """
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)

        def _done(t: asyncio.Task) -> None:
            self._background_tasks.discard(t)
            if t.cancelled():
                return
            exc = t.exception()
            if exc is not None:
                # Surface to stdout — ui/run.py foregrounds the server.
                import traceback
                print(f"  [ws-bg] handler crashed: {type(exc).__name__}: {exc}")
                traceback.print_exception(type(exc), exc, exc.__traceback__)

        task.add_done_callback(_done)
        return task

    async def _handle_incoming(self, payload: dict[str, Any]) -> None:
        mtype = payload.get("type")

        if mtype == "power":
            action = payload.get("action")
            if action == "on":
                await self._power_on()
            elif action == "off":
                await self._power_off()

        elif mtype == "mephisto":
            action = payload.get("action")
            if action == "connect":
                await self._mephisto_connect()
            elif action == "disconnect":
                await self._mephisto_disconnect()

        elif mtype == "scope_change":
            await self._handle_scope_change(payload)

        elif mtype == "pursuit_start":
            await self._handle_pursuit_start(payload)

        elif mtype == "pursuit_stop":
            await self._handle_pursuit_stop(payload)

        elif mtype == "confirmation":
            await self._confirmation_queue.put(payload)

        elif mtype == "plan_approval":
            await self._plan_approval_queue.put(payload)

        elif mtype == "prompt":
            if not self.state.can_accept_prompt():
                await self.bridge.push_raw({
                    "type": "error",
                    "message": "Mephisto not docked — AI agent unavailable. "
                               "Connect Mephisto or use the skill grid.",
                })
                return
            text = payload.get("text", "").strip()
            if not text or self._prompt_handler is None:
                return
            maybe = self._prompt_handler(text)
            if hasattr(maybe, "__await__"):
                await maybe  # type: ignore[misc]

        elif mtype == "dispatch":
            if not self.state.can_accept_dispatch():
                await self.bridge.push_raw({
                    "type": "error",
                    "message": "unit is off — press power to boot",
                })
                return
            skill = payload.get("skill", "")
            args = payload.get("args", {}) or {}
            if not skill or self._dispatch_handler is None:
                return
            maybe = self._dispatch_handler(skill, args)
            if hasattr(maybe, "__await__"):
                await maybe  # type: ignore[misc]
