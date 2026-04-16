"""FAKE: synthetic wardrive survey with GPS-tagged networks."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import (
    fake_bssid, fake_capture_path, fake_channel, fake_encryption,
    fake_gps, fake_rssi, fake_ssid, now_iso, ago_iso, mark_synthetic,
    pack_summary, _rng,
)
from faust.tools.registry import ToolResult


def execute(args: dict[str, Any]) -> ToolResult:
    interface = args.get("interface", "wlan1mon")
    duration_s = int(args.get("duration_s", 60))
    include_ble = args.get("include_ble", True)
    output_format = args.get("output_format", "json")

    rng = _rng(f"wardrive:{interface}:{duration_s}")
    net_count = max(3, duration_s // 15 + rng.randint(0, 4))

    networks = []
    for i in range(net_count):
        seed = f"wardrive:{interface}:{i}"
        lat, lon, alt = fake_gps(seed)
        networks.append({
            "ssid": fake_ssid(seed),
            "bssid": fake_bssid(seed),
            "channel": fake_channel(seed=seed),
            "encryption": fake_encryption(seed),
            "first_seen": ago_iso(duration_s),
            "last_seen": now_iso(),
            "strongest_rssi_dbm": fake_rssi(seed=seed),
            "lat": lat,
            "lon": lon,
            "alt_m": alt,
        })

    ble_devices = []
    if include_ble:
        ble_count = rng.randint(2, 8)
        for i in range(ble_count):
            seed = f"wardrive-ble:{interface}:{i}"
            lat, lon, _ = fake_gps(seed)
            ble_devices.append({
                "name": rng.choice(["Tile", "AirTag", "Fitbit", "iPhone", None]),
                "mac": fake_bssid(seed),
                "rssi_dbm": fake_rssi(seed=seed),
                "lat": lat,
                "lon": lon,
            })

    out = fake_capture_path("wardrive", "json" if output_format == "json" else "csv")

    result = mark_synthetic({
        "survey": {
            "start_time": ago_iso(duration_s),
            "duration_s": duration_s,
            "gps_fix": "3d",
            "observations": len(networks) * 12 + len(ble_devices) * 4,
        },
        "networks": networks,
        "ble_devices": ble_devices,
        "output_file": out,
    })

    open_nets = [n for n in networks if n["encryption"] == "Open"]
    summary = pack_summary({
        "wifi_mapped": len(networks),
        "ble_mapped": len(ble_devices),
        "open_networks": len(open_nets),
        "gps_fix": "3d",
        "duration_s": duration_s,
        "output_file": out,
    })
    return ToolResult(result=result, summary=summary)
