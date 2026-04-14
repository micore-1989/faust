"""
UI web server.

Serves the three-zone touchscreen UI as static HTML/CSS/JS and bridges
agent events to the browser via WebSocket.

Architecture:
  - aiohttp serves static files from faust/ui/static/
  - WebSocket at /ws streams JSON events to connected clients
  - The EventBridge fans out events from the agent loop to all clients
  - Touch confirmation responses come back over the same WebSocket

Usage:
    bridge = EventBridge()
    server = UIServer(bridge, host="0.0.0.0", port=8080)
    await server.start()
    # ... agent loop pushes events to bridge ...
    await server.stop()
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from aiohttp import web

from .bridge import EventBridge


STATIC_DIR = Path(__file__).parent / "static"


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
        self._app = web.Application()
        self._runner: web.AppRunner | None = None
        self._confirmation_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._plan_approval_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._prompt_queue: asyncio.Queue[str] = asyncio.Queue()

        # Routes.
        self._app.router.add_get("/ws", self._ws_handler)
        self._app.router.add_get("/", self._index_handler)
        self._app.router.add_static("/", STATIC_DIR, show_index=False)

    async def _index_handler(self, request: web.Request) -> web.FileResponse:
        return web.FileResponse(STATIC_DIR / "index.html")

    async def start(self) -> None:
        """Start the server (non-blocking — runs in the background)."""
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()

    async def stop(self) -> None:
        """Shut down the server."""
        if self._runner is not None:
            await self._runner.cleanup()

    async def wait_for_confirmation(self) -> dict[str, Any]:
        """Block until the UI sends a confirmation response.

        Returns a dict like:
          {"type": "confirmation", "call_id": "c1", "approved": true}
        """
        return await self._confirmation_queue.get()

    async def wait_for_prompt(self) -> str:
        """Block until the UI sends a user prompt."""
        return await self._prompt_queue.get()

    async def wait_for_plan_approval(self) -> dict[str, Any]:
        """Block until the UI sends a plan approval response.

        Returns:
          {"type": "plan_approval", "plan_id": "plan-abc", "approved": true}
        """
        return await self._plan_approval_queue.get()

    async def _ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        """WebSocket handler: streams events to client, receives confirmations."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        q = self.bridge.subscribe()
        send_task: asyncio.Task | None = None

        try:
            # Task that forwards events from the bridge to this WebSocket.
            async def _send_loop() -> None:
                while True:
                    data = await q.get()
                    await ws.send_json(data)

            send_task = asyncio.create_task(_send_loop())

            # Read loop: client sends prompts and confirmation responses.
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    try:
                        payload = json.loads(msg.data)
                        mtype = payload.get("type")
                        if mtype == "confirmation":
                            await self._confirmation_queue.put(payload)
                        elif mtype == "plan_approval":
                            await self._plan_approval_queue.put(payload)
                        elif mtype == "prompt":
                            text = payload.get("text", "").strip()
                            if text:
                                await self._prompt_queue.put(text)
                    except json.JSONDecodeError:
                        pass
                elif msg.type == web.WSMsgType.ERROR:
                    break
        finally:
            if send_task is not None:
                send_task.cancel()
            self.bridge.unsubscribe(q)

        return ws
