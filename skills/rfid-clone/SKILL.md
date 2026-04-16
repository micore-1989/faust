---
name: rfid_clone
description: >
  Clone a 125 kHz LF RFID credential (HID Prox, EM4100, T5577) onto a blank
  T5577 card. Reads the source card, then writes its ID to a programmable
  blank. ACTIVE — writes to a physical card.
parameters_schema:
  type: object
  properties:
    action:
      type: string
      enum: ["read", "clone"]
      description: >
        "read" = read the source card and display its data without writing.
        "clone" = read source, then write to a blank T5577 card.
        Default "read".
    source_id:
      type: string
      description: >
        Optional pre-known card ID (hex string) to write directly to blank,
        skipping the read step. Use when the source card data was captured
        in a previous read.
    card_type:
      type: string
      enum: ["em4100", "hid_prox", "auto"]
      description: >
        Card protocol to use. "auto" attempts to detect the card type.
        Default "auto".
    timeout_s:
      type: integer
      description: >
        How long to wait for card presentation in seconds. Default 10.
  required: []
typical_duration_s: 5
sensitivity: active
allowed_tools:
  - rfid_clone
---

# RFID Clone

The "Clone access credential" Pursuit. Reads and clones 125 kHz low-frequency
RFID cards — the kind commonly used for building access (HID ProxCard II,
EM4100 keyfobs, etc.) — onto blank T5577 programmable cards.

## What it returns

Read mode:
```json
{
  "action": "read",
  "card_type": "em4100",
  "card_id": "0F00234A81",
  "facility_code": 15,
  "card_number": 9160,
  "raw_bits": "1111111000000001111000000100011010100100000001",
  "signal_strength": "strong"
}
```

Clone mode:
```json
{
  "action": "clone",
  "source_id": "0F00234A81",
  "card_type": "em4100",
  "write_success": true,
  "verify_match": true
}
```

## Hardware

- **T5577/EM4305 combined reader/writer** — 125 kHz module with coil antenna.
  Connected via UART to Faust's Pi 5. Can read EM4100, HID Prox, and write
  to T5577/EM4305 programmable blanks.
- **RDM6300** — backup read-only 125 kHz reader (UART). Used if the combined
  module's read performance is poor.
- **T5577 blank cards** — 5-pack of programmable LF RFID cards included in BOM.

## Implementation notes

The T5577 is a multi-protocol programmable chip. It can emulate EM4100, HID
Prox II, Indala, AWID, and other 125 kHz protocols by writing the appropriate
modulation config to its configuration block.

Write sequence:
1. Read source card → extract raw bitstream + identify protocol
2. Present blank T5577 → write configuration block (modulation, bit rate)
3. Write data blocks with the source card's ID
4. Verify by reading back the T5577 and comparing to source

The combined reader/writer module handles the T5577 write protocol internally.
The tool sends commands over UART and parses responses.

## Scope requirements

- Operator must have authorization to clone the credential
- This tool is `sensitivity: active` because it writes to a physical card,
  but does not affect any access control system until the cloned card is
  physically presented to a reader
- Cloning someone else's credential without authorization is illegal

## Typical workflow

1. `rfid_clone action=read` — read the source badge
2. Operator verifies the captured data
3. `rfid_clone action=clone` — write to blank T5577
4. Physical verification at the target reader
