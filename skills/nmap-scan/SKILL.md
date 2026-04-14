---
name: nmap_scan
description: >
  Active network port scan. Returns open ports, services, versions, and OS
  fingerprint for target hosts. Sends probe packets — observable on the network.
parameters_schema:
  type: object
  properties:
    target:
      type: string
      description: Target host, CIDR, or IP range (e.g. "192.168.1.0/24" or "10.0.0.5")
    ports:
      type: string
      description: Port spec — "top1000" (default), "all", or range "1-65535"
    scan_type:
      type: string
      enum: ["connect", "syn", "udp", "version", "script_default"]
      description: SYN is fastest but needs root. Connect works unprivileged. Default "syn".
    timing:
      type: integer
      description: Timing template 0-5. Higher is faster, more detectable. Default 3.
  required:
    - target
sensitivity: active
allowed_tools:
  - nmap_scan
---

# Nmap Scan

Standard active network reconnaissance via nmap. Identifies live hosts,
open ports, running services, and (with version detection) software versions.

## What it returns

```json
{
  "hosts": [{
    "ip": "192.168.1.10",
    "hostname": "router.local",
    "status": "up",
    "os": "Linux 4.x",
    "open_ports": [
      {"port": 22, "service": "ssh", "version": "OpenSSH 8.9"},
      {"port": 80, "service": "http", "version": "nginx 1.24"}
    ]
  }],
  "scan_duration_s": 12.4
}
```

## Implementation

`nmap` CLI is the standard. Use `-oX` for XML output and parse it with `python-nmap`
or `xml.etree`. Requires `nmap` installed. SYN scans need `sudo`.

## Scope

- Active scans show up in target IDS/firewall logs
- Only scan networks you have authorization to test
- Timing template 3 is balanced; 5 is fast but noisy
