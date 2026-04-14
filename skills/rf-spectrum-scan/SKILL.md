---
name: rf_spectrum_scan
description: >
  Wideband RF spectrum survey using HackRF Pro. Scans a frequency range and
  reports signal strength across the band — find unknown transmitters,
  identify ISM/LMR/cellular activity. Passive.
parameters_schema:
  type: object
  properties:
    start_mhz:
      type: number
      description: Start frequency in MHz
    end_mhz:
      type: number
      description: End frequency in MHz
    step_khz:
      type: integer
      description: Bin size in kHz. Default 500.
    dwell_ms:
      type: integer
      description: Time per bin. Higher catches more intermittent signals. Default 100.
  required:
    - start_mhz
    - end_mhz
sensitivity: passive
allowed_tools:
  - rf_spectrum_scan
---

# RF Spectrum Scan

Wide-band frequency survey. Sweeps the specified range and measures signal
power per bin. Useful for finding rogue transmitters, surveying cellular
activity, or identifying the frequency of an unknown signal.

## What it returns

```json
{
  "start_mhz": 433,
  "end_mhz": 435,
  "step_khz": 500,
  "peaks": [
    {"freq_mhz": 433.92, "power_dbm": -32, "bandwidth_khz": 250},
    {"freq_mhz": 434.3, "power_dbm": -58, "bandwidth_khz": 50}
  ],
  "full_scan_file": "captures/spectrum_433_435_1745174400.csv"
}
```

## Implementation

`hackrf_sweep` for fast wide sweeps, or `soapy_power` for finer control:

```
hackrf_sweep -f 433:435 -w 500000 -1 | awk ...
```

Parse output into per-bin dBm values, run simple peak detection, save
full sweep to CSV for later analysis.

## Scope

- Pure RX, no transmission — fully passive
- Legal everywhere for RX-only operation
