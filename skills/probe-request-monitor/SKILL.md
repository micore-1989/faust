---
name: probe_request_monitor
description: >
  Track 802.11 probe requests to build a device inventory of who's nearby
  and what networks they remember. Privacy/awareness tool. Passive.
parameters_schema:
  type: object
  properties:
    interface:
      type: string
      description: Monitor-mode interface
    duration_s:
      type: integer
      description: Monitoring duration. Default 300.
    deanonymize:
      type: boolean
      description: Correlate randomized MACs across time windows to track real devices. Default true.
  required:
    - interface
sensitivity: passive
allowed_tools:
  - probe_request_monitor
---

# Probe Request Monitor

Listens for 802.11 probe requests and records each device's remembered
SSIDs. Useful for understanding what clients expect in the area (shapes
karma/evil-portal targeting), detecting persistent visitors, or auditing
your own devices' MAC randomization behavior.

## What it returns

```json
{
  "duration_s": 300,
  "device_count": 34,
  "devices": [
    {
      "mac": "aa:bb:cc:dd:ee:ff",
      "randomized": false,
      "vendor": "Apple",
      "probed_ssids": ["HomeWiFi", "Starbucks", "attwifi"],
      "first_seen": "2026-04-20T14:30:00Z",
      "last_seen": "2026-04-20T14:34:58Z",
      "probe_count": 47
    }
  ]
}
```

## Implementation

Scapy sniff for Dot11ProbeReq frames. For deanonymization, cluster
randomized MACs by their probe-request contents + inter-arrival timing
(common research heuristic: same SSID list + similar timing = same device).

## Scope

- Listening to broadcast probes is legal in most jurisdictions
- Storing MAC→SSID mappings long-term raises privacy concerns;
  data kept to `captures/` with automatic rotation
