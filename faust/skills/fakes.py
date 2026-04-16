"""
Shared helpers for FAKE tool.py implementations.

This module exists to let the agent demo end-to-end on a development Mac
BEFORE the RF hardware arrives. Every skill's tool.py uses these helpers
to produce realistic-looking synthetic data.

When real hardware arrives, each skill's tool.py gets rewritten to drive
the actual radio / NIC / reader. This file can stay (as a reference or
for CI) or go away.

Design principles:
  - Plausible, not random. Data should look like something a real tool
    would emit.
  - Input-sensitive. Results respect the caller's parameters (interface,
    target, count, etc.) — don't ignore args.
  - Deterministic where it helps. Same BSSID input → same details out,
    so scan→deauth→capture chains produce a coherent story.
  - No real side effects. No network traffic, no file writes that
    couldn't be regenerated.
"""

from __future__ import annotations

import hashlib
import random
import time
from datetime import datetime, timezone
from typing import Any


# Global flag the UI/CLI can check. Set False when the last skill's real
# tool.py arrives — at that point fakes are dead code.
SIMULATED = True


# ── MAC / BSSID / vendor ────────────────────────────────────────

# Common OUI prefixes for realism
_VENDOR_OUIS = {
    "Apple":    "3c:22:fb",
    "Samsung":  "e8:50:8b",
    "Cisco":    "00:0c:29",
    "TP-Link":  "50:c7:bf",
    "Netgear":  "84:1b:5e",
    "Intel":    "00:1b:77",
    "Espressif": "a4:cf:12",  # ESP32s
    "Unknown":  "02:00:00",   # locally administered
}


def fake_mac(vendor: str | None = None, seed: str | None = None) -> str:
    """Plausible MAC address. If vendor is given, prefix with its OUI."""
    rng = _rng(seed)
    oui = _VENDOR_OUIS.get(vendor or "Unknown", _VENDOR_OUIS["Unknown"])
    suffix = ":".join(f"{rng.randint(0, 255):02x}" for _ in range(3))
    return f"{oui}:{suffix}"


def fake_bssid(seed: str | None = None) -> str:
    vendors = ["TP-Link", "Netgear", "Cisco", "Unknown"]
    rng = _rng(seed)
    return fake_mac(rng.choice(vendors), seed)


def fake_client_mac(seed: str | None = None) -> str:
    vendors = ["Apple", "Samsung", "Intel"]
    rng = _rng(seed)
    return fake_mac(rng.choice(vendors), seed)


# ── WiFi ────────────────────────────────────────────────────────

_SSID_POOL = [
    "TargetNet", "CorpWiFi", "CorpWiFi-5G", "GuestWiFi", "HomeWiFi",
    "Starbucks WiFi", "attwifi", "xfinitywifi", "NETGEAR24",
    "TP-Link_E8A2", "Linksys01283", "Verizon_QMXK3", "Spectrum-G4",
    "HP-Print-01-LaserJet", "FBI_Surveillance_Van", "Pretty Fly for a WiFi",
]


def fake_ssid(seed: str | None = None) -> str:
    return _rng(seed).choice(_SSID_POOL)


def fake_rssi(near: bool = False, seed: str | None = None) -> int:
    """RSSI in dBm. near=True for ~3-10ft, False for further."""
    rng = _rng(seed)
    if near:
        return rng.randint(-50, -35)
    return rng.randint(-85, -45)


def fake_channel(band: str = "all", seed: str | None = None) -> int:
    rng = _rng(seed)
    if band == "2.4":
        return rng.choice([1, 6, 11])
    if band == "5":
        return rng.choice([36, 40, 44, 48, 149, 153, 157, 161])
    return rng.choice([1, 6, 11, 36, 40, 44, 149, 153])


_ENCRYPTIONS = ["WPA2-PSK", "WPA3-SAE", "WPA2/WPA3 Mixed", "Open", "WPA2-Enterprise"]


def fake_encryption(seed: str | None = None) -> str:
    # Open is rare; weight distribution
    rng = _rng(seed)
    roll = rng.random()
    if roll < 0.60: return "WPA2-PSK"
    if roll < 0.80: return "WPA2/WPA3 Mixed"
    if roll < 0.90: return "WPA3-SAE"
    if roll < 0.95: return "WPA2-Enterprise"
    return "Open"


# ── BLE ─────────────────────────────────────────────────────────

