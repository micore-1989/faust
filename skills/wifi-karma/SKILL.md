---
name: wifi_karma
description: >
  Karma attack — monitors probe requests from nearby devices and responds
  to each one as if Faust is the requested network. Devices then auto-connect
  to Faust's rogue AP. DISRUPTIVE.
parameters_schema:
  type: object
  properties:
    interface:
      type: string
      description: Monitor-mode interface
    duration_s:
      type: integer
      description: How long to run. Default 300.
    restrict_to_opens:
      type: boolean
      description: Only respond to open-network probes (never WPA). Safer. Default true.
  required:
    - interface
typical_duration_s: 60
sensitivity: disruptive
allowed_tools:
  - wifi_karma
---

# WiFi Karma

Mass rogue AP attack. Uses a single radio to sniff probe requests and
impersonate any SSID the client asks about. Phones with remembered open
networks ("CoffeeShop", "FreeWiFi", "airport") silently reconnect.

## What it returns

```json
{
  "probes_seen": 1247,
  "ssids_impersonated": ["FreeWiFi", "Starbucks", "attwifi"],
  "clients_associated": [
    {"mac": "aa:bb:cc:dd:ee:ff", "ssid": "Starbucks", "duration_s": 45}
  ],
  "duration_s": 300
}
```

## Implementation

- `hostapd-mana` (the actively-maintained Karma fork) on ALFA AWUS036ACM
- Or `eaphammer` with `--bssid-hop`
- Configure to respond only to open-auth probes for safety

## Scope

- Affects every device in range with remembered open networks
- Extremely disruptive in public spaces — only in isolated test environments
- Disclosure layer requires hold-to-confirm
