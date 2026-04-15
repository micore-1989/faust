"""FAKE: synthetic BLE GATT enumeration."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import mark_synthetic, _rng


_COMMON_SERVICES = [
    {"uuid": "0000180f-0000-1000-8000-00805f9b34fb", "name": "Battery Service",
     "chars": [{"uuid": "00002a19-0000-1000-8000-00805f9b34fb",
                "name": "Battery Level", "flags": ["read", "notify"], "value": "58"}]},
    {"uuid": "0000180a-0000-1000-8000-00805f9b34fb", "name": "Device Information",
     "chars": [{"uuid": "00002a29-0000-1000-8000-00805f9b34fb",
                "name": "Manufacturer Name", "flags": ["read"], "value": "Acme"},
               {"uuid": "00002a24-0000-1000-8000-00805f9b34fb",
                "name": "Model Number", "flags": ["read"], "value": "X-1"}]},
    {"uuid": "00001800-0000-1000-8000-00805f9b34fb", "name": "Generic Access",
     "chars": [{"uuid": "00002a00-0000-1000-8000-00805f9b34fb",
                "name": "Device Name", "flags": ["read"], "value": "Device"}]},
]


def execute(args: dict[str, Any]) -> dict[str, Any]:
    mac = args.get("mac", "00:00:00:00:00:00")
    read_values = args.get("read_values", True)

    rng = _rng(f"ble_enum:{mac}")
    # Pick 2-3 services.
    n_services = rng.randint(2, 3)
    selected = rng.sample(_COMMON_SERVICES, k=min(n_services, len(_COMMON_SERVICES)))

    services = []
    for svc in selected:
        chars = []
        for char in svc["chars"]:
            entry = {"uuid": char["uuid"], "name": char["name"], "flags": char["flags"]}
            if read_values and "read" in char["flags"]:
                entry["value_hex"] = char["value"] if char.get("value") else "00"
            chars.append(entry)
        services.append({"uuid": svc["uuid"], "name": svc["name"], "characteristics": chars})

    return mark_synthetic({
        "mac": mac,
        "connected": True,
        "services": services,
    })
