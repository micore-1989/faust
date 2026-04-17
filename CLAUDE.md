# Faust — Project Frame & Working Context

**Last updated:** April 16, 2026
**Document purpose:** This file is read at the start of every session. It captures both *why* this project exists (the research thesis) and *how* it works (the architectural rules, config defaults, and operational discipline). When this file updates, the date above changes; anything older than that date elsewhere in the repo may reflect earlier framings.

**What changed in this revision:** A conversation on April 16 worked through the LLM-capability ceiling and reframed the agent architecture. Local small models (≤7B) cannot reliably do multi-step exploitation reasoning — this is a model-capability wall, not a hardware problem, and pivoting to Orange Pi 5 Max would not fix it. The LLM's role on Faust is now scoped more honestly: natural-language interface, fuzzy parameter inference, output interpretation, single-step suggestions, and vision — with cloud (Claude) as the brain for anything requiring multi-step reasoning. The local cascade is retained as the offline-capable / privacy-preserving data point, not as the primary reasoning engine. Metasploit is slated for integration as MCP-style tools driven by the cloud agent, not as loaded context. Hailo AI HAT+ 2 is retained; its strengths (VLM, power efficiency, prefill-heavy workloads) fit the new role better than the old one. See "Part II — Architectural pivot (April 16, 2026)" below.

---

## Part I — The project frame

### What Faust is

Faust is an **AI-native pentesting handheld** built by an undergraduate researcher (Misha) as a **research instrument** for a political science / cybersecurity professor whose work sits at the intersection of cyber tech, privacy, and policy.

**Faust is not a product.** It is not being commercialized, sold, distributed, or demoed to untrained users. It is not being hardened against end-user misuse because there are no end users. It is a **research artifact** built to generate evidence about a specific empirical question.

### The research question

**Is AI-augmented pentesting at near-workstation capability now buildable, by a motivated individual, using commodity hardware, for approximately $2.5K — and what policy implications follow from the answer?**

Faust is the attempt to answer the first half of that question by construction. If the answer is yes, the second half becomes urgent and the device itself becomes the evidence lawmakers, think tanks, and the security-research community need to reason about it.

### The thesis the device argues for

**Capability proliferation.** The claim is that meaningful offensive cybersecurity capability — previously requiring expertise, time, or significant resources — is now accessible to a hacking-enthusiast operator with rough general knowledge, through the combination of commodity RF hardware, open-source pentesting tooling, and AI (locally-run or cloud-accessed). The device exists to make that claim concrete rather than speculative.

The project takes **no position on what policy should follow**. The author is not a lawmaker and does not claim to know whether regulation of AI, hardware, software, or none of these is the right response. The contribution is the evidence. Policy reasoning is downstream and belongs to people whose job that is.

### The three-part policy-relevant structure

The device's design deliberately combines three properties, because the policy argument is meaningfully weaker if any one is dropped:

1. **Capable** — agentic LLM operation of a full RF + network pentesting stack (WiFi, BLE, sub-GHz, NFC, LF RFID, IR, and — via Metasploit on Mephisto — network exploitation). Capability is what makes this worth policy attention.
2. **Cheap** — a working build totals roughly $2K-2.5K in commodity parts from commodity vendors, shipped to a student address. This is a deliberate constraint: the budget limit is a research variable, not an engineering limit. "You can buy this at Adafruit, AliExpress, and Amazon" is part of the claim.
3. **Unattributable under consumer-tracking regimes** — Faust is not a smart device. It has no Google/Apple/Microsoft account binding, no cellular IMEI tied to a subscription, no ISP subscription records, no app-store telemetry. It carries no tracking infrastructure that a non-forensic actor could use to link the device to an individual. It is not forensically untraceable under lab-grade RF analysis — every transmitter has identifiable fingerprints — and the project documentation does not claim it is. The claim is specifically that it operates outside the commercial surveillance infrastructure that catches most devices most of the time. This is the pragmatist version of the anonymity argument and it is the version that is actually true.

Each property individually is uninteresting. The combination is the policy-relevant artifact.

### The two-tier LLM architecture is itself a data point

The project supports two LLM tiers, **and the comparison between them is part of the research output**:

