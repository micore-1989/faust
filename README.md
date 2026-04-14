# faust

AI-native pentesting handheld. Local-LLM agent + multi-radio RF + handheld form factor.

**Status:** Build phase, week 1 (Apr 14 – May 15, 2026). Hardware ordered Apr 13. Demo deadline May 15.

## Architecture (one paragraph)

Two-unit split. **Faust** is the operator handheld: Pi 5 1GB, 8" DSI touchscreen, full RF stack (HackRF Pro, ESP32 Marauder, ALFA WiFi, PN532 NFC, CC1101 sub-GHz, IR, RFID, iButton, GPS). **Mephisto** is the navigator peripheral: Pi 5 16GB + Hailo-10H AI HAT+ 2 running Qwen 2.5-VL 3B with function calling. They connect over captive USB-C with magnetic dock; transport is HTTP/JSON over USB-ethernet gadget mode. Faust is always master and executes all tool calls. Mephisto only advises (proposes tool calls, never touches dispatch). Two-layer disclosure model: blanket first-boot acceptance + per-action banner with hold-to-confirm for disruptive operations.

See `docs/` for the full design chunks.

## Repo layout

```
faust/                  Python package
  agent/                loop, backends, dispatch, disclosure, journal
  skills/               SKILL.md loader
  tools/                tool registry
  transport/            Faust↔Mephisto link management
  ui/                   aiohttp + WebSocket + three-zone web UI
  tests/                mock-backend tests, no hardware needed
skills/                 SKILL.md files (OpenClaw format)
deploy/                 Pi provisioning scripts (mephisto/, faust/)
docs/                   Design chunks, parts list, project context
captures/               Runtime PCAP/IQ output (gitignored)
journal.db              Tamper-evident disclosure journal (gitignored)
```

## Two environments, one codebase

The agent is designed to run identically in two places — development on a Mac/Linux
workstation and production on the Pi hardware. The only thing that changes is env vars.

| | Mac dev | Faust + Mephisto (prod) |
|---|---|---|
| `FAUST_BACKEND` | `ollama` (default) | `mephisto` |
| LLM endpoint | `localhost:11434/v1` | `10.66.0.2:8000/v1` (USB-ethernet) |
| LLM runtime | Ollama | hailo-ollama on Mephisto's Hailo-10H NPU |
| Skills | Same `skills/` directory | Same `skills/` directory |
| Tool implementations | Stubs return "not implemented" | Real `tool.py` per skill (wired as hardware arrives) |
| UI | Chromium / Safari on your desktop | Chromium kiosk on 8" DSI |
| Disclosure journal | `journal.db` at project root | Same |
| Confirmation UI | CLI stdin OR web overlay | Web overlay on touchscreen |

**No code changes between environments.** The `OllamaBackend` speaks OpenAI-compatible
HTTP; hailo-ollama exposes the same protocol. All backend specifics live behind
`faust/agent/backends.py`.

## Python environments

Three requirements files for three scenarios — keeps Faust's 1GB Pi lean:

| File | For | Installs |
|---|---|---|
| `requirements.txt` | **Faust deployment** (Pi 5 1GB) | Core only (~50MB). No torch. Works because Faust uses RemoteEmbeddingScoper — Mephisto does all ML. |
| `requirements-mephisto.txt` | **Mephisto deployment** (Pi 5 16GB) | Core + sentence-transformers + torch + numpy. Needed for scoper service + potentially local LLM fallback. |
| `requirements-dev.txt` | **Mac/Linux development** | Everything — lets you run the full stack locally, run all tests, iterate on agent logic. |

## Quickstart — Mac dev

```bash
# 1. Virtualenv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt      # core + scoper (torch) for local dev

# 2. Local LLMs (both models — Ollama serves them from the same endpoint)
brew install ollama
ollama pull qwen2.5:1.5b-instruct   # fast (Pass 2 parameterize)
ollama pull qwen2.5:7b-instruct     # deep (Pass 1 planning)
ollama serve &

# 3a. Run tests (no LLM needed — mock backend)
python -m faust.tests.test_loop
python -m faust.tests.test_skill_loader
python -m faust.tests.test_disclosure
python -m faust.tests.test_transport
python -m faust.tests.test_ui

# 3b. Run against a prompt via CLI
python -m faust.cli "add 17 and 25, then echo the answer"

# 3c. Run the touchscreen UI in your browser
python -m faust.ui.run            # live agent — talks to Ollama
python -m faust.ui.run --demo     # synthetic events for layout prototyping
# open http://localhost:8080
```

