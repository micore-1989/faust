---
name: wpa_crack
description: >
  Offline crack of a captured WPA handshake or PMKID against a wordlist.
  Active — uses CPU (or Hailo NPU if configured) for hash computation.
parameters_schema:
  type: object
  properties:
    hash_file:
      type: string
      description: Path to hashcat-format .22000 file (from wifi_handshake_capture or wifi_pmkid_capture)
    wordlist:
      type: string
      description: Wordlist path. Default built-in top10k common passwords.
    rules:
      type: string
      enum: ["none", "best64", "dive"]
      description: Hashcat rule set for mutation. Default "none".
    time_budget_s:
      type: integer
      description: Max runtime. Stops gracefully and reports progress. Default 300.
  required:
    - hash_file
typical_duration_s: 300
sensitivity: active
allowed_tools:
  - wpa_crack
---

# WPA Crack

Offline dictionary attack against a captured WPA handshake or PMKID.
Hashcat is the tool; this wraps it with sensible defaults for the
handheld form factor (tight time budget, moderate wordlist).

## What it returns

```json
{
  "hash_file": "captures/handshake_aabbccddeeff.22000",
  "bssid": "aa:bb:cc:dd:ee:ff",
  "ssid": "TargetNet",
  "cracked": true,
  "password": "passw0rd123!",
  "duration_s": 47,
  "hashes_per_second": 12500,
  "wordlist_progress": "32%"
}
```

## Implementation

`hashcat -m 22000 hash.22000 wordlist.txt -r rules/best64.rule --runtime=300`

On Pi 5 CPU, ~10-50K hashes/sec. On Hailo NPU via hailo-hashcat (if
available), much faster. Output the hash-file.potfile entry when cracked.

## Scope

- Offline work — no RF activity
- Cracking captured data is legally distinct from capture — both require
  authorization