- **Local mode** — Qwen 2.5 family on-device (1.5B on Hailo-10H for fast / triage / VLM-adjacent work, 7B on Pi 5 CPU via llama.cpp when deeper local reasoning is needed). Fully on-device, no outbound traffic. **Capability-bounded** — good at single-step tool dispatch, parameter filling, output interpretation, and vision; unreliable at multi-step exploitation reasoning. This is the "you cannot regulate this with network policy" data point, *and* the "here is where the capability ceiling of purely-local AI sits in 2026" data point.
- **Cloud mode** — Claude (via Claude Agent SDK / MCP) over the wire. **Capability-unbounded at the reasoning layer** — handles multi-step planning, exploit chain reasoning, cross-domain synthesis. This is the "AI-provider policy is a potential lever" data point.

**Mapping what each mode can and cannot do, at what capability level, is part of the research output.** Showing both tiers is stronger than showing either alone, because it identifies which regulatory interventions (chip-level, model-level, provider-level, training-data-level) would actually catch this kind of device and which would not. The capability gap between the tiers *is itself* a finding.

### The operator model

Faust is operated by the researcher, by the supervising professor, by collaborating researchers, and by research students who understand the stakes. No human-subjects study is planned; no IRB is required.

The target capability for the AI layer is: **serve an operator who is a hacking enthusiast with rough general knowledge** — understands what nmap does, can name some common attacks, knows roughly what the device's hardware makes possible — but is not an expert pentester and has not operated these tools end-to-end. The LLM is expected to carry the expert reasoning: translate natural-language requests into multi-stage plans, select appropriate tools, parameterize them correctly, interpret their output, and escalate or iterate based on results.

This is an ambitious target and the engineering reflects it. In the cloud-mode configuration this target is achievable today. In the local-mode configuration it is **partially achievable** — specifically, the local models are strong at interface / parameter-filling / output-interpretation work, and weak at open-ended multi-step planning. Documenting this gap honestly is part of the research contribution.

The disclosure, journal, and scope-authorization machinery in the codebase exists as **research instrumentation** — it generates the evidence about how AI agents can make consequential actions legible, contestable, and accountable. It is not there to protect an untrusted operator from their own choices. The operator is informed; the machinery's job is to log, surface, and structure the decision-making in a way that produces publishable data about disclosure architectures.

### The test environment

Two-tier:

1. **Researcher-owned bench** — a handful of Linux systems, ESP32s, Bluetooth devices, RF targets that belong to the researcher. Used for iteration, initial skill development, and routine testing.
2. **Professor-run lab environment** — refined servers, purposefully vulnerable targets, realistic infrastructure, under the professor's authorization. Used for validation and for generating research evidence of the device's capabilities in a more realistic setting.

Any target outside these two environments is out-of-scope and enforced by the device's scope-authorization layer.

### Funding and resource envelope

$2,500 allocated for the v1 build (spent, documented in `faust-parts-list.md`). Any beyond-budget spending comes from the researcher's own pocket and is to be avoided, because the affordability constraint is itself part of the research claim. Hardware decisions should continue to honor this — premium components (Jetson, custom PCBs in quantity, expensive SDRs) are out of scope not for engineering reasons but because they would undermine the thesis.

### Time horizon

Senior thesis scope. Work will continue alongside coursework over roughly two years, with the expectation that the device will continue evolving. There is no ship deadline and no feature freeze. **Any references to a "May 15, 2026" demo date in older documents reflect an earlier project framing and should be disregarded.**

### What success looks like

In priority order:

1. **A cloud-LLM version** (Claude via Agent SDK + MCP tools) that can execute multi-step pentesting skills on Faust in response to natural-language requests from a non-expert operator, against the authorized test environments, and can correctly reject requests that are out of scope. *This is the version that actually delivers the "plain English, complex goals" vision and is achievable with current technology.*
2. **A locally-run LLM version** with the same interface surface but honestly-scoped capability — strong at single-step dispatch and interpretation, documented-weak at multi-step planning. Serves as the comparison data point and the offline-capable fallback.
3. **Publication or presentation** of the findings in a form the target audiences — academic reviewers, policy researchers and lawmakers, the security-research community — can engage with. What form this takes is to be determined. The capability gap between the two LLM tiers, and the Metasploit integration story, are central to the argument.

