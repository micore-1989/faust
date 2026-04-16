"""
Wardrive Pursuit implementation.

Spec §10.4:
    "Drive or walk while capturing WiFi and GPS simultaneously. Exports
    a geo-tagged network map."

Loop: wifi_scan every ~5s for duration_minutes, yielding progress and
activity. GPS is intentionally left as TODO — no gps_* skill exists in
the catalog yet. Networks are accumulated across passes and written as
a CSV artifact at the end.
"""

from __future__ import annotations

import asyncio
import csv
from pathlib import Path
from typing import Any

from ..models import PursuitResultPartial, PursuitYield
from ._helpers import interruptible_sleep, unwrap_result


SCAN_INTERVAL_S = 5.0
ARTIFACT_DIR = Path("/tmp")


async def run(params: dict[str, Any], dispatcher, stop_event: asyncio.Event):
    """Loop wifi_scan every ~5s for duration_minutes. Write a geo-tagged
    CSV (GPS columns left blank until a gps_fix skill exists) and emit
    it as an artifact."""
    duration_minutes = int(params.get("duration_minutes", 30))
    band = params.get("frequency_band", "2.4 GHz only")
    run_id = params.get("_run_id", "current")
    total_s = max(1.0, duration_minutes * 60.0)
    csv_path = ARTIFACT_DIR / f"faust-wardrive-{run_id}.csv"

    yield PursuitYield(progress=0.0, activity=f"Wardrive starting · {duration_minutes} min · {band}")

    seen_networks: dict[str, dict[str, Any]] = {}
    gps_fixes = 0
    loop = asyncio.get_event_loop()
    start_s = loop.time()
    pass_count = 0

    while True:
        if stop_event.is_set():
            break

        elapsed = loop.time() - start_s
        if elapsed >= total_s:
            break

        pass_count += 1
        scan_result = unwrap_result(
            await dispatcher.dispatch("wifi_scan", {"band": band})
        )

        networks = scan_result.get("networks") or []
        for n in networks:
            bssid = n.get("bssid") or n.get("id") or str(id(n))
            if bssid not in seen_networks:
                seen_networks[bssid] = n

        # TODO(5b): needs skill `gps_fix` — no GPS skill in the catalog.
        # Until one exists, the CSV's GPS columns stay blank and we don't
        # dispatch a real fix. Activity log reflects that honestly.
        # gps_result = unwrap_result(await dispatcher.dispatch("gps_fix", {}))

        new_count = len(networks)
        total_count = len(seen_networks)
        yield PursuitYield(
            progress=min(0.95, elapsed / total_s),
            eta_s=int(max(0, total_s - elapsed)),
            activity=(
                f"Pass {pass_count}: {new_count} networks this sweep · "
                f"{total_count} unique · (GPS: unavailable — see TODO)"
            ),
        )

        if await interruptible_sleep(SCAN_INTERVAL_S, stop_event):
            break

    # Write artifact even if stopped early.
    try:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["bssid", "ssid", "channel", "rssi_dbm", "encryption",
                        "lat", "lon", "gps_fix"])
            for n in seen_networks.values():
                w.writerow([
                    n.get("bssid", ""),
                    n.get("ssid", ""),
                    n.get("channel", ""),
                    n.get("rssi_dbm", ""),
                    n.get("encryption", ""),
                    "", "", "no",
                ])
    except Exception:
        # Non-fatal: artifact write failure shouldn't crash the Pursuit.
        csv_path = Path("")

    minutes_run = (loop.time() - start_s) / 60.0
    summary = (
        f"{len(seen_networks)} networks captured over "
        f"{minutes_run:.1f} min, {gps_fixes} with GPS fix"
    )
    yield PursuitResultPartial(
        summary=summary,
        artifacts=[str(csv_path)] if str(csv_path) else [],
    )
