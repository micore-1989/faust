---
name: ble_pair_bruteforce
description: >
  Brute-force BLE pairing PINs against a target device. DISRUPTIVE — generates
  many failed pairing attempts, which most devices will log and alert on.
parameters_schema:
  type: object
  properties:
    mac:
      type: string
      description: Target BLE MAC
    pin_list:
      type: string
      enum: ["common", "numeric4", "numeric6", "custom"]
      description: PIN set — "common" (0000, 1234, 1111...), numeric4/6 exhaustive. Default "common".
    custom_pins:
      type: array
      items: {type: string}
      description: PINs to try if pin_list=custom
    delay_ms:
      type: integer
      description: Wait between attempts. Too fast triggers rate limits. Default 500.
  required:
    - mac
typical_duration_s: 240
sensitivity: disruptive
allowed_tools:
  - ble_pair_bruteforce
---

# BLE Pair Bruteforce

Tries pairing PINs against a BLE device. Mostly effective against older or
cheaply-designed devices that accept static PINs and don't rate-limit.

## What it returns

```json
{
  "mac": "aa:bb:cc:dd:ee:ff",
  "attempts": 47,
  "success": true,
  "pin": "0000",
  "duration_s": 24
}
```

## Implementation

`bluetoothctl` scripted, or `bleak` with manual Legacy Pairing exchange.
Most modern devices use LE Secure Connections (ECDH), which can't be
brute-forced this way.

## Scope

- Very noisy — devices log pairing failures
- Many devices lock after N attempts
- Only on devices you own, for authorized assessment
