---
name: spectrum_anomaly
description: >
  Compare current RF spectrum against a learned baseline and flag unusual
  activity. Catches things like new transmitters, jammers, or frequency
  hoppers operating in your area. Passive.
parameters_schema:
  type: object
  properties:
    baseline_file:
      type: string
      description: Path to a stored baseline spectrum. If absent, builds one.
    start_mhz:
      type: number
      description: Start frequency. Default 300.
    end_mhz:
      type: number
      description: End frequency. Default 2500.
    threshold_db:
      type: integer
      description: dB change from baseline that triggers an alert. Default 15.
    duration_s:
      type: integer
      description: Observation duration per scan. Default 60.
  required: []
typical_duration_s: 60
sensitivity: passive
allowed_tools:
  - spectrum_anomaly
---

# Spectrum Anomaly

Builds a statistical baseline of what the RF spectrum looks like in a
given location, then detects deviations. Useful for:
- Finding rogue transmitters in a previously-clean environment
- Detecting jammers (large wideband noise floor rise)
- Catching intermittent transmitters (drones, bugs, tracking devices)

## What it returns

```json
{
  "baseline_age_days": 7,
  "anomalies": [
    {
      "freq_mhz": 2408,
      "current_dbm": -42,
      "baseline_dbm": -85,
      "delta_db": 43,
      "interpretation": "likely new 2.4 GHz transmitter or intentional emitter",
      "first_seen": "2026-04-20T14:30:12Z"
    }
  ],
  "scan_range_mhz": [300, 2500]
}
```

## Implementation

- `hackrf_sweep` for wide, fast spectrum capture
- Statistical baseline: per-bin rolling mean + stddev over multiple prior scans
- Alert when current sample > baseline + threshold_db for sustained duration
- Use `numpy` for the baseline math — trivial compute

## Scope

- Pure RX — no transmission
- Baseline is location-specific; carry separate baselines for home/office/travel
