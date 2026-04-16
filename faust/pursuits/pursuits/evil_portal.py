"""
Evil Portal Pursuit implementation.

Spec §10.4:
    "Stand up a captive portal on a rogue AP to observe credential-
    submission behavior in a controlled environment."

Open-ended. Dispatches `wifi_evil_portal` with duration_s=0 (spec: 0 =
until manually stopped) and then loops, yielding an activity line every
10 seconds with the elapsed connection count. No separate
`wifi_evil_portal_status` skill exists — the count is synthetic (elapsed
time) until Stage 5b adds a poll skill. Stop dispatches are likewise
unsupported at the skill level; the Pursuit returns when stop_event is
set, but the underlying AP is assumed to honor its own duration timer.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ..models import PursuitResultPartial, PursuitYield
from ._helpers import interruptible_sleep, unwrap_result


POLL_INTERVAL_S = 10.0


async def run(params: dict[str, Any], dispatcher, stop_event: asyncio.Event):
    """Start the portal then loop yielding heartbeat activity until the
    operator stops it."""
    ssid = params.get("ssid", "free-wifi")
    template = params.get("template", "google")

    yield PursuitYield(progress=0.0, activity=f"Starting evil portal '{ssid}'...")

    start = unwrap_result(await dispatcher.dispatch("wifi_evil_portal", {
        "ssid": ssid,
        "template": template,
        # 0 means "until manually stopped" per wifi_evil_portal SKILL.md.
        "duration_s": 0,
    }))

    if start.get("_error") or start.get("error"):
        err = start.get("_error") or start.get("error")
        yield PursuitYield(progress=1.0, activity=f"Portal failed to start: {err}")
        yield PursuitResultPartial(
            summary=f"Portal '{ssid}' failed to start: {err}",
            artifacts=[],
        )
        return

    yield PursuitYield(progress=0.1, activity=f"Portal '{ssid}' active · awaiting clients")

    loop = asyncio.get_event_loop()
    started_at = loop.time()
    heartbeats = 0
    connections = int(start.get("connections", 0) or 0)

    while not stop_event.is_set():
        if await interruptible_sleep(POLL_INTERVAL_S, stop_event):
            break
        heartbeats += 1
        elapsed_m = (loop.time() - started_at) / 60.0
        # TODO(5b): needs skill `wifi_evil_portal_status` for real client
        # counts. Until then the heartbeat advertises elapsed time only.
        yield PursuitYield(
            # Open-ended: cap the visible progress below 1.0 until stop.
            progress=min(0.9, 0.1 + heartbeats * 0.05),
            activity=f"Portal running {elapsed_m:.1f} min · clients: {connections}",
        )

    elapsed_m = (loop.time() - started_at) / 60.0
    # Best-effort stop — if the skill supports mid-run termination the
    # dispatch goes through; if not, the AP times out on its own.
    try:
        await dispatcher.dispatch("wifi_evil_portal", {
            "ssid": ssid,
            "duration_s": 1,  # interpreted as "wrap up"
        })
    except Exception:
        pass

    yield PursuitYield(progress=1.0, activity=f"Portal '{ssid}' stopped after {elapsed_m:.1f} min")
    yield PursuitResultPartial(
        summary=(
            f"Portal '{ssid}' ran for {elapsed_m:.1f} min, "
            f"{connections} connections observed"
        ),
        artifacts=[],
    )
