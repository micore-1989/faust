---
name: nfc_emulate
description: >
  Emulate an NFC/RFID tag using the PN532 in target (emulation) mode. The
  tag data comes from a previous nfc_read capture, or from an explicit
  payload. ACTIVE — the emulated tag responds to readers in range.
parameters_schema:
  type: object
  properties:
    action:
      type: string
      enum: ["emulate_uid", "emulate_tag", "emulate_ndef"]
      description: >
        "emulate_uid" = minimum spoof, just return a UID (works against
        many access control readers that only check UID).
        "emulate_tag" = full MIFARE Classic / NTAG emulation with sector data.
        "emulate_ndef" = emulate a writable NDEF tag (e.g. URL redirect).
    uid:
      type: string
      description: >
        Hex-encoded UID to emulate (e.g. "04A23B1CD45880"). Required for
        emulate_uid; used as UID for emulate_tag and emulate_ndef.
    source_file:
      type: string
      description: >
        Path to a JSON file from a previous nfc_read capture. Used for
        emulate_tag (provides the full sector/block data).
    ndef_payload:
      type: string
      description: >
        NDEF record payload as a URI string. Used for emulate_ndef.
        Example - "https://example.com" or "tel:+15551234567".
    duration_s:
      type: integer
      description: >
        How long to emulate, in seconds. 0 = until manually stopped.
        Default 60.
  required:
    - action
sensitivity: active
allowed_tools:
  - nfc_emulate
---

# NFC Emulate

Puts the PN532 into target mode and responds to NFC readers as if it were
a physical tag. Useful for demonstrating access control bypasses and for
testing reader configurations.

## What it returns

```json
{
  "action": "emulate_uid",
  "uid": "04A23B1CD45880",
  "duration_s": 60,
  "reads_detected": 3,
  "readers": [
    {"timestamp": "2026-04-20T14:30:12Z", "command": "GET_UID"},
    {"timestamp": "2026-04-20T14:30:45Z", "command": "READ_BLOCK_0"}
  ]
}
```

## Hardware

- **PN532 v3** — supports ISO 14443-A target (tag emulation) mode natively.
  Configured via SAM configuration command (0x14) with target mode 0x02.

Note: the PN532's emulation capabilities are limited:
- **UID spoofing** — works for most access readers.
- **Full MIFARE Classic emulation** — PN532 can emulate 1K Classic but
  performance varies. Better emulators exist (Proxmark3, ChameleonMini)
  but PN532 is what we have.
- **NTAG emulation** — works well.
- **MIFARE DESFire** — PN532 cannot emulate.

## Implementation notes

Use `libnfc` with the `nfc-emulate-forum-tag4` / `nfc-emulate-uid` examples
as reference, or `adafruit-circuitpython-pn532` with a custom target-mode
loop.

For full Classic emulation, the read requests need to be serviced in real
time (sub-millisecond). Python may not be fast enough — consider C or
offloading to a microcontroller if emulation performance is poor.

## Scope requirements

- Operator must have authorization to emulate the captured credential
- Emulating someone else's badge without authorization is illegal in most
  jurisdictions
- The disclosure layer will require confirmation (sensitivity: active)

## Typical workflow

1. `nfc_read` — capture target tag data
2. Operator reviews captured data
3. `nfc_emulate` (this skill) — present as the captured tag at a reader
4. Verify the reader accepts (or detect if it doesn't, revealing controls)
