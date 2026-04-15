"""FAKE: synthetic wideband RF spectrum sweep."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import fake_capture_path, mark_synthetic, _rng


# Known strong emitters by frequency band.
_KNOWN_PEAKS = {
    (88, 108): ("FM broadcast", -30, 200),
    (433.7, 434.1): ("ISM keyfob/doorbell", -40, 250),
    (915, 928): ("LoRa / ISM", -45, 500),
    (2400, 2483): ("WiFi 2.4 / BLE", -25, 20000),
    (5170, 5830): ("WiFi 5", -35, 20000),
    (850, 900): ("GSM / LTE", -50, 200),
}


def execute(args: dict[str, Any]) -> dict[str, Any]:
    start_mhz = float(args.get("start_mhz", 300))
    end_mhz = float(args.get("end_mhz", 2500))
    step_khz = int(args.get("step_khz", 500))
    dwell_ms = int(args.get("dwell_ms", 100))

    rng = _rng(f"rf_spectrum:{start_mhz}:{end_mhz}")

    peaks = []
    for (lo, hi), (label, base_dbm, bw) in _KNOWN_PEAKS.items():
        if lo > end_mhz or hi < start_mhz:
            continue
        # Drop a peak near the middle of the overlap.
        overlap_lo = max(lo, start_mhz)
        overlap_hi = min(hi, end_mhz)
        mid = rng.uniform(overlap_lo, overlap_hi)
        peaks.append({
            "freq_mhz": round(mid, 3),
            "power_dbm": base_dbm + rng.randint(-10, 10),
            "bandwidth_khz": bw,
            "likely_source": label,
        })

    path = fake_capture_path(f"spectrum_{int(start_mhz)}_{int(end_mhz)}", "csv")

    return mark_synthetic({
        "start_mhz": start_mhz,
        "end_mhz": end_mhz,
        "step_khz": step_khz,
        "dwell_ms": dwell_ms,
        "peaks": peaks,
        "full_scan_file": path,
    })
