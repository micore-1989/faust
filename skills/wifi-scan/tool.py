"""FAKE: synthetic WiFi scan. Replace with real aircrack-ng/airodump-ng when ALFA arrives."""
from __future__ import annotations

import random
from typing import Any

from faust.skills.fakes import (
    fake_bssid, fake_channel, fake_client_mac, fake_encryption,
    fake_rssi, fake_ssid, mark_synthetic, _rng,
)


def execute(args: dict[str, Any]) -> dict[str, Any]:
    interface = args.get("interface", "wlan1mon")
    duration_s = int(args.get("duration_s", 10))
    band = args.get("band", "all")

    # Deterministic-ish — same interface on same scan gives same results.
    rng = _rng(f"wifi_scan:{interface}:{band}")
    count = rng.randint(4, 9)

    networks = []
    for i in range(count):
        seed = f"wifi_scan:{interface}:{band}:{i}"
        ssid = fake_ssid(seed)
        bssid = fake_bssid(seed)
        chan = fake_channel(band, seed)
        rssi = fake_rssi(near=(rng.random() > 0.7), seed=seed)
        enc = fake_encryption(seed)

        # Some APs have associated clients.
        n_clients = rng.randint(0, 4) if rng.random() > 0.4 else 0
        clients = [
            {
                "mac": fake_client_mac(f"{seed}:c{j}"),
                "rssi_dbm": rssi + rng.randint(-15, 5),
                "probes": [fake_ssid(f"{seed}:p{j}{k}") for k in range(rng.randint(0, 2))],
            }
            for j in range(n_clients)
        ]
        networks.append({
            "ssid": ssid,
            "bssid": bssid,
            "channel": chan,
            "rssi_dbm": rssi,
            "encryption": enc,
            "clients": clients,
        })

    # Sort by signal strength (strongest first) — operators care about this.
    networks.sort(key=lambda n: -n["rssi_dbm"])

    return mark_synthetic({
        "networks": networks,
        "scan_duration_s": duration_s,
        "total_frames": rng.randint(800, 5000),
        "interface": interface,
        "band": band,
    })
