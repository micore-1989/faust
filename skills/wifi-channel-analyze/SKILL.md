---
name: wifi_channel_analyze
description: >
  Survey 2.4/5 GHz WiFi channel utilization. Identifies congested channels,
  interferers, and where to place a new AP. Passive.
parameters_schema:
  type: object
  properties:
    interface:
      type: string
      description: Monitor-mode interface
    band:
      type: string
      enum: ["2.4", "5", "all"]
      description: Band to scan. Default "all".
    duration_s:
      type: integer
      description: Time per channel, seconds. Default 3.
  required:
    - interface
sensitivity: passive
allowed_tools:
  - wifi_channel_analyze
---

# WiFi Channel Analyze

Measures per-channel airtime utilization, frame counts, and noise floor.
Complements `wifi_scan` — instead of listing networks, maps RF conditions
across the band.

## What it returns

```json
{
  "band": "all",
  "channels": [
    {"channel": 1, "freq_mhz": 2412, "utilization_pct": 12,
     "frame_count": 842, "avg_rssi_dbm": -72},
    {"channel": 6, "freq_mhz": 2437, "utilization_pct": 67,
     "frame_count": 4291, "avg_rssi_dbm": -45},
    {"channel": 36, "freq_mhz": 5180, "utilization_pct": 3,
     "frame_count": 97, "avg_rssi_dbm": -68}
  ],
  "recommendation": "5 GHz channels 36-48 have lowest utilization"
}
```

## Implementation

Hop through channels with `iw dev wlan1 set channel X`, sniff for the
duration, count frames and estimate airtime from frame durations.

## Scope

- Fully passive — only listens
- Takes ~90s for full 2.4+5 GHz sweep at default duration
