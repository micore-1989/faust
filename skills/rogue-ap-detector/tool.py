"""FAKE: synthetic rogue AP / evil-twin detection."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import (
    fake_bssid, fake_channel, fake_rssi, fake_ssid, ago_iso, mark_synthetic, _rng,
)


def execute(args: dict[str, Any]) -> dict[str, Any]:
    interface = args.get("interface", "wlan1mon")
    whitelist = args.get("whitelist") or []
    duration_s = int(args.get("duration_s", 60)) or 60

    rng = _rng(f"rogue_ap:{interface}:{duration_s}:{len(whitelist)}")

    whitelist_ssids = {w["ssid"]: w["bssid"] for w in whitelist if isinstance(w, dict)}

    # Seen networks: mix of whitelist matches, unknown APs, and maybe one evil twin.
    networks_seen = len(whitelist_ssids) + rng.randint(3, 8)

    evil_twins = []
    # 15% chance of detecting an evil twin.
    if whitelist_ssids and rng.random() < 0.15:
        victim = rng.choice(list(whitelist_ssids.keys()))
        rogue_bssid = fake_bssid(f"rogue:{victim}")
        evil_twins.append({
            "ssid": victim,
            "legitimate_bssid": whitelist_ssids[victim],
            "rogue_bssid": rogue_bssid,
            "rogue_rssi_dbm": fake_rssi(near=True),
            "rogue_channel": fake_channel(seed=f"rogue:{victim}"),
            "legit_channel": 6,
            "encryption_mismatch": rng.random() < 0.5,
            "first_seen": ago_iso(duration_s),
        })

    unknown_aps = [
        {
            "ssid": fake_ssid(f"unknown:{i}"),
            "bssid": fake_bssid(f"unknown:{i}"),
            "channel": fake_channel(seed=f"unknown:{i}"),
            "rssi_dbm": fake_rssi(seed=f"unknown:{i}"),
        }
        for i in range(rng.randint(2, 4))
    ]

    return mark_synthetic({
        "interface": interface,
        "monitoring_duration_s": duration_s,
        "networks_seen": networks_seen,
        "evil_twins": evil_twins,
        "unknown_aps": unknown_aps,
        "whitelist_matches": len(whitelist_ssids),
    })
