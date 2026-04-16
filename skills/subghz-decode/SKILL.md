---
name: subghz_decode
description: >
  Decode known sub-GHz protocols from a captured IQ file or live capture.
  Recognizes weather stations, doorbells, garage remotes, tire-pressure
  sensors, and many other ISM-band devices. Passive.
parameters_schema:
  type: object
  properties:
    capture_file:
      type: string
      description: Path to a captured IQ file. If omitted, performs a live capture.
    frequency_mhz:
      type: number
      description: Frequency to capture/decode. Default 433.92.
    duration_s:
      type: integer
      description: For live capture - duration. Default 10.
    protocols:
      type: array
      items: {type: string}
      description: Protocol filter (e.g. ["keeloq", "acurite"]). Omit for all known.
  required: []
typical_duration_s: 15
sensitivity: passive
allowed_tools:
  - subghz_decode
pivot_hints:
  - when: "summary.has_rolling_code == true"
    suggest: "Rolling-code protocol detected — plain subghz_replay will NOT work. Rolljam/rollback attacks require capture of an unused code during intended operation; flag this to the operator."
  - when: "summary.decoded_count >= 1"
    suggest: "Signals decoded — subghz_replay (action=analyze) can confirm the modulation/bitrate, and subghz_replay (action=replay) can retransmit the capture if the protocol is fixed-code."
---

# Sub-GHz Decode

Identifies and decodes sub-GHz protocols against the `rtl_433` database
(~200 known protocols). Works on captured IQ or live RX.

## What it returns

```json
{
  "frequency_mhz": 433.92,
  "decoded": [
    {
      "protocol": "Acurite-Tower",
      "device_id": 12345,
      "values": {"temp_c": 22.4, "humidity_pct": 45, "battery": "ok"},
      "timestamp": "2026-04-20T14:30:12Z"
    },
    {
      "protocol": "KeeLoq",
      "serial": "0x1A2B3C",
      "button": "unlock",
      "rolling_counter": 47211,
      "is_rolling": true
    }
  ],
  "unknown_signals": 3,
  "duration_s": 10
}
```

## Implementation

`rtl_433` (works with HackRF via `-d` flag, or reads IQ files). Parse
its JSON output and include in the result.

```
rtl_433 -F json -f 433920000 -s 2000000 -T 10
```

## Scope

- Passive observation — no transmission
- Weather data and similar are not personally identifying
- Automotive KeeLoq captures are recorded for analysis; replay requires
  `subghz_replay` which has its own disclosure
