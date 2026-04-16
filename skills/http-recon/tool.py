"""FAKE: synthetic HTTP/web recon."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import mark_synthetic, pack_summary, _rng
from faust.tools.registry import ToolResult


_PATHS = [
    ("/", 200, 4200),
    ("/admin", 200, 1842),
    ("/admin/login", 200, 2100),
    ("/.git/config", 200, 92),
    ("/.env", 403, 0),
    ("/robots.txt", 200, 128),
    ("/api/v1/users", 401, 42),
    ("/api/v1/health", 200, 22),
    ("/wp-admin/", 302, 0),
    ("/phpinfo.php", 404, 0),
    ("/backup.zip", 404, 0),
    ("/server-status", 403, 0),
    ("/actuator/env", 200, 3821),
]

# Paths that almost always indicate a weakness the planner should flag.
_VULN_INDICATORS = {"/.git/config", "/.env", "/actuator/env", "/server-status", "/phpinfo.php", "/backup.zip"}


def execute(args: dict[str, Any]) -> ToolResult:
    target_url = args.get("target_url", "https://target.example.com")
    wordlist = args.get("wordlist", "common")
    threads = int(args.get("threads", 10))
    recursive = args.get("recursive", False)

    rng = _rng(f"http_recon:{target_url}:{wordlist}")

    # Pick a realistic subset of the hits.
    endpoints = rng.sample(_PATHS, k=min(rng.randint(4, 8), len(_PATHS)))
    endpoints_found = [
        {"path": p, "status": status, "length": length}
        for (p, status, length) in sorted(endpoints, key=lambda e: e[0])
    ]

    tech_pool = ["nginx/1.24.0", "PHP", "WordPress 6.4", "jQuery 3.6",
                 "Apache Tomcat 9", "Django 4.2", "Express 4", "nginx 1.18.0"]
    technologies = rng.sample(tech_pool, k=rng.randint(2, 4))

    # Total requests loosely matches wordlist size.
    total_requests = {"common": 4200, "big": 220000, "api": 1100}.get(wordlist, 4200)
    duration_s = total_requests // (threads * 90)

    result = mark_synthetic({
        "target": target_url,
        "server": technologies[0] if technologies else "unknown",
        "technologies": technologies,
        "endpoints_found": endpoints_found,
        "total_requests": total_requests,
        "scan_duration_s": max(5, duration_s),
        "recursive": bool(recursive),
    })

    vuln_hits = [e for e in endpoints_found if e["path"] in _VULN_INDICATORS and e["status"] < 400]
    admin_hits = [e for e in endpoints_found if "admin" in e["path"] and e["status"] < 400]
    summary = pack_summary({
        "endpoints_found": len(endpoints_found),
        "vuln_indicators": len(vuln_hits),
        "admin_endpoints": len(admin_hits),
        "server": technologies[0] if technologies else "unknown",
        "first_vuln_path": vuln_hits[0]["path"] if vuln_hits else None,
    })
    return ToolResult(result=result, summary=summary)
