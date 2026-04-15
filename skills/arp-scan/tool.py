"""FAKE: synthetic ARP enumeration."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import fake_mac, mark_synthetic, _rng


_VENDORS = ["Apple", "Samsung", "Cisco", "TP-Link", "Netgear", "Intel", "Espressif"]


def execute(args: dict[str, Any]) -> dict[str, Any]:
    interface = args.get("interface", "wlan0")
    subnet = args.get("subnet", "192.168.1.0/24")
    timeout_s = int(args.get("timeout_s", 5))

    rng = _rng(f"arp_scan:{interface}:{subnet}")

    base = subnet.split("/")[0].rsplit(".", 1)[0]
    count = rng.randint(5, 14)
    hosts = []
    for i in range(count):
        seed = f"arp:{subnet}:h{i}"
        hr = _rng(seed)
        vendor = hr.choice(_VENDORS)
        hosts.append({
            "ip": f"{base}.{hr.randint(2, 254)}",
            "mac": fake_mac(vendor, seed),
            "vendor": vendor,
        })

    # Dedupe by IP.
    seen, unique = set(), []
    for h in hosts:
        if h["ip"] not in seen:
            seen.add(h["ip"])
            unique.append(h)
    unique.sort(key=lambda h: tuple(int(x) for x in h["ip"].split(".")))

    return mark_synthetic({
        "interface": interface,
        "subnet": subnet,
        "hosts": unique,
        "host_count": len(unique),
        "scan_duration_s": round(rng.uniform(1.5, timeout_s), 1),
    })