*Note on ordering: earlier versions of this document prioritized the local version as the "groundbreaking" outcome. That framing was based on an overestimate of what small open-weight models can reliably do for multi-step exploitation reasoning. The honest version is: cloud delivers the vision, local documents the ceiling, and **the comparison is the contribution**. Both tiers are worth building.*

### Novelty claim, refined

**"Handheld RF + physical pentesting body for agentic AI."** The desktop and cloud "vibe hacking" tooling ecosystem (Claude Code, XBOW, Penligent, HackerAI, PentestGPT) is built around web applications, code bases, and network services. Nobody has built an agentic-AI-driven body for **physical-layer and RF-layer security research on handheld hardware**. That intersection — (handheld form factor) × (rich RF stack) × (agentic AI operating it) — is the specific gap Faust occupies. The novelty claim survived the architectural pivot intact.

---

## Part II — Architectural pivot (April 16, 2026)

This section documents the pivot in one place so later readers can find it. Subsequent sections describe the **post-pivot** architecture; earlier chunk documents in `docs/` describe the pre-pivot reasoning and are preserved for the research record.

### What the pivot changes

1. **Reasoning ceiling accepted.** Local models under 13B cannot reliably do multi-step exploitation reasoning. This is a **model-capability** wall, not a context-window wall, not a compute wall. PentestGPT v2 documents Type B (planning) failures persisting even with GPT-4. Qwen 2.5 7B on Pi 5 CPU hits this ceiling hard. More context window does not fix it; more tokens/sec does not fix it; swapping to Orange Pi 5 Max does not fix it.

2. **LLM role reframed.** The AI's job on Faust is now scoped as:
   - **Natural-language interface** over the RF and network tool stack
   - **Fuzzy parameter inference** (infer MACs, targets, channels from context rather than requiring the operator to paste them)
   - **Output interpretation** (translate raw scan output to plain English)
   - **Single-step suggestions** ("port 22 is open, SSH 7.4 — here are candidate modules")
   - **Vision** (point camera at a device / keypad / lock → identify, suggest attack surface)
   - **Guided workflows** where the LLM fills parameters in pre-structured skill compositions
   - **Triage** (decide whether a request needs cloud escalation)
   
   What the local LLM is **not** asked to do: discover novel multi-step exploit chains from first principles.

3. **Cloud agent is the brain for multi-step work.** Claude via Claude Agent SDK becomes the primary reasoning layer when the user asks for anything requiring multi-hop planning. The local tier handles simple, fast, offline, and vision work.

4. **Metasploit is a tool, not context.** Rather than "load Metasploit knowledge into the LLM's context," install the Metasploit Framework on Mephisto and expose it via `msfrpcd`, wrapped as a set of MCP-style tools (`msf_search`, `msf_module_info`, `msf_check`, `msf_run`, `msf_session_cmd`, etc.). The agent sees ~8 Metasploit tools, not 2,300 modules. Module-specific knowledge comes from MSF itself or from targeted retrieval (scoper pattern, extended with an MSF module embedding index).

5. **Hailo's role is redefined, not diminished.** Hailo's weaknesses (autoregressive token throughput, locked zoo, 2048-token cap) mattered when Mephisto was supposed to be the planner. In the new architecture those weaknesses are irrelevant. Hailo's strengths (VLM, power efficiency, prefill-heavy workloads, stable 1.5B for triage) are exactly what the new local tier needs. **No pivot to Orange Pi 5 Max.**

### What the pivot does NOT change

- All 41 SKILL.md files and their sensitivity classifications
- Disclosure layer, journal, Approver contract
- Two-unit hardware split (Faust handheld + Mephisto navigator)
- USB-ethernet gadget-mode transport
- Scope-authorization machinery
- The OpenClaw SKILL.md format as the skill primitive
- The research thesis or the policy argument
- The hardware BOM

### "Vibe hacking" as a term

