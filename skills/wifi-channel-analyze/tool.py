"""FAKE: synthetic channel utilization survey."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import mark_synthetic, _rng


_2_4_CHANNELS = [1, 6, 11]
_5_CHANNELS = [36, 40, 44, 48, 149, 153, 157, 161]


def _freq_mhz(chan: int) -> int:
    if chan <= 14:
        return 2407 + 5 * chan
    return 5000 + 5 * chan


def execute(args: dict[str, Any]) -> dict[str, Any]:
    interface = args.get("interface", "wlan1mon")
    band = args.get("band", "all")
    duration_s = int(args.get("duration_s", 3))

    rng = _rng(f"chan_analyze:{interface}:{band}")

    channels_to_scan = []
    if band in ("2.4", "all"):
        channels_to_scan.extend(_2_4_CHANNELS)
    if band in ("5", "all"):
        channels_to_scan.extend(_5_CHANNELS)

    channels = []
    for ch in channels_to_scan:
        seed = f"chan_analyze:{interface}:{band}:{ch}"
        cr = _rng(seed)
        # 2.4 GHz channels 1/6/11 tend to be busy; 5 GHz less so.
        busy = ch in (6,) or (ch in (1, 11) and cr.random() > 0.4)
        util = cr.randint(40, 85) if busy else cr.randint(2, 25)
        channels.append({
            "channel": ch,
            "freq_mhz": _freq_mhz(ch),
            "utilization_pct": util,
            "frame_count": util * cr.randint(50, 150),
            "avg_rssi_dbm": cr.randint(-85, -45),
        })

    # Pick the quietest as recommendation.
    recommended = min(channels, key=lambda c: c["utilization_pct"])
    rec_band = "2.4 GHz" if recommended["channel"] <= 14 else "5 GHz"

    return mark_synthetic({
        "band": band,
        "channels": channels,
        "recommendation": (
            f"{rec_band} channel {recommended['channel']} has the lowest "
            f"utilization ({recommended['utilization_pct']}%)"
        ),
        "scan_duration_s": duration_s * len(channels_to_scan),
    })
