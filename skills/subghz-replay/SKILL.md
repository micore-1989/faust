---
name: subghz_replay
description: >
  Capture or replay a sub-GHz RF signal (keyfobs, garage door openers,
  wireless doorbells, weather stations). Capture is passive; replay is
  disruptive — transmits on licensed RF bands.
parameters_schema:
  type: object
  properties:
    action:
      type: string
      enum: ["capture", "replay", "analyze"]
      description: >
        "capture" = listen on a frequency and record raw IQ.
        "replay" = retransmit a previously captured signal.
        "analyze" = decode protocol (OOK/FSK, bitrate, modulation) from capture.
    frequency_mhz:
      type: number
      description: >
        Center frequency in MHz. Common: 315, 433.92, 868, 915.
    sample_rate:
      type: integer
      description: Sample rate in Hz. Default 2000000 (2 Msps).
    duration_s:
      type: integer
      description: Capture or replay duration in seconds. Default 5.
    capture_file:
      type: string
      description: >
        For replay/analyze: path to a previously captured IQ file.
        For capture: output path, auto-generated if omitted.
    repeats:
      type: integer
      description: For replay mode - how many times to transmit. Default 3.
    radio:
      type: string
      enum: ["hackrf", "cc1101"]
      description: >
        Which radio to use. HackRF has better range and broader frequency
        coverage (100 kHz – 6 GHz). CC1101 is a backup for 300-928 MHz
        with lower power. Default "hackrf".
  required:
    - action
    - frequency_mhz
sensitivity: active
allowed_tools:
  - subghz_replay
---

# Sub-GHz Capture & Replay

Captures and retransmits low-frequency RF signals in the 300-930 MHz range
where most consumer wireless devices operate — garage doors, car keyfobs,
wireless doorbells, 433 MHz sensors, etc.

## What it returns

Capture mode:
```json
{
  "action": "capture",
  "frequency_mhz": 433.92,
  "sample_rate": 2000000,
  "duration_s": 5,
  "capture_file": "captures/rf_433920000_1745174400.iq",
  "peak_dbm": -42,
  "signal_detected": true
}
```

Replay mode:
```json
{
  "action": "replay",
  "frequency_mhz": 433.92,
  "capture_file": "captures/rf_433920000_1745174400.iq",
  "repeats_sent": 3,
  "success": true
}
```

Analyze mode:
```json
{
  "action": "analyze",
  "capture_file": "...",
  "modulation": "OOK",
  "bitrate_bps": 2400,
  "decoded": "011010110010110...",
  "likely_protocol": "PT2262 / EV1527",
  "is_rolling_code": false
}
```

## Hardware

- **HackRF Pro** (primary) — 100 kHz – 6 GHz, 20 Msps. Covers any sub-GHz
  band with excellent sensitivity and TX power. USB-C.
- **CC1101** (backup) — 300-928 MHz only, low power. Useful when HackRF is
  busy with another skill or for battery-saving operation.

## Implementation notes

**Capture (HackRF):**
```
hackrf_transfer -r capture.iq -f 433920000 -s 2000000 -n <samples>
```

**Replay (HackRF):**
```
hackrf_transfer -t capture.iq -f 433920000 -s 2000000 -x 40
```

The `-x 40` sets TX gain (max 47); adjust based on range vs. risk of RF
splatter on adjacent frequencies.

**Analyze:** use `urh` (Universal Radio Hacker) as a subprocess, or
`rtl_433` for known protocol decoding. URH is more flexible but slower.

## Rolling codes

Modern car keyfobs and many garage doors use rolling codes — a captured
signal is valid only once. A simple replay will fail. The `analyze` mode
flags `is_rolling_code: true` when it detects KeeLoq or similar schemes.
Dealing with rolling codes is out of scope for MK1 (requires rollback /
desync attacks like RollJam, which are significantly more involved and
legally sensitive).

## Scope requirements

- **Transmitting on licensed RF bands is regulated.** In the US, FCC Part 15
  permits low-power transmission on 315/433/915 MHz under specific limits.
  Replaying captured signals exceeds what Part 15 intends.
- Operator must have authorization for the target system
- Testing on owned garage doors, keyfobs, doorbells ONLY
- NEVER transmit near public infrastructure (garage doors at hotels,
  commercial buildings, etc.)

## Typical workflow

1. `subghz_replay action=capture frequency_mhz=433.92` — press button on target
2. `subghz_replay action=analyze capture_file=<path>` — decode the protocol
3. If not rolling-code: `subghz_replay action=replay capture_file=<path>`
