"""FAKE: synthetic nmap port scan."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import mark_synthetic, _rng


_COMMON_SERVICES = {
    22:   ("ssh", "OpenSSH 8.9"),
    80:   ("http", "nginx 1.24"),
    443:  ("https", "nginx 1.24 (TLSv1.3)"),
    445:  ("microsoft-ds", "Samba 4.18"),
    3306: ("mysql", "MySQL 8.0"),
    5432: ("postgresql", "PostgreSQL 15"),
    8080: ("http-alt", "Apache Tomcat"),
    3389: ("ms-wbt-server", "Microsoft RDP"),
    23:   ("telnet", "legacy telnetd"),
    21:   ("ftp", "vsftpd 3.0"),
    25:   ("smtp", "Postfix 3.7"),
    53:   ("dns", "BIND 9.18"),
}


def execute(args: dict[str, Any]) -> dict[str, Any]:
    target = args.get("target", "192.168.1.0/24")
    ports = args.get("ports", "top1000")
    scan_type = args.get("scan_type", "syn")
    timing = int(args.get("timing", 3))

    rng = _rng(f"nmap:{target}:{ports}:{scan_type}")

    # Generate 2-5 live hosts.
    host_count = 1 if "/" not in target else rng.randint(2, 5)
    base_ip = target.split("/")[0].rsplit(".", 1)[0]

    hosts = []
    for i in range(host_count):
        seed = f"nmap:{target}:host{i}"
        hr = _rng(seed)
        ip = target.split("/")[0] if host_count == 1 else f"{base_ip}.{hr.randint(2, 254)}"
        # Each host has 1-5 open ports from the common set.
        n_ports = hr.randint(1, 5)
        port_keys = hr.sample(list(_COMMON_SERVICES.keys()), k=min(n_ports, len(_COMMON_SERVICES)))
        open_ports = [
            {"port": p, "service": _COMMON_SERVICES[p][0], "version": _COMMON_SERVICES[p][1]}
            for p in sorted(port_keys)
        ]
        hosts.append({
            "ip": ip,
            "hostname": hr.choice(["router.local", "server.local", "nas.local", None]),
            "status": "up",
            "os": hr.choice(["Linux 5.x", "Linux 6.x", "Windows 10", "macOS 14", "OpenWrt"]),
            "open_ports": open_ports,
        })

    return mark_synthetic({
        "target": target,
        "scan_type": scan_type,
        "timing": timing,
        "hosts": hosts,
        "scan_duration_s": round(rng.uniform(3.0, 25.0), 1),
    })
