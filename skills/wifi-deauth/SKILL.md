---
name: wifi_deauth
description: >
  Send 802.11 deauthentication frames to disconnect a client from an access
  point. Requires monitor-mode interface. DISRUPTIVE — causes immediate
  disconnection of the target client.
parameters_schema:
  type: object
  properties:
    bssid:
      type: string
      description: Target access point BSSID (MAC address)
    client:
      type: string
      description: Target client MAC, or "ff:ff:ff:ff:ff:ff" for broadcast
    interface:
      type: string
      description: Monitor-mode WiFi interface (e.g. wlan0mon)
    count:
      type: integer
      description: Number of deauth frames to send (default 5)
  required:
    - bssid
    - client
    - interface
sensitivity: disruptive
allowed_tools:
  - wifi_deauth
---

# WiFi Deauth

Sends 802.11 deauthentication frames using the specified monitor-mode interface
(ALFA AWUS036ACM, MediaTek MT7612U — in-kernel `mt76` driver on Pi 5 Bookworm).
This is a **disruptive** action — the disclosure layer will require hold-to-confirm
before execution.

## Scope requirements

- Operator must have authorization for the target network
- Target BSSID must be in the declared scope
- Testing MUST be on an isolated VLAN / router you own

## Implementation notes

Requires `aireplay-ng` from the aircrack-ng suite, or raw scapy injection.
The tool.py for this skill is intentionally absent until the ALFA AWUS036ACM
arrives and monitor mode is validated on Pi 5.
