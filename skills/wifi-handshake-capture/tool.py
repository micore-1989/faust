"""FAKE: synthetic WPA handshake capture."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import (
    fake_bssid, fake_capture_path, fake_client_mac, fake_ssid,
    mark_synthetic, _rng,
)


def execute(args: dict[str, Any]) -> dict[str, Any]:
    interface = args.get("interface", "wlan1mon")
    bssid = args.get("bssid") or fake_bssid()
    channel = args.get("channel", 6)
    timeout_s = int(args.get("timeout_s", 60))

    rng = _rng(f"handshake:{bssid}")

    # 75% of attempts capture — rest are timeouts where no client reconnected.
    captured = rng.random() < 0.75

    if not captured:
        return mark_synthetic({
            "captured": False,
            "bssid": bssid,
            "channel": channel,
            "reason": "no client reconnected within timeout",
            "timeout_s": timeout_s,
            "eapol_frames": rng.randint(0, 1),
        })

    seed = f"handshake:{bssid}"
    ssid = fake_ssid(seed)
    client = fake_client_mac(seed)
    pcap = fake_capture_path(f"handshake_{bssid.replace(':','')}", "pcap", seed)

    return mark_synthetic({
        "captured": True,
        "bssid": bssid,
        "ssid": ssid,
        "client": client,
        "eapol_frames": 4,
        "pcap_path": pcap,
        "hash_file": pcap.replace(".pcap", ".22000"),
        "crack_hint": f"hashcat -m 22000 {pcap.replace('.pcap', '.22000')} wordlist.txt",
    })