### Dev simulator — simulate the Faust+Mephisto split on one Mac

`python -m faust.ui.run` loads the scoper **in-process** on Mac. That's fine
for agent logic iteration, but it doesn't exercise the HTTP scoper service
that Faust will use in production.

For a more realistic dev setup, use the simulator. It spins up two Python
processes: the scoper service (mimics Mephisto :8082) and the UI (configured
to use `RemoteEmbeddingScoper` against the local scoper service):

```bash
bash deploy/dev-simulator.sh start     # start scoper + UI
bash deploy/dev-simulator.sh status    # check what's running
bash deploy/dev-simulator.sh logs      # tail both services
bash deploy/dev-simulator.sh stop      # stop everything
```

Ollama still runs as your LLM backend (the simulator doesn't manage it —
you start `ollama serve &` separately). The scoper runs in a separate Python
process on port 8082, exactly as it will on Mephisto.

This mode catches bugs that the in-process scoper never hits:
- HTTP serialization issues
- Scoper process dying / being restarted mid-session
- Latency tolerance in the RemoteEmbeddingScoper client

Logs are written to `.dev-sim/logs/` (gitignored).

## Quickstart — Faust + Mephisto (prod)

```bash
# On Mephisto (Pi 5 16GB + Hailo HAT):
#   1. Flash Pi OS Lite 64-bit to microSD
#   2. git clone + pip install -r requirements-mephisto.txt
#   3. Install hailo-ollama, pull Qwen 2.5 1.5B (fast backend, port 8000)
#   4. Run deploy/mephisto/setup-gadget.sh    — USB-ethernet gadget mode
#   5. Run deploy/mephisto/setup-planning.sh  — llama.cpp + Qwen 2.5 7B (port 8081)
#   6. Run deploy/mephisto/setup-scoper.sh    — embedding scoper service (port 8082)
#   7. Reboot — Mephisto serves three endpoints on 10.66.0.2:
#        :8000 fast LLM (hailo-ollama, Qwen 1.5B)
#        :8081 deep LLM (llama.cpp, Qwen 7B int4)
#        :8082 skill scoper (sentence-transformers, MiniLM-L6-v2)

# On Faust (Pi 5 1GB + DSI + RF stack):
#   1. Flash Pi OS 64-bit to microSD
#   2. git clone + pip install -r requirements.txt   (core only — no torch!)
#   3. Run deploy/faust/setup-usb-host.sh — configure usb0 side
#   4. Set env:
export FAUST_BACKEND=mephisto
#   5. Run:
python -m faust.ui.run
# Chromium kiosk opens http://localhost:8080 on the DSI
#
# Faust never runs sentence-transformers or torch — it calls Mephisto's
# scoper service over USB-ethernet. Keeps Faust's 1GB RAM comfortable.
```

## Configuration

All backend/model/endpoint config flows through `faust/agent/config.py`. Override via env:

| Variable | Default | Notes |
|---|---|---|
| `FAUST_BACKEND` | `ollama` | `ollama` \| `mephisto` \| `claude` |
| `FAUST_LLM_ENDPOINT` | `http://localhost:11434/v1` | Fast backend `/v1` root. Auto-redirects to `10.66.0.2:8000/v1` when `backend=mephisto` |
| `FAUST_MODEL` | `qwen2.5:1.5b-instruct` | Fast model (Pass 2 parameterize) |
| `FAUST_PLANNING_ENABLED` | `true` | Enable deep-model planning cascade |
| `FAUST_PLANNING_ENDPOINT` | (empty → uses `FAUST_LLM_ENDPOINT`) | Deep backend. Auto-redirects to `10.66.0.2:8081/v1` for `backend=mephisto` |
| `FAUST_PLANNING_MODEL` | `qwen2.5:7b-instruct` | Deep model (Pass 1 planning) |
| `FAUST_PLANNING_TIMEOUT_S` | `120` | Planning can be slow on Pi 5 CPU |
| `FAUST_SCOPER_K` | `12` | Top-K skills in the planning catalog |
| `FAUST_SCOPER_ENDPOINT` | (empty → local on Mac, `10.66.0.2:8082/v1` on Mephisto) | Remote scoper URL. Keeps Faust lean (no torch on Pi 1GB). |
| `FAUST_MODE` | `twopass` | `twopass` (plan+execute) \| `single` (legacy AgentLoop) |
| `FAUST_API_KEY` | — | Claude backend only |

