# Chunk 3 (rewritten) — Compute & On-Device LLM Landscape

**Project:** AI-native pentesting handheld
**Chunk status:** Complete
**Date:** April 11, 2026
**Framing note:** This chunk surveys every plausible compute path for the device. No single “right answer” is enforced — each option has honest tradeoffs that depend on which constraints (deadline, form factor, power, flexibility, model capability, ecosystem maturity) you choose to prioritize. Chunk 4 (the BOM) will make this branching structural by pricing each path.

-----

## 1. The ground truth: what actually runs, at what speed, on what hardware

Before recommendations, the measured numbers. All figures are from independent reviews or reproducible community benchmarks, not vendor marketing.

### Token generation on small models (1B–3B)

|Hardware                                       |Model                     |Tokens/sec     |Source                            |
|-----------------------------------------------|--------------------------|---------------|----------------------------------|
|Hailo-10H NPU (AI HAT+ 2)                      |DeepSeek R1 Distill 1.5B  |**6.7**        |CNX Software measured Jan 2026    |
|Pi 5 CPU (Ollama)                              |DeepSeek R1 Distill 1.5B  |**9.04**       |CNX Software same review          |
|Hailo-10H NPU                                  |Qwen2 1.5B                |9.45           |Hailo’s own published figure      |
|Pi 5 CPU (Ollama)                              |Qwen2.5 1.5B              |5–8            |Stratosphere Lab benchmarks       |
|Pi 5 CPU (Ollama)                              |Qwen2.5 0.5B              |~20            |DFRobot                           |
|Pi 5 CPU (Ollama)                              |Llama 3.2 3B Q4_K_M       |4–6            |Multiple community sources        |
|Pi 5 CPU (Llamafile)                           |1.5B class                |up to 4× Ollama|arXiv 2511.07425 SBC benchmark    |
|RK3588 NPU (Orange Pi 5 Max, ODROID-M2)        |Qwen2.5 3B                |**8.45**       |AmeriDroid with Trevor Unland     |
|RK3588 NPU                                     |TinyLlama 1.1B            |**10–15**      |TinyComputers benchmarks          |
|RK3588 NPU                                     |Llama 3.1 (tested configs)|**2–3× Pi 5**  |IndieDroid Nova benchmark repo    |
|Jetson Orin Nano Super                         |Quantized 1–3B            |**28–55**      |NVIDIA + GenAI Protos measurements|
|Jetson AGX Orin                                |gpt-oss-20B via vLLM      |40             |NVIDIA blog                       |
|RK1820 / RK1828 (new LLM-specific accelerators)|Qwen2.5 / Qwen3 3B–7B     |**59–180**     |CNX Software Dec 2025             |

### Power draw under LLM load

|Hardware                      |Power                        |Context                      |
|------------------------------|-----------------------------|-----------------------------|
|Hailo-10H                     |~2.1–2.5W inference          |Host CPU stays idle          |
|Pi 5 CPU under LLM load       |~10W                         |All 4 cores pegged           |
|Pi 5 + Hailo HAT combined peak|~18–20W                      |PMIC reset risk on 15W supply|
|Orange Pi 5 Max (RK3588 NPU)  |~5–6W                        |LLM on NPU                   |
|Jetson Orin Nano Super        |7W low-power / 15W Super mode|Configurable                 |

### What this table tells you

**For LLM-only throughput, the ranking is: RK1820 >> Jetson Orin Nano Super > RK3588 > Hailo-10H ≈ Pi 5 CPU.** The Hailo is not the fastest option for LLM inference, and independently measured numbers directly contradict the marketing narrative of “40 TOPS AI accelerator.” CNX Software’s review language — *“feels more like an AI decelerator than an AI accelerator”* — is blunt but accurate for the 1.5B text-generation workload.

**For power efficiency, Hailo wins decisively.** At ~2.5W inference with the host CPU idle, no other option in this class comes close on tokens-per-second-per-watt. That matters for a battery-powered handheld; it doesn’t matter for a tethered desktop device.

**For VLM and vision workloads, Hailo is genuinely strong.** 40 TOPS on compute-heavy CNN and transformer-prefill workloads (CLIP, Qwen2.5-VL 3B, YOLO object detection) is where it earns its keep. This is Hailo’s actual design center — Hailo’s own blog explicitly positions the chip for *“high compute upfront, then small response”* workloads, which is the opposite of autoregressive text generation.

-----

