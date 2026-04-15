"""FAKE: synthetic WiFi deauth attack."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import fake_bssid, fake_client_mac, mark_synthetic, _rng


def execute(args: dict[str, Any]) -> dict[str, Any]:
    bssid = args.get("bssid") or fake_bssid()
    client = args.get("client") or "ff:ff:ff:ff:ff:ff"
    interface = args.get("interface", "wlan1mon")
    count = int(args.get("count", 5))

    rng = _rng(f"deauth:{bssid}:{client}")

    # Broadcast deauth is more likely to succeed than targeted.
    broadcast = client == "ff:ff:ff:ff:ff:ff"
    disconnected = (rng.random() < 0.90 if not broadcast else True)

    return mark_synthetic({
        "bssid": bssid,
        "client": client,
        "interface": interface,
        "frames_sent": count * rng.randint(1, 3),
        "disconnected": disconnected,
        "broadcast": broadcast,
        "duration_ms": count * rng.randint(50, 200),
    })
