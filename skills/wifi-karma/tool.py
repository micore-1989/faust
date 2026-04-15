"""FAKE: synthetic Karma mass rogue AP."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import fake_client_mac, fake_ssid, mark_synthetic, _rng


def execute(args: dict[str, Any]) -> dict[str, Any]:
    interface = args.get("interface", "wlan1mon")
    duration_s = int(args.get("duration_s", 300))
    restrict_to_opens = args.get("restrict_to_opens", True)

    rng = _rng(f"karma:{interface}:{duration_s}")

    probes_seen = rng.randint(200, 1500)
    # About 10% of probes are for open networks we can impersonate.
    ssids_impersonated = list({fake_ssid(f"karma:{interface}:{i}")
                               for i in range(rng.randint(2, 6))})

    n_associated = rng.randint(0, 3) if restrict_to_opens else rng.randint(0, 5)
    associated = [
        {
            "mac": fake_client_mac(f"karma-client:{i}"),
            "ssid": rng.choice(ssids_impersonated),
            "duration_s": rng.randint(10, 120),
        }
        for i in range(n_associated)
    ]

    return mark_synthetic({
        "probes_seen": probes_seen,
        "ssids_impersonated": ssids_impersonated,
        "clients_associated": associated,
        "duration_s": duration_s,
        "restrict_to_opens": restrict_to_opens,
    })
