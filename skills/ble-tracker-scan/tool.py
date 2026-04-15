"""FAKE: synthetic BLE tracker (AirTag, Tile, etc.) scan."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import (
    fake_mac, ago_iso, now_iso, mark_synthetic, _rng,
)


_TRACKER_TYPES = ["airtag", "tile", "chipolo", "smarttag"]


def execute(args: dict[str, Any]) -> dict[str, Any]:
    duration_s = int(args.get("duration_s", 300))
    min_sightings = int(args.get("min_sightings", 3))
    known_devices = set(args.get("known_devices") or [])

    rng = _rng(f"tracker_scan:{duration_s}")
    devices_seen = rng.randint(30, 60)

    # Most scans find nothing. Occasionally a tracker appears.
    suspected = []
    if rng.random() < 0.25:
        seed = f"tracker:suspect"
        t_type = rng.choice(_TRACKER_TYPES)
        mac = fake_mac("Apple" if t_type == "airtag" else None, seed)
        if mac not in known_devices:
            sightings = rng.randint(min_sightings, 15)
            suspected.append({
                "type": t_type,
                "mac": mac,
                "rssi_history": [rng.randint(-70, -45) for _ in range(sightings)],
                "sightings": sightings,
                "first_seen": ago_iso(duration_s),
                "last_seen": now_iso(),
                "moving_with_operator": rng.random() > 0.5,
                "estimated_distance_m": round(rng.uniform(0.5, 5.0), 1),
            })

    return mark_synthetic({
        "scan_duration_s": duration_s,
        "devices_seen": devices_seen,
        "suspected_trackers": suspected,
    })