Anthropic themselves now use **"vibe hacking"** to describe agentic-AI-driven offensive security work (analogous to "vibe coding"). Claude Code has become the dominant platform for this kind of work in the wild — documented in Anthropic's own November 2025 disclosure of the first large-scale AI-orchestrated cyber espionage campaign, and in the Mexico government breach campaign where ~75% of RCE activity was generated by Claude Code. Hallucination remains a real failure mode even at the Claude Sonnet / Opus level — agents claim to have extracted credentials that do not work, or flag as "critical discoveries" data that is publicly available. The research device must **design around this**, not pretend it doesn't happen: disclosure layer, scope checking, and human-in-the-loop validation are partial answers. Documenting the hallucination failure mode as it manifests on Faust is part of the research output.

---

## Part III — Working architecture (post-pivot)

### Faust and Mephisto: roles

**Faust** is the mobile pentesting handheld. It carries the display, the operator controls, the full RF peripheral stack (WiFi, BLE, sub-GHz, NFC, LF RFID, IR, SDR), the battery, and the **tool-execution layer**. Faust hosts the agent loop, the skill registry, the dispatcher, the disclosure layer, and the journal. Tool execution always happens on Faust — Mephisto never touches hardware directly. Faust can operate independently with its local triage model; in this mode it is a lower-capability device (think "Flipper Zero with natural-language input") but functional.

**Mephisto** is the navigator peripheral. It carries:
- The Hailo-10H NPU for fast local inference (Qwen 2.5 1.5B for triage + parameter filling; Qwen 2.5-VL 3B for vision)
- The 16GB-RAM Pi 5 for larger-model CPU inference (Qwen 2.5 7B via llama.cpp — used when local deep reasoning is explicitly requested, and as fallback when the cloud is unreachable)
- The **Metasploit Framework daemon** (`msfrpcd`), accessible to the agent via the MCP tool wrapper
- The **MCP server** that exposes Metasploit (and potentially other heavy tools) to whichever agent brain is active
- An **MSF module embedding index** (reuses the scoper pattern) for semantic search over Metasploit modules

When Mephisto is docked, Faust's capability expands: cloud-agent-driven multi-step work (if internet is available), VLM, deeper local fallback, and Metasploit access.

**Communication.** HTTP/JSON over USB-ethernet gadget mode. Mephisto exposes:
- OpenAI-compatible `/v1/chat/completions` endpoint on port 8000 (fast / Hailo)
- OpenAI-compatible `/v1/chat/completions` endpoint on port 8081 (deep / Pi 5 CPU 7B, when enabled)
- Scoper service on port 8082 (skill retrieval)
- MCP server on port 8083 (Metasploit tools, plus future heavy-tool wrappers)

### The three-brain architecture

The agent loop on Faust routes requests to one of three "brains" based on task complexity and operator preference:

1. **Fast local (Hailo, Qwen 2.5 1.5B).** Handles: known-intent tool dispatch ("scan wifi"), parameter filling, output summarization, triage decisions ("is this a complex request?"). Sub-second to a few seconds. Default for simple, fast, or offline use.
2. **Deep local (Pi 5 CPU, Qwen 2.5 7B via llama.cpp).** Handles: multi-step plans the operator explicitly wants to stay on-device, fallback when cloud is unreachable, research comparison data for the thesis. ~60s per plan. Opt-in per-session.
3. **Cloud (Claude via Claude Agent SDK + MCP).** Handles: multi-step exploitation reasoning, novel cross-domain tasks, Metasploit-driven post-exploitation. Requires internet. Per-call cost is bounded and tracked. Default for complex requests when the operator has enabled cloud mode.

**Triage.** When cloud mode is enabled, the fast-local model acts as a cheap gate: short prompts with obvious tool intent dispatch locally; anything ambiguous, multi-step, or requiring exploitation reasoning escalates to Claude. The operator sees which brain answered and can override.

### Metasploit integration

**MSF runs on Mephisto** as a long-lived `msfrpcd` daemon. A Python-based MCP server wraps the RPC API and exposes a clean set of tools to whichever agent brain is active:

- `msf_search(query, type=exploit|auxiliary|post|payload)` → candidate modules with rank, disclosure date, CVE refs
- `msf_module_info(module_path)` → full options, targets, payloads, references
- `msf_set_options(module_path, options)` → configure a module
- `msf_check(module_path)` → safe vulnerability check (passive, per disclosure classification)
- `msf_run(module_path, options)` → execute (disruptive, requires explicit approval)
- `msf_list_sessions()` → established sessions
- `msf_session_cmd(session_id, command)` → run command in session (disruptive)
- `msf_session_close(session_id)` → close session

