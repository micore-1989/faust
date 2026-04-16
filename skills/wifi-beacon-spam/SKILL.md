---
name: wifi_beacon_spam
description: >
  Flood fake SSID beacons to confuse WiFi scanners and stress-test client
  stacks. DISRUPTIVE — consumes airtime on 2.4/5 GHz bands.
parameters_schema:
  type: object
  properties:
    interface:
      type: string
      description: Monitor-mode interface
    ssid_list:
      type: array
      items: {type: string}
      description: SSIDs to broadcast. Omit for random/funny defaults.
    channel:
      type: integer
      description: Channel to broadcast on. Default 6.
    count_per_ssid:
      type: integer
      description: Beacons per second per SSID. Default 10.
    duration_s:
      type: integer
      description: How long. Default 30.
  required:
    - interface
typical_duration_s: 60
sensitivity: disruptive
allowed_tools:
  - wifi_beacon_spam
---

# WiFi Beacon Spam

Broadcasts thousands of fake beacons, filling nearby devices' SSID lists
with junk. Historically used as a Flipper-Zero iOS DoS (pre-17.2 crash).
Modern use: test WiFi scanner behavior and detection tuning.

## What it returns

```json
{
  "ssids_broadcast": 200,
  "beacons_sent": 180000,
  "channel": 6,
  "duration_s": 30
}
```

## Implementation

ESP32-S3 Marauder `attackap` or scapy-based beacon flooder on the ALFA:

```
sudo mdk4 wlan1mon b -c 6 -s 500
```

## Scope

- Consumes 2.4/5 GHz airtime — degrades adjacent networks
- Only in isolated RF environments with authorization
