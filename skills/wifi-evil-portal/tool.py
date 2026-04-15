"""FAKE: synthetic Evil Portal credential harvest."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import (
    fake_capture_path, fake_client_mac, fake_hash, now_iso, ago_iso,
    mark_synthetic, _rng,
)


_FAKE_USERS = ["alice", "bob", "charlie", "diane", "evan"]


def execute(args: dict[str, Any]) -> dict[str, Any]:
    ssid = args.get("ssid", "TargetNet-Guest")
    template = args.get("template", "google")
    channel = int(args.get("channel", 6))
    duration_s = int(args.get("duration_s", 300))

    rng = _rng(f"evilportal:{ssid}:{template}")

    # Most portals get at least a few misclicks.
    n_clients = rng.randint(1, 5)
    n_creds = rng.randint(0, min(n_clients, 3))

    creds = []
    for i in range(n_creds):
        seed = f"evilportal:{ssid}:cred:{i}"
        user = rng.choice(_FAKE_USERS)
        creds.append({
            "client_mac": fake_client_mac(seed),
            "timestamp": ago_iso(duration_s - (i * 30)),
            "email": f"{user}@example.com",
            "password_hash": f"sha256:{fake_hash(16, seed)}",
        })

    return mark_synthetic({
        "ap_bssid": "02:11:22:33:44:55",
        "ssid": ssid,
        "channel": channel,
        "template": template,
        "duration_s": duration_s,
        "clients_connected": n_clients,
        "credentials_captured": creds,
        "log_file": fake_capture_path("evil_portal", "log"),
    })
