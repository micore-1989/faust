---
name: arp_scan
description: >
  Passively enumerate hosts on the local Ethernet/WiFi segment by sending
  ARP requests. Faster than ICMP scans, works behind firewalls that block ping.
parameters_schema:
  type: object
  properties:
    interface:
      type: string
      description: Network interface to scan from (e.g. wlan0, usb0, eth0)
    subnet:
      type: string
      description: CIDR subnet, auto-detected from interface if omitted
    timeout_s:
      type: integer
      description: Seconds to wait for replies. Default 5.
  required:
    - interface
typical_duration_s: 15
sensitivity: passive
allowed_tools:
  - arp_scan
---

# ARP Scan

Layer-2 host discovery. Sends ARP Who-Has broadcasts and listens for replies.
Only works on the local broadcast domain but is extremely fast (<5s for /24)
and bypasses any IP-layer filtering.

## What it returns

```json
{
  "interface": "wlan0",
  "subnet": "192.168.1.0/24",
  "hosts": [
    {"ip": "192.168.1.1", "mac": "aa:bb:cc:dd:ee:ff", "vendor": "TP-Link"},
    {"ip": "192.168.1.42", "mac": "11:22:33:44:55:66", "vendor": "Apple"}
  ],
  "host_count": 12,
  "scan_duration_s": 4.2
}
```

## Implementation

`arp-scan` CLI (`sudo arp-scan --interface=X --localnet`) or scapy
(`srp(Ether(dst='ff:ff:ff:ff:ff:ff')/ARP(pdst=subnet), timeout=5)`).
MAC-to-vendor lookup via the IEEE OUI database (ships with `arp-scan`).

## Scope

- Passive from a detection standpoint — looks like normal ARP traffic
- Still requires authorization to be on the network
