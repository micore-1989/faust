---
name: wardrive
description: >
  GPS-tagged WiFi and BLE survey. Continuously scans for wireless networks
  and BLE devices while recording GPS coordinates, building a georeferenced
  map of the RF environment. Passive — listens only.
parameters_schema:
  type: object
  properties:
    duration_s:
      type: integer
      description: >
        Survey duration in seconds. 0 = run until manually stopped.
        Default 60.
    interface:
      type: string
      description: >
        WiFi interface in monitor mode for WiFi scanning (e.g. wlan1mon).
    include_ble:
      type: boolean
      description: >
        Also scan for BLE devices during the survey. Adds BLE advertisements
        to the output alongside WiFi networks. Default true.
    output_format:
      type: string
      enum: ["kismet_csv", "wigle_csv", "json"]
      description: >
        Output format. "kismet_csv" and "wigle_csv" are compatible with
        standard wardriving tools and the WiGLE.net upload format.
        "json" is the native faust format. Default "json".
    min_gps_fix:
      type: string
      enum: ["2d", "3d"]
      description: >
        Minimum GPS fix quality before recording begins. "3d" = latitude,
        longitude, and altitude. "2d" = latitude and longitude only.
        Default "2d".
  required:
    - interface
typical_duration_s: 60
sensitivity: passive
allowed_tools:
  - wardrive
---

# Wardrive

The "Wardrive" Pursuit. Continuously scans for WiFi networks and BLE devices
while correlating each observation with GPS coordinates from the NEO-M9N
receiver. Produces a georeferenced survey of the local wireless environment.

## What it returns

```json
{
  "survey": {
    "start_time": "2026-04-20T14:30:00Z",
    "duration_s": 120,
    "gps_fix": "3d",
    "observations": 847
  },
  "networks": [
    {
      "ssid": "CorpWiFi",
      "bssid": "aa:bb:cc:dd:ee:ff",
      "channel": 11,
      "encryption": "WPA3-SAE",
      "first_seen": "2026-04-20T14:30:12Z",
      "last_seen": "2026-04-20T14:31:45Z",
      "strongest_rssi_dbm": -38,
      "lat": 34.1067,
      "lon": -117.7098,
      "alt_m": 412.3
    }
  ],
  "ble_devices": [
    {
      "name": "Conference Room Beacon",
      "mac": "11:22:33:44:55:66",
      "rssi_dbm": -52,
      "lat": 34.1068,
      "lon": -117.7097,
      "services": ["0000180a-0000-1000-8000-00805f9b34fb"]
    }
  ],
  "output_file": "captures/wardrive_20260420_143000.json"
}
```

## Hardware

- **u-blox NEO-M9N** — multi-constellation GNSS receiver (GPS, GLONASS,
  Galileo, BeiDou). Connected via UART. Provides 1-10 Hz position updates
  with ~2m accuracy outdoors. Indoor accuracy degrades significantly.
- **ALFA AWUS036ACM** — WiFi scanning in monitor mode (same as `wifi_scan`).
- **ESP32-S3 Marauder** — BLE scanning when `include_ble` is true.

## Implementation notes

Runs three concurrent async tasks:

1. **GPS reader** — reads NMEA sentences from NEO-M9N over UART, maintains
   current fix (lat, lon, alt, hdop, fix quality).
2. **WiFi scanner** — runs continuous channel-hopping capture, correlates each
   new AP/client observation with the current GPS position.
3. **BLE scanner** (optional) — runs BLE advertisement capture, correlates
   with GPS.

Output is streamed to a file in `captures/` (gitignored) and buffered in
memory for the tool return value. For long surveys, only summary statistics
are returned to the model to avoid context exhaustion — the full dataset
lives in the output file.

GPS fix must be acquired before recording begins. The tool reports "waiting
for GPS fix..." until the minimum fix quality is achieved. The NEO-M9N
typically acquires a cold fix in 26s and a warm fix in 1-2s.

## File formats

- **json** — native faust format. Full observation data, machine-readable.
- **kismet_csv** — compatible with Kismet import tools.
- **wigle_csv** — compatible with WiGLE.net bulk upload (for contributing to
  the public wardriving database, if the operator chooses).

## Typical workflow

1. Ensure GPS has a fix (check NEO-M9N status LED or query GPS status)
2. `wardrive interface=wlan1mon duration_s=300` — 5-minute survey
3. Review the output in `captures/`
4. Cross-reference with `wifi_scan` for deeper analysis of specific networks
