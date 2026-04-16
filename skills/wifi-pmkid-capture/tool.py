"""FAKE: synthetic PMKID capture."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import (
    fake_bssid, fake_capture_path, fake_hash, fake_ssid,
    mark_synthetic, pack_summary, _rng,
)
from faust.tools.registry import ToolResult


def execute(args: dict[str, Any]) -> ToolResult:
    bssid = args.get("bssid") or fake_bssid()
    channel = args.get("channel", 6)
    timeout_s = int(args.get("timeout_s", 30))

    rng = _rng(f"pmkid:{bssid}")

    # ~70% of APs leak PMKID on first EAPOL (real-world rate roughly matches).
    captured = rng.random() < 0.70

    if not captured:
        result = mark_synthetic({
            "captured": False,
            "bssid": bssid,
            "channel": channel,
            "reason": "AP did not include PMKID in initial EAPOL (likely WPA3 or hardened firmware)",
            "timeout_s": timeout_s,
        })
        summary = pack_summary({
            "captured": False,
            "bssid": bssid,
            "reason": "no_pmkid_in_eapol",
        })
        return ToolResult(result=result, summary=summary)

    seed = f"pmkid:{bssid}"
    ssid = fake_ssid(seed)
    hash_path = fake_capture_path(f"pmkid_{bssid.replace(':','')}", "22000", seed)

    result = mark_synthetic({
        "captured": True,
        "bssid": bssid,
        "ssid": ssid,
        "pmkid": fake_hash(32, seed),
        "hash_file": hash_path,
        "crack_hint": f"hashcat -m 22000 {hash_path} wordlist.txt",
    })
    summary = pack_summary({
        "captured": True,
        "bssid": bssid,
        "ssid": ssid,
        "hash_file": hash_path,
    })
    return ToolResult(result=result, summary=summary)
