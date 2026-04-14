---
name: ble_spam
description: >
  Flood BLE advertisement packets targeting iOS/Android/Windows pairing
  prompts (SwiftPair, QuickShare, iOS proximity dialogs). DISRUPTIVE —
  causes notification spam on nearby devices.
parameters_schema:
  type: object
  properties:
    mode:
      type: string
      enum: ["ios_proximity", "swift_pair", "fast_pair", "all"]
      description: >
        Which advertisement type to spam.
        "ios_proximity" = Apple Continuity (AirPods, AirTag setup dialogs).
        "swift_pair" = Windows Swift Pair device-discovery popups.
        "fast_pair" = Google Fast Pair Android popups.
        "all" = rotate through all three.
    duration_s:
      type: integer
      description: How long to spam, in seconds. Default 30.
    interval_ms:
      type: integer
      description: Milliseconds between adverts. Default 20 (50 Hz). Minimum 10.
  required:
    - mode
sensitivity: disruptive
allowed_tools:
  - ble_spam
---

# BLE Spam

Floods BLE advertisements that trigger pairing/proximity prompts on nearby
devices. Used to demo the lack of authentication in BLE advertisement
protocols and to test how defenders respond to nuisance RF attacks.

## What it returns

```json
{
  "mode": "ios_proximity",
  "duration_s": 30,
  "advertisements_sent": 1500,
  "interval_ms": 20,
  "success": true
}
```

## Hardware

- **ESP32-S3 Marauder** — primary. Marauder firmware supports
  `spam apple`, `spam windows`, `spam google`, and `spam samsung` commands.
  The ESP32-S3's BLE radio is well-suited for rapid advertisement cycling.

## Implementation notes

Send the appropriate command to Marauder over USB-serial:

- iOS proximity: `spam apple`
- Swift Pair: `spam windows`
- Fast Pair: `spam google`
- Samsung QuickShare: `spam samsung`

Each advertisement rotates through a list of fake device names and
manufacturer data to maximize popup generation. Marauder handles the
timing internally — `interval_ms` is a hint, not strict.

Stop with `stopspam`.

## Why it's disruptive

- On iOS, this can cause devices to crash (iOS < 17.2 had a known DOS)
- Users experience a flood of unwanted notifications
- In public spaces this affects bystanders who have not consented
- Newer Apple devices patched the crash bug; modern iOS just shows the popup

## Scope requirements

- NEVER run in public spaces, offices, or near anyone not in-scope
- Testing MUST be on devices you own in an isolated environment
- The disclosure layer will require hold-to-confirm
- The journal records the duration and mode but not target identities

## Typical workflow

1. `ble_scan` — survey what devices are present
2. `ble_spam mode=all duration_s=15` (this skill) — test detection
3. Review: did defender systems/users notice? What was logged?
