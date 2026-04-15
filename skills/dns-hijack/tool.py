"""FAKE: synthetic DNS hijacking."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import fake_capture_path, mark_synthetic, _rng


def execute(args: dict[str, Any]) -> dict[str, Any]:
    interface = args.get("interface", "wlan0")
    mappings = args.get("mappings") or []
    duration_s = int(args.get("duration_s", 60)) or 60

    rng = _rng(f"dns_hijack:{interface}:{len(mappings)}")

    # Baseline query volume plus the hijacked domain redirections.
    queries_seen = duration_s * rng.randint(2, 8)
    queries_redirected = 0
    if mappings:
        # ~10-30% of queries hit our target domains.
        queries_redirected = int(queries_seen * rng.uniform(0.1, 0.3))

    clients = [f"192.168.1.{rng.randint(10, 200)}" for _ in range(rng.randint(1, 3))]

    return mark_synthetic({
        "interface": interface,
        "mappings": mappings,
        "duration_s": duration_s,
        "queries_seen": queries_seen,
        "queries_redirected": queries_redirected,
        "clients_affected": list(set(clients)),
        "log_file": fake_capture_path("dns_hijack", "log"),
    })
