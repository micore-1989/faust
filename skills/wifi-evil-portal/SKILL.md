---
name: wifi_evil_portal
description: >
  Host a rogue access point with a captive portal that mimics a target SSID.
  Clients that connect are presented with a fake login page to harvest
  credentials. DISRUPTIVE — broadcasts an AP and potentially intercepts
  traffic from unwitting clients.
parameters_schema:
  type: object
  properties:
    ssid:
      type: string
      description: SSID to broadcast (should match target network for evil-twin)
    template:
      type: string
      enum: ["google", "office365", "facebook", "starbucks", "custom"]
      description: >
        Pre-built captive portal template. "custom" loads HTML from the path
        specified in `custom_html_path`.
    custom_html_path:
      type: string
      description: Path to custom portal HTML (only used when template=custom)
    channel:
      type: integer
      description: 2.4 GHz channel to broadcast on. Default 6.
    duration_s:
      type: integer
      description: >
        How long to run the portal, in seconds. 0 = until manually stopped.
        Default 300 (5 minutes).
  required:
    - ssid
    - template
sensitivity: disruptive
allowed_tools:
  - wifi_evil_portal
---

# Evil Portal

Broadcasts a rogue WiFi access point with a captive portal that prompts
users for credentials. A common technique for assessing phishing
susceptibility and validating detection controls.

## What it returns

```json
{
  "ap_bssid": "02:11:22:33:44:55",
  "ssid": "TargetNet-Guest",
  "channel": 6,
  "template": "google",
  "clients_connected": 2,
  "credentials_captured": [
    {
      "client_mac": "aa:bb:cc:dd:ee:ff",
      "timestamp": "2026-04-20T14:32:10Z",
      "email": "victim@example.com",
      "password_hash": "sha256:..."
    }
  ],
  "log_file": "captures/evil_portal_1745174400.log"
}
```

## Hardware

- **ESP32-S3 Marauder** — primary path. Marauder firmware has built-in
  Evil Portal support with ~15 template sites. Portal HTML stored on the
  Marauder's microSD. Simple serial command: `evilportal <template>`.
- **Pi 5 + ALFA** alternative — using `hostapd` + `dnsmasq` + custom
  captive portal web server. Much more flexible but more setup.

## Implementation notes

**Marauder path (recommended for v1):**
1. Send `stopscan` to cancel any active scans on Marauder
2. Send `evilportal ssid=<ssid> channel=<ch> template=<name>`
3. Poll Marauder's `getportallog` periodically for captured credentials
4. Send `stopportal` when done

**Pi + ALFA path (more flexible):**
1. Put ALFA into AP mode with `hostapd`
2. Run `dnsmasq` as DHCP + DNS (redirects all hostnames to the portal IP)
3. Serve the portal HTML with a lightweight Python HTTP server
4. Log POST requests to capture credentials

Passwords should be stored as hashes, never plaintext. The journal must
record the fact of capture without the actual credential values.

## Scope requirements

**This skill is sensitivity: disruptive because:**
- It actively deceives users
- Captured credentials have legal/ethical weight even when hashed
- On open frequencies, it may affect nearby networks

- Testing MUST be in an isolated environment with only authorized test users
- NEVER run in a public space, office, or near anyone not in-scope
- The disclosure layer will require hold-to-confirm per the architecture

## Typical workflow

1. `wifi_scan` — identify target SSID to clone
2. `wifi_evil_portal` (this skill) — stand up the rogue AP + portal
3. (Optional) `wifi_deauth` — boot clients off real AP to encourage reconnection
4. Review `captures/evil_portal_*.log` for results
