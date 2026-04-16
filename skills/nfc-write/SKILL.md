---
name: nfc_write
description: >
  Write data to an NFC tag — NDEF records, MIFARE Classic sectors, or raw
  block data. Active — requires physical tag presentation.
parameters_schema:
  type: object
  properties:
    mode:
      type: string
      enum: ["ndef_uri", "ndef_text", "ndef_wifi", "mifare_sector", "raw"]
      description: What to write
    uri:
      type: string
      description: For ndef_uri - URI to write (https, tel, mailto, etc.)
    text:
      type: string
      description: For ndef_text - plain text
    wifi_ssid:
      type: string
      description: For ndef_wifi - SSID
    wifi_pass:
      type: string
      description: For ndef_wifi - WPA password
    sector:
      type: integer
      description: For mifare_sector - target sector number
    data_hex:
      type: string
      description: For mifare_sector/raw - hex data
    key_hex:
      type: string
      description: For mifare_sector - authentication key if not default
  required:
    - mode
typical_duration_s: 5
sensitivity: active
allowed_tools:
  - nfc_write
---

# NFC Write

Writes NDEF records or raw data to NFC tags via the PN532. Common uses:
test-tag provisioning, WiFi-config stickers, URL beacons, MIFARE clone
completion (paired with `rfid_clone` or `nfc_crack_mifare`).

## What it returns

```json
{
  "mode": "ndef_uri",
  "tag_uid": "04A23B1CD45880",
  "tag_type": "NTAG215",
  "bytes_written": 42,
  "verified": true
}
```

## Implementation

`adafruit-circuitpython-pn532` for NDEF:

```python
pn532.ntag2xx_write_block(page, data)
```

For MIFARE Classic, authenticate first with key_a or key_b, then
write the target block.

## Scope

- Writes are permanent (NTAGs only rewritten if not locked)
- Writing to someone else's tag without authorization is modification of
  their property — operator responsibility
