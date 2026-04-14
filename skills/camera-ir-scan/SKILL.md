---
name: camera_ir_scan
description: >
  Detect hidden cameras by looking for IR emissions and retroreflective
  lens glints. Uses the Pi Camera Module + IR LED. Counter-surveillance.
  Passive.
parameters_schema:
  type: object
  properties:
    mode:
      type: string
      enum: ["ir_emission", "lens_glint", "both"]
      description: >
        "ir_emission" - passive scan for IR LEDs (night-vision cameras).
        "lens_glint" - active: pulse the IR LED and look for retroreflection
                       from camera lenses.
        "both" - run both modes. Default "both".
    duration_s:
      type: integer
      description: Scan duration. Default 30.
    sensitivity_threshold:
      type: integer
      description: Detection threshold 0-255. Lower = more sensitive. Default 40.
  required: []
sensitivity: passive
allowed_tools:
  - camera_ir_scan
---

# Camera IR Scan

Finds hidden cameras in a room via two optical effects:

1. **IR emission** — night-vision cameras emit 850-940 nm IR that's
   invisible to the eye but bright to the Pi camera with its IR filter
   removed (or to a camera sensitive at those wavelengths).

2. **Lens glint** — all cameras have lenses; when illuminated with IR,
   the lens retroreflects a small, intense spot back to the source.
   Pulsing the IR LED and correlating peak brightness in the camera
   feed reveals lenses even when cameras are powered off.

## What it returns

```json
{
  "mode": "both",
  "detections": [
    {
      "type": "ir_emission",
      "position_px": [412, 298],
      "intensity": 187,
      "confidence": "high"
    },
    {
      "type": "lens_glint",
      "position_px": [820, 410],
      "retroreflection_delta": 142,
      "confidence": "medium"
    }
  ],
  "capture_image": "captures/camera_scan_1745174400.jpg"
}
```

## Hardware

- **Pi Camera Module 3** (rear-facing) for image capture
- **IR LED** (same one used by `ir_capture`, repurposed)

## Implementation

OpenCV pipeline:
- IR emission mode: capture, extract near-IR channel, threshold for bright spots
- Lens glint mode: capture with IR LED off → capture with IR LED on →
  diff the frames, threshold for peaks

## Scope

- Personal counter-surveillance tool
- Fully passive for IR-emission mode
- Lens-glint mode transmits IR but in the non-regulated ~940 nm band
