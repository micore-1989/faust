"""FAKE: synthetic BLE device scan."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import fake_ble_device, mark_synthetic, _rng


def execute(args: dict[str, Any]) -> dict[str, Any]:
    duration_s = int(args.get("duration_s", 10))
    filter_name = (args.get("filter_name") or "").lower()
    filter_rssi = args.get("filter_rssi")

    rng = _rng(f"ble_scan:{duration_s}")
    count = rng.randint(3, 8)

    devices = [fake_ble_device(f"ble_scan:{i}") for i in range(count)]

    # Apply filters.
    if filter_name:
        devices = [d for d in devices if d["name"] and filter_name in d["name"].lower()]
    if filter_rssi is not None:
        devices = [d for d in devices if d["rssi_dbm"] >= int(filter_rssi)]

    # Sort by signal strength.
    devices.sort(key=lambda d: -d["rssi_dbm"])

    return mark_synthetic({
        "devices": devices,
        "scan_duration_s": duration_s,
        "total_advertisements": sum(rng.randint(1, 40) for _ in devices),
    })