## 2. Why the Hailo is slower than expected for LLMs (technical reason matters)

LLM token generation is **memory-bandwidth-bound**, not compute-bound, at the 1B–3B scale. Every generated token requires streaming the entire model’s weights through the compute units once. Throughput is capped by how fast weights can be read from memory, not by how many TOPS the compute can execute.

- The Hailo-10H’s LPDDR4X bandwidth is roughly in the same class as the Pi 5’s LPDDR4X.
- The PCIe Gen 2 ×1 lane between Pi and HAT is bandwidth-limited (~400–500 MB/s real-world).
- So the 40 TOPS of compute sits mostly idle during token generation.

This is not a Hailo bug. It’s the fundamental physics of small-model autoregressive inference. The same dynamic is why even an H100 GPU doesn’t linearly scale token generation with FLOPs — it hits memory bandwidth limits. NVIDIA’s Jetson pulls ahead because it has higher memory bandwidth (102 GB/s on Orin Nano Super) and CUDA kernels that exploit it.

Where Hailo wins is the *prefill* stage (processing the input prompt before generation starts), and vision models where the entire workload is front-loaded compute. For an agent that takes long prompts and emits short tool calls, prefill matters more than generation — but your two-layer disclosure + 2048 context constraint works against that usage pattern.

-----

## 3. Supported models and locks (Hailo specifically)

Hailo runtime (v5.2.0, early 2026) — the Ollama-compatible zoo:

- Qwen2 1.5B
- Qwen2.5 1.5B Instruct
- Qwen2.5-Coder 1.5B
- Llama 3.2 1B
- DeepSeek R1 Distill Qwen 1.5B
- (Llama 3.2 3B was supported, was removed)

Context window: **2048 tokens** on-NPU. Not configurable up.

Adding your own models requires Hailo’s **Dataflow Compiler (DFC)**:

- Runs only on x86_64 Ubuntu, not on Pi
- Requires NDA-gated developer account
- Uses QuaROT + GPTQ fusion pipeline (non-trivial to operate well)
- In practice, you are locked to the zoo for v1

Other Hailo-specific fragility:

- Kernel driver version mismatch (Pi OS ships GenAI 5.1.1, Hailo’s stack on 5.2.0)
- Documented conflicts: `h10-hailort` vs `hailort`
- PCIe lane contention with NVMe SSD (the Pi 5 has only one lane)
- `hailo-ollama` does not auto-start after reboot (requires systemd unit)
- ~20W combined load causes PMIC resets on 15W supplies

-----

## 4. Small-model tool-calling quality — the pleasant surprise

From the **MikeVeerman tool-calling benchmark** (Feb 2026), testing 8 small local models on tool-use *judgment* (not format) — meaning: does the model pick the correct tool, and does it *refrain* from calling a tool when the prompt doesn’t warrant one?

**Key findings:**

- **Qwen2.5 1.5B tied for highest tool-calling judgment** among tested small models
- **Qwen2.5 1.5B outperformed Qwen2.5 3B** — parameter count is non-monotonic with agent quality when judgment is measured
- Most models fail the “keyword trigger” test: called `get_weather` any time they saw “weather” in the prompt, even when explicitly told not to. Qwen2.5 1.5B resists this unusually well.
- Top-tier (four-way tie at 0.880 score): lfm2.5 1.2B, qwen3 0.6B, qwen3 4B, phi4-mini 3.8B
- Even the best model misses ~10% of actionable prompts
- The dangerous failure mode is not “model refuses to act” — it’s “model confidently takes the wrong action”

**Implication for the project:** Qwen2.5 1.5B — already supported on Hailo — is among the best small models for agent work. There is no fundamental model-capability wall at this parameter count. The limits are context-window size (2048 is tight) and model-selection flexibility (you can’t try lfm2.5 1.2B or Qwen3 0.6B on Hailo unless/until Hailo adds them).

The “confirmation prompts remain necessary” finding is direct external validation of the two-layer disclosure model. Destructive/disruptive action confirmation at this model scale is a **reliability requirement**, not UX polish.

-----

## 5. The complete option space

Every plausible compute path, with honest tradeoffs. No advocacy, just mapping.

### Option A — Pi 5 + Hailo AI HAT+ 2

**The path currently specced.**

