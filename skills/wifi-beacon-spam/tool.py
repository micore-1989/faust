"""FAKE: synthetic beacon spam."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import mark_synthetic, _rng


def execute(args: dict[str, Any]) -> dict[str, Any]:
    interface = args.get("interface", "wlan1mon")
    ssid_list = args.get("ssid_list") or None
    channel = int(args.get("channel", 6))
    count_per_ssid = int(args.get("count_per_ssid", 10))
    duration_s = int(args.get("duration_s", 30))

    rng = _rng(f"beacon_spam:{interface}:{channel}")

    if not ssid_list:
        pool = ["FBI_Surveillance_Van", "Pretty Fly for a WiFi", "VIRUS",
                "Free WiFi", "Click Here", "Bait", "Test"]
        ssid_list = rng.sample(pool, rng.randint(3, 5))

    beacons = len(ssid_list) * count_per_ssid * duration_s

    return mark_synthetic({
        "interface": interface,
        "ssids_broadcast": len(ssid_list),
        "ssid_list": ssid_list,
        "beacons_sent": beacons,
        "channel": channel,
        "duration_s": duration_s,
    })