**Module retrieval.** The scoper pattern extends to Metasploit: at Mephisto provisioning time, all installed module descriptions are embedded (sentence-transformers, MiniLM-L6-v2, same model the skill scoper uses). `msf_search` can then be semantic-rank rather than pure text match, which catches "RCE on file share" → EternalBlue even when the module description doesn't use those exact words.

**Metasploit SKILLs.** Domain guidance for using MSF lives in SKILL.md files (`skills/metasploit-workflow/`, `skills/smb-exploitation/`, `skills/web-exploitation/`, `skills/credential-attacks/`, `skills/post-exploitation/`) — procedural, not data dumps. Claude activates these contextually when MSF work is in scope. ~500 tokens each.

**Sensitivity classifications for MSF tools:**
- `msf_search`, `msf_module_info`, `msf_list_sessions` → **passive**
- `msf_check`, `msf_set_options` → **active**
- `msf_run`, `msf_session_cmd`, `msf_session_close` → **disruptive**

**Scope enforcement at the MSF wrapper.** Defense-in-depth: the MCP server itself validates that target IPs in `msf_run` options are within the session's authorized scope, independent of whether the calling agent respects scope. This matters both for research discipline and as evidence of a useful architectural pattern (scope-checking at the tool layer, not just the agent layer).

### Hard architectural rules — do not violate

