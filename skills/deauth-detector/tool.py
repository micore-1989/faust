"""FAKE: synthetic 802.11 deauth monitoring."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import (
    fake_bssid, fake_capture_path, fake_client_mac, fake_ssid,
    ago_iso, now_iso, mark_synthetic, pack_summary, _rng,
)
from faust.tools.registry import ToolResult


def execute(args: dict[str, Any]) -> ToolResult:
    interface = args.get("interface", "wlan1mon")
    duration_s = int(args.get("duration_s", 60)) or 60
    threshold = int(args.get("threshold", 5))

    rng = _rng(f"deauth_detector:{interface}:{duration_s}")

    # ~20% of scans detect an active attack.
    under_attack = rng.random() < 0.2

    alerts = []
    deauth_count = rng.randint(0, 15)
    if under_attack:
        seed = "deauth_attacker"
        alerts.append({
            "source_mac": fake_client_mac(seed),
            "target_bssid": fake_bssid(seed),
            "target_ssid": fake_ssid(seed),
            "frames_per_minute": rng.randint(threshold * 10, 300),
            "first_seen": ago_iso(duration_s),
            "last_seen": now_iso(),
            "likely": "attack",
        })
        deauth_count = rng.randint(50, 500)

    result = mark_synthetic({
        "interface": interface,
        "monitoring_duration_s": duration_s,
        "deauth_frames_seen": deauth_count,
        "disassoc_frames_seen": rng.randint(0, 15),
        "alerts": alerts,
        "threshold": threshold,
        "pcap_path": fake_capture_path("deauth_monitor"),
    })

    summary = pack_summary({
        "under_attack": under_attack,
        "alerts": len(alerts),
        "deauth_frames": deauth_count,
        "attacker_mac": alerts[0]["source_mac"] if alerts else None,
        "target_bssid": alerts[0]["target_bssid"] if alerts else None,
    })
    return ToolResult(result=result, summary=summary)
