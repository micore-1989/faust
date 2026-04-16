---
name: nfc_read
description: >
  Read an NFC/RFID tag placed on the PN532 reader. Returns UID, tag type,
  NDEF records, and raw sector data for MIFARE Classic. Passive — reads only,
  does not write or modify the tag.
parameters_schema:
  type: object
  properties:
    timeout_s:
      type: integer
      description: >
        How long to wait for a tag to be presented, in seconds. Default 10.
    read_sectors:
      type: boolean
      description: >
        If true, attempt to read all accessible sectors (MIFARE Classic) or
        pages (NTAG). Requires default keys for encrypted sectors. Default false.
    keys:
      type: array
      items:
        type: string
      description: >
        Optional list of 6-byte hex keys to try for MIFARE Classic sector
        authentication (e.g. ["FFFFFFFFFFFF", "A0A1A2A3A4A5"]). Default
        keys (FFx6, 000000000000, and common vendor defaults) are always tried.
  required: []
typical_duration_s: 5
sensitivity: passive
allowed_tools:
  - nfc_read
pivot_hints:
  - when: "summary.is_mifare_classic == true"
    suggest: "MIFARE Classic detected — if sectors did not read with default keys, nfc_crack_mifare (darkside/hardnested) recovers unknown keys. After cracking, re-run nfc_read with those keys to dump sectors."
  - when: "summary.has_ndef == true"
    suggest: "NDEF records present — contents may include URIs or Wi-Fi credentials. Review the full result and consider nfc_write to edit or clone."
  - when: "summary.readable_sectors >= 1"
    suggest: "Sectors already readable — rfid_clone (for 125 kHz) or nfc_write (for 13.56 MHz) can clone this tag onto a blank."
---

# NFC Read

Reads NFC/RFID tags at 13.56 MHz using the PN532 module. Supports ISO 14443
Type A (MIFARE Classic, MIFARE Ultralight, NTAG 21x) and ISO 14443 Type B.

## What it returns

```json
{
  "uid": "04:A2:3B:1C:D4:58:80",
  "uid_length": 7,
  "tag_type": "NTAG215",
  "atqa": "0044",
  "sak": "00",
  "ndef": [
    {"type": "uri", "payload": "https://example.com"}
  ],
  "sectors": null,
  "raw_pages": [
    {"page": 0, "data": "04A23B1C"},
    {"page": 1, "data": "D4588000"}
  ]
}
```

For MIFARE Classic with `read_sectors: true`:

```json
{
  "uid": "A1B2C3D4",
  "uid_length": 4,
  "tag_type": "MIFARE_Classic_1K",
  "atqa": "0004",
  "sak": "08",
  "ndef": null,
  "sectors": [
    {
      "sector": 0,
      "key_a": "FFFFFFFFFFFF",
      "blocks": [
        {"block": 0, "data": "A1B2C3D488040062636465666768"},
        {"block": 1, "data": "00000000000000000000000000000000"},
        {"block": 2, "data": "00000000000000000000000000000000"},
        {"block": 3, "data": "FFFFFFFFFFFFFF078069FFFFFFFFFFFF"}
      ]
    }
  ]
}
```

## Hardware

- **PN532 NFC module** (v3) — connected via I2C or SPI to Faust's Pi 5.
  Supports reader/writer and card emulation modes. I2C address 0x24 (default).

## Implementation notes

Uses `adafruit-circuitpython-pn532` (primary — first-class Pi 5 support,
purpose-built for this module over I2C/SPI). `nfcpy` is a fallback but is
primarily designed for USB NFC readers (ACR122U); its I2C/SPI support for
PN532 is experimental.

Key cracking (hardnested, darkside) is out of scope for this tool — that would
be a separate `nfc_crack` skill at `sensitivity: active`. This tool only reads
with known keys.

The PN532 requires the tag to be held within ~3cm of the reader coil. The tool
should provide clear feedback about tag detection state ("waiting for tag...",
"tag detected", "reading...").

## Typical workflow

1. `nfc_read` (this tool) — identify the tag type and read accessible data
2. Operator reviews the tag contents
3. `nfc_write` (future skill, active) — write data or clone to a blank tag
4. `nfc_emulate` (future skill, active) — emulate the tag using PN532
