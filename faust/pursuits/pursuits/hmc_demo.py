"""
Harvey Mudd Demo Pursuit implementation.

Spec §10.4:
    "Scripted demonstration sequence for the student showcase: scan,
    capture, Pursuit-complete. Uses a dedicated demo SSID."

Scripted, short, explicitly not authorized-scope-checked. Dispatches
wifi_scan and a brief wifi_handshake_capture (the closest available
substitute for a generic `wifi.capture`). Demo completion is journaled
by the runner's terminal entry — no separate `journal.append` skill
exists and that's fine.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ..models import PursuitResultPartial, PursuitYield
from ._helpers import interruptible_sleep, unwrap_result


DEMO_SSID = "faust-demo"
ARTIFACT_DIR = Path("/tmp")


async def run(params: dict[str, Any], dispatcher, stop_event: asyncio.Event):
    """Scripted 3-minute sequence: scan → detect demo net → brief
    handshake capture → complete."""
    run_id = params.get("_run_id", "current")
    capture_path = ARTIFACT_DIR / f"faust-hmc-demo-{run_id}.pcap"

    # Step 1: kickoff.
    yield PursuitYield(progress=0.0, activity="Starting Harvey Mudd demo...")
    if await interruptible_sleep(0.5, stop_event):
        return

    # Step 2: wifi_scan.
    scan = unwrap_result(await dispatcher.dispatch("wifi_scan", {}))
    networks = scan.get("networks") or []
    network_count = len(networks)
    yield PursuitYield(
        progress=0.3,
        activity=f"wifi_scan complete · {network_count} networks",
    )
    if stop_event.is_set():
        return

    # Step 3: synthetic detection (no real skill — just a scripted line).
    if await interruptible_sleep(0.8, stop_event):
        return
    yield PursuitYield(
        progress=0.5,
        activity=f"Demo network '{DEMO_SSID}' detected",
    )

    # Step 4: brief capture. Closest skill is wifi_handshake_capture; we
    # use a very short timeout so the demo stays short.
    demo_bssid = "02:00:de:ad:be:ef"  # canonical locally-assigned demo BSSID
    if stop_event.is_set():
        return
    cap = unwrap_result(await dispatcher.dispatch("wifi_handshake_capture", {
        "bssid": demo_bssid,
        "channel": 6,
        "timeout_s": 5,
        "output_file": str(capture_path),
    }))
    capture_artifact = cap.get("output_file") or str(capture_path)
    yield PursuitYield(
        progress=0.8,
        activity=f"wifi_handshake_capture → {capture_artifact}",
    )

    # Step 5: completion. No `journal.append` skill exists; the runner's
    # terminal journal entry covers this.
    if await interruptible_sleep(0.3, stop_event):
        return
    yield PursuitYield(progress=1.0, activity="Demo complete")

    yield PursuitResultPartial(
        summary=f"HMC demo complete — {network_count} networks scanned",
        artifacts=[capture_artifact],
    )
