"""FAKE: synthetic IMSI catcher / Stingray detection."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import mark_synthetic, pack_summary, _rng
from faust.tools.registry import ToolResult


def execute(args: dict[str, Any]) -> ToolResult:
    bands = args.get("bands") or ["GSM-850", "GSM-1900", "LTE-B2", "LTE-B4"]
    duration_s = int(args.get("duration_s", 120))
    known_towers_file = args.get("known_towers_file")

    rng = _rng(f"imsi:{','.join(bands)}:{duration_s}")

    towers_seen = rng.randint(6, 16)
    suspicious = []

    # ~10% chance of finding something suspicious per scan.
    if rng.random() < 0.1:
        seed = "imsi:suspect"
        sr = _rng(seed)
        suspicious.append({
            "cell_id": sr.randint(10_000, 99_999),
            "mcc_mnc": "310-260",
            "lac": sr.randint(10_000, 99_999),
            "band": sr.choice(bands),
            "signal_dbm": sr.randint(-45, -25),
            "reason": sr.choice([
                "cell ID not in baseline, unusually strong signal",
                "SIB missing encryption info (possible A5/0 downgrade)",
                "frequency not registered to any known carrier",
            ]),
            "confidence": sr.choice(["low", "medium", "high"]),
        })

    result = mark_synthetic({
        "bands": bands,
        "duration_s": duration_s,
        "towers_seen": towers_seen,
        "suspicious": suspicious,
        "baseline_matches": towers_seen - len(suspicious),
    })

    first = suspicious[0] if suspicious else None
    summary = pack_summary({
        "towers_seen": towers_seen,
        "suspicious": len(suspicious),
        "confidence": first["confidence"] if first else None,
        "reason": first["reason"] if first else None,
    })
    return ToolResult(result=result, summary=summary)