|Dimension             |Reality                                                |
|----------------------|-------------------------------------------------------|
|LLM tok/sec (1.5B)    |6–10 on NPU, 5–9 on CPU fallback                       |
|Context window        |2048 tokens (NPU)                                      |
|Model flexibility     |Locked to Hailo zoo                                    |
|Power draw under load |~5W typical, ~18–20W peak combined                     |
|Supports 7B+ models   |No, in practice                                        |
|VLM capability        |Strong — Hailo’s design center                         |
|Ecosystem maturity    |Pi ecosystem mature; Hailo-LLM toolchain young, fragile|
|Deadline risk (May 15)|Lowest — you’ve been planning around this              |
|Cost (core compute)   |~$210 (Pi 5 8GB ~$80 + AI HAT+ 2 ~$130)                |

**Best for:** builders who value power efficiency, want a clean CPU offload, care about the VLM future (camera-based recon), and are willing to work within a locked model zoo and 2048-token context.

**Worst for:** builders who need model-swap flexibility, want larger context, are running agents that generate long outputs, or want to experiment with newer models (Qwen3, lfm2.5, Phi-4) as they appear.

### Option B — Pi 5, CPU-only (no accelerator)

**The minimalist path. Skip the HAT entirely.**

|Dimension            |Reality                                                           |
|---------------------|------------------------------------------------------------------|
|LLM tok/sec (1.5B)   |5–9 via Ollama, up to 4× faster with Llamafile                    |
|Context window       |Whatever the model supports natively (Qwen2.5 → 32K, Qwen3 → 128K)|
|Model flexibility    |Anything with GGUF quantization                                   |
|Power draw under load|~10W (all 4 cores pegged)                                         |
|Supports 7B+ models  |Yes, slowly (~1–3 tok/sec)                                        |
|VLM capability       |Poor (CPU-only VLMs are painful)                                  |
|Ecosystem maturity   |Very mature — llama.cpp / Ollama are the standard                 |
|Deadline risk        |Lowest — fewest moving parts                                      |
|Cost (core compute)  |~$80 (Pi 5 8GB alone)                                             |

**Best for:** builders who prioritize model flexibility, need larger context, want a working stack on day one, don’t care about the 2.5W power advantage.

**Worst for:** builders for whom CPU contention during inference is a problem (agent can’t render UI or run scans simultaneously without stutter), or who need VLM later. Saves $130 vs Option A. The single biggest “simplification” choice available.

### Option C — Orange Pi 5 Max / Radxa Rock 5 / ODROID-M2 (Rockchip RK3588)

**The NPU-that-actually-accelerates-LLMs path.**

|Dimension           |Reality                                                                               |
|--------------------|--------------------------------------------------------------------------------------|
|LLM tok/sec (1.5B)  |10–15                                                                                 |
|LLM tok/sec (3B)    |~8.45 (ODROID-M2)                                                                     |
|Context window      |2048 default, configurable higher with more RAM                                       |
|Model flexibility   |Anything convertible via RKLLM toolkit (open, no NDA)                                 |
|Tool-calling support|**Already wired** — `rkllama` supports Qwen + Llama 3.2+ formats natively             |
|Power draw          |~5–6W (NPU)                                                                           |
|Supports 7B+ models |Yes, at degraded speed                                                                |
|Quantization        |W8A8 only (less aggressive than Hailo’s W4A8; bigger model files)                     |
|VLM capability      |Yes — RKLLM supports Qwen2.5-VL, Qwen3-VL, InternVL3 with vision encoders             |
|Ecosystem maturity  |Less mature than Pi for peripherals/HATs; more mature than Hailo for LLM-specific work|
|Deadline risk       |Medium — you’d be learning a new SBC                                                  |
|Cost (core compute) |Orange Pi 5 Max 16GB ~$130–160                                                        |

**Best for:** builders who want the best LLM-per-dollar in this class, need model flexibility, want VLM capability that actually works at usable speed, and are comfortable stepping outside the Pi ecosystem.

**Worst for:** builders who have learned the Pi ecosystem specifically (HATs, GPIO libraries, well-trodden community documentation), or who need the camera stack integration Pi provides out-of-box.

**Key practical note:** your RF tooling runs over USB to an ESP32/Marauder anyway. The host SBC does not touch the RF hardware directly. That means swapping the SBC is less disruptive than it might seem — most of your custom work (agent loop, skill definitions, disclosure layer, UI) is portable across SBCs as long as you’re running Ubuntu/Debian.

### Option D — NVIDIA Jetson Orin Nano Super (8GB)

**The pure-performance path.**

