"""
Static Pursuit metadata + implementation lookup.

The 7 v1 Pursuits plus Custom are registered at import time with the exact
copy and parameter schemas from faust-ui-spec.md §10.4. The concrete
implementation functions live in `IMPLEMENTATIONS` and are filled by
Stage 5b — in Stage 5a it's empty, so the runner emits
PursuitStopped(reason="error") for any real Pursuit. Tests register a
fake implementation directly into this dict.
"""

from __future__ import annotations

from typing import Callable

from .models import ParamSpec, Pursuit


PURSUITS: dict[str, Pursuit] = {
    "wardrive": Pursuit(
        id="wardrive",
        title="Wardrive",
        description=(
            "Drive or walk while capturing WiFi and GPS simultaneously. "
            "Exports a geo-tagged network map."
        ),
        duration_hint="~30 min",
        tools_used=["WIFI", "GPS"],
        parameters=[
            ParamSpec(name="duration_minutes", type="int", default=30),
            ParamSpec(
                name="frequency_band",
                type="enum",
                default="2.4 GHz only",
                choices=["2.4 GHz only", "5 GHz only", "dual band"],
            ),
            ParamSpec(name="gps_required", type="bool", default=True),
        ],
    ),
    "clone-credential": Pursuit(
        id="clone-credential",
        title="Clone Access Credential",
        description=(
            "Read an LF RFID card (T5577/EM4100/HID Prox) and write its "
            "data to a blank card."
        ),
        duration_hint="~2 min",
        tools_used=["LF RFID"],
        parameters=[],
    ),
    "replay-subghz": Pursuit(
        id="replay-subghz",
        title="Replay Sub-GHz Remote",
        description="Capture a garage door or keyfob transmission, analyze, and replay.",
        duration_hint="~5 min",
        tools_used=["SUB-GHZ"],
        parameters=[
            ParamSpec(
                name="frequency_mhz",
                type="enum",
                default="433.92",
                choices=["315", "433.92", "868", "915"],
            ),
        ],
    ),
    "evil-portal": Pursuit(
        id="evil-portal",
        title="Evil Portal",
        description=(
            "Stand up a captive portal on a rogue AP to observe "
            "credential-submission behavior in a controlled environment."
        ),
        duration_hint="open-ended",
        tools_used=["WIFI"],
        parameters=[
            ParamSpec(name="ssid", type="string", default="free-wifi"),
        ],
    ),
    "bluetooth-recon": Pursuit(
        id="bluetooth-recon",
        title="Bluetooth Recon",
        description=(
            "Passively survey nearby BLE devices, log advertisements, "
            "classify vendor and role."
        ),
        duration_hint="~10 min",
        tools_used=["WIFI", "BLE"],
        parameters=[
            ParamSpec(name="duration_minutes", type="int", default=10),
        ],
    ),
    "subghz-capture-analyze": Pursuit(
        id="subghz-capture-analyze",
        title="Sub-GHz Capture + Analyze",
        description=(
            "Capture IQ data on a chosen frequency, demodulate, and extract "
            "recognizable signal patterns."
        ),
        duration_hint="~15 min",
        tools_used=["SUB-GHZ"],
        parameters=[
            ParamSpec(name="frequency_mhz", type="string", default="433.92"),
            ParamSpec(name="capture_seconds", type="int", default=120),
        ],
    ),
    "hmc-demo": Pursuit(
        id="hmc-demo",
        title="Harvey Mudd Demo",
        description=(
            "Scripted demonstration sequence for the student showcase: "
            "scan, capture, Pursuit-complete. Uses a dedicated demo SSID."
        ),
        duration_hint="~3 min",
        tools_used=["WIFI", "JOURNAL"],
        parameters=[],
    ),
    "custom": Pursuit(
        id="custom",
        title="Custom Pursuit",
        description="Build your own Pursuit.",
        duration_hint="—",
        tools_used=[],
        parameters=[],
        is_custom=True,
    ),
}


# Stage 5b filled these in. Runner emits PursuitStopped(error) if the
# lookup misses. Tests inject their own callables via the `implementations`
# parameter on run_pursuit rather than mutating this dict.
from .pursuits import (  # noqa: E402
    bluetooth_recon,
    clone_credential,
    evil_portal,
    hmc_demo,
    replay_subghz,
    subghz_capture_analyze,
    wardrive,
)


IMPLEMENTATIONS: dict[str, Callable] = {
    "wardrive": wardrive.run,
    "clone-credential": clone_credential.run,
    "replay-subghz": replay_subghz.run,
    "evil-portal": evil_portal.run,
    "bluetooth-recon": bluetooth_recon.run,
    "subghz-capture-analyze": subghz_capture_analyze.run,
    "hmc-demo": hmc_demo.run,
    # "custom" intentionally absent — Stage 11 builder.
}


# Canonical display order — 7 real Pursuits first, Custom last. The UI
# grid renders from this list; don't alphabetize.
_DISPLAY_ORDER = [
    "wardrive",
    "clone-credential",
    "replay-subghz",
    "evil-portal",
    "bluetooth-recon",
    "subghz-capture-analyze",
    "hmc-demo",
    "custom",
]


def list_pursuits() -> list[Pursuit]:
    """Return all Pursuits in canonical display order."""
    return [PURSUITS[pid] for pid in _DISPLAY_ORDER]


def get_pursuit(pursuit_id: str) -> Pursuit:
    """Return Pursuit by id. Raises KeyError if not registered."""
    return PURSUITS[pursuit_id]


def validate_params(pursuit: Pursuit, params: dict) -> list[str]:
    """Validate params against the Pursuit's ParamSpec list. Returns a list
    of error strings (empty = all good). Used by the server before spawning
    a runner so invalid payloads fail fast with a readable message."""
    errors: list[str] = []
    spec_by_name = {p.name: p for p in pursuit.parameters}

    for spec in pursuit.parameters:
        if spec.required and spec.name not in params:
            errors.append(f"missing required param: {spec.name}")
            continue
        if spec.name not in params:
            continue
        val = params[spec.name]
        if spec.type == "int":
            if not isinstance(val, int) or isinstance(val, bool):
                errors.append(f"{spec.name!r}: expected int, got {type(val).__name__}")
        elif spec.type == "bool":
            if not isinstance(val, bool):
                errors.append(f"{spec.name!r}: expected bool, got {type(val).__name__}")
        elif spec.type == "string":
            if not isinstance(val, str):
                errors.append(f"{spec.name!r}: expected string, got {type(val).__name__}")
        elif spec.type == "enum":
            if spec.choices is not None and val not in spec.choices:
                errors.append(
                    f"{spec.name!r}: {val!r} not in choices {spec.choices}"
                )

    # Unknown keys: warn but don't block. Clients may send extras harmlessly.
    return errors


def apply_defaults(pursuit: Pursuit, params: dict) -> dict:
    """Merge client-supplied params on top of the Pursuit's default values."""
    merged: dict = {}
    for spec in pursuit.parameters:
        if spec.default is not None:
            merged[spec.name] = spec.default
    merged.update(params)
    return merged
