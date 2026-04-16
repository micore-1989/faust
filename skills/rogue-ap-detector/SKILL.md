---
name: rogue_ap_detector
description: >
  Defense: flag evil-twin APs broadcasting a whitelist SSID from an
  unauthorized BSSID, and enumerate unknown nearby access points.
parameters_schema:
  type: object
  properties:
    interface:
      type: string
      description: Monitor-mode WiFi interface (e.g. wlan1mon)
    whitelist:
      type: array
      items:
        type: object
        properties:
          ssid: {type: string}
          bssid: {type: string}
      description: >
        Known-good SSIDs with their legitimate BSSIDs. Any AP broadcasting
        a whitelisted SSID from a non-whitelisted BSSID is flagged as an
        evil twin.
    duration_s:
      type: integer
      description: Monitoring duration in seconds. Default 60.
    rssi_delta_alert:
      type: integer
      description: >
        Alert when a known BSSID's RSSI changes by more than N dBm between
        scans — may indicate spoofing or position change. Default 20.
  required:
    - interface
typical_duration_s: 60
sensitivity: passive
allowed_tools:
  - rogue_ap_detector
pivot_hints:
  - when: "summary.evil_twins >= 1"
    suggest: "Evil twin detected for SSID summary.victim_ssid on BSSID summary.rogue_bssid. Operator decision: (a) wifi_deauth against the rogue to protect legit clients, (b) alert-only, (c) evidence collection via wifi_handshake_capture scoped to the rogue."
  - when: "summary.unknown_aps >= 5"
    suggest: "Many unknown APs present — environment may be congested or the whitelist may be incomplete. Consider updating the whitelist before treating this as a threat signal."
---

# Rogue AP Detector

Counter-surveillance tool for detecting evil-twin access points — rogue
APs that broadcast the same SSID as a legitimate network to phish credentials
or perform MITM attacks. Also catches unexpected APs on a whitelist-based
policy.

## What it returns

```json
{
  "monitoring_duration_s": 60,
  "networks_seen": 23,
  "evil_twins": [
    {
      "ssid": "CorpWiFi",
      "legitimate_bssid": "aa:bb:cc:11:22:33",
      "rogue_bssid": "02:de:ad:be:ef:00",
      "rogue_rssi_dbm": -45,
      "rogue_channel": 11,
      "legit_channel": 6,
      "encryption_mismatch": true,
      "first_seen": "2026-04-20T14:30:12Z"
    }
  ],
  "unknown_aps": [
    {
      "ssid": "FreeCafeWiFi",
      "bssid": "c0:ff:ee:11:22:33",
      "channel": 1,
      "rssi_dbm": -52
    }
  ],
  "whitelist_matches": 3
}
```

## Hardware

- **ALFA AWUS036ACM** (MT7612U) in monitor mode

## Implementation notes

Two detection heuristics:

**1. Whitelist mismatch (evil twin)**
For each AP observed, check if its SSID is on the whitelist. If yes,
check if the BSSID matches. If the SSID matches but the BSSID doesn't,
it's an evil twin.

**2. Feature mismatch**
Compare the suspected evil twin's features against the known-good AP:
- Different channel → suspicious (same SSID usually means same AP, same channel)
- Different encryption (e.g. WPA2 → open) → definitely suspicious
- Different vendor OUI on the BSSID → strong signal of rogue

**3. RSSI anomaly (optional)**
Track RSSI over time. A legitimate AP's RSSI drifts slowly (±5 dBm as
you move). A sudden large change can indicate a different physical device
spoofing the MAC.

Uses scapy or airodump-ng CSV output. scapy is more flexible for custom
heuristics.

## Whitelist config

Whitelists can be built incrementally — on first run, snapshot all
currently-visible "trusted" APs (you're on your home network, you know
them) and save as `whitelist.json`. Future runs alert on any deviation.

Example:
```json
[
  {"ssid": "HomeWiFi", "bssid": "aa:bb:cc:dd:ee:ff"},
  {"ssid": "HomeWiFi-5G", "bssid": "aa:bb:cc:dd:ee:f0"},
  {"ssid": "CorpWiFi", "bssid": "11:22:33:44:55:66"}
]
```

## Why this matters

- Evil-twin attacks are the #1 credential theft vector for public WiFi
- Hotel/airport/conference networks are particularly vulnerable
- Most end users cannot distinguish a rogue AP from the real one; a
  detector device in your pocket can

## Typical workflow

1. First visit to a venue: `wifi_scan` + save the result as whitelist
2. Later visits: `rogue_ap_detector` with that whitelist
3. If alerts fire, avoid connecting and move to cellular data