|Dimension              |Reality                                                              |
|-----------------------|---------------------------------------------------------------------|
|LLM tok/sec (1–3B)     |28–55                                                                |
|Context window         |Limited only by RAM; 8K+ easily                                      |
|Model flexibility      |Full CUDA + TensorRT-LLM + vLLM + llama.cpp — anything               |
|Power draw             |7W low-power, 15W Super mode                                         |
|Supports 7B+ models    |Yes, genuinely well                                                  |
|VLM capability         |Excellent (VILA, Qwen2.5-VL, etc.)                                   |
|Ecosystem maturity     |Very mature, heavily used in robotics                                |
|Deadline risk          |Medium–high (different OS, different workflow)                       |
|Cost (core compute)    |~$250 dev kit                                                        |
|**Form-factor problem**|Dev kit is physically larger than Pi 5, heavier, awkward for handheld|

**Best for:** v2 builds or desktop/benchtop research devices where form factor doesn’t matter. Genuine sweet spot for local LLM agent work if you’re willing to accept a bigger device.

**Worst for:** v1 handheld under this deadline. Carrier boards (like the Seeed reComputer or J1010) can shrink it, but they add cost and are their own integration project.

### Option E — Rockchip RK1820 / RK1828 (new LLM-specific accelerators)

**The “wait six months” path.**

|Dimension                |Reality                                             |
|-------------------------|----------------------------------------------------|
|LLM tok/sec              |59–180 on Qwen2.5/3 3B–7B                           |
|Form factor              |SO-DIMM and M.2                                     |
|Availability             |Dev kit $889–$1029 as of Dec 2025 (with RK3588 host)|
|Standalone module pricing|Unknown — kit prices suggest ~$200–400 for modules  |
|Ecosystem                |Brand new, almost no community tooling              |

**Best for:** tracking for v2. Not a v1 option due to availability, cost, and zero community tooling. Worth watching for a hypothetical “v2 with custom carrier board.”

### Option F — Offload the LLM to a paired phone/laptop

**The cheat path.**

Run the LLM on the user’s paired phone (iOS/Android Ollama apps now exist) or a laptop over WiFi/BT. Handheld becomes a thin client that executes tools and streams to/from the paired device.

|Dimension                    |Reality                                                     |
|-----------------------------|------------------------------------------------------------|
|LLM speed                    |Whatever the paired device can do (could be 30–100+ tok/sec)|
|Power on handheld            |Minimal — no LLM compute                                    |
|Form factor                  |Handheld stays small                                        |
|Zero-exfiltration            |Preserved if paired device is personal                      |
|Connectivity dependency      |Requires paired device always present                       |
|**Undermines the core pitch**|The “everything on-device” story is gone                    |

**Best for:** builders willing to rethink the pitch as “local-network LLM agent with RF handheld front-end.” Genuinely viable architecture — the handheld becomes a keyboard/screen/RF-front-end for an LLM running on a nearby device. But it is a different project.

### Option G — Hybrid: small supervisor on-device + larger model remotely

Run a tiny supervisor model (0.5B–1B) on the handheld for tool-call decisions, kick reasoning-heavy work to a paired device. Mentioned for completeness; probably overkill for v1.

-----

## 6. How the choice interacts with chunk 2’s agent harness decision

The chunk 2 recommendation — write your own loop, adopt OpenClaw’s SKILL.md format, speak to an OpenAI-compatible endpoint — was deliberately designed to keep this decision reversible. Every option A–D speaks OpenAI-compatible HTTP (or can be wrapped to). That means:

- **Swapping A → B:** change one URL. Same model files might even work.
- **Swapping A → C:** change host SBC, reinstall OS, repoint the agent. Skill definitions and disclosure layer are portable.
- **Swapping A → D:** change host SBC, reinstall OS, rebuild model with TensorRT. Skill definitions and disclosure layer are portable.
- **Swapping to F (paired phone):** add a network hop. Agent logic unchanged.

The only hardware decision that commits you is the custom PCB / 3D-printed shell dimensions. Do not finalize those until the compute path is chosen and benchmarked.

-----

## 7. Decision dimensions worth weighing explicitly

These are the axes the decision turns on. Which one matters most is a judgment call, not a research finding:

**Deadline risk (May 15):** Option A and B win. You’ve done Pi work. You know the ecosystem. C and D are additional learning.

**Form factor / “handheldness”:** A, B, C are all roughly equivalent (credit-card SBC + HAT). D is larger and heavier. F keeps the handheld smallest.

