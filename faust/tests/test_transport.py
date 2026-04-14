"""
Transport link tests.

Tests MephistoLink health checking and state transitions using a mock HTTP
server. No real hardware or network needed.

Run with: python -m faust.tests.test_transport
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx

from faust.transport.link import LinkState, LinkStatus, MephistoLink


# ------------- Mock HTTP transport for httpx -------------------

class MockTransport(httpx.AsyncBaseTransport):
    """Returns canned responses for /v1/models. Plugs into httpx.AsyncClient."""

    def __init__(self, handler=None):
        self._handler = handler or self._default_handler

    @staticmethod
    def _default_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=500, text="no handler")

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return self._handler(request)


def _models_ok(request: httpx.Request) -> httpx.Response:
    """Mephisto is up, model loaded."""
    return httpx.Response(
        status_code=200,
        json={"data": [{"id": "qwen2.5:1.5b-instruct", "object": "model"}]},
    )


def _models_empty(request: httpx.Request) -> httpx.Response:
    """Mephisto HTTP is up but no model loaded."""
    return httpx.Response(
        status_code=200,
        json={"data": []},
    )


def _models_500(request: httpx.Request) -> httpx.Response:
    """Mephisto returns a server error."""
    return httpx.Response(status_code=500, text="internal error")


def _make_link(handler) -> MephistoLink:
    """Create a MephistoLink with a mocked HTTP client."""
    link = MephistoLink(endpoint="http://10.66.0.2:8000/v1", timeout_s=1.0)
    link._client = httpx.AsyncClient(transport=MockTransport(handler))
    return link


# ------------- Tests -------------------------------------------

async def test_connected_state():
    link = _make_link(_models_ok)
    status = await link.check()
    assert status.state == LinkState.CONNECTED
    assert status.model == "qwen2.5:1.5b-instruct"
    assert status.latency_ms >= 0
    assert status.error is None
    await link.aclose()
    print("✓ connected state when model is loaded")


async def test_reachable_no_model():
    link = _make_link(_models_empty)
    status = await link.check()
    assert status.state == LinkState.REACHABLE
    assert status.model is None
    assert status.error is None
    await link.aclose()
    print("✓ reachable state when no model loaded")


async def test_reachable_http_error():
    link = _make_link(_models_500)
    status = await link.check()
    assert status.state == LinkState.REACHABLE
    assert status.error == "HTTP 500"
    await link.aclose()
    print("✓ reachable state on HTTP 500")


async def test_disconnected_on_connect_error():
    def _raise(request):
        raise httpx.ConnectError("connection refused")

    link = _make_link(_raise)
    status = await link.check()
    assert status.state == LinkState.DISCONNECTED
    assert "connection refused" in (status.error or "")
    await link.aclose()
    print("✓ disconnected state on connection error")


async def test_disconnected_on_timeout():
    def _raise(request):
        raise httpx.ConnectTimeout("timed out")

    link = _make_link(_raise)
    status = await link.check()
    assert status.state == LinkState.DISCONNECTED
    assert "timed out" in (status.error or "")
    await link.aclose()
    print("✓ disconnected state on timeout")


async def test_initial_state_is_unknown():
    link = _make_link(_models_ok)
    assert link.status.state == LinkState.UNKNOWN
    await link.aclose()
    print("✓ initial state is UNKNOWN before first check")


async def test_status_updates_after_check():
    link = _make_link(_models_ok)
    assert link.status.state == LinkState.UNKNOWN
    await link.check()
    assert link.status.state == LinkState.CONNECTED
    await link.aclose()
    print("✓ status property updates after check()")


async def test_state_transitions():
    """Link transitions connected → disconnected → connected."""
    call_count = 0

    def _handler(request):
        nonlocal call_count
        call_count += 1
        if call_count <= 1:
            return _models_ok(request)
        elif call_count == 2:
            raise httpx.ConnectError("lost link")
        else:
            return _models_ok(request)

    link = _make_link(_handler)

    s1 = await link.check()
    assert s1.state == LinkState.CONNECTED

    s2 = await link.check()
    assert s2.state == LinkState.DISCONNECTED

    s3 = await link.check()
    assert s3.state == LinkState.CONNECTED

    await link.aclose()
    print("✓ state transitions: connected → disconnected → connected")


async def test_endpoint_stored():
    link = _make_link(_models_ok)
    assert link.endpoint == "http://10.66.0.2:8000/v1"
    status = await link.check()
    assert status.endpoint == "http://10.66.0.2:8000/v1"
    await link.aclose()
    print("✓ endpoint stored in link and status")


async def test_last_check_timestamp():
    import time
    link = _make_link(_models_ok)
    before = time.time()
    status = await link.check()
    after = time.time()
    assert before <= status.last_check <= after
    await link.aclose()
    print("✓ last_check timestamp is set")


async def main():
    await test_connected_state()
    await test_reachable_no_model()
    await test_reachable_http_error()
    await test_disconnected_on_connect_error()
    await test_disconnected_on_timeout()
    await test_initial_state_is_unknown()
    await test_status_updates_after_check()
    await test_state_transitions()
    await test_endpoint_stored()
    await test_last_check_timestamp()
    print("\nall transport tests passed")


if __name__ == "__main__":
    asyncio.run(main())
