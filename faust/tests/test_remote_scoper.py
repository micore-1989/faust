"""
RemoteEmbeddingScoper tests.

Verifies the client side of the Faust→Mephisto scoper RPC:
  - Happy path: returns the server's skill list, filtered to known names
  - Falls back gracefully on connection error / HTTP error / bad JSON
  - make_scoper factory picks Remote when endpoint is set

Uses aiohttp for a real in-process server — more realistic than mocking
the HTTP client and catches wire-format issues.

Run with: python -m faust.tests.test_remote_scoper
"""

from __future__ import annotations

import asyncio
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from aiohttp import web

from faust.agent.config import AgentConfig
from faust.skills.scoper import (
    NoopScoper,
    RemoteEmbeddingScoper,
    SkillScoper,
    make_scoper,
)


# ── Test server harness ────────────────────────────────────────

class FakeScoperServer:
    """Minimal aiohttp server for testing the client."""

    def __init__(self, response_skills: list[str] | None = None,
                 status: int = 200, bad_json: bool = False) -> None:
        self.response_skills = response_skills if response_skills is not None else []
        self.status = status
        self.bad_json = bad_json
        self.requests: list[dict] = []
        self.runner: web.AppRunner | None = None
        self.port: int = 0

    async def _handle(self, request: web.Request) -> web.Response:
        body = await request.json()
        self.requests.append(body)
        if self.bad_json:
            return web.Response(
                body=b"not json!",
                status=self.status,
                content_type="application/json",
            )
        return web.json_response(
            {"skills": self.response_skills},
            status=self.status,
        )

    async def start(self, port: int = 0) -> None:
        app = web.Application()
        app.router.add_post("/v1/scope", self._handle)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", port)
        await site.start()
        # Grab the actual port if 0 was requested.
        for s in self.runner.sites:
            self.port = s._server.sockets[0].getsockname()[1]
            break

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()


# ── Tests ───────────────────────────────────────────────────────

async def test_remote_scoper_happy_path():
    server = FakeScoperServer(response_skills=["wifi_scan", "wifi_deauth"])
    await server.start()

    try:
        scoper = RemoteEmbeddingScoper(
            endpoint=f"http://127.0.0.1:{server.port}/v1",
            skill_names=["wifi_scan", "wifi_deauth", "ble_scan", "nfc_read"],
        )
        result = await scoper.top_k("scan the wifi please", k=3)
        assert result == ["wifi_scan", "wifi_deauth"]
        assert len(server.requests) == 1
        assert server.requests[0]["query"] == "scan the wifi please"
        assert server.requests[0]["k"] == 3
    finally:
        await server.stop()
    print("✓ remote scoper happy path")


async def test_remote_scoper_filters_unknown_names():
    """If the server returns skill names Faust doesn't know about,
    they should be filtered out (shouldn't happen in practice, but
    defensive)."""
    server = FakeScoperServer(response_skills=["wifi_scan", "hallucinated_tool"])
    await server.start()

    try:
        scoper = RemoteEmbeddingScoper(
            endpoint=f"http://127.0.0.1:{server.port}/v1",
            skill_names=["wifi_scan", "ble_scan"],
        )
        result = await scoper.top_k("query", k=5)
        assert result == ["wifi_scan"]  # hallucinated_tool filtered
    finally:
        await server.stop()
    print("✓ remote scoper filters unknown skill names from server response")


async def test_remote_scoper_fallback_on_connection_error():
    """Server is not running — scoper should fall back to returning all names."""
    scoper = RemoteEmbeddingScoper(
        endpoint="http://127.0.0.1:1/v1",  # deliberately nothing there
        skill_names=["wifi_scan", "ble_scan", "nfc_read"],
        timeout_s=0.5,
    )
    result = await scoper.top_k("query", k=2)
    assert result == ["wifi_scan", "ble_scan"]  # fallback returns first k names
    print("✓ remote scoper falls back on connection error")


async def test_remote_scoper_fallback_on_http_error():
    server = FakeScoperServer(status=500)
    await server.start()

    try:
        scoper = RemoteEmbeddingScoper(
            endpoint=f"http://127.0.0.1:{server.port}/v1",
            skill_names=["wifi_scan", "ble_scan"],
        )
        result = await scoper.top_k("query", k=2)
        assert result == ["wifi_scan", "ble_scan"]  # fallback
    finally:
        await server.stop()
    print("✓ remote scoper falls back on HTTP 500")


async def test_remote_scoper_fallback_on_bad_json():
    server = FakeScoperServer(bad_json=True)
    await server.start()

    try:
        scoper = RemoteEmbeddingScoper(
            endpoint=f"http://127.0.0.1:{server.port}/v1",
            skill_names=["a", "b", "c"],
        )
        result = await scoper.top_k("query", k=2)
        assert result == ["a", "b"]  # fallback
    finally:
        await server.stop()
    print("✓ remote scoper falls back on malformed server response")


async def test_make_scoper_uses_remote_when_endpoint_set():
    server = FakeScoperServer(response_skills=["wifi_scan"])
    await server.start()

    try:
        scoper = make_scoper(
            Path("/tmp/nonexistent_skills"),
            ["wifi_scan", "ble_scan"],
            remote_endpoint=f"http://127.0.0.1:{server.port}/v1",
        )
        assert isinstance(scoper, RemoteEmbeddingScoper)
        result = await scoper.top_k("scan", k=1)
        assert result == ["wifi_scan"]
    finally:
        await server.stop()
    print("✓ make_scoper uses Remote when endpoint is set")


async def test_make_scoper_falls_through_to_noop():
    """Neither remote nor local available → NoopScoper."""
    scoper = make_scoper(
        Path("/tmp/nonexistent"),
        ["a", "b"],
        prefer_embedding=False,
        remote_endpoint=None,
    )
    assert isinstance(scoper, NoopScoper)
    print("✓ make_scoper falls through to NoopScoper when nothing available")


async def test_config_auto_routes_to_mephisto_scoper():
    cfg = AgentConfig(backend="mephisto", scoper_endpoint="")
    assert cfg.effective_scoper_endpoint() == "http://10.66.0.2:8082/v1"

    cfg2 = AgentConfig(backend="ollama", scoper_endpoint="")
    assert cfg2.effective_scoper_endpoint() == ""  # no auto-route for dev

    cfg3 = AgentConfig(backend="ollama", scoper_endpoint="http://custom:9000/v1")
    assert cfg3.effective_scoper_endpoint() == "http://custom:9000/v1"
    print("✓ config auto-routes to Mephisto scoper in prod")


async def main():
    await test_remote_scoper_happy_path()
    await test_remote_scoper_filters_unknown_names()
    await test_remote_scoper_fallback_on_connection_error()
    await test_remote_scoper_fallback_on_http_error()
    await test_remote_scoper_fallback_on_bad_json()
    await test_make_scoper_uses_remote_when_endpoint_set()
    await test_make_scoper_falls_through_to_noop()
    await test_config_auto_routes_to_mephisto_scoper()
    print("\nall remote scoper tests passed")


if __name__ == "__main__":
    asyncio.run(main())
