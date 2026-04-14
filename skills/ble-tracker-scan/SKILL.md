---
name: ble_tracker_scan
description: >
  Scan for BLE tracking devices (AirTags, Tile, Chipolo, Samsung SmartTag)
  that may be following the operator. Detects trackers not paired with
  the operator's own devices. Privacy / counter-surveillance tool. Passive.
parameters_schema:
  type: object
  properties:
    duration_s:
      type: integer
      description: >
        Scan duration. AirTags rotate their public key every 15 minutes —
        longer scans (>900s) can detect rotation patterns. Default 300.
    min_sightings:
      type: integer
      description: >
        Minimum sightings before alerting. A tracker that only appears
        once is likely passing through; one seen 5+ times over 5 minutes
        is likely following you. Default 3.
    known_devices:
      type: array
      items:
        type: string
      description: >
        MAC addresses of known-friendly trackers (your own AirTags, your
        partner's Tile, etc.). Excluded from alerts.
  required: []
sensitivity: passive
allowed_tools:
  - ble_tracker_scan
---

# BLE Tracker Scan

Privacy and counter-surveillance tool. Scans for BLE trackers that may be
attached to the operator or their belongings without consent. Detects
AirTags, Tiles, Chipolos, and Samsung SmartTags.

Modeled after Apple's Tracker Detect (Android) and AirGuard, but device-
agnostic and runnable on demand.

## What it returns

```json
{
  "scan_duration_s": 300,
  "devices_seen": 47,
  "suspected_trackers": [
    {
      "type": "airtag",
      "mac": "6a:7b:8c:9d:ae:bf",
      "rssi_history": [-58, -55, -62, -60, -57],
      "sightings": 12,
      "first_seen": "2026-04-20T14:30:00Z",
      "last_seen": "2026-04-20T14:35:00Z",
      "moving_with_operator": true,
      "estimated_distance_m": 1.5
    },
    {
      "type": "tile",
      "mac": "c4:d5:e6:f7:08:19",
      "sightings": 5,
      "moving_with_operator": false
    }
  ]
}
```

## Hardware

- **ESP32-S3 Marauder** (preferred — BLE scan performance)
- Pi 5 onboard Bluetooth via `bleak` (fallback)

## Implementation notes

Tracker fingerprinting is pattern-based:

**AirTag:**
- Advertises as Apple iBeacon (company code 0x004C)
- Specific byte pattern in manufacturer data: `0x12, 0x19`
- MAC address rotates every 15 minutes; UID is the service payload hash
- Will emit a sound when separated from owner for >8-24h (useful confirmation)

**Tile:**
- Advertises service UUID `0000FEED-0000-1000-8000-00805F9B34FB`
- Plus Tile-specific service `0000FEEC-...`

**Chipolo:**
- Advertises service UUID `0000FE8C-...`

**Samsung SmartTag:**
- Advertises company code 0x0075 (Samsung)
- Specific byte pattern in manufacturer data

The "moving_with_operator" heuristic requires GPS context:
- If the same tracker is seen over a GPS distance of >500m without
  intermediate signal loss, it's likely traveling with you
- Cross-reference with the `wardrive` skill's GPS coordinates

## Why this matters

- Stalkerware via commodity trackers is an active and growing threat
- Neither iOS nor Android reliably detect cross-platform trackers
  (Apple's Find My alerts iPhones about unknown AirTags, but not Tiles
  or Chipolos; Android covers AirTags only if Tracker Detect is installed)
- A dedicated scan device with BLE monitoring is the only reliable way
  to check

## Typical workflow

1. Return home from somewhere you suspect (dating app meetup, hotel, etc.)
2. `ble_tracker_scan duration_s=600 known_devices=[your own AirTags]`
3. Review any suspected trackers
4. If a tracker is moving with you, physically locate it (use RSSI
   gradient — move around and find the RSSI peak)
