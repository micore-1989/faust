"""FAKE: synthetic sub-GHz capture/analyze/replay."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import fake_capture_path, mark_synthetic, pack_summary, _rng
from faust.tools.registry import ToolResult


_KNOWN_PROTOCOLS = ["PT2262 / EV1527", "Princeton PT2260", "KeeLoq", "HCS301", "Nice Flor-S"]


def execute(args: dict[str, Any]) -> ToolResult:
    action = args.get("action", "capture")
    frequency_mhz = float(args.get("frequency_mhz", 433.92))
    capture_file = args.get("capture_file")
    duration_s = int(args.get("duration_s", 5))
    repeats = int(args.get("repeats", 3))
    radio = args.get("radio", "hackrf")
    sample_rate = int(args.get("sample_rate", 2000000))

    rng = _rng(f"subghz:{action}:{frequency_mhz}:{capture_file}")

    if action == "capture":
        path = fake_capture_path(f"rf_{int(frequency_mhz * 1e6)}", "iq")
        detected = rng.random() < 0.8
        result = mark_synthetic({
            "action": "capture",
            "frequency_mhz": frequency_mhz,
            "sample_rate": sample_rate,
            "duration_s": duration_s,
            "capture_file": path,
            "peak_dbm": rng.randint(-65, -25) if detected else -90,
            "signal_detected": detected,
            "radio": radio,
        })
        summary = pack_summary({
            "action": "capture",
            "signal_detected": detected,
            "capture_file": path,
            "freq_mhz": frequency_mhz,
        })
        return ToolResult(result=result, summary=summary)

    if action == "analyze":
        protocol = rng.choice(_KNOWN_PROTOCOLS)
        is_rolling = protocol in ("KeeLoq", "HCS301", "Nice Flor-S")
        result = mark_synthetic({
            "action": "analyze",
            "capture_file": capture_file,
            "modulation": rng.choice(["OOK", "FSK"]),
            "bitrate_bps": rng.choice([1200, 2400, 4800]),
            "decoded": "".join(rng.choice("01") for _ in range(48)),
            "likely_protocol": protocol,
            "is_rolling_code": is_rolling,
        })
        summary = pack_summary({
            "action": "analyze",
            "protocol": protocol,
            "is_rolling_code": is_rolling,
            "replayable": not is_rolling,
        })
        return ToolResult(result=result, summary=summary)

    # replay
    success = rng.random() < 0.85
    result = mark_synthetic({
        "action": "replay",
        "frequency_mhz": frequency_mhz,
        "capture_file": capture_file,
        "repeats_sent": repeats,
        "success": success,
    })
    summary = pack_summary({
        "action": "replay",
        "success": success,
        "repeats": repeats,
        "freq_mhz": frequency_mhz,
    })
    return ToolResult(result=result, summary=summary)
