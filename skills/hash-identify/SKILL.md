---
name: hash_identify
description: >
  Identify the hash type of an unknown hash string. Returns hashcat/john
  modes and confidence. Passive — pure local analysis.
parameters_schema:
  type: object
  properties:
    hash_string:
      type: string
      description: The hash to identify (hex, base64, or formatted like $6$...)
  required:
    - hash_string
sensitivity: passive
allowed_tools:
  - hash_identify
---

# Hash Identify

Given an unknown hash, suggests what algorithm produced it. Wraps the
`name-that-hash` / `hashid` logic in a structured call.

## What it returns

```json
{
  "hash": "5f4dcc3b5aa765d61d8327deb882cf99",
  "candidates": [
    {"type": "MD5", "hashcat_mode": 0, "john_format": "raw-md5", "confidence": "high"},
    {"type": "NTLM", "hashcat_mode": 1000, "confidence": "medium"}
  ]
}
```

## Implementation

Pattern match against known hash structure (length, character set, prefixes):
- `$2a$...` / `$2b$...` → bcrypt
- `$6$...` → sha512crypt
- 32 hex → MD5 or NTLM (ambiguous)
- 40 hex → SHA1
- 64 hex → SHA256
- Use `name-that-hash` library for confidence scoring

## Scope

- Pure local analysis
- No transmission
