"""FAKE: synthetic sub-GHz protocol decoding."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import now_iso, mark_synthetic, pack_summary, _rng
from faust.tools.registry import ToolResult


def execute(args: dict[str, Any]) -> ToolResult:
    frequency_mhz = float(args.get("frequency_mhz", 433.92))
    duration_s = int(args.get("duration_s", 10))
    protocols = args.get("protocols") or []
    capture_file = args.get("capture_file")

    rng = _rng(f"subghz_decode:{frequency_mhz}:{duration_s}:{capture_file}")

    # Common devices on 433 MHz: weather stations, doorbells, keyfobs.
    samples = [
        {
            "protocol": "Acurite-Tower", "device_id": 12345,
            "values": {"temp_c": 22.4, "humidity_pct": 45, "battery": "ok"},
            "timestamp": now_iso(),
        },
        {
            "protocol": "KeeLoq", "serial": "0x1A2B3C", "button": "unlock",
            "rolling_counter": 47211, "is_rolling": True,
        },
        {
            "protocol": "Prologue-TH", "device_id": 88, "channel": 1,
            "values": {"temp_c": 20.1, "humidity_pct": 52},
            "timestamp": now_iso(),
        },
        {
            "protocol": "TPMS-Subaru", "sensor_id": "0xDEADBE",
            "values": {"pressure_kpa": 220, "temp_c": 28},
        },
    ]

    # Pick a subset.
    n = rng.randint(1, min(3, len(samples)))
    decoded = rng.sample(samples, n)
    if protocols:
        decoded = [d for d in decoded if d["protocol"] in protocols]

    result = mark_synthetic({
        "frequency_mhz": frequency_mhz,
        "decoded": decoded,
        "unknown_signals": rng.randint(0, 5),
        "duration_s": duration_s,
    })

    protos = sorted({d["protocol"] for d in decoded})
    has_rolling = any(d.get("is_rolling") for d in decoded)
    summary = pack_summary({
        "decoded_count": len(decoded),
        "protocols": protos,
        "has_rolling_code": has_rolling,
        "unknown_signals": result["unknown_signals"],
        "first_device": decoded[0]["protocol"] if decoded else None,
    })
    return ToolResult(result=result, summary=summary)
