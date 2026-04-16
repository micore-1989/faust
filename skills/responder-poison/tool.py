"""FAKE: synthetic Responder LLMNR/NBT-NS poisoning."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import (
    fake_capture_path, fake_hash, ago_iso, mark_synthetic, pack_summary, _rng,
)
from faust.tools.registry import ToolResult


_FAKE_USERS = ["alice", "bob", "admin", "svc_backup", "jsmith", "mgarcia"]
_FAKE_DOMAINS = ["CORP", "ACME", "INTERNAL"]


def execute(args: dict[str, Any]) -> ToolResult:
    interface = args.get("interface", "wlan0")
    duration_s = int(args.get("duration_s", 300))
    protocols = args.get("protocols") or ["LLMNR", "NBT-NS", "mDNS"]
    analyze_mode = args.get("analyze_mode", False)

    rng = _rng(f"responder:{interface}:{duration_s}:{analyze_mode}")

    poisoned_queries = duration_s // 2 + rng.randint(0, duration_s)

    if analyze_mode:
        result = mark_synthetic({
            "interface": interface,
            "duration_s": duration_s,
            "protocols": protocols,
            "analyze_mode": True,
            "poisoned_queries": 0,
            "queries_observed": poisoned_queries,
            "hashes_captured": [],
        })
        summary = pack_summary({
            "analyze_mode": True,
            "queries_observed": poisoned_queries,
            "hashes_captured": 0,
        })
        return ToolResult(result=result, summary=summary)

    # Random chance of capturing 0-3 hashes.
    n_hashes = rng.choice([0, 0, 1, 1, 2, 3])
    hashes = []
    for i in range(n_hashes):
        seed = f"responder:hash:{i}"
        hr = _rng(seed)
        domain = hr.choice(_FAKE_DOMAINS)
        user = hr.choice(_FAKE_USERS)
        hashes.append({
            "hash_type": "NTLMv2",
            "username": f"{domain}\\{user}",
            "source_ip": f"192.168.1.{hr.randint(10, 200)}",
            "timestamp": ago_iso(duration_s - i * 30),
            "hash": fake_hash(64, seed),
        })

    log_file = fake_capture_path("responder", "log")
    result = mark_synthetic({
        "interface": interface,
        "duration_s": duration_s,
        "protocols": protocols,
        "poisoned_queries": poisoned_queries,
        "hashes_captured": hashes,
        "log_file": log_file,
    })
    summary = pack_summary({
        "hashes_captured": len(hashes),
        "unique_users": len({h["username"] for h in hashes}),
        "hash_type": hashes[0]["hash_type"] if hashes else None,
        "first_username": hashes[0]["username"] if hashes else None,
        "log_file": log_file,
    })
    return ToolResult(result=result, summary=summary)
