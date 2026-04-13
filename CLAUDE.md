# Context for Claude Code

This file is read automatically by Claude Code at the start of each session. It exists so context doesn't have to be re-established every time.

## Project

**faust** — AI-native pentesting handheld. Two-unit split: **Faust** (operator handheld, Pi 5 1GB + 8" DSI + full RF stack) and **Mephisto** (navigator peripheral, Pi 5 16GB + Hailo-10H NPU running Qwen 2.5-VL 3B). Connected via captive USB-C with magnetic dock. Communication: HTTP/JSON over USB-ethernet gadget mode.

**Demo deadline:** May 15, 2026. Today is week 1 of a 4-week build window. Hardware ordered Apr 13, arriving staggered Apr 14 – May 11.

## Hard architectural rules — do not violate

1. **Faust is always master.** Mephisto only *advises* (proposes tool calls). Faust is the only thing that ever invokes a tool. The architecture enforces this: the agent loop runs on Faust, and Mephisto is just an HTTP endpoint behind `LLMBackend`.
2. **Backend abstraction is sacrosanct.** All LLM specifics live behind `LLMBackend` in `faust/agent/backends.py`. No `hailo-ollama`-isms or Claude-API-isms anywhere else. Adding a new backend = subclass `LLMBackend`.
3. **Disclosure goes through the dispatch seam.** The agent loop NEVER calls `registry.invoke()` directly — only `dispatcher.dispatch()`. The `Approver` callback is the contract; do not bypass it.
4. **Skills follow OpenClaw SKILL.md format.** YAML frontmatter (`name`, `description`, `allowed_tools`, `sensitivity`) + markdown body. The skill loader populates the same `ToolRegistry` the agent loop consumes.
5. **Sensitivity is a three-class system:** `passive` | `active` | `disruptive`. This is the disclosure layer's contract with skills.

## Architecture decisions already made (chunk references in `docs/`)

- **Compute path:** Pi 5 1GB (Faust) + Pi 5 16GB + Hailo AI HAT+ 2 (Mephisto). See `docs/chunk-3-compute.md` for why this hybrid won over options A/B/C/F.
- **Agent harness:** Roll-our-own Ring 4 async loop. Not Claude Agent SDK (Claude-tied), not OpenClaw runtime (workstation/messaging assumptions). See `docs/chunk-2-agent-harness.md`.
- **Skill format:** OpenClaw `SKILL.md` (format only — not their runtime). See `docs/chunk-2-agent-harness.md`.
- **Transport:** HTTP/JSON over USB-ethernet gadget mode. Mephisto exposes OpenAI-compatible `/v1/chat/completions`.
- **Model:** Qwen 2.5-VL 3B function-calling on Hailo. See `docs/chunk-3-compute.md` for the MikeVeerman tool-calling benchmark that justified small-model choice.
- **Cloud fallback:** Claude API optional when Faust has internet. `ClaudeBackend` stub exists in `backends.py`.

## What's built today

`faust/` package contains the agent loop scaffold:
- `agent/loop.py` — Ring 4 async loop, structured event stream out
- `agent/backends.py` — `LLMBackend` ABC + working `OllamaBackend` + stub `ClaudeBackend`
- `agent/dispatch.py` — disclosure seam; `Approver` callback contract
- `agent/events.py` — `Thinking` / `ToolCallProposed` / `ToolCallExecuted` / `Final`
- `agent/config.py` — single source of backend/endpoint/model truth
- `tools/registry.py` — in-memory tool registry, exports OpenAI tool schemas
- `cli.py` — dev runner with demo `echo` and `add` tools
- `tests/test_loop.py` — 7 tests, mock backend, run with `python -m faust.tests.test_loop`

## What's next (priority order)

1. **Skill loader** — parse `SKILL.md` files in `skills/`, populate `ToolRegistry`. Should support YAML frontmatter validation via pydantic, fail loudly on malformed skills.
2. **Disclosure layer** — real `Approver` implementation. `passive` → log to journal + execute. `active` → confirmation banner, block. `disruptive` → hold-to-confirm gesture, block. Journal must be append-only and tamper-evident.
3. **UI skeleton** — three-zone touchscreen layout (Faust 8" DSI 1280×800). Renders the same event stream the CLI consumes.
4. **Mephisto OS prep script** — Pi imager script for cold-spare microSD; first-boot handles hailo-ollama install + systemd unit (per `docs/chunk-3-compute.md` gotchas).
5. **Faust↔Mephisto transport** — USB-ethernet gadget mode, Mephisto serves `/v1/chat/completions`, Faust points `FAUST_LLM_ENDPOINT` at it.
6. **SKILL.md drafts** for the 6 MK1 priority Pursuits.

## Code style preferences

- **Async by default** for anything I/O-bound. The loop is async; new code that talks to network or hardware should be too.
- **Type hints everywhere.** `from __future__ import annotations` at the top of every file. Use `dict`, `list`, `X | None` (3.11+ syntax).
- **Dataclasses for structured data**, not dicts. Events, configs, tool results.
- **Errors propagate; don't swallow.** The dispatch layer is the one place that catches tool exceptions — everywhere else, let them rise.
- **Tests use a mock backend.** No test should require a running LLM. See `tests/test_loop.py` for the pattern.
- **No premature optimization.** This is a research device under deadline. Working > clever.

## Hardware context

- Faust: Pi 5 1GB, 8" Waveshare DSI 1280×800 (Rev 2.2, fixes Rev 2.1 Pi-5 short bug), Armor Lite V5 cooler, 4× Molicel P30B 18650 in Geekworm X1202 UPS HAT
- Mephisto: Pi 5 16GB + AI HAT+ 2 (Hailo-10H, 40 TOPS, 8GB on-board), Armor Lite V5 cooler, 2× P30B in Geekworm X1201 UPS
- RF on Faust: HackRF Pro (USB-C, 100 kHz – 6 GHz, BACKORDERED until ~Apr 27 – May 11), ESP32-S3 Marauder Add-On (Electronic Cats), ALFA AWUS036ACM USB WiFi (RTL8812AU, monitor mode + injection), PN532, T5577 R/W, RDM6300, CC1101, IR LED + TSOP38238, DS9092 iButton probe, NEO-M9N GPS

## Theme / branding (for UI work)

- Goethe primary palette + Bulgakov accents
- Mathematical italic 𝑓 (Faust) morphs to Ψ (Mephisto) when docked
- Three-zone shell, category navigation, sub-window template

## Files not in git (gitignored — see `.gitignore`)

- `captures/` — PCAP, IQ recordings (large + sensitive)
- `journal.db` — disclosure journal (per-device)
- `models/` — `*.gguf`, `*.hef`, `*.rkllm` model files
- `.env` — secrets (e.g. Claude API key for cloud fallback)

## Operational discipline

- Skills that touch the air (deauth, evil portal, replay, RF transmit) must use `sensitivity: disruptive` in their SKILL.md frontmatter.
- All testing of disruptive skills happens against an SSID on a router I own, on an isolated VLAN. NEVER against the home network.
- Repo is private until I've audited what's in it.
