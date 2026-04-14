"""
Event stream bridge: agent loop → WebSocket clients.

The bridge is an async queue that sits between the agent loop's event stream
and any number of connected WebSocket clients. Events are serialized to JSON
and broadcast to all connected clients.

Design:
  - Agent loop yields Event dataclasses
  - Bridge converts them to JSON dicts and pushes to a broadcast queue
  - Each WebSocket handler reads from its own copy of the queue
  - The bridge also supports pushing status updates (link state, etc.)
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from typing import Any

from ..agent.events import Event


class EventBridge:
    """Fan-out bridge from a single event source to N WebSocket clients."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        """Create a new subscription queue. Each WebSocket handler calls this."""
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        """Remove a subscription queue when a client disconnects."""
        self._subscribers = [s for s in self._subscribers if s is not q]

    async def push_event(self, event: Event) -> None:
        """Convert an agent Event to JSON and broadcast to all subscribers."""
        data = _event_to_dict(event)
        for q in self._subscribers:
            await q.put(data)

    async def push_raw(self, data: dict[str, Any]) -> None:
        """Push an arbitrary JSON-serializable dict (status updates, etc.)."""
        for q in self._subscribers:
            await q.put(data)


def _event_to_dict(event: Event) -> dict[str, Any]:
    """Serialize an Event dataclass to a JSON-safe dict."""
    d = asdict(event)
    # asdict handles nested dataclasses. We just need to ensure
    # everything is JSON-serializable.
    return json.loads(json.dumps(d, default=str))
