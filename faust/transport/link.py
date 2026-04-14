"""
Faust↔Mephisto transport link.

Manages the USB-ethernet connection to Mephisto. Provides:
  - Health checking (is Mephisto's LLM endpoint reachable?)
  - Connection state tracking (connected / disconnected / degraded)
  - Periodic background health polling

The link does NOT own the LLM backend — it just reports connectivity so
the agent loop and UI can make informed decisions (show connection status,
fall back to local CPU or cloud, etc.).

Network topology (captive USB-ethernet, /30 point-to-point):
  Faust  (host)     10.66.0.1
  Mephisto (gadget)  10.66.0.2   → hailo-ollama at :8000/v1
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx


# Default Mephisto endpoint on the captive USB-ethernet link.
MEPHISTO_ENDPOINT = "http://10.66.0.2:8000/v1"


class LinkState(Enum):
    """Connection state for the Faust→Mephisto link."""
    UNKNOWN = "unknown"          # Haven't checked yet.
    CONNECTED = "connected"      # Mephisto responding, model loaded.
    REACHABLE = "reachable"      # HTTP reachable but /v1/models failed or empty.
    DISCONNECTED = "disconnected"  # Not reachable at all.


@dataclass
class LinkStatus:
    """Snapshot of the current link state."""
    state: LinkState
    endpoint: str
    model: str | None = None       # Model name if connected.
    latency_ms: int = 0            # Round-trip to health endpoint.
    last_check: float = 0.0        # time.time() of last check.
    error: str | None = None       # Last error message if not connected.


class MephistoLink:
    """Manages connectivity to Mephisto's LLM endpoint.

    Usage:
        link = MephistoLink()
        status = await link.check()
        if status.state == LinkState.CONNECTED:
            # safe to send inference requests
            ...

        # Or run background polling:
        link.start_polling(interval_s=5)
        ...
        link.stop_polling()
    """

    def __init__(
        self,
        endpoint: str = MEPHISTO_ENDPOINT,
        timeout_s: float = 3.0,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self._timeout = timeout_s
        self._client = httpx.AsyncClient(timeout=self._timeout)
        self._status = LinkStatus(
            state=LinkState.UNKNOWN,
            endpoint=self.endpoint,
        )
        self._poll_task: asyncio.Task[None] | None = None

    @property
    def status(self) -> LinkStatus:
        """Current link status (last known). Call check() for a fresh probe."""
        return self._status

    async def check(self) -> LinkStatus:
        """Probe Mephisto's health. Returns updated LinkStatus.

        Hits GET /v1/models — this is the lightest OpenAI-compatible endpoint
        and confirms both HTTP connectivity and that hailo-ollama is serving.
        """
        start = time.monotonic()
        try:
            resp = await self._client.get(f"{self.endpoint}/models")
            latency_ms = int((time.monotonic() - start) * 1000)

            if resp.status_code != 200:
                self._status = LinkStatus(
                    state=LinkState.REACHABLE,
                    endpoint=self.endpoint,
                    latency_ms=latency_ms,
                    last_check=time.time(),
                    error=f"HTTP {resp.status_code}",
                )
                return self._status

            data = resp.json()
            models = data.get("data", [])
            model_name = models[0]["id"] if models else None

            self._status = LinkStatus(
                state=LinkState.CONNECTED if model_name else LinkState.REACHABLE,
                endpoint=self.endpoint,
                model=model_name,
                latency_ms=latency_ms,
                last_check=time.time(),
            )

        except (httpx.ConnectError, httpx.ConnectTimeout):
            self._status = LinkStatus(
                state=LinkState.DISCONNECTED,
                endpoint=self.endpoint,
                latency_ms=int((time.monotonic() - start) * 1000),
                last_check=time.time(),
                error="connection refused or timed out",
            )
        except Exception as e:
            self._status = LinkStatus(
                state=LinkState.DISCONNECTED,
                endpoint=self.endpoint,
                latency_ms=int((time.monotonic() - start) * 1000),
                last_check=time.time(),
                error=f"{type(e).__name__}: {e}",
            )

        return self._status

    def start_polling(self, interval_s: float = 5.0) -> None:
        """Start background health polling. Non-blocking."""
        if self._poll_task is not None:
            return  # Already polling.

        async def _poll_loop() -> None:
            while True:
                await self.check()
                await asyncio.sleep(interval_s)

        self._poll_task = asyncio.create_task(_poll_loop())

    def stop_polling(self) -> None:
        """Stop background health polling."""
        if self._poll_task is not None:
            self._poll_task.cancel()
            self._poll_task = None

    async def aclose(self) -> None:
        """Shut down the link (cancel polling, close HTTP client)."""
        self.stop_polling()
        await self._client.aclose()
