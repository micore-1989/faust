"""FAKE: synthetic spectrum anomaly detection."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import now_iso, mark_synthetic, _rng


def execute(args: dict[str, Any]) -> dict[str, Any]:
    baseline_file = args.get("baseline_file")
    start_mhz = float(args.get("start_mhz", 300))
    end_mhz = float(args.get("end_mhz", 2500))
    threshold_db = int(args.get("threshold_db", 15))
    duration_s = int(args.get("duration_s", 60))

    rng = _rng(f"spectrum_anomaly:{start_mhz}:{end_mhz}:{threshold_db}")

    baseline_age_days = rng.randint(1, 30) if baseline_file else 0
    anomalies = []

    # ~20% chance of an anomaly in a given scan.
    if rng.random() < 0.20:
        seed = "anomaly:1"
        ar = _rng(seed)
        freq = round(ar.uniform(start_mhz, end_mhz), 1)
        baseline_dbm = ar.randint(-95, -75)
        current = baseline_dbm + ar.randint(threshold_db + 5, 50)
        anomalies.append({
            "freq_mhz": freq,
            "current_dbm": current,
            "baseline_dbm": baseline_dbm,
            "delta_db": current - baseline_dbm,
            "interpretation": ar.choice([
                "likely new transmitter or intentional emitter",
                "wideband noise floor rise — possible jammer",
                "intermittent signal consistent with a drone data link",
            ]),
            "first_seen": now_iso(),
        })

    return mark_synthetic({
        "baseline_age_days": baseline_age_days,
        "scan_range_mhz": [start_mhz, end_mhz],
        "threshold_db": threshold_db,
        "duration_s": duration_s,
        "anomalies": anomalies,
    })
