# Chunk 1 — Prior Art Survey

**Project:** AI-native pentesting handheld ("vibe-hacking" research device)
**Chunk status:** Complete
**Date:** April 11, 2026

---

## 1. The Pi + Kali handheld genre (saturated, not a competitor)

The "Raspberry Pi running Kali Linux in a handheld shell" concept has existed since roughly 2017 and is a crowded DIY space. Representative projects:

- **ThePwnPal** — Pi + touchscreen + Kali, general-purpose pentesting handheld
- **MobilePenBerry** — similar
- **SwissArmyPi** — similar
- **Pwnagotchi** — Pi Zero, WiFi-only, focused on WPA handshake capture with a gamified "pet" interface
- **P4wnP1** — Pi Zero USB attack platform (HID injection, network implants)
- **Null Byte's Pi Box** — tutorial-style builds

**Common pattern:** Pi-class compute + Kali toolchain + small screen + battery, typically WiFi-only or WiFi + Bluetooth via the Pi's built-in radios. Linux-first, CLI-driven, no agent layer, no multi-radio RF integration beyond 2.4GHz.

**Relevance to this build:** These establish that the "Pi in a handheld" form factor is well-understood and supported. They are *not* competitors — none of them integrate Flipper-class multi-radio RF, and none have an on-device LLM agent layer.

---

## 2. HackBat — closest multi-radio open-source prior art (reference design, not competitor)

Created by Pablo Trujillo, 2024. Documented on Hackster.io, GitHub (`controlpaths/hackbat`), Tom's Hardware, CNX Software, Circuit Digest.

### Hardware
| Component | Chip | Interface | Function |
|---|---|---|---|
| MCU | RP2040 (dual Cortex-M0+ @ 133MHz, 264KB SRAM) | — | Main controller |
| Sub-GHz RF | TI CC1101 | SPI | 315 / 433 / 868 / 915 MHz |
| NFC | NXP PN532 | I2C | 13.56 MHz |
| WiFi | ESP-12F (ESP8266) | UART via RP2040 USB-UART bridge | 2.4 GHz |
| Display | 128x64 OLED, SH110X driver (SSD1306 compatible with mods) | I2C | UI |
| Storage | microSD | SPI | Expansion |
| USB | RP2040 USB host/device | — | HID keyboard emulation |

KiCad files, schematics, PCB layout, BOM, and Gerbers all open-source on GitHub. Manufacturable via JLCPCB.

### Critical caveat
**No firmware was ever released by the creator.** HackBat is hardware-only — anyone building one writes their own firmware on top of Arduino libraries for each peripheral. Multiple community forks exist (e.g. `rgomez31UAQ/HackBat_Flipper-RP2040`) but no consolidated firmware.

### Relevance to this build
HackBat is a **reference design for the RF peripheral layer**, not a competitor. It's an RP2040 Flipper clone — no compute headroom for ML, no agent layer, no touchscreen. The CC1101 + PN532 + ESP-for-WiFi combination is the well-trodden path for multi-radio DIY and the HackBat KiCad files are worth reading before finalizing the RF portion of the BOM.

---

## 3. LLM + pentesting landscape (active category, but not on edge hardware)

Local-LLM pentesting agents are a real and growing category in 2026. Representative work:

### METATRON (April 2026)
- Open-source (MIT), `github.com/sooryathejas/METATRON`
- Parrot OS / Debian-based Linux
- CLI-based, Python 3
- Orchestrates nmap, nikto, whois, dig, whatweb, curl
- Local LLM via Ollama — fine-tuned `metatron-qwen` (Qwen 3.5 9B abliterated variant)
- 16,384-token context, agentic loop (model can request more tool runs mid-analysis)
- Min 8.4 GB RAM for the 9B model
- Zero-exfiltration guarantee (all inference on-device)

