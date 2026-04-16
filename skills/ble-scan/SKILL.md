---
name: ble_scan
description: >
  Scan for nearby Bluetooth Low Energy devices. Returns device names, MAC
  addresses, RSSI, advertised services, and manufacturer data. Passive —
  listens to BLE advertisements only.
parameters_schema:
  type: object
  properties:
    duration_s:
      type: integer
      description: >
        Scan duration in seconds. BLE advertisements are periodic (typically
        20ms–10s intervals), so longer scans catch more devices. Default 10.
    filter_name:
      type: string
      description: >
        Optional substring filter on device name. Case-insensitive. Only
        devices whose advertised name contains this string are returned.
    filter_rssi:
      type: integer
      description: >
        Minimum RSSI in dBm. Devices weaker than this are excluded.
        Useful for proximity filtering (e.g. -60 = roughly within 5m).
  required: []
typical_duration_s: 20
sensitivity: passive
allowed_tools:
  - ble_scan
pivot_hints:
  - when: "summary.connectable >= 1"
    suggest: "Connectable devices present — ble_service_enum can list their GATT services and identify writable characteristics."
  - when: "summary.devices_found == 0"
    suggest: "No BLE devices in range. The environment may be RF-quiet or the radio may not be in scanning mode. Consider rf_spectrum_scan around 2.4 GHz to confirm."
---

# BLE Scan

Passive Bluetooth Low Energy reconnaissance. Listens for BLE advertisement
packets and builds a device inventory of the local RF environment.

## What it returns

```json
{
  "devices": [
    {
      "name": "Tile Mate",
      "mac": "aa:bb:cc:dd:ee:ff",
      "rssi_dbm": -48,
      "address_type": "random",
      "services": ["0000feed-0000-1000-8000-00805f9b34fb"],
      "manufacturer_data": {"004c": "0215..."},
      "connectable": true
    }
  ],
  "scan_duration_s": 10,
  "total_advertisements": 312
}
```

## Hardware

- **ESP32-S3 Marauder** — handles BLE scanning via Marauder firmware's
  `scanble` command over USB-serial. The Marauder's onboard ESP32-S3 has a
  capable BLE 5.0 radio.
- Alternatively, the Pi's onboard Bluetooth can be used via `bluetoothctl` or
  `bleak` (Python async BLE library), but the Marauder provides richer raw
  advertisement data.

## Implementation notes

Two possible backends:

1. **Marauder serial** — send `scanble` command over USB-serial, parse the
   Marauder output format. Faster bring-up, less control.
2. **bleak (Python)** — native async BLE scanning via the Pi's Bluetooth
   adapter. More control over filtering and service enumeration, but requires
   `bluetoothd` not to be holding the adapter.

Prefer Marauder for v1 since it's already connected and the firmware handles
the low-level BLE stack. Fall back to bleak if Marauder BLE proves unreliable.

## Typical workflow

1. `ble_scan` (this tool) — discover BLE devices in range
2. Operator picks a target device
3. BLE service enumeration (future skill) — connect and list GATT services
4. BLE read/write (future skill) — interact with specific characteristics
