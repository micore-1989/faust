---
name: wifi_handshake_capture
description: >
  Capture a WPA/WPA2 4-way handshake by listening on a target channel while
  a client reconnects. Typically chained after wifi_deauth to force a
  reconnection. The captured handshake can be cracked offline.
parameters_schema:
  type: object
  properties:
    interface:
      type: string
      description: Monitor-mode WiFi interface.
      default: wlan1mon
    bssid:
      type: string
      description: Target access point BSSID. Pre-fill from best_handshake_target of a prior wifi_scan summary when available.
    channel:
      type: integer
      description: Channel of the target AP. Pre-fill from top_3[].channel in the matching wifi_scan entry.
      default: 6
    timeout_s:
      type: integer
      description: How long to listen before giving up. A client must associate within this window.
      default: 120
    output_file:
      type: string
      description: PCAP output path. Defaults to captures/handshake_<bssid>_<ts>.pcap when omitted.
  required:
    - bssid
typical_duration_s: 120
sensitivity: active
allowed_tools:
  - wifi_handshake_capture
pivot_hints:
  - when: "summary.captured == true"
    suggest: "Handshake captured — hash_file is at summary.hash_file. wpa_crack can now attempt offline brute force with a wordlist."
  - when: "summary.captured == false"
    suggest: "No client reconnected within the timeout. Consider wifi_deauth against an associated client (from a prior wifi_scan) to force reassociation, or switch to wifi_pmkid_capture which does not require a client."
---

# WiFi Handshake Capture

Passive-then-active 802.11 handshake capture. Listens on the target channel
for the 4-way EAPOL exchange between an AP and a client during association.
Writes a PCAP that can be cracked offline with hashcat / aircrack-ng.

## What it returns

```json
{
  "captured": true,
  "bssid": "aa:bb:cc:dd:ee:ff",
  "ssid": "TargetNet",
  "client": "11:22:33:44:55:66",
  "eapol_frames": 4,
  "pcap_path": "captures/handshake_aabbccddeeff_1745174400.pcap",
  "crack_hint": "hashcat -m 22000 captures/handshake_aabbccddeeff_1745174400.pcap wordlist.txt"
}
```

## Hardware

- **ALFA AWUS036ACM** (MT7612U) in monitor mode
- ESP32-S3 Marauder can also do this via its `sniffpmkid` / `sniffeapol`
  commands, written to its onboard microSD

## Implementation notes

Two approaches:

1. **aircrack-ng** — `airodump-ng -c <ch> --bssid <bssid> -w <out> wlan1mon`.
   The handshake is detected when 2+ EAPOL frames are captured in the
   correct sequence. Watch stderr for `[ WPA handshake: <bssid> ]`.

2. **Marauder** — send `sniffeapol` command over USB-serial. Marauder writes
   PCAP to its microSD. Faust polls for the file, copies over USB storage.

Prefer aircrack-ng on Faust for tight integration. Fall back to Marauder
if the ALFA is busy with another skill.

## Typical workflow

1. `wifi_scan` — identify target BSSID and a currently-associated client
2. `wifi_deauth` — force the client to reconnect (disruptive, requires confirm)
3. `wifi_handshake_capture` (this skill) — capture the reconnect
4. `hashcat_crack` (future skill) — offline brute force with a wordlist

## Scope requirements

- Operator must have authorization to capture handshakes on this network
- Cracking the captured handshake offline is legally distinct from capture —
  both require authorization
- Testing MUST be on a router you own, on an isolated VLAN
