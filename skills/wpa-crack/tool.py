"""FAKE: synthetic WPA/PMKID dictionary crack."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import fake_bssid, mark_synthetic, _rng


_COMMON_PASSWORDS = [
    "password123", "12345678", "passw0rd!", "summer2024", "letmein1",
    "Welcome123", "CompanyPass!", "changeme", "admin123", "baseball1",
]


def execute(args: dict[str, Any]) -> dict[str, Any]:
    hash_file = args.get("hash_file", "captures/unknown.22000")
    wordlist = args.get("wordlist", "top10k")
    rules = args.get("rules", "none")
    time_budget_s = int(args.get("time_budget_s", 300))

    rng = _rng(f"wpa_crack:{hash_file}:{rules}")

    # ~50% of real-world captures crack in a modest wordlist with simple rules.
    cracked = rng.random() < (0.6 if rules != "none" else 0.45)
    duration = rng.randint(10, min(time_budget_s, 180))

    result: dict[str, Any] = {
        "hash_file": hash_file,
        "bssid": fake_bssid(f"wpa_crack:{hash_file}"),
        "ssid": rng.choice(["TargetNet", "CorpWiFi", "HomeWiFi", "GuestWiFi"]),
        "wordlist": wordlist,
        "rules": rules,
        "hashes_per_second": rng.randint(8_000, 45_000),
        "duration_s": duration,
        "cracked": cracked,
    }

    if cracked:
        result["password"] = rng.choice(_COMMON_PASSWORDS)
        result["wordlist_progress"] = f"{rng.randint(5, 75)}%"
    else:
        result["wordlist_progress"] = "100%"
        result["note"] = "exhausted wordlist; try bigger wordlist or rules"

    return mark_synthetic(result)
