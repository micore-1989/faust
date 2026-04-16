---
name: deauth_detector
description: >
  Defense: passively monitor 802.11 deauth/disassoc frames to detect an
  active jamming or evil-twin attack against nearby APs.
parameters_schema:
  type: object
  properties:
    interface:
      type: string
      description: Monitor-mode WiFi interface (e.g. wlan1mon)
    duration_s:
      type: integer
      description: Monitoring duration. 0 = run until manually stopped. Default 60.
    channel:
      type: integer
      description: Lock to a specific channel. Omit to hop all channels.
    threshold:
      type: integer
      description: >
        Alert when more than N deauth frames are seen per source MAC per
        minute. Default 5 (typical attacks emit 50-500 frames/minute;
        legitimate disassocs are much rarer).
  required:
    - interface
typical_duration_s: 60
sensitivity: passive
allowed_tools:
  - deauth_detector
pivot_hints:
  - when: "summary.under_attack == true"
    suggest: "Active deauth attack in progress from summary.attacker_mac against summary.target_bssid. Operator options: alert only, wifi_scan to locate the attacker's AP, or rogue_ap_detector to correlate with evil-twin activity."
---

# Deauth Detector

Counter-surveillance tool. Watches for 802.11 deauthentication and
disassociation frames, which are the hallmark of active WiFi attacks
(including the ones Faust itself can perform).

## What it returns

```json
{
  "monitoring_duration_s": 60,
  "deauth_frames_seen": 237,
  "disassoc_frames_seen": 12,
  "alerts": [
    {
      "source_mac": "aa:bb:cc:dd:ee:ff",
      "target_bssid": "11:22:33:44:55:66",
      "target_ssid": "HomeWiFi",
      "frames_per_minute": 185,
      "first_seen": "2026-04-20T14:30:12Z",
      "last_seen": "2026-04-20T14:31:45Z",
      "likely": "attack"
    }
  ],
  "pcap_path": "captures/deauth_monitor_1745174400.pcap"
}
```

## Hardware

- **ALFA AWUS036ACM** (MT7612U) in monitor mode — same adapter as offensive
  WiFi skills. The ALFA's monitor mode lets us see management frames
  directly.

## Implementation notes

Uses scapy to sniff management frames and filter for subtypes 0xC
(deauthentication) and 0xA (disassociation):

```python
from scapy.all import sniff, Dot11
def handle(pkt):
    if pkt.haslayer(Dot11) and pkt.type == 0 and pkt.subtype in (0xC, 0xA):
        ...
sniff(iface="wlan1mon", prn=handle, store=False)
```

For each (source, target) pair, keep a rolling 60-second counter. Emit
an alert when the threshold is crossed. Write full frames to a PCAP for
later analysis.

## Why this matters

- **Detect attacks in progress.** Deauth floods are the first step in
  most WiFi attack chains (handshake capture, PMKID, evil-twin).
- **Validate your own activity.** After running `wifi_deauth`, use this
  to confirm the frames hit the intended target.
- **Physical security.** A surprise deauth storm at a venue is often a
  signal that someone is actively probing.

## Typical workflow

1. `deauth_detector interface=wlan1mon duration_s=600` — watch for 10 min
2. Review alerts: any unexpected attacks on your own network?
3. If alerted, cross-reference with `wifi_scan` to identify the attacker
