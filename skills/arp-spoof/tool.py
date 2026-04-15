"""FAKE: synthetic ARP spoofing attack."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import mark_synthetic, _rng


def execute(args: dict[str, Any]) -> dict[str, Any]:
    interface = args.get("interface", "wlan0")
    target_ip = args.get("target_ip", "192.168.1.42")
    gateway_ip = args.get("gateway_ip", "192.168.1.1")
    forward = args.get("forward", True)
    duration_s = int(args.get("duration_s", 60)) or 60

    rng = _rng(f"arp_spoof:{target_ip}:{gateway_ip}")

    # ~1 poison packet per second per direction.
    poisoned = duration_s * 2 * rng.randint(3, 7)
    bytes_forwarded = duration_s * rng.randint(10_000, 200_000) if forward else 0

    return mark_synthetic({
        "interface": interface,
        "target_ip": target_ip,
        "gateway_ip": gateway_ip,
        "forward_enabled": bool(forward),
        "poisoned_entries": poisoned,
        "duration_s": duration_s,
        "bytes_forwarded": bytes_forwarded,
    })
