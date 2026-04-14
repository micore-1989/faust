---
name: hid_payload
description: >
  Execute a BadUSB-style keyboard payload against a target computer
  connected via Faust's USB-A port. Pi 5 enumerates as a USB HID keyboard
  and types the payload at high speed. DISRUPTIVE — bypasses screen locks,
  executes arbitrary commands as the logged-in user.
parameters_schema:
  type: object
  properties:
    payload_file:
      type: string
      description: >
        Path to a Ducky Script file. See payloads/ directory for pre-built
        scripts (recon, persistence, exfil).
    raw_script:
      type: string
      description: >
        Inline Ducky Script as a multiline string. Use instead of payload_file
        for ad-hoc payloads.
    target_os:
      type: string
      enum: ["windows", "macos", "linux", "auto"]
      description: >
        Target OS. Affects keyboard layout, GUI shortcuts, and terminal
        paths. "auto" attempts detection from USB descriptors.
        Default "auto".
    typing_speed_wpm:
      type: integer
      description: >
        Words per minute. Faster is less suspicious but more error-prone
        on slow targets. Default 400 (fast, ~50 chars/sec).
  required: []
sensitivity: disruptive
allowed_tools:
  - hid_payload
---

# HID Payload (BadUSB)

Turns Faust into a USB keyboard when plugged into a target computer. Types
arbitrary keystrokes faster than a human can — sufficient to open a
terminal, run commands, exfil data, drop persistence, etc.

Flipper Zero has this via its USB-C port. Faust uses its panel-mount USB-A
as the attack port.

## What it returns

```json
{
  "payload_file": "payloads/recon_macos.duckyscript",
  "target_os": "macos",
  "executed": true,
  "keystrokes_sent": 342,
  "duration_ms": 6800,
  "detected_usb_host": "Darwin 23.6.0"
}
```

## Hardware

- **Pi 5 USB-A (panel-mount)** — when Faust is plugged into a target
  computer via its USB-A port, the Pi 5's USB gadget mode enumerates as
  a HID keyboard. Requires `dwc2` + `g_hid` kernel modules (similar to
  the USB-ethernet gadget setup for Mephisto).

Note: Faust's USB-C port is reserved for the Mephisto dock. The USB-A is
the attack interface. The operator physically plugs Faust's USB-A into
the target system.

## Implementation notes

This requires USB gadget mode configured on Faust's Pi 5. Different from
Mephisto's USB-ethernet gadget — uses `g_hid` instead of `g_ether`.

```
sudo modprobe g_hid \
    report=<HID_keyboard_descriptor_hex> \
    report_length=8
```

Then write keystroke reports to `/dev/hidg0` at typing speed.

A Python Ducky Script interpreter reads the .duckyscript file and emits
the right HID reports for each line (`STRING foo`, `GUI r`, `ENTER`, etc.).

## Payload library

Suggested structure:
```
payloads/
  recon_macos.duckyscript      — open terminal, run `system_profiler` etc.
  recon_windows.duckyscript    — open PowerShell, run `systeminfo` etc.
  recon_linux.duckyscript      — open terminal, run `uname -a; whoami` etc.
  exfil_browser_creds.duckyscript — grab browser saved passwords
  persistence_launchd.duckyscript — install a launchd job (macOS)
```

Payloads should be curl'd to a local URL or printed to stdout — they
should NOT phone home to external hosts. All data stays on the Faust.

## Scope requirements

- **This is a disruptive skill with real legal weight.** Plugging an
  unauthorized HID keyboard into someone else's computer is unauthorized
  access — a crime in most jurisdictions.
- Operator must have written authorization for the target system
- Testing on your own computers ONLY
- Payloads should avoid destructive actions; stick to reconnaissance and
  benign demonstrations unless the engagement explicitly scopes them
- The journal records which payload was executed, duration, and target OS —
  NOT the commands themselves (since the payload file is the authoritative
  record)

## Typical workflow

1. Choose or write a Ducky Script payload
2. Physically plug Faust's USB-A into the target computer
3. `hid_payload payload_file=payloads/recon_macos.duckyscript` — operator
   confirms via hold-to-confirm
4. Faust types the payload (~5-30 seconds depending on length)
5. Review output written to Faust's `captures/` directory
