"""FAKE: synthetic hidden camera IR/glint detection."""
from __future__ import annotations

from typing import Any

from faust.skills.fakes import fake_capture_path, mark_synthetic, _rng


def execute(args: dict[str, Any]) -> dict[str, Any]:
    mode = args.get("mode", "both")
    duration_s = int(args.get("duration_s", 30))
    threshold = int(args.get("sensitivity_threshold", 40))

    rng = _rng(f"camera_scan:{mode}:{duration_s}:{threshold}")

    detections = []

    # ~15% chance to "find" something — most rooms are clean.
    if rng.random() < 0.15:
        seed = "camscan:hit1"
        hr = _rng(seed)
        detections.append({
            "type": hr.choice(["ir_emission", "lens_glint"]),
            "position_px": [hr.randint(100, 1180), hr.randint(100, 700)],
            "intensity": hr.randint(threshold + 10, 255),
            "confidence": hr.choice(["low", "medium", "high"]),
        })
        # Occasionally a second detection (bonus lens glint near the emitter).
        if hr.random() < 0.3:
            detections.append({
                "type": "lens_glint",
                "position_px": [hr.randint(100, 1180), hr.randint(100, 700)],
                "retroreflection_delta": hr.randint(100, 200),
                "confidence": "medium",
            })

    return mark_synthetic({
        "mode": mode,
        "duration_s": duration_s,
        "sensitivity_threshold": threshold,
        "detections": detections,
        "capture_image": fake_capture_path("camera_scan", "jpg"),
    })