**Battery life:** A wins decisively on pure LLM workloads (Hailo at 2.5W vs Pi 5 CPU at 10W is ~4× battery life during active inference). If inference is occasional and other work dominates the duty cycle, advantage shrinks.

**Model flexibility / future-proofing:** B, C, D win. A locks you to 5 models and one quantization. B, C, D let you ride the monthly improvements in the small-model ecosystem.

**Context window:** B, C, D win. 2048 tokens is tight enough that you will architect around it, and that architectural work doesn’t transfer if you later want a longer context.

**Tool-calling confidence:** All options can run Qwen2.5 1.5B, which is the benchmark winner. C has tool-calling *already wired* in rkllama; A requires you to wire it yourself atop hailo-ollama. B via Ollama has it native.

**VLM for summer work:** A wins (strong). C is capable. D is strong. B is weak.

**Cost (v1 core compute):** B ~$80, A ~$210, C ~$130–160, D ~$250.

**Open-source story for the writeup:** C’s RKLLM toolkit is more open than Hailo’s NDA-gated DFC. If “open, reproducible research device” is part of the narrative, C is stronger.

**Ecosystem familiarity:** A and B are Pi-native. C and D are learning curves.

-----

## 8. Genuine recommendations, plural

Different reasonable builders would choose differently here. Four coherent paths:

### The conservative/deadline path: **Option A (Pi 5 + Hailo)**

Stay with the original plan. Accept 2048-token context as an architectural constraint; accept the Hailo model zoo. Prioritize shipping a working v1 by May 15 over compute optimization. Wins: lowest deadline risk, best power, best VLM future, leverages existing planning. Accept: locked-in ecosystem, not the fastest LLM.

### The simplification path: **Option B (Pi 5 CPU-only)**

Drop the HAT. Save $130. Run Ollama / llama.cpp with any GGUF model. Gain larger context and model flexibility. Wins: simplest toolchain, $130 saved, maximum model flexibility. Accept: CPU contention with UI/scans, weaker VLM future, ~10W sustained during inference kills battery faster.

### The performance path: **Option C (Orange Pi 5 Max + rkllama)**

Step outside Pi ecosystem to get 2–3× LLM performance at the same price class, plus tool-calling already wired. Wins: best LLM/$ ratio in this class, open toolchain, larger context viable, VLM still usable. Accept: less mature peripheral/HAT ecosystem, have to port Pi-specific tooling (though ESP32-over-USB RF stack is portable).

### The rethink-the-pitch path: **Option F (paired phone/laptop)**

Make the handheld a thin client. LLM runs on a personal phone or laptop over WiFi/BT. Handheld does RF, UI, tool execution. Wins: fastest practical LLM, smallest handheld form factor, no thermal issues, cheapest handheld BOM. Accept: the “fully autonomous handheld” pitch becomes “local-network agent with RF front-end” — a different (but still defensible) narrative.

The right choice depends on which constraint you weight most heavily: deadline (A), simplicity (B), performance (C), or form factor + flexibility (F). There is no universally correct answer here.

-----

## 9. What to do before committing (regardless of path)

Three things are worth doing *before* locking in a path:

1. **Benchmark Qwen2.5 1.5B against your real agent prompt on whatever SBC you have access to now.** Even if it’s a Pi 5 without the HAT, measure: tokens/sec on your system prompt + skill definitions + a realistic user query. See if 2048 tokens is livable or painful for your skill set.
1. **Write a “hardware abstraction” line in the agent code now.** One config variable: `LLM_ENDPOINT = "http://localhost:8000/v1"`. Every other path in this chunk speaks that protocol. Don’t hard-code `hailo-ollama`-specific behavior anywhere.
1. **Sketch the handheld shell’s internal dimensions *after* benchmarking.** If benchmarking kills Option A, you want to know before you’ve 3D-printed a case sized for Pi 5 + HAT stack.

-----

## 10. Toolchain gotchas by path

### Option A (Hailo)

- DFC only runs on x86_64 Ubuntu; locked to Hailo’s zoo in practice
- Kernel driver version hell (`h10-hailort` vs `hailort` conflicts)
- Pi OS GenAI package 5.1.1 vs Hailo stack 5.2.0 mismatch
- PCIe lane contention with NVMe SSD
- `hailo-ollama` doesn’t auto-start; need systemd unit
- ~20W peak on 15W supply causes PMIC resets; need proper supply + active cooling
- Thermal throttling without active cooling

