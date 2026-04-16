"""
Bluetooth Recon Pursuit implementation.

Spec §10.4:
    "Passively survey nearby BLE devices, log advertisements, classify
    vendor and role."

Loop `ble_scan` in 10-second intervals for `duration_minutes` total,
accumulating unique devices across passes. Final artifact is a JSON
device list.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from ..models import PursuitResultPartial, PursuitYield
from ._helpers import interruptible_sleep, unwrap_result


SCAN_WINDOW_S = 10
ARTIFACT_DIR = Path("/tmp")


async def run(params: dict[str, Any], dispatcher, stop_event: asyncio.Event):
    """Scan BLE in 10s chunks for `duration_minutes` minutes. Accumulate
    unique devices by MAC, classify vendor by OUI where provided."""
    duration_minutes = int(params.get("duration_minutes", 10))
    total_s = max(SCAN_WINDOW_S, duration_minutes * 60)
    run_id = params.get("_run_id", "current")
    artifact_path = ARTIFACT_DIR / f"faust-ble-recon-{run_id}.json"

    yield PursuitYield(
        progress=0.0,
        activity=f"BLE recon · {duration_minutes} min · {SCAN_WINDOW_S}s windows",
    )

    devices: dict[str, dict[str, Any]] = {}
    passes = 0
    loop = asyncio.get_event_loop()
    started = loop.time()

    while True:
        if stop_event.is_set():
            break
        elapsed = loop.time() - started
        if elapsed >= total_s:
            break

        passes += 1
        scan = unwrap_result(await dispatcher.dispatch("ble_scan", {
            "duration_s": SCAN_WINDOW_S,
        }))

        pass_devices = scan.get("devices") or scan.get("value") or []
        new_count = 0
        for d in pass_devices:
            mac = d.get("mac") or d.get("bssid") or d.get("address")
            if not mac:
                continue
            if mac not in devices:
                devices[mac] = d
                new_count += 1

        vendor_count = sum(
            1 for d in devices.values() if d.get("vendor") or d.get("manufacturer")
        )
        yield PursuitYield(
            progress=min(0.95, elapsed / total_s),
            eta_s=int(max(0, total_s - elapsed)),
            activity=(
                f"Pass {passes}: +{new_count} new · {len(devices)} total · "
                f"{vendor_count} identified"
            ),
        )
        # Yield control between passes so the event loop can service
        # stop_event trips even when ble_scan returns instantly (mock
        # dispatcher in tests, or a real scan that happened to find
        # nothing). Real hardware naturally paces via its own I/O.
        if await interruptible_sleep(0.01, stop_event):
            break

    try:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            json.dumps(list(devices.values()), indent=2, default=str),
            encoding="utf-8",
        )
    except Exception:
        artifact_path = Path("")

    vendor_count = sum(
        1 for d in devices.values() if d.get("vendor") or d.get("manufacturer")
    )
    yield PursuitResultPartial(
        summary=(
            f"{len(devices)} unique BLE devices, "
            f"{vendor_count} with identifiable vendor"
        ),
        artifacts=[str(artifact_path)] if str(artifact_path) else [],
    )