_BLE_NAMES = [
    "AirPods Pro", "Galaxy Buds2", "Tile Mate", "JBL Go 2",
    "LG TV", "Bose QC45", "Anker A3909", "Polar H10",
    "Fitbit Charge 5", "Mi Band 7", "Logitech MX",
    None, None,  # unnamed devices are common
]


def fake_ble_device(seed: str | None = None) -> dict[str, Any]:
    rng = _rng(seed)
    name = rng.choice(_BLE_NAMES)
    return {
        "name": name,
        "mac": fake_mac("Apple" if name and "AirPods" in (name or "") else None, seed),
        "rssi_dbm": fake_rssi(seed=seed),
        "address_type": rng.choice(["public", "random"]),
        "connectable": rng.random() > 0.3,
    }


# ── NFC ─────────────────────────────────────────────────────────

_TAG_TYPES = ["NTAG215", "NTAG213", "MIFARE_Classic_1K", "MIFARE_Ultralight", "MIFARE_DESFire_EV2"]


def fake_uid(length: int = 7, seed: str | None = None) -> str:
    rng = _rng(seed)
    return ":".join(f"{rng.randint(0, 255):02X}" for _ in range(length))


def fake_tag_type(seed: str | None = None) -> str:
    return _rng(seed).choice(_TAG_TYPES)


# ── GPS ─────────────────────────────────────────────────────────

def fake_gps(seed: str | None = None) -> tuple[float, float, float]:
    """Return (lat, lon, alt_m). Roughly near Harvey Mudd college."""
    rng = _rng(seed)
    lat = 34.1067 + (rng.random() - 0.5) * 0.002
    lon = -117.7098 + (rng.random() - 0.5) * 0.002
    alt = 412.0 + (rng.random() - 0.5) * 20
    return (round(lat, 6), round(lon, 6), round(alt, 1))


# ── Files / timestamps ──────────────────────────────────────────

def fake_capture_path(prefix: str, ext: str = "pcap", seed: str | None = None) -> str:
    rng = _rng(seed)
    ts = int(time.time()) - rng.randint(0, 300)
    return f"captures/{prefix}_{ts}.{ext}"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ago_iso(seconds_ago: int = 0) -> str:
    t = time.time() - seconds_ago
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Deterministic RNG ──────────────────────────────────────────

def _rng(seed: str | None = None) -> random.Random:
    """Seeded Random when `seed` is given, else global Random.

    This lets callers produce consistent outputs for consistent inputs
    (e.g. same BSSID argument → same details) while non-seeded calls
    give fresh randomness.
    """
    if seed is None:
        return random
    h = hashlib.sha256(seed.encode()).digest()
    return random.Random(int.from_bytes(h[:8], "big"))


# ── Hashes ──────────────────────────────────────────────────────

def fake_hash(length: int = 32, seed: str | None = None) -> str:
    """Return `length` hex characters of deterministic-ish hash."""
    src = (seed or f"{time.time()}{random.random()}").encode()
    return hashlib.sha256(src).hexdigest()[:length]


# ── Synthetic annotation ────────────────────────────────────────

def mark_synthetic(result: dict[str, Any]) -> dict[str, Any]:
    """Tag a result as fake so the UI can show a DEMO banner if desired.

    The _synthetic key is intentionally underscore-prefixed so the LLM
    is unlikely to treat it as data worth referencing — it's a meta-flag.
    """
    result["_synthetic"] = True
    return result


# ── Summary channel ─────────────────────────────────────────────

def _approx_json_len(d: dict[str, Any]) -> int:
    import json as _json
    return len(_json.dumps(d, default=str))


def pack_summary(fields: dict[str, Any], max_chars: int = 200) -> dict[str, Any]:
    """Return a compact summary dict, trimming lowest-priority fields first.

    Skills use this to hand the agent loop a structured ≤max_chars digest of
    what was learned (alongside the full result). Fields are declared in
    priority order — when the encoded length exceeds max_chars, fields from
    the tail drop until it fits. Guarantees the summary is small and valid
    JSON for the Pass 2 / re-plan feedforward paths.

    Example:
        summary = pack_summary({
            "networks_found": 8,
            "best_handshake_target": "aa:bb:cc:dd:ee:ff",
            "karma_candidates": 0,
            "top_3": [...],       # dropped first if we overflow
        })
    """
    packed = dict(fields)
    keys = list(packed.keys())
    # Drop from the tail until under budget.
    while keys and _approx_json_len(packed) > max_chars:
        packed.pop(keys.pop())
    return packed