### Option B (Pi 5 CPU)

- Llamafile > Ollama for throughput, but less polished UX
- Context × model-size competes for system RAM (model + KV cache + OS + agent + UI)
- All 4 cores pegged means UI/scans suffer during inference
- No upgrade path to accelerator without rearchitecting power budget

### Option C (RK3588)

- RKLLM toolkit version mismatches between converted models and runtime (1.1.x vs 1.2.x files are incompatible)
- W8A8 only — larger model files, more RAM pressure
- `rkllama` is community-maintained, small team, bus factor
- Less community documentation for obscure peripherals
- Camera stack integration is more work than on Pi

### Option D (Jetson Orin Nano Super)

- JetPack version dependencies are strict
- Need to flash via x86 Linux host with NVIDIA SDK Manager
- Force Recovery Mode (jumper pin) required for initial flash
- Form factor: ~100mm × 80mm dev kit vs Pi 5’s 85mm × 56mm
- Power budget: sustained 15W needs beefier battery than Pi class

### Option F (paired device)

- Network latency between handheld and host affects feel
- Trust boundary: what happens when paired device is compromised?
- Reconnection logic after network drops
- Discovery / pairing UX
- Breaks “works anywhere, no network” narrative

-----

## 11. Does anything exist that already does this?

Confirmed again with wider searches in this chunk: **no**, nothing on the market or in open-source occupies the three-way intersection of (local-LLM agent) + (multi-radio RF) + (handheld form factor for pentesting).

Closest adjacents remain:

- **METATRON** — local-LLM pentesting agent, workstation-only, no RF, no handheld
- **HackBat** — multi-radio handheld, MCU-class, no LLM, no agent
- **Jetson Orin Nano + OpenClaw personal assistants** — local LLM on edge, general-purpose, no RF
- **Flipper Zero, M1 multitool** — multi-radio handheld, no LLM

Novelty claim from chunk 1 survives chunk 3.

-----

## 12. References (primary)

- CNX Software AI HAT+ 2 review with measured tok/sec — https://www.cnx-software.com/2026/01/20/raspberry-pi-ai-hat-2-review-a-40-tops-ai-accelerator-tested-with-computer-vision-llm-and-vlm-workloads/
- Hailo-10H Awesome Agents deep dive — https://awesomeagents.ai/hardware/hailo-10h/
- Hardware Corner Pi + AI HAT+ 2 analysis — https://www.hardware-corner.net/local-llms-raspberry-pi-ai-hat-plus-2/
- MikeVeerman tool-calling benchmark — https://github.com/MikeVeerman/tool-calling-benchmark
- RKLLama — https://github.com/NotPunchnox/rkllama
- TinyComputers RK3588 NPU benchmarks — https://tinycomputers.io/posts/rockchip-rk3588-npu-benchmarks.html
- Stratosphere Lab Pi 5 LLM benchmarks — https://www.stratosphereips.org/blog/2025/6/5/how-well-do-llms-perform-on-a-raspberry-pi-5
- arXiv 2511.07425 — SBC LLM benchmarks with Ollama and Llamafile
- Hailo GenAI model explorer — https://hailo.ai/products/hailo-software/model-explorer/generative-ai/devices/hailo-10h/
- NVIDIA Jetson edge-AI guide — https://developer.nvidia.com/blog/getting-started-with-edge-ai-on-nvidia-jetson-llms-vlms-and-foundation-models-for-robotics/
- Hailo LLM runtime architecture blog — https://hailo.ai/blog/bringing-generative-ai-to-the-edge-llm-on-hailo-10h/
- CNX Software RK1820/RK1828 coverage — https://www.cnx-software.com/2025/12/30/rockchip-rk1820-rk1828-so-dimm-and-m-2-llm-vlm-ai-accelerator-modules-devkits-and-benchmarks/
- AmeriDroid ODROID-M2 + Nova benchmarks — https://ameridroid.com/blogs/ameriblogs/rk3588-npu-shines-for-local-llms-indiedroid-nova-and-odroid-m2-performance-comparison
- Pelochus ezrknn-llm (RK3588 LLM tooling) — https://github.com/Pelochus/ezrknn-llm

-----

**Next chunk:** BOM. Structured around the open question from this chunk — four parallel component lists for paths A / B / C / F, common parts called out once, and cost totals for each path under the $1000 ceiling.