# Chunk 2 — Agent Harness Evaluation

**Project:** AI-native pentesting handheld
**Chunk status:** Complete
**Date:** April 11, 2026

---

## 1. What each option actually is

### OpenClaw
A **personal AI assistant platform**, launched late January 2026 (formerly Moltbot/Clawdbot). Runs on a workstation, connects to messaging apps (WhatsApp, Telegram, Slack, Signal, iMessage), uses a "channel → brain → body" architecture. Skills are markdown+YAML folders (`SKILL.md` with YAML frontmatter). ClawHub registry has 5,400+ community skills. MIT-licensed, local-first (memory stored as markdown files on disk). Supports cloud models *and* local Ollama/LM Studio. Heartbeat scheduler for autonomous wakeups.

**Problem for this project:** OpenClaw assumes a persistent workstation, a messaging-channel interaction model, and a keyboard/chat input paradigm. A handheld device with a touchscreen and physical RF tools uses maybe 5% of OpenClaw's surface area. The skill format is valuable; the runtime is overhead.

### Claude Agent SDK
Anthropic's official Python/TypeScript SDK — the same agent loop that powers Claude Code, exposed as a library. Features: built-in agent loop, tool orchestration, context management with compaction reserve, MCP server support (in-process `createSdkMcpServer` + external subprocess servers), permission modes (`default` + approval callback, `acceptEdits`, `bypassPermissions`), pre/post-tool hooks, `stop_reason` handling, cost/turn limits.

**Problem for this project:** tied to Claude API models. Doesn't natively run local models. Using it would mean either cloud inference (breaks zero-exfiltration) or fighting the SDK's abstractions to swap in a local backend.

### Raw tool-use loop
Pattern from Anthropic's Ring 1–5 tutorial: a while loop on `stop_reason == "tool_use"`, dispatch tool calls, append results to message history, repeat until `end_turn` or max-iteration cap. Maybe 150–250 lines of Python for this project's scope. Works with any model backend (Ollama, llama.cpp, Hailo runtime, OpenAI-compatible endpoints, Claude API). Complete control.

### Hermes (not a harness)
Hermes / Nous Hermes Pro are **fine-tuned models** optimized for function calling — a model choice, not a framework. Would sit *inside* whatever harness is selected. Not relevant to this comparison.

---

## 2. Decision criteria for the constraint set

1. **Local-model-first.** Harness cannot assume Claude API access.
2. **Small fixed tool set.** ~8–15 tools (WiFi scan, deauth, BLE scan, NFC read/write, sub-GHz capture/replay, HID injection, network probe, auxiliary). Not hundreds.
3. **Latency matters.** Quantized 7–9B model on embedded hardware, every abstraction layer costs tokens and round-trips.
4. **Disclosure hooks at the loop layer.** Two-layer disclosure (first-boot blanket + per-action banner for sensitive ops) is fundamentally "intercept tool calls before execution, surface to user." Requires clean hook/middleware points.
5. **Tight context budget.** ~16K tokens on a 9B model. No room for framework boilerplate padding the prompt.

---

## 3. Recommendation — roll your own loop, borrow OpenClaw's skill format

### The build
- **Loop:** Ring 4 pattern from Anthropic's tutorial, adapted to Ollama's OpenAI-compatible endpoint (assumption verified in chunk 3). While-loop on `stop_reason == "tool_use"`, dispatch tools, append results, repeat with max-iteration cap.
- **Skills:** adopt OpenClaw's `SKILL.md` format — YAML frontmatter (`name`, `description`, `allowed_tools`, `sensitivity`) + markdown body. Skill loader reads directory, parses frontmatter, injects skills list + active skill body into the system prompt. Portable, readable, ecosystem-compatible without the OpenClaw runtime.
- **Disclosure hooks:** wrap tool dispatch in a function that checks the tool's `sensitivity` class and either executes immediately (passive), surfaces a touchscreen banner and waits for confirm (active/disruptive), or logs to a tamper-evident journal on blanket-acceptance mode.
- **Optional TDA:** PentestGPT v2's four-dimension Task Difficulty Assessment (horizon, evidence confidence, context load, historical success rate) as a pre-loop scoring pass. ~50 lines. Consider for v1.1.

### Dependency footprint
```
requests / httpx    # HTTP to local model endpoint
pydantic            # typed tool input validation
pyyaml              # SKILL.md frontmatter
python-markdown     # SKILL.md body parsing
```
That's the full core-agent dependency list. Hardware libs come separately.

### Rejected alternatives
- **OpenClaw runtime:** would import an entire personal-assistant platform to use 5% of it. Fights messaging-channel and workstation assumptions. Context-budget tax on every inference.
- **Claude Agent SDK:** excellent but Claude-API-tied. Swap to local later would be painful. If the device had cloud access to Claude Haiku 4.5, this would be the right choice — but zero-exfiltration is a core project pitch.

---

## 4. What to steal from surveyed work

| Source | Steal | Why |
|---|---|---|
| OpenClaw | `SKILL.md` format (YAML frontmatter + markdown body) | Portable, readable, 5,400-skill ecosystem |
| Claude Agent SDK | Pre/post-tool hook pattern | Clean mental model for where disclosure layer wedges in |
| Claude Agent SDK | Context compaction reserve (~1K tokens reserved for response) | Prevents mid-reasoning truncation on tight context budgets |
| PentestGPT v2 | Four-dimension TDA | Addresses Type B failures (planning/state) that persist regardless of tooling |
| PentestGPT v2 | Typed tool interfaces | Pydantic at dispatch catches hallucinated arguments before execution |
| PentAGI | Execution monitoring + task planning for <32B models | Documented 2x quality improvement, loop prevention |

---

## 5. Implications for BOM and build plan

1. **Compute ask is lower than with OpenClaw.** No separate personal-assistant runtime daemon. Pi 5 + Hailo remains right, but no extra daemon budget.
2. **Skill directory in the GitHub repo from day one.** `skills/wifi-recon/SKILL.md`, `skills/sub-ghz-capture/SKILL.md`, etc. Disclosure class (`sensitivity: passive | active | disruptive`) lives in frontmatter.
3. **No framework lock-in.** If Claude Agent SDK gains local-model support or OpenClaw adds a minimal mode, migration is viable — skill format is compatible.
4. **Supervisor/validator seam from day one.** Even if no-op in v1, `validate_tool_call` hook should exist so it can be activated when tool-use quality issues surface on the quantized local model.

---

## 6. Open uncertainty carried into chunk 3

The recommendation assumes the local model (likely Qwen 3.5 7B or Llama 3.x 8B quantized on Hailo) does tool use competently. PentAGI's guide documents that **models under 32B parameters require execution monitoring and task planning supervision** — they report 2x better results with supervision on Qwen 3.5-27B-FP8. If tool-use quality on a 7–9B quantized model is poor, no harness choice compensates. Chunk 3 (Hailo-10H LLM reality check) must answer whether the target model runs at acceptable tokens/sec with acceptable tool-use quality on the available quantized variants.

---

## References (primary sources)

- OpenClaw docs — https://docs.openclaw.ai/tools/skills
- OpenClaw overview — https://openclaw.ai/
- Claude Agent SDK docs — https://platform.claude.com/docs/en/agent-sdk/overview
- Claude Agent SDK agent loop — https://platform.claude.com/docs/en/agent-sdk/agent-loop
- Tool-use tutorial (Ring 1–5) — https://platform.claude.com/docs/en/agents-and-tools/tool-use/build-a-tool-using-agent
- PentAGI supervision notes — https://github.com/vxcontrol/pentagi
- PentestGPT v2 (Type A/B failures, TDA) — https://arxiv.org/html/2602.17622v1

---

**Next chunk:** Hailo-10H LLM reality check — what actually runs on the AI HAT+ 2 NPU, supported quantized models, realistic tokens/sec, toolchain gotchas. The highest-risk unknown in the project.