## Project status

| Component | Status |
|---|---|
| Agent loop scaffold (Ring 4, async) | ✓ 7 tests |
| Skill loader (SKILL.md → registry) | ✓ 16 tests |
| Disclosure layer (journal + approver) | ✓ 13 tests |
| Faust↔Mephisto transport (USB-ethernet) | ✓ 10 tests — gadget-mode scripts untested on hardware |
| UI skeleton (three-zone web app) | ✓ 5 tests — live agent + demo mode |
| Embedding skill scoper (retrieval) | ✓ 8 tests — top-K relevant skills per prompt |
| Two-pass agent (plan → execute) | ✓ 8 tests — Mephisto plans with lean catalog, Faust executes per-step |
| 41 SKILL.md drafts across 10 categories | ✓ stubs ready for tool.py implementations |
| Real tool.py implementations | pending — blocked on hardware arrival Apr 14 – May 11 |
| Mephisto OS prep script | pending |

## Skill inventory (MK1 — 41 skills)

| Category | Count | Skills |
|---|---|---|
| **WiFi** | 9 | wifi_scan, wifi_deauth, wifi_handshake_capture, wifi_pmkid_capture, wifi_evil_portal, wifi_karma, wifi_beacon_spam, wifi_channel_analyze, wardrive |
| **BLE** | 4 | ble_scan, ble_spam, ble_service_enum, ble_pair_bruteforce |
| **NFC** | 4 | nfc_read, nfc_write, nfc_emulate, nfc_crack_mifare |
| **RFID** | 1 | rfid_clone |
| **Sub-GHz** | 2 | subghz_replay, subghz_decode |
| **RF** | 1 | rf_spectrum_scan |
| **IR** | 1 | ir_capture |
| **USB/HID** | 1 | hid_payload |
| **Network** | 6 | nmap_scan, arp_scan, arp_spoof, responder_poison, dns_hijack, http_recon |
| **Analysis** | 3 | pcap_inspect, wpa_crack, hash_identify |
| **Defense** | 7 | deauth_detector, rogue_ap_detector, ble_tracker_scan, probe_request_monitor, imsi_catcher_detector, camera_ir_scan, spectrum_anomaly |
| Dev/demo | 2 | echo, add |

Distribution by sensitivity: 23 passive, 11 active, 7 disruptive.

## Agent architecture (two-pass, dual-model cascade)

**Pass 1 — planning (rare, deep)**
Runs on the **deep backend**: Qwen 2.5 **7B** int4 on Mephisto's Pi 5 CPU via
llama.cpp (port 8081), or local Ollama with the 7B model in dev. Receives
only a lean catalog (name + description + sensitivity per skill) + the user
prompt. Outputs a structured Plan via the `submit_plan` tool — ordered
skill invocations with intent descriptions. ~60s per plan on Pi 5 CPU.

**Plan approval**: surfaced to the operator via the UI. Approve/reject.

**Pass 2 — per-step parameterize (frequent, fast)**
Runs on the **fast backend**: Qwen 2.5 **1.5B** on Mephisto's Hailo NPU
(port 8000), or local Ollama in dev. For each plan step, loads *just that
skill's* full schema, asks the fast model to fill parameters (sees intent +
prior step results + one tool schema), dispatches through the disclosure
layer, records in the journal, feeds results into the next step. ~2-5s per step.

**Fallback semantics:** if the deep backend is unreachable, Pass 1 automatically
falls back to the fast backend with a safety note appended to the plan so the
operator knows they got the less-capable planner. Nothing breaks.

Context budget per call:
- Pass 1 (planning): ~1000-1400 tokens (catalog + prompt)
- Pass 2 (per step): ~400-700 tokens (intent + one schema + history)

Neither exceeds Hailo's 2048-token window. The deep model (Qwen 7B) has
a much larger native context (128K), so it never runs out even for
complex multi-step plans with large historical context.

**Why the cascade helps:** Qwen 2.5 1.5B is strong at tool selection but weaker
at multi-hop reasoning. Qwen 2.5 7B handles conditional logic, dependency
ordering, and novel multi-step tasks much better. The cascade gives you 7B-class
planning quality for the ~1 call per request where it matters, without paying
the 60s latency on every call.

## License

TBD. Currently private.
