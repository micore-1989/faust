---
name: ir_capture
description: >
  Capture and replay infrared remote control signals. Records IR codes from
  the TSOP38238 receiver and replays them via the IR LED. Capture is passive;
  replay is active.
parameters_schema:
  type: object
  properties:
    action:
      type: string
      enum: ["capture", "replay"]
      description: >
        "capture" = listen for IR signals and decode them.
        "replay" = transmit a previously captured IR code.
    timeout_s:
      type: integer
      description: >
        For capture mode: how long to wait for an IR signal in seconds.
        Default 15.
    protocol:
      type: string
      enum: ["nec", "rc5", "rc6", "sony", "samsung", "raw", "auto"]
      description: >
        IR protocol to expect/transmit. "auto" attempts protocol detection
        during capture. "raw" captures/replays raw pulse timings without
        protocol decoding. Default "auto".
    code:
      type: string
      description: >
        For replay mode: the IR code to transmit. Hex string for protocol-
        decoded codes (e.g. "20DF10EF"), or JSON array of pulse/gap
        microsecond timings for raw mode.
    repeat:
      type: integer
      description: >
        Number of times to transmit the code. Some devices require 2-3
        repeats. Default 3.
  required:
    - action
sensitivity: active
allowed_tools:
  - ir_capture
---

# IR Capture & Replay

Captures infrared remote control signals and replays them. Useful for
interacting with TVs, projectors, HVAC systems, and other IR-controlled
equipment during physical security assessments.

## What it returns

Capture mode:
```json
{
  "action": "capture",
  "protocol": "nec",
  "address": "04",
  "command": "08",
  "code_hex": "20DF10EF",
  "raw_timings_us": [9000, 4500, 560, 560, 560, 1690, ...],
  "confidence": 0.98
}
```

Replay mode:
```json
{
  "action": "replay",
  "protocol": "nec",
  "code_hex": "20DF10EF",
  "repeats_sent": 3,
  "success": true
}
```

## Hardware

- **TSOP38238** — 38 kHz IR receiver module. Demodulates the 38 kHz carrier
  and outputs the raw envelope signal. Connected to a Pi GPIO input pin.
- **IR LED** — high-output infrared LED driven through an IRLZ44N MOSFET from
  a Pi GPIO output pin. The MOSFET allows driving the LED at higher current
  than the Pi GPIO can source directly (~100mA vs 16mA).

## Implementation notes

Uses `lgpio` for precise GPIO timing (required for IR — timing-critical
protocol, microsecond-level accuracy matters). `pigpio` does NOT support Pi 5
(GPIO moved to the RP1 southbridge); `lgpio` is the successor with Pi 5
support and hardware-timed waveforms via `tx_wave()`. The Pi's hardware PWM
can generate the 38 kHz carrier for transmission.

Protocol decoding:
- **NEC** — most common (LG, Samsung, many consumer devices). 32-bit code.
- **RC5/RC6** — Philips standard. Manchester-encoded.
- **Sony SIRC** — 12/15/20-bit variants.
- **Raw** — fallback when protocol detection fails. Captures and replays
  exact pulse/gap timings.

The IR LED's effective range is ~5-8m with the MOSFET driver. For longer range,
a higher-current LED or lens focusing would be needed (MK2 consideration).

## Typical workflow

1. `ir_capture action=capture` — point a remote at the TSOP38238, press a button
2. Operator reviews the decoded signal
3. `ir_capture action=replay code=20DF10EF` — replay toward the target device
4. Verify the device responded (e.g., TV turned off)
