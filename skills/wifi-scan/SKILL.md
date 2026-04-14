---
name: wifi_scan
description: >
  Scan for nearby WiFi networks and clients using monitor mode. Returns SSIDs,
  BSSIDs, channels, signal strength, encryption type, and associated clients.
  Passive — listens only, does not transmit.
parameters_schema:
  type: object
  properties:
    interface:
      type: string
      description: >
        WiFi interface in monitor mode (e.g. wlan1mon). The ALFA AWUS036ACM
        must be placed into monitor mode before scanning.
    duration_s:
      type: integer
      description: >
        Scan duration in seconds. Longer scans catch more intermittent clients.
        Default 10.
    band:
      type: string
      enum: ["2.4", "5", "all"]
      description: >
        Frequency band to scan. "2.4" = 2.4 GHz only, "5" = 5 GHz only,
        "all" = both bands. Default "all".
    channel:
      type: integer
      description: >
        Lock to a specific channel instead of hopping. Omit to hop all
        channels in the selected band.
  required:
    - interface
sensitivity: passive
allowed_tools:
  - wifi_scan
---

# WiFi Scan

Passive 802.11 reconnaissance. Puts the ALFA AWUS036ACM into monitor mode and
captures beacon frames, probe requests, and data frames to build a picture of
the local WiFi environment.

## What it returns

```json
{
  "networks": [
    {
      "ssid": "TargetNet",
      "bssid": "aa:bb:cc:dd:ee:ff",
      "channel": 6,
      "rssi_dbm": -42,
      "encryption": "WPA2-PSK",
      "clients": [
        {"mac": "11:22:33:44:55:66", "rssi_dbm": -55, "probes": ["OtherNet"]}
      ]
    }
  ],
  "scan_duration_s": 10,
  "total_frames": 4821
}
```

## Hardware

- **ALFA AWUS036ACM** (MediaTek MT7612U) — USB WiFi adapter with monitor mode +
  packet injection on both 2.4 GHz and 5 GHz. Uses the in-kernel `mt76` driver
  on Pi 5 Bookworm — no out-of-tree driver needed.
- Pi onboard WiFi cannot do monitor mode on 5 GHz or inject packets — it stays
  on the management network.

## Implementation notes

Uses `airodump-ng` (aircrack-ng suite) or raw scapy sniffing. The adapter
must be placed into monitor mode first (`airmon-ng start wlan1`). The tool
should handle mode switching automatically if the interface isn't already in
monitor mode.

Channel hopping uses the kernel's built-in channel-hop when no specific channel
is requested. Locking to a channel is useful when targeting a known AP for
client enumeration or pre-handshake-capture recon.

## Typical workflow

1. `wifi_scan` (this tool) — discover networks and clients
2. Operator picks a target BSSID + client
3. `wifi_deauth` — force client reconnection (disruptive, requires confirmation)
4. Handshake capture (future skill) — grab the 4-way handshake during reconnect
