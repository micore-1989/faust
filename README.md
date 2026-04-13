# faust

AI-native pentesting handheld. Local-LLM agent + multi-radio RF + handheld form factor.

**Status:** Build phase, week 1 (Apr 14 – May 15, 2026). Hardware ordered Apr 13. Demo deadline May 15.

## Architecture (one paragraph)

Two-unit split. **Faust** is the operator handheld: Pi 5 1GB, 8" DSI touchscreen, full RF stack (HackRF Pro, ESP32 Marauder, ALFA WiFi, PN532 NFC, CC1101 sub-GHz, IR, RFID, iButton, GPS). **Mephisto** is the navigator peripheral: Pi 5 16GB + Hailo-10H AI HAT+ 2 running Qwen 2.5-VL 3B with function calling. They connect over captive USB-C with magnetic dock; transport is HTTP/JSON over USB-ethernet gadget mode. Faust is always master and executes all tool calls. Mephisto only advises (proposes tool calls, never touches dispatch). Two-layer disclosure model: blanket first-boot acceptance + per-action banner with hold-to-confirm for disruptive operations.

See `docs/` for the full design chunks.

## Repo layout

```
faust/                  Python package — agent loop, backends, dispatch, tools
skills/                 SKILL.md files (OpenClaw format) — populated by skill loader
docs/                   Design chunks, parts list, project context
scripts/                OS prep, Pi imager, deployment helpers
captures/               Runtime PCAP/IQ output (gitignored)
```

## Quickstart (dev environment)

Requires Python 3.11+ and a local OpenAI-compatible LLM endpoint for development.

```bash
# 1. Virtualenv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Local LLM (matches what Hailo runs in production)
brew install ollama         # macOS
ollama pull qwen2.5:3b-instruct
ollama serve &              # background

# 3. Run the agent against a trivial demo prompt
export FAUST_MODEL=qwen2.5:3b-instruct
python -m faust.cli "add 17 and 25, then echo the answer"

# 4. Run tests (no LLM required — uses mock backend)
python -m faust.tests.test_loop
```

## Configuration

All backend/model/endpoint config flows through `faust/agent/config.py`. Override via env:

| Variable | Default | Notes |
|---|---|---|
| `FAUST_BACKEND` | `ollama` | `ollama` \| `claude` |
| `FAUST_LLM_ENDPOINT` | `http://localhost:11434/v1` | OpenAI-compatible `/v1` root |
| `FAUST_MODEL` | `qwen2.5:1.5b-instruct` | Whatever the backend serves |
| `FAUST_API_KEY` | — | Claude backend only |

In production on Faust: `FAUST_LLM_ENDPOINT=http://mephisto.local:8000/v1`.

## Project status

| Component | Status |
|---|---|
| Agent loop scaffold (Ring 4, async) | ✓ done, 7 tests passing |
| Skill loader (SKILL.md → registry) | pending |
| Disclosure layer (real Approver) | pending — seam exists in `dispatch.py` |
| UI skeleton (three-zone touchscreen) | pending |
| Faust↔Mephisto transport (USB-ethernet) | pending |
| Mephisto OS prep | pending |

## License

TBD. Currently private.
