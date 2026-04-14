---
name: pcap_inspect
description: >
  Analyze a captured PCAP for interesting traffic — credentials, cleartext
  protocols, DNS queries, HTTP endpoints, 802.11 handshakes. Passive —
  operates on already-captured data.
parameters_schema:
  type: object
  properties:
    pcap_path:
      type: string
      description: Path to .pcap or .pcapng
    extract:
      type: array
      items:
        type: string
        enum: ["creds", "dns", "http", "handshakes", "pmkid", "images", "smb", "all"]
      description: What to extract. Default ["creds", "dns", "http", "handshakes"].
    max_items_per_category:
      type: integer
      description: Cap results per category. Default 50.
  required:
    - pcap_path
sensitivity: passive
allowed_tools:
  - pcap_inspect
---

# PCAP Inspect

Offline analysis of captured traffic. Surfaces the "interesting" subset
without overwhelming the agent with packet-level detail.

## What it returns

```json
{
  "pcap_path": "captures/evil_portal_1745174400.pcap",
  "packet_count": 48291,
  "credentials": [
    {"protocol": "http-basic", "user": "alice", "pass_sha256": "..."},
    {"protocol": "ftp", "user": "admin", "pass_sha256": "..."}
  ],
  "dns_queries": [
    {"name": "analytics.example.com", "count": 142},
    {"name": "login.target.com", "count": 7}
  ],
  "http_requests": [
    {"method": "POST", "url": "https://target/login", "user_agent": "..."}
  ],
  "wpa_handshakes": [
    {"bssid": "aa:bb:cc:dd:ee:ff", "ssid": "TargetNet",
     "hash_file": "captures/extracted_22000.hash"}
  ]
}
```

## Implementation

- `tshark` with display filters for each extraction type
- `aircrack-ng` to identify WPA handshakes
- `hcxpcapngtool -o output.22000 capture.pcapng` for PMKID/handshake extraction
- Credentials never logged in plaintext — hashes only, actual values stored
  in an encrypted captures/ side-file

## Scope

- Analyzing pcap you captured yourself — fine
- Analyzing pcap obtained without authorization — legal trouble
