"""FAKE: synthetic probe request monitoring."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import (
    fake_client_mac, fake_ssid, ago_iso, now_iso, mark_synthetic, _rng,
)


_VENDORS = ["Apple", "Samsung", "Intel", "Google", "Unknown"]


def execute(args: dict[str, Any]) -> dict[str, Any]:
    interface = args.get("interface", "wlan1mon")
    duration_s = int(args.get("duration_s", 300)) or 300
    deanonymize = args.get("deanonymize", True)

    rng = _rng(f"probe_monitor:{interface}:{duration_s}")

    n_devices = rng.randint(8, 35)
    devices = []
    for i in range(n_devices):
        seed = f"probe:dev:{i}"
        dr = _rng(seed)
        vendor = dr.choice(_VENDORS)
        # iOS 14+ and Android 10+ randomize by default.
        randomized = dr.random() < 0.7
        probes = [fake_ssid(f"{seed}:p{j}") for j in range(dr.randint(1, 5))]
        devices.append({
            "mac": fake_client_mac(seed),
            "randomized": randomized,
            "vendor": vendor if not randomized else "Unknown",
            "probed_ssids": probes,
            "first_seen": ago_iso(duration_s),
            "last_seen": now_iso(),
            "probe_count": dr.randint(1, 50),
        })

    return mark_synthetic({
        "interface": interface,
        "duration_s": duration_s,
        "device_count": len(devices),
        "devices": devices,
        "deanonymize": bool(deanonymize),
    })