### PentAGI (vxcontrol/pentagi, 10k+ GitHub stars)
- Go backend, React frontend, GraphQL
- Multi-agent (Researcher, Developer, Executor) in isolated Docker containers
- Supports OpenAI, Anthropic, and local models via Ollama
- Local-LLM guide recommends **4× RTX 5090 GPUs** for Qwen 3.5-27B-FP8
- Minimum stated: 2 vCPU + 4GB RAM (but real performance needs much more)

### PentestAgent (academic, arXiv Nov 2024)
- Multi-agent framework with RAG
- Reconnaissance, search, planning, execution agents
- Benchmarked against VulHub + HackTheBox CTF targets
- GPT-4 > GPT-3.5 in results; Llama 3.1 tested with hardware limits

### PentestGPT v2 (arXiv Feb 2026)
- **Key finding applicable to this project:** analyzed 28 LLM pentesting systems and categorized failures:
  - **Type A failures** — capability gaps (missing tools, bad prompts) — addressable by engineering
  - **Type B failures** — planning and state management limits — persist regardless of tooling
- Introduces Task Difficulty Assessment (TDA): horizon estimation, evidence confidence, context load, historical success rate
- Reports: augmenting with difficulty assessment drops Type B failure rate from 58% to 27%
- Tool and Skill Layer with typed interfaces for 38 security tools + skill compositions encoding expert attack patterns

---

## 4. The actual gap this project occupies

Not "LLM + pentesting" (well-explored). Not "multi-radio DIY" (HackBat and Flipper). The **three-way intersection** is empty:

1. Local-LLM agentic pentesting
2. Multi-radio RF (Flipper-class, not just WiFi)
3. Handheld / embedded / battery-powered form factor

No project found occupies this intersection. Every LLM pentesting agent surveyed assumes workstation-class hardware (Docker, Ollama, multi-GPU). Every multi-radio handheld (Flipper, HackBat, M1) is MCU-class with no compute for ML. This project is Pi 5 + NPU (AI HAT+ 2 with Hailo-10H) + ESP32/Marauder + eventual CC1101/PN532 + local LLM + agent — the embedded constraint is what forces the architectural interest.

---

## 5. Implications for build & framing

1. **Novelty claim to use in writeups and README:** "Local-LLM agentic pentesting on constrained edge hardware with integrated multi-radio RF." Defensible under the April 2026 survey. Avoid broader claims like "first LLM pentesting tool" — those are false.

2. **HackBat schematics are worth reading** before finalizing the RF BOM. CC1101 + PN532 is a known-good combo with working KiCad.

3. **Skill/tool layer is the right architecture.** Field is converging here (PentestGPT v2's Tool and Skill Layer, PentAGI's agent specialization, METATRON's tool orchestration). Validates the general OpenClaw-style approach, doesn't validate OpenClaw specifically — chunk 2 question.

4. **Type B failures are the real risk,** not tool access. Agent loop design, context management, and difficulty assessment matter more than piling on tools. Consider a lightweight TDA-style mechanism even in v1.

5. **Zero-exfiltration framing is increasingly legible in the space.** METATRON leads with it. This aligns naturally with the two-layer disclosure model you already planned — frame it as "data stays on device, actions are disclosed to operator." That's a coherent research/policy narrative.

---

## References (primary sources from research)

- HackBat — https://github.com/controlpaths/hackbat
- HackBat Hackster writeup — https://www.hackster.io/pablotrujillojuan/hackbat-1dfdbc
- METATRON — https://github.com/sooryathejas/METATRON (referenced in CybersecurityNews coverage April 2026)
- PentAGI — https://github.com/vxcontrol/pentagi
- PentestAgent — https://arxiv.org/html/2411.05185v1
- PentestGPT v2 — https://arxiv.org/html/2602.17622v1

---

**Next chunk:** Agent harness evaluation (OpenClaw vs. Hermes vs. Claude Agent SDK vs. raw tool-use loop — and whether a framework is even necessary given the fixed tool set).
