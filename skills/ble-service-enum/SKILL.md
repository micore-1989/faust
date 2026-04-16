---
name: ble_service_enum
description: >
  Connect to a BLE device and enumerate its GATT services, characteristics,
  and descriptors. Reveals how the device can be interacted with. Active —
  initiates a connection.
parameters_schema:
  type: object
  properties:
    mac:
      type: string
      description: Target BLE MAC address (from ble_scan)
    read_values:
      type: boolean
      description: Read the current value of each readable characteristic. Default true.
    timeout_s:
      type: integer
      description: Connection timeout. Default 15.
  required:
    - mac
typical_duration_s: 10
sensitivity: active
allowed_tools:
  - ble_service_enum
---

# BLE Service Enumeration

Connects to a BLE peripheral and walks its GATT tree. Returns every service,
characteristic, flag (read/write/notify/indicate), and (optionally) the
current readable value.

## What it returns

```json
{
  "mac": "aa:bb:cc:dd:ee:ff",
  "services": [
    {
      "uuid": "0000180f-0000-1000-8000-00805f9b34fb",
      "name": "Battery Service",
      "characteristics": [
        {
          "uuid": "00002a19-...",
          "name": "Battery Level",
          "flags": ["read", "notify"],
          "value_hex": "58"
        }
      ]
    }
  ]
}
```

## Implementation

`bleak` (Python async BLE):

```python
async with BleakClient(mac) as client:
    for svc in client.services:
        for char in svc.characteristics: ...
```

Marauder can do simple enum via `gatt`, but bleak is more capable.

## Scope

- Creates a log entry on many devices ("connected to unknown device")
- Some devices require pairing before enumeration
