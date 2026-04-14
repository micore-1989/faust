---
name: http_recon
description: >
  Web application reconnaissance — fingerprint, directory brute force, find
  endpoints, identify technologies. Sends many HTTP requests to the target.
parameters_schema:
  type: object
  properties:
    target_url:
      type: string
      description: Target URL (e.g. "https://target.example.com")
    wordlist:
      type: string
      enum: ["common", "big", "api"]
      description: Wordlist size. "common" ~4K entries, "big" ~220K, "api" ~1K. Default "common".
    threads:
      type: integer
      description: Concurrent requests. Higher is faster but more detectable. Default 10.
    recursive:
      type: boolean
      description: Recursively scan found directories. Default false.
  required:
    - target_url
sensitivity: active
allowed_tools:
  - http_recon
---

# HTTP Recon

Web recon — identifies server software, framework, hidden endpoints, and
common misconfigurations. Combines fingerprinting with directory/file
brute forcing.

## What it returns

```json
{
  "target": "https://target.example.com",
  "server": "nginx/1.24.0",
  "technologies": ["PHP", "WordPress 6.4", "jQuery 3.6"],
  "endpoints_found": [
    {"path": "/admin", "status": 200, "length": 1842},
    {"path": "/.git/config", "status": 200, "length": 92},
    {"path": "/api/v1/users", "status": 401, "length": 42}
  ],
  "total_requests": 4211,
  "scan_duration_s": 45
}
```

## Implementation

- `whatweb` or `wappalyzer-cli` for fingerprinting
- `ffuf` or `gobuster` for directory brute force
- Parse and correlate outputs into structured JSON

```
ffuf -w /wordlists/common.txt -u https://target/FUZZ -t 10 -of json
```

## Scope

- Generates obvious log volume on target
- Respect rate limits and robots.txt for engagement scoping
- Only against targets in-scope for the engagement
