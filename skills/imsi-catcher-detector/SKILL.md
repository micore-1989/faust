---
name: imsi_catcher_detector
description: >
  Detect rogue cellular base stations (Stingrays / IMSI catchers) by scanning
  nearby GSM/LTE cells and flagging anomalies. Passive.
parameters_schema:
  type: object
  properties:
    bands:
      type: array
      items: {type: string}
      description: Bands to scan. Default ["GSM-850", "GSM-1900", "LTE-B2", "LTE-B4"] for North America.
    duration_s:
      type: integer
      description: Scan duration. Default 120.
    known_towers_file:
      type: string
      description: Path to a JSON baseline of known cells. If absent, builds one on first run.
  required: []
typical_duration_s: 120
sensitivity: passive
allowed_tools:
  - imsi_catcher_detector
---

# IMSI Catcher Detector

Scans cellular bands looking for signs of a rogue base station:
- New cell ID in your area that wasn't there yesterday
- Unusual power levels (stingrays often TX loud to win selection)
- Missing or unusual System Information broadcasts
- Non-standard encryption (GSM A5/0 downgrades)
- Cells on frequencies not used by legitimate carriers

## What it returns

```json
{
  "towers_seen": 12,
  "suspicious": [
    {
      "cell_id": 99999,
      "mcc_mnc": "310-260",
      "lac": 12345,
      "band": "GSM-1900",
      "signal_dbm": -32,
      "reason": "cell ID not in baseline, unusually strong signal",
      "confidence": "medium"
    }
  ],
  "baseline_matches": 11
}
```

## Implementation

HackRF Pro + `gr-gsm` for GSM, `srsRAN` for LTE cell search. Parse the
SIB messages for Cell ID / TAC / carrier ID. Compare against baseline
(build via first few scans in known-safe locations).

## Scope

- Pure passive — listens to broadcast beacons only
- Legitimate cellular scanning, though some countries restrict SDR
  on licensed bands
- Best run periodically in your normal travel zones to build baseline
