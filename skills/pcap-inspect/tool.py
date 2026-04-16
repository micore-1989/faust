"""FAKE: synthetic pcap analysis."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import fake_bssid, fake_hash, mark_synthetic, pack_summary, _rng
from faust.tools.registry import ToolResult


def execute(args: dict[str, Any]) -> ToolResult:
    pcap_path = args.get("pcap_path", "captures/unknown.pcap")
    extract = args.get("extract") or ["creds", "dns", "http", "handshakes"]
    max_items = int(args.get("max_items_per_category", 50))

    rng = _rng(f"pcap_inspect:{pcap_path}:{','.join(extract)}")

    result: dict[str, Any] = {
        "pcap_path": pcap_path,
        "packet_count": rng.randint(1500, 50_000),
    }

    if "creds" in extract or "all" in extract:
        n = rng.randint(0, min(3, max_items))
        result["credentials"] = [
            {
                "protocol": rng.choice(["http-basic", "ftp", "telnet"]),
                "user": rng.choice(["alice", "admin", "user"]),
                "pass_sha256": fake_hash(64, f"pcap:cred:{i}"),
            }
            for i in range(n)
        ]

    if "dns" in extract or "all" in extract:
        domains = ["analytics.example.com", "cdn.example.com", "login.target.com",
                   "telemetry.microsoft.com", "doh.example"]
        n = rng.randint(1, min(5, max_items))
        result["dns_queries"] = [
            {"name": rng.choice(domains), "count": rng.randint(1, 200)}
            for _ in range(n)
        ]

    if "http" in extract or "all" in extract:
        n = rng.randint(0, min(5, max_items))
        result["http_requests"] = [
            {"method": rng.choice(["GET", "POST", "PUT"]),
             "url": f"https://target/{rng.choice(['login', 'api/v1/users', 'assets/app.js'])}",
             "user_agent": "Mozilla/5.0"}
            for _ in range(n)
        ]

    if "handshakes" in extract or "all" in extract:
        n = rng.randint(0, 2)
        result["wpa_handshakes"] = [
            {
                "bssid": fake_bssid(f"pcap:hs:{i}"),
                "ssid": rng.choice(["TargetNet", "CorpWiFi", "HomeWiFi"]),
                "hash_file": f"captures/extracted_{i}.22000",
            }
            for i in range(n)
        ]

    result = mark_synthetic(result)

    # Opinion fields — what should the planner pivot on?
    handshakes = result.get("wpa_handshakes", [])
    creds = result.get("credentials", [])
    summary = pack_summary({
        "packet_count": result["packet_count"],
        "handshakes_count": len(handshakes),
        "has_crackable_hash": bool(handshakes),
        "first_hash_file": handshakes[0]["hash_file"] if handshakes else None,
        "creds_count": len(creds),
        "dns_queries_count": len(result.get("dns_queries", [])),
        "http_requests_count": len(result.get("http_requests", [])),
    })
    return ToolResult(result=result, summary=summary)
