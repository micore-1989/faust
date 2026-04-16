---
name: nfc_crack_mifare
description: >
  Recover MIFARE Classic sector keys using darkside, hardnested, or nested
  attacks. Requires a tag with at least one known key. Active — sends many
  authentication attempts.
parameters_schema:
  type: object
  properties:
    attack:
      type: string
      enum: ["darkside", "hardnested", "nested", "auto"]
      description: Attack type. "auto" tries darkside first, then hardnested. Default "auto".
    known_key:
      type: string
      description: A known key in hex (required for nested/hardnested). Default keys tried first.
    known_sector:
      type: integer
      description: Sector the known key authenticates
    target_sector:
      type: integer
      description: Sector to recover key for. -1 = all sectors. Default -1.
  required: []
typical_duration_s: 60
sensitivity: active
allowed_tools:
  - nfc_crack_mifare
---

# MIFARE Classic Key Crack

Recovers encrypted MIFARE Classic sector keys via crypto-1 weaknesses.
MIFARE Classic is used in many legacy access-control and transit cards —
and is thoroughly broken.

## What it returns

```json
{
  "uid": "A1B2C3D4",
  "attack_used": "hardnested",
  "keys_recovered": {
    "0": {"key_a": "FFFFFFFFFFFF", "key_b": "FFFFFFFFFFFF"},
    "1": {"key_a": "A0A1A2A3A4A5", "key_b": "000000000000"},
    "5": {"key_a": "1234ABCD5678", "key_b": "AABBCCDDEEFF"}
  },
  "duration_s": 47
}
```

## Implementation

PN532 with `mfcuk` (darkside) and `mfoc` (nested). Better with a
Proxmark3 but PN532 works for most cards.

```
mfcuk -C -R 0:A -v 1 -O crack.log    # darkside
mfoc -P 500 -O dump.mfd               # nested (needs known key)
```

Hardnested needs Proxmark3 for practical speed — PN532 is too slow.

## Scope

- MIFARE Classic is deprecated — only legacy systems use it
- DESFire / Plus don't have this weakness
- Operator must have authorization for the card/system