1. **Backend abstraction is sacrosanct.** All LLM specifics live behind `LLMBackend` in `faust/agent/backends.py`. No hailo-ollama-isms, no Claude-API-isms, no llama.cpp-isms elsewhere. Adding a new backend = subclass `LLMBackend`. The three brains (fast local, deep local, cloud) are three backend instances, not three code paths.
2. **Disclosure goes through the dispatch seam.** The agent loop NEVER calls `registry.invoke()` directly — only `dispatcher.dispatch()`. The Approver callback is the contract; do not bypass it. This applies equally to local-agent-driven and cloud-agent-driven tool calls.
3. **Skills follow OpenClaw SKILL.md format.** YAML frontmatter (`name`, `description`, `allowed_tools`, `sensitivity`, `parameters_schema`) + markdown body. The skill loader populates the same `ToolRegistry` the agent loop consumes, and the same registry is what the MCP server exposes to the cloud agent.
4. **Sensitivity is a three-class system:** `passive | active | disruptive`. This is the disclosure layer's contract with skills and with MCP-wrapped external tools (including MSF).
5. **Scope authorization is enforced at multiple layers.** Agent system prompt (tells the agent what's in scope), dispatcher (validates before executing), and — for MCP-wrapped tools like MSF — the MCP server itself. Redundancy is intentional.
6. **Local planning retains two-pass + scoper + cascade for the deep-local tier.** When the operator explicitly opts into local-only deep reasoning, the existing two-pass architecture (lean catalog Pass 1 on 7B, per-step parameterize Pass 2 on 1.5B) is the path. Token budget discipline (catalog top-K, 2048-window headroom) still applies there. This tier is **no longer the default**, but it remains fully supported because it is one of the research thesis data points.
7. **Cloud agent sees MCP tools, not the lean catalog.** When Claude is the brain, it uses the Claude Agent SDK's tool schema mechanism directly against the MCP server, which exposes Faust's skills + Metasploit's operations + any future MCP-wrapped capability. The scoper is unused in cloud-mode tool selection (Claude handles selection natively), though it may still be used for the MSF module embedding index.
8. **Triage is cheap and stateless.** The fast-local model's triage role is a single forward pass with a minimal system prompt: classify request as `simple_tool_call | complex_reasoning | vision_required | out_of_scope`. It does not see conversation history beyond the current turn. Keeps costs low and behavior predictable.
9. **Hallucination-retry on local planning stays.** Planner validates skill names against the catalog; one retry on hallucinated names, then surface a `safety_note` and proceed. This is a property of the deep-local tier; the cloud agent has its own error recovery.
10. **Re-plan on surprise (local only).** When a step errors mid-execution in the deep-local tier, the planner is invoked again with current state and replaces remaining steps. Capped at `replan_max=1` per turn. Cloud agent handles replanning natively.
11. **Cross-turn memory is bounded (local tier).** `conversation_memory_turns=1` and `conversation_memory_chars=2000` for local Pass 1 so the 2048-token Hailo window stays safe on fast-only fallback. Cloud mode uses Claude's native context management.
12. **Sigil taxonomy is the category primitive.** Seven categories: `wifi_ble, sub_ghz, nfc, lf_rfid, ir, vision, meta`. New skills map to one; `meta` is the fallback (not `misc`). Scoper Stage-1 routing depends on this taxonomy. Metasploit tools do not get sigil categories — they are registered via a separate MCP tool group.

### Config defaults — chosen for token budget reasons (deep-local tier)

| Knob | Default | Why |
|------|---------|-----|
| `scoper_k` | 12 | Catalog of top-12 fits ~1000 tokens; with system + prompt + submit_plan tool stays under 2048 |
| `replan_max` | 1 | One re-plan per turn protects against runaway loops while letting the agent recover from a surprise |
| `conversation_memory_turns` | 1 | Last user+assistant pair only; older turns dropped |
| `conversation_memory_chars` | 2000 | Hard cap on combined history content |
| `planning_timeout_s` | 120 | Qwen 7B on Pi 5 CPU takes ~60s per plan; 120s gives headroom |
| `FAUST_TRIAGE_ENABLED` | true | Fast-local triages before cloud escalation when cloud mode is on |
| `FAUST_CLOUD_DEFAULT` | false | Cloud mode is opt-in per session; local is the default |

### Architecture decisions already made

- **Compute path:** Pi 5 1GB (Faust) + Pi 5 16GB + Hailo AI HAT+ 2 (Mephisto). See `docs/chunk-3-compute.md` for why this hybrid won over options A/B/C/F. **The April 16 pivot reaffirmed this choice** — Orange Pi 5 Max considered, rejected, because the reasoning bottleneck is model capability, not hardware, and Hailo's strengths (VLM, power efficiency) fit the new role.
- **Agent harness (local tier):** Roll-our-own Ring 4 async loop. See `docs/chunk-2-agent-harness.md`.
- **Agent harness (cloud tier):** Claude Agent SDK with MCP tool exposure. Integrates at the `LLMBackend` layer; the existing dispatcher, disclosure, and journal pipeline are reused downstream.
- **Skill format:** OpenClaw SKILL.md (format only — not their runtime).
- **Transport:** HTTP/JSON over USB-ethernet gadget mode. Mephisto exposes multiple endpoints (fast LLM, deep LLM, scoper, MCP server).
- **Model cascade (local):** Qwen 2.5 1.5B Instruct on Hailo (fast / triage / Pass 2) + Qwen 2.5 7B on Pi 5 CPU via llama.cpp (deep / Pass 1, opt-in) + Qwen 2.5-VL 3B on Hailo for vision. See `docs/chunk-3-compute.md` for the MikeVeerman tool-calling benchmark that justified small-model choice.
- **Cloud model:** Claude (Sonnet default, Opus for hardest tasks). `ClaudeBackend` in `backends.py` evolves into a full Claude Agent SDK integration.
- **Metasploit as MCP tools, not as context.** Install on Mephisto, expose via MCP wrapper, retrieval via extended scoper.

### Current architectural state

- **Skill catalog:** 41 SKILL.md files across the seven sigil categories. Each has a corresponding `tool.py`; skills without real hardware backing use `skills/fakes.py` synthetic data, flagged via `mark_synthetic()` so the agent never mistakes a stubbed result for real output.
- **Refactor state:** The five-prompt agent-layer refactor has landed (lean Pass 1 planner, preferred_args wiring, 7-sigil taxonomy remap, two-stage scoper routing, token-budget enforcement) plus the scoper-regex follow-up fix. This is the deep-local-tier architecture.
- **Cloud tier:** `ClaudeBackend` stub exists; full Claude Agent SDK integration is pending work.
- **Metasploit integration:** not yet built; targeted as the next major architectural direction. Steps: install MSF on Mephisto → build MCP server wrapping `msfrpcd` → write initial MSF SKILLs → index module embeddings → wire into dispatcher → write sensitivity-aware disclosure paths.
- **Tests:** 244 tests across all test modules, all mock-backend (no LLM or hardware needed to run the suite).

### Package layout (`faust/`)

- `agent/loop.py` — Ring 4 async loop (legacy single-pass mode)
- `agent/twopass.py` — `TwoPassAgent`: plan → approve → per-step parameterize + dispatch. Includes re-plan on surprise + cross-turn conversation memory. Default mode for the **deep-local tier**.
- `agent/planner.py` — Pass 1 logic with `submit_plan` meta-tool. Dual-backend cascade (deep → fast fallback) + hallucination-retry.
- `agent/catalog.py` — builds lean skill catalog from the registry
- `agent/plan.py` — `Plan`/`PlanStep` dataclasses
- `agent/backends.py` — `LLMBackend` ABC + `OllamaBackend` + `ClaudeBackend` (stub, evolving to full Claude Agent SDK wrapper). **Triage gating logic lives here** for the cloud tier.
- `agent/budget.py` — token-budget enforcement (catalog trimming, estimation) — local tier only
- `agent/dispatch.py` — disclosure seam; Approver callback contract. Used by **all three** brains.
- `agent/disclosure.py` — `DisclosureApprover` + tamper-evident journal integration
- `agent/journal.py` — SQLite hash-chained journal
- `agent/events.py` — `Thinking` / `PlanProposed` / `ToolCallProposed` / `ToolCallExecuted` / `Final`
- `agent/config.py` — single source of backend/endpoint/model/mode truth (now includes triage + cloud config)
- `agent/triage.py` — **(planned)** fast-local triage classifier for cloud-mode requests
- `agent/mcp_client.py` — **(planned)** client-side wrapper for calling Mephisto's MCP server; used by the Claude Agent SDK integration and by the local tier when calling MSF
- `skills/loader.py` — SKILL.md parser + registry populator (pydantic-validated)
- `skills/scoper.py` — embedding-based skill retrieval. `LocalEmbeddingScoper` for Mephisto/dev, `RemoteEmbeddingScoper` (HTTP to Mephisto) for Faust to keep its 1GB Pi lean, `NoopScoper` fallback. Used by local-tier planning.
- `skills/scoper_routing.py` — Stage 1 keyword routing by sigil category.
- `skills/fakes.py` — shared synthetic-data helpers; `mark_synthetic()` flags every result with `_synthetic: true`.
- `tools/registry.py` — in-memory tool registry, exports OpenAI tool schemas (consumed by local agent) and MCP tool schemas (consumed by cloud agent via the MCP server).
- `transport/link.py` — Faust↔Mephisto USB-ethernet health checking
- `ui/state.py` + `ui/server.py` + `ui/run.py` + `ui/static/*` — UI, single-screen-at-a-time, three-brain indicator planned (shows which brain answered a given turn)
- `cli.py` — terminal runner with stdin confirmation
- `skills/*/SKILL.md + skills/*/tool.py` — 41 skills; Metasploit skills to be added
- `deploy/mephisto/*` — gadget mode, llama.cpp, scoper service, **(planned)** msfrpcd + MCP server provisioning
- `deploy/faust/setup-usb-host.sh` — Faust host-side USB-ethernet
- `deploy/dev-simulator.sh` — end-to-end Mac simulator

### UI design language

Single-view-at-a-time navigation stack (off → splash → boot → home → category → skill | chat). Apple-esque visual language: clean typography, generous whitespace, subtle borders, rounded corners. The UI state reflects Mephisto's dock state — when Mephisto is undocked the accent color is one palette; when docked, the color shifts to another, signaling the capability expansion. The thematic palette draws from Goethe's *Faust* (primary) and Bulgakov's *Master and Margarita* (accent). A mathematical italic 𝑓 serves as the Faust glyph; when Mephisto is connected, the glyph morphs to Ψ. **Post-pivot addition:** a small indicator showing which brain (fast-local / deep-local / cloud) answered each turn, because the research value of the tool partly depends on making this visible. The UI has been roughly built and will be revisited later.

### Hardware context

- **Faust:** Pi 5 1GB, 8" Waveshare DSI 1280×800 (Rev 2.2, fixes Rev 2.1 Pi 5 short bug), Armor Lite V5 cooler, 4× Molicel P30B 18650 in Geekworm X1202 UPS HAT.
- **Mephisto:** Pi 5 16GB + AI HAT+ 2 (Hailo-10H, 40 TOPS, 8GB on-board LPDDR4X), Armor Lite V5 cooler, 2× Molicel P30B in Geekworm X1201 UPS HAT. Now also hosts `msfrpcd` and the MCP server.
- **RF on Faust:** HackRF Pro (USB-C, 100 kHz – 6 GHz), ESP32-S3 Marauder Add-On (Electronic Cats), ALFA AWUS036ACM USB WiFi (MT7612U, monitor mode + injection, in-kernel mt76 driver), PN532 (13.56 MHz NFC), T5577 R/W (125 kHz LF RFID), RDM6300 (LF RFID reader), CC1101 (sub-GHz backup), IR LED + TSOP38238, DS9092 iButton probe, NEO-M9N GPS.
- **Pi Camera Module 3** on Faust for VLM work (Qwen 2.5-VL 3B on Hailo).

Full parts detail lives in `faust-parts-list.md`.

### Code style preferences

- Async by default for anything I/O-bound.
- Type hints everywhere. `from __future__ import annotations` at the top of every file. `dict`, `list`, `X | None` (3.11+ syntax).
- Dataclasses for structured data, not dicts.
- Errors propagate; don't swallow. Dispatch layer is the one place that catches tool exceptions.
- Tests use a mock backend. No test should require a running LLM.
- Working > clever. Architectural clarity matters more than micro-optimization.

### Files not in git (see .gitignore)

- `captures/` — PCAP, IQ recordings
- `journal.db` — disclosure journal (per-device)
- `models/` — `*.gguf`, `*.hef`, `*.rkllm` model files
- `.env` — secrets (e.g. Claude API key for cloud mode)
- **(new)** `msf_index.db` — Metasploit module embedding index (rebuilt per MSF update)

### Research-ethics and operational discipline

These rules exist because this is research work done by a responsible researcher in authorized environments, not because the operator needs protecting from the device:

- Skills that touch the air (deauth, evil portal, replay, RF transmit) must use `sensitivity: disruptive` in their SKILL.md frontmatter. Same rule applies to MSF tools that run exploits or session commands.
- All testing of disruptive skills happens against targets within the authorized test environments — the researcher's own bench or the professor's lab. Never against home WiFi, neighbors' networks, or any infrastructure outside the defined scope.
- **Cloud-mode privacy consideration:** sending target information and scan output to Claude's API means that data leaves the device. This is fine for the authorized test environments but must be disclosed to the operator at session start when cloud mode is enabled. The journal records which brain answered which turn so the audit trail is complete.
- The repo is private until it has been audited for anything sensitive (captures, journal entries, API keys, scope definitions referencing real networks). Public release, if it happens, is a separate and deliberate step.

---

## Instructions for Claude (the AI reading this document)

This project is a **research instrument, not a product**. When reasoning about architectural decisions, feature priorities, or trade-offs, default to what serves the research thesis — capability, affordability, unattributability, and honest documentation of what the device does and doesn't do. Deadline pressure, shippability, and user-safety-against-misuse framings should not drive recommendations here. The operator is informed; the environment is authorized; the goal is evidence.

**Be honest about capability ceilings.** The April 16 pivot happened because an earlier version of this project was overpromising what purely-local small models can do for multi-step reasoning. The honest story — "local is strong at interface and single-step work, cloud is needed for multi-step reasoning, and the gap is itself the finding" — serves the research better than the aspirational story did. Apply the same honesty to future decisions.

**When uncertain whether a given decision serves the thesis, ask.**

The chunk-1 through chunk-4 documents in the project contain the architectural decisions, BOM, compute analysis, and agent harness design at greater depth. Note that chunk-3 (compute) and chunk-2 (agent harness) were written before the April 16 pivot; their decisions mostly survive, but their framing around "local LLM as the brain" should be read alongside Part II of this document.
