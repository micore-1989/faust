# Faust UI — Build Plan

**Project:** Faust (AI-native pentesting handheld) — Implementation sequence
**Target:** Ship May 15, 2026
**Version:** 1.0
**Audience:** Claude Code, executing one stage at a time against `github.com/micore-1989/faust`

---

## 0. How to use this document

This is an 11-stage sequence of Claude Code prompts. Each stage:

- Is **scoped to one coherent pass** (~½ to 2 days of work)
- Names the spec sections it implements and the tests it must leave green
- States files it creates, modifies, and must not touch
- Ends with a **verification step** you run before marking the stage done
- Lists hand-off notes for the next stage

**Work stages in order.** Later stages assume earlier ones have landed. Where a stage can be skipped in a pinch (Stage 4 without Stage 5, e.g.), it is called out.

**One Claude Code session per stage.** Paste that stage's prompt as the whole user turn; let it work to completion; verify; commit; move on.

**Global invariants (never violate):**

1. `faust/tests/test_ui.py:131` (the prompt-handler deadlock guard) stays green. Period.
2. `faust/agent/dispatch.py` is the Approver seam — disclosure flows through it. Do not bypass.
3. Background-task dispatch for `prompt` and `dispatch` (see `server.py:232-235`) is preserved.
4. WebSocket at `/ws`, port 8080, aiohttp — do not swap transport or framework.
5. `viewStack` / `goBack()` pattern preserved in the client.
6. Reconnect re-sends `state` + `skills` (preserved).
7. `body.active` hook preserved.
8. Sensitivity pills preserved.
9. Smart-default injection preserved.
10. CLAUDE.md rule 3 (disclosure through dispatch seam) — **read before Stage 4**.

**The 111-test suite is the floor.** Any stage that lowers the count without explicit spec authorization is failing the stage.

---

## Stage template

Each stage below follows this shape:

- **Objective** — one paragraph
- **Inputs** — spec sections, files to read
- **Produces** — files created/modified
- **Must not touch** — files out of scope this pass
- **Tests** — what stays green, what's extended, what's new
- **The prompt** — verbatim text to paste to Claude Code
- **Verify** — manual checks before commit
- **Hand-off** — what the next stage assumes

---

## Stage 1 — Foundation (CSS, fonts, base)

**Objective:** Stand up the visual substrate without wiring behavior. Palette, typography, font-face, layout grid, spacing scale, base components, sigil SVG files. No view logic, no JS changes.

**Inputs:**

- `faust-ui-spec.md` §1 (pre-build tasks), §4 (palette), §5 (typography), §6 (layout grid), §7 (components 7.1–7.12)
- `faust-sigil-spec.md` §2 (all 7 SVG sources), §4 (tile CSS)

**Produces:**

- `faust/ui/static/assets/sigils/sigil-wifi-ble.svg` through `sigil-meta.svg` (7 files)
- `faust/ui/static/assets/fonts/` populated (WOFF2s — Misha provides, Claude Code references)
- `faust/ui/static/assets/illustrations/boot-splash.png` (Misha provides, Claude Code references)
- `faust/ui/static/style.css` — REPLACED with new CSS per spec. Current CSS preserved as `style.css.backup` for reference
- No changes to `index.html` or `app.js` yet

**Must not touch:**

- `faust/ui/static/index.html` (Stage 6)
- `faust/ui/static/app.js` (Stage 6+)
- Any Python file
- Any test file

**Tests:**

- All 111 existing tests stay green (no behavioral change; CSS-only pass)
- No new tests

**The prompt:**

> You are implementing Stage 1 of Faust UI rebuild — Foundation pass. Read `faust-ui-spec.md` §1, §4, §5, §6, §7.1–§7.12, and `faust-sigil-spec.md` §2 and §4.
>
> **Task:** Replace `faust/ui/static/style.css` with a new stylesheet per spec, create the seven sigil SVG files, and leave everything else untouched.
>
> **Scope:**
>
> 1. Back up current `faust/ui/static/style.css` as `style.css.backup` in the same directory.
> 2. Write a new `faust/ui/static/style.css` that includes:
>    - All `@font-face` declarations for Jost (400/500/700/900) and JetBrainsMono (400/500) pointing to `/assets/fonts/*.woff2` (spec §5.2)
>    - All palette CSS variables in `:root` (scholar aliased as defaults) and `body[data-mode="pact"]` overrides (spec §4.1)
>    - All spacing-scale variables (spec §6.4)
>    - All typography utility classes (`.type-wordmark-xl`, `.type-h1`, etc. per spec §5.4)
>    - Base component classes: `.top-bar`, `.panel`, `.dot`, `.btn-primary`, `.btn-secondary`, `.rule-heavy`, `.rule-hair`, `.mono-block`, `.modal`, `.modal-backdrop`, `.sensitivity-pill`, `.radio-tile` and state variants (spec §7 and sigil spec §4)
>    - Global transition on color properties (spec §12.1)
>    - Preserved `body.active` hook as an empty class (spec §7.12)
>    - Kiosk quirks: no text selection on body, hidden scrollbars (spec §17.7)
>    - All 0.5px borders for hairline, 3px for heavy rules, 0px radius (spec §6.5)
> 3. Create seven SVG files in `faust/ui/static/assets/sigils/` using the exact SVG source in sigil spec §2.1–§2.7. Filenames: `sigil-wifi-ble.svg`, `sigil-sub-ghz.svg`, `sigil-nfc.svg`, `sigil-lf-rfid.svg`, `sigil-ir.svg`, `sigil-vision.svg`, `sigil-meta.svg`.
>
> **Constraints:**
>
> - Do NOT modify `index.html` or `app.js`. The old HTML/JS will continue to reference the old CSS class names and will look broken — that's expected for Stage 1 and fixed in Stage 6. The 111-test suite does not exercise styling, so tests should stay green.
> - Do NOT commit. Just make the changes. Misha will run tests and commit manually.
> - All color values use CSS variables. Zero raw hex in component classes.
> - Zero color keywords (no `white`, `black`, etc.).
> - Zero rounded corners.
>
> **When done,** report:
>
> - List of files created and modified
> - Confirmation that 111 tests pass (run `pytest` to verify)
> - Any deviations from spec with reason

**Verify:**

```bash
cd faust
pytest -q                           # expect 111 passed
ls faust/ui/static/assets/sigils/   # expect 7 svgs
grep -c '^:root' faust/ui/static/style.css  # at least 1
```

Smoke-test by loading `http://localhost:8080` in a browser — old UI will look broken (expected — CSS class names have changed; HTML/JS catch up in Stage 6). The sigil SVGs should be visible at `/assets/sigils/sigil-wifi-ble.svg` etc.

**Hand-off to Stage 2:** Visual substrate ready. Stage 2 is pure backend — adds phase-marker events to the agent so Stage 6+ can render them.

---

## Stage 2 — Agent phase-marker events

**Objective:** Extend `TwoPassAgent` to emit phase-marker events (`PlanningStarted`, `CatalogBuildStarted`, `ParameterizingStep`, `ParameterizingDone`) so the UI can show what Mephisto is doing during the 30–120s Pass 1 silence.

**Inputs:**

- `faust-ui-spec.md` §2.4 (WS protocol), §16.1 (event additions), §17.5 (coalescing behavior)

**Produces:**

- `faust/agent/events.py` — adds new dataclasses
- `faust/agent/twopass.py` — emits new events at defined points
- `faust/ui/bridge.py` — maps new events to WS messages
- `faust/ui/server.py` — WS message emission (`planning_started`, `parameterizing_step`)
- `faust/tests/test_twopass.py` — extends to verify emissions
- `faust/tests/test_bridge.py` (or equivalent) — asserts message shape

**Must not touch:**

- `faust/ui/static/*` — frontend catches up in Stage 6
- `faust/agent/catalog.py` — Stage 3
- `faust/agent/disclosure.py` — Stage 4
- `faust/ui/state.py` — Stage 3

**Tests:**

- All existing tests stay green
- `test_twopass.py` gets new cases asserting event emission at the right moments
- New integration test: a full agent turn emits `PlanningStarted(phase="catalog")` → `PlanningStarted(phase="plan")` → `ParameterizingStep` × N → `Final`
- Total tests: ≥ 115

**The prompt:**

> You are implementing Stage 2 of Faust UI rebuild — Agent phase-marker events. Read `faust-ui-spec.md` §2.4 and §16.1. Read the current `faust/agent/events.py`, `faust/agent/twopass.py`, `faust/ui/bridge.py`, `faust/ui/server.py`, and `faust/tests/test_twopass.py` to understand the existing event pipeline.
>
> **Task:** Add four new event types to the agent, emit them from `TwoPassAgent` at the defined moments, bridge them to WebSocket messages, and cover with tests.
>
> **Changes:**
>
> 1. **`faust/agent/events.py`:** Add four new frozen dataclasses, following the style of existing events:
>
>    ```python
>    @dataclass(frozen=True)
>    class PlanningStarted:
>        phase: Literal["catalog", "plan", "replan"]
>        attempt: int = 0
>
>    @dataclass(frozen=True)
>    class CatalogBuildStarted:
>        skill_count: int
>
>    @dataclass(frozen=True)
>    class ParameterizingStep:
>        step: int
>        of: int
>        skill: str
>        intent: str
>
>    @dataclass(frozen=True)
>    class ParameterizingDone:
>        step: int
>        of: int
>    ```
>
>    Add to the `AgentEvent` type union.
>
> 2. **`faust/agent/twopass.py`:** In `TwoPassAgent.run()`:
>    - At catalog build entry: emit `CatalogBuildStarted(skill_count=len(catalog))` and `PlanningStarted(phase="catalog")`.
>    - At planner call entry: emit `PlanningStarted(phase="plan")`.
>    - Before each `_parameterize_step` call: emit `ParameterizingStep(step=i+1, of=len(plan.steps), skill=step.skill, intent=step.intent)`.
>    - After `_parameterize_step` returns: emit `ParameterizingDone(step=i+1, of=len(plan.steps))`.
>    - On re-plan trigger (if any): emit `PlanningStarted(phase="replan", attempt=attempt_count)`.
>
>    Keep emissions minimal — each one is a single `yield` or `await self._emit(...)` call, depending on the existing pattern.
>
> 3. **`faust/ui/bridge.py`:** Add handlers mapping the new events to WS messages per `faust-ui-spec.md` §2.4:
>    - `CatalogBuildStarted` → `{"type": "planning_started", "phase": "catalog", "skill_count": n}` (fold the catalog-start into the `planning_started` message with phase=catalog; UI treats it as the leading phase marker)
>    - `PlanningStarted` → `{"type": "planning_started", "phase": ..., "attempt": ...}`
>    - `ParameterizingStep` → `{"type": "parameterizing_step", "step": ..., "of": ..., "skill": ..., "intent": ...}`
>    - `ParameterizingDone` → no WS emission (internal signal for future UI clearing)
>
> 4. **`faust/ui/server.py`:** Wire the new bridge emissions through `_send` or equivalent on all connected clients.
>
> 5. **Tests:**
>    - Extend `test_twopass.py`: given a plan with 3 steps, assert the sequence of event types matches `[CatalogBuildStarted, PlanningStarted(catalog), PlanningStarted(plan), ParameterizingStep(1,3), ParameterizingDone(1,3), ParameterizingStep(2,3), ..., <existing tool-call events>, Final]` — order may vary between `PlanningStarted` phases depending on exact flow, but the set of emitted types and their counts must match.
>    - Add a bridge test verifying message shape for all four new types.
>    - Ensure `test_ui.py:131` still passes (the deadlock guard).
>
> **Constraints:**
>
> - Background-task dispatch for `prompt`/`dispatch` handlers MUST be preserved in `server.py:232-235`. Do not change that pattern.
> - Do not touch `dispatch.py`, `disclosure.py`, `catalog.py`, or `ui/state.py` — those are future stages.
> - The legacy `thinking` WS message type keeps its existing behavior (single-pass mode still uses it). Do not repurpose it.
>
> **When done,** report the diff summary, test count, and any ambiguity encountered in the event emission points.

**Verify:**

```bash
pytest -q                                   # expect ≥ 115 passed (was 111 + ≥4 new)
pytest -q faust/tests/test_twopass.py       # specifically new cases
pytest -q faust/tests/test_ui.py::test_prompt_handler_does_not_deadlock_on_approval  # MUST pass
grep 'PlanningStarted' faust/agent/twopass.py | wc -l   # expect several emit points
```

Smoke-test in demo mode: `python -m faust.ui.run --demo`, open browser, send a prompt, inspect the WebSocket frames in dev tools — new message types should appear.

**Hand-off to Stage 3:** Agent now emits phase markers. Stage 3 remaps the catalog categories to 7 sigil groups so the UI's tiles can key off them cleanly.

---

## Stage 3 — Category remap + SimulatorState expansion

**Objective:** Rewrite `_categorize()` to return exactly 7 sigil-group strings, and add `scope`, `battery`, `first_dock_this_boot` fields to `SimulatorState` so the server can push them to clients.

**Inputs:**

- `faust-ui-spec.md` §8.3 (category remap table), §11.1 (state shape), §16.2 (category remap code), §16.3 (SimulatorState additions)

**Produces:**

- `faust/agent/catalog.py` — `_categorize()` rewritten to return one of 7 strings; old 11-category logic preserved as `_raw_categorize` and mapped via `SIGIL_GROUP_MAP`
- `faust/ui/state.py` — `SimulatorState` gets `scope`, `battery`, `first_dock_this_boot` fields plus `ScopeState` and `BatteryState` dataclasses
- `faust/ui/server.py` — `state` message serialization includes new fields
- `faust/tests/test_catalog.py` — all 41 skill packages still categorize to one of the 7 groups
- `faust/tests/test_simulator_state.py` — new fields in roundtrip tests

**Must not touch:**

- Frontend (Stage 6+)
- Agent events (Stage 2 done, no regression)
- Disclosure / Approver chain (Stage 4)
- Pursuits (Stage 5)

**Tests:**

- All existing tests green
- `test_catalog.py`: every skill maps to exactly one of `{wifi_ble, sub_ghz, nfc, lf_rfid, ir, vision, meta}`
- `test_simulator_state.py`: new fields roundtrip through `to_dict()` / `from_dict()`
- Total tests: ≥ 120

**The prompt:**

> You are implementing Stage 3 — Category remap + SimulatorState expansion. Read `faust-ui-spec.md` §8.3, §11.1, §16.2, §16.3. Read current `faust/agent/catalog.py`, `faust/ui/state.py`, `faust/tests/test_catalog.py`, `faust/tests/test_simulator_state.py`.
>
> **Task A: Category remap.**
>
> 1. In `faust/agent/catalog.py`, rename the current `_categorize` to `_raw_categorize` (preserves the 11-category logic).
> 2. Add a module-level `SIGIL_GROUP_MAP` dict exactly as specified in `faust-ui-spec.md` §16.2.
> 3. Write a new `_categorize(skill)` that calls `_raw_categorize`, looks up the result in `SIGIL_GROUP_MAP`, and returns the mapped group. If a raw category isn't in the map, return `"meta"`.
> 4. Add handling for vision/camera-based skills: if the skill imports `picamera2` or has `vision`/`camera` in its module path, classify as `vision` (handle in `_raw_categorize`, then let the map pass it through — `"vision": "vision"`).
> 5. Ensure the module exports exactly 7 distinct category strings across all 41 skills.
>
> **Task B: SimulatorState expansion.**
>
> 1. Add dataclasses to `faust/ui/state.py`:
>    ```python
>    @dataclass
>    class ScopeState:
>        template: Optional[Literal["recon", "self-test", "pentesting"]] = None
>        description: Optional[str] = None
>
>    @dataclass
>    class BatteryState:
>        percent: int = 82
>        charging: bool = False
>    ```
> 2. Add to `SimulatorState`:
>    ```python
>    scope: ScopeState = field(default_factory=ScopeState)
>    battery: BatteryState = field(default_factory=BatteryState)
>    first_dock_this_boot: bool = True
>    ```
> 3. Update `SimulatorState.to_dict()` to include these fields per the state shape in `faust-ui-spec.md` §11.1.
> 4. When transitioning `mephisto` to `connected` for the first time in a boot session, set `first_dock_this_boot` to `True` on the transition, then `False` after the `state` message is emitted (so the first-dock ceremony fires exactly once per boot — see UI spec §10.13).
> 5. When transitioning `power` to `off`, reset `first_dock_this_boot` to `True` (so next boot gets a fresh ceremony).
>
> **Task C: Tests.**
>
> 1. `test_catalog.py`: add a parametrized test iterating over every skill in `skills/`, asserting `_categorize(skill)` returns one of `{"wifi_ble","sub_ghz","nfc","lf_rfid","ir","vision","meta"}`. Also assert every group has at least one skill mapped to it (otherwise the dashboard would have a dead tile).
> 2. `test_simulator_state.py`: add tests for `ScopeState` and `BatteryState` serialization, for the `first_dock_this_boot` flag transitions on dock/undock/power-off, and for dict roundtrip including the new fields.
>
> **Constraints:**
>
> - `test_ui.py:131` must still pass.
> - Don't change any skill files themselves. Only `catalog.py` logic changes.
> - If a skill genuinely can't be mapped to any radio (e.g. a pure analysis tool), let it fall through to `meta`.
>
> **When done,** report: updated category counts per group, total tests, any skills that needed manual disambiguation.

**Verify:**

```bash
pytest -q                           # expect ≥ 120 passed
pytest -q faust/tests/test_catalog.py -v  # verify all 7 groups have skills
pytest -q faust/tests/test_simulator_state.py -v  # verify new fields
python -c "from faust.agent.catalog import _categorize, SIGIL_GROUP_MAP; print(set(SIGIL_GROUP_MAP.values()))"  # expect 7 unique
```

**Hand-off to Stage 4:** Agent emits structured phase markers, categorizes to 7 groups, `SimulatorState` carries scope/battery/first-dock. Stage 4 adds TrustCache middleware + the full Scope subsystem.

---

## Stage 4 — Scope subsystem + TrustCache

**Objective:** Wire the full scope-change flow end-to-end (WS message, server-side storage, journal entry), and install `TrustCache` middleware wrapping `DisclosureApprover` so destructive actions auto-approve within a 10-minute window per scope.

**Inputs:**

- `faust-ui-spec.md` §10.10 (scope modal), §11.3 (trust memory), §16.4 (TrustCache code)
- `CLAUDE.md` rule 3 (disclosure through the dispatch seam) — read this carefully

**Produces:**

- `faust/agent/disclosure.py` — adds `TrustCache` class; `DisclosureApprover` unchanged
- `faust/ui/run.py` — installs TrustCache wrapping DisclosureApprover in the approver chain
- `faust/ui/server.py` — new handler for `{"type": "scope_change"}`; emits updated state; creates `scope.set` journal entry; calls `TrustCache.invalidate()`
- `faust/ui/state.py` — methods for `set_scope(template, description)`
- `faust/journal/` (or wherever journal lives) — `scope.set` entry type
- `faust/tests/test_disclosure.py` — new test cases for TrustCache behavior
- `faust/tests/test_ui.py` — new cases for `scope_change` message handling

**Must not touch:**

- Pursuits (Stage 5)
- Frontend (Stage 6+)
- Agent internals (stages 2–3 complete)

**Tests:**

- All existing tests green, **including `test_ui.py:131`** — the TrustCache insertion must not break the deadlock guard
- `test_disclosure.py`:
  - First call: inner Approver runs, result cached if approved
  - Second call within 10 min, same scope: cached approval — inner NOT called
  - Second call within 10 min, different scope: inner called
  - Second call after 10+ min: inner called
  - `invalidate()` clears cache — next call runs inner
- `test_ui.py`:
  - `scope_change` message updates state, emits `state` message to client
  - `scope_change` creates journal entry
  - `scope_change` invalidates TrustCache
- Total tests: ≥ 128

**The prompt:**

> You are implementing Stage 4 — Scope subsystem + TrustCache middleware. Read `faust-ui-spec.md` §10.10, §11.3, §16.4. **Read `CLAUDE.md` rule 3 carefully — do not bypass the dispatch seam.** Read `faust/agent/disclosure.py`, `faust/agent/dispatch.py`, `faust/ui/run.py`, `faust/ui/server.py`.
>
> **Task A: TrustCache middleware.**
>
> 1. In `faust/agent/disclosure.py`, add `TrustCache` exactly as specified in `faust-ui-spec.md` §16.4. It must:
>    - Take an `inner: Approver` and `window_s: int = 600`
>    - Have `async __call__(tool_name, args, sensitivity) -> bool` matching the Approver protocol
>    - Cache the tuple `(scope_key, timestamp)` on successful approval only
>    - Auto-approve if within window AND scope_key matches current state
>    - Expose `invalidate()` for scope-change handlers
>    - Expose a way to query "was this approval fresh or remembered" so the journal can stamp it (e.g. `last_decision_was_cached: bool`)
> 2. `scope_key` derivation: for `template=None`, return `"none"`. For templates `recon` and `self-test`, return the template name. For `pentesting`, return `pentesting:<description>` (so different pentest engagements don't share trust).
> 3. `TrustCache` must NOT bypass `DisclosureApprover` — it wraps it. When the cache misses, it delegates to `inner` and stores the result only on approval. On rejection, cache is untouched.
>
> **Task B: Install in approver chain.**
>
> In `faust/ui/run.py` where the Approver is assembled for the dispatcher, wrap `DisclosureApprover` in `TrustCache`. The chain should be:
>
> - `ScopeApprover` (existing hard-gate — rejects tools outside scope) →
> - `TrustCache` (new, auto-approves within window) →
> - `DisclosureApprover` (existing, shows modal / fires `confirmation_request`) →
> - `ConfigApprover` (if it exists, for config-driven bypass)
>
> Order matters: ScopeApprover before TrustCache (scope is a hard gate, not just a trust signal), TrustCache before DisclosureApprover (cached approvals skip the modal). Preserve whatever's currently in `run.py`; only inject TrustCache between ScopeApprover and DisclosureApprover.
>
> Store a module-level reference or pass TrustCache instance into the server so the `scope_change` handler can call `invalidate()`.
>
> **Task C: Scope change handler.**
>
> 1. In `server.py`, add handler for `{"type": "scope_change", "template": str|null, "description": str|null}`:
>    - Validate template is one of `"recon"`, `"self-test"`, `"pentesting"`, or `null`
>    - If pentesting, require non-empty description
>    - Call `state.set_scope(template, description)` (add this method to `SimulatorState`)
>    - Call `trust_cache.invalidate()`
>    - Create a journal entry `scope.set` with previous scope, new scope, timestamp
>    - Emit updated `state` message to all connected clients
> 2. Add `SimulatorState.set_scope()` which updates `self.scope` and returns the previous value (for journaling).
>
> **Task D: Tests.**
>
> 1. `test_disclosure.py` — add `TestTrustCache` class with at minimum:
>    - `test_first_call_runs_inner`
>    - `test_cached_within_window_skips_inner`
>    - `test_cached_across_scope_boundary_runs_inner`
>    - `test_cached_after_window_expiry_runs_inner`
>    - `test_invalidate_clears_cache`
>    - `test_rejection_not_cached`
>    - `test_scope_key_derivation` (none, recon, self-test, pentesting with descriptions)
> 2. `test_ui.py` — add:
>    - `test_scope_change_updates_state`
>    - `test_scope_change_emits_state_message`
>    - `test_scope_change_creates_journal_entry`
>    - `test_scope_change_invalidates_trust`
>    - `test_scope_change_rejects_pentesting_without_description`
> 3. **Crucially,** `test_prompt_handler_does_not_deadlock_on_approval` must still pass. If the TrustCache insertion alters the flow such that `DisclosureApprover` is bypassed for the test's destructive call, that's OK — but the test invariant (that a prompt-handler call doesn't deadlock) must hold. Adjust the test if needed to explicitly test the trust-miss path, but do not remove the deadlock guard.
>
> **Constraints:**
>
> - CLAUDE.md rule 3: disclosure flows through the dispatch seam. TrustCache is an approver, not a disclosure-layer bypass. The server must still treat the result of the approver chain as authoritative.
> - Time-based behavior in tests: use a monotonic time injection (e.g. `time_source: Callable[[], float] = time.monotonic`) so tests can fast-forward without `asyncio.sleep(600)`.
>
> **When done,** report: diff summary, test count, confirmation that `test_ui.py:131` still passes, example trace of a two-call sequence showing trust-hit behavior.

**Verify:**

```bash
pytest -q                                              # expect ≥ 128 passed
pytest -q faust/tests/test_disclosure.py::TestTrustCache -v
pytest -q faust/tests/test_ui.py::test_prompt_handler_does_not_deadlock_on_approval  # MUST pass
pytest -q faust/tests/test_ui.py -k scope_change -v
```

Manual trace in demo: `--demo` mode, two sequential destructive dispatches in the same scope within 10 min → first one fires `confirmation_request`, second one does not. Scope change between the two → second one fires modal again.

**Hand-off to Stage 5:** Scope plumbing complete. Stage 5 builds Pursuits — a new subsystem on top of existing infra.

---

## Stage 5 — Pursuits subsystem

**Objective:** Build the Pursuits subsystem: registry of 7 predefined Pursuits + Custom placeholder, runner that emits progress/activity/complete events, WS handlers, persistence. Each Pursuit dispatches real skills through the existing Approver chain — destructive steps still fire confirmation modals.

**Inputs:**

- `faust-ui-spec.md` §10.4 (Pursuits tab + cards), §10.4.1 (detail/running), §10.4.2 (complete poster), §16.5 (subsystem shape)

**Produces:**

- `faust/pursuits/__init__.py`
- `faust/pursuits/models.py` — `Pursuit`, `PursuitRun`, `PursuitResult` dataclasses
- `faust/pursuits/registry.py` — the 7 Pursuits + Custom placeholder
- `faust/pursuits/runner.py` — execute a Pursuit, emit events
- `faust/pursuits/storage.py` — persist run history
- `faust/pursuits/pursuits/` — individual Pursuit implementations (7 files)
- `faust/ui/server.py` — handlers for `pursuit_start`, `pursuit_stop`; emits `pursuit_progress`, `pursuit_activity`, `pursuit_complete`
- `faust/ui/state.py` — tracks active Pursuit in state
- `faust/tests/test_pursuits.py` — runner behavior, event emissions, stop handling
- `faust/tests/test_ui.py` — WS message handling for Pursuits

**Must not touch:**

- Frontend (Stage 6+)
- Existing skills — Pursuits use them, don't rewrite them
- Approver chain — Pursuits dispatch through existing chain

**Tests:**

- All existing tests green (including `test_ui.py:131`)
- `test_pursuits.py`:
  - Registry has 8 entries (7 + Custom)
  - Each of the 7 Pursuits is runnable (may be stubbed in tests with fake dispatcher)
  - Runner emits progress + activity + complete events in correct order
  - Stop signal gracefully terminates
  - Destructive Pursuits still trigger the approver chain (mock DisclosureApprover; assert it was called)
- `test_ui.py`:
  - `pursuit_start` kicks off a run
  - `pursuit_stop` cancels in-flight
  - `pursuit_complete` persists journal entry
- Total tests: ≥ 142

**The prompt:**

> You are implementing Stage 5 — Pursuits subsystem. Read `faust-ui-spec.md` §10.4, §10.4.1, §10.4.2, §16.5. Read `faust/agent/dispatch.py` and `faust/ui/server.py` to understand how skills are dispatched and how background tasks work (spawn pattern at `server.py:232-235`).
>
> **Task A: Models.**
>
> In `faust/pursuits/models.py`:
>
> ```python
> @dataclass(frozen=True)
> class Pursuit:
>     id: str                      # e.g. "wardrive"
>     title: str                   # "Wardrive"
>     description: str             # display blurb
>     duration_hint: str           # "~30 min"
>     tools_used: list[str]        # ["wifi", "gps"]
>     parameters: list[ParamSpec]  # each with name, type, default, choices
>     is_stoppable: bool = True
>     is_custom: bool = False
>
> @dataclass
> class PursuitRun:
>     pursuit_id: str
>     run_id: str                  # uuid
>     started_at: float
>     params: dict
>     progress: float = 0.0        # 0.0–1.0
>     eta_s: Optional[int] = None
>     status: Literal["running", "stopped", "complete", "error"] = "running"
>     activity: list[str] = field(default_factory=list)
>
> @dataclass
> class PursuitResult:
>     run_id: str
>     summary: str                 # short human-readable result
>     journal_entry_id: str
>     artifacts: list[str] = field(default_factory=list)
> ```
>
> **Task B: Registry.**
>
> In `faust/pursuits/registry.py`, define the 7 Pursuits exactly as in `faust-ui-spec.md` §10.4. Expose:
>
> - `PURSUITS: dict[str, Pursuit]` — keys are Pursuit ids
> - `list_pursuits() -> list[Pursuit]` — ordered for UI display, Custom last
> - `get_pursuit(pursuit_id: str) -> Pursuit` — raises if not found
>
> Include a 'custom' Pursuit as a placeholder (`is_custom=True`, empty parameters).
>
> **Task C: Runner.**
>
> In `faust/pursuits/runner.py`, write `run_pursuit(pursuit, params, dispatcher, bridge, stop_event)` — an async function that:
>
> 1. Creates a `PursuitRun` with a uuid run_id
> 2. Emits `PursuitStarted(run_id, pursuit_id, params)` via bridge
> 3. Calls the Pursuit's implementation (see Task D)
> 4. The implementation is an async generator yielding activity lines and progress updates; runner forwards these as `PursuitProgress(run_id, progress, eta_s)` and `PursuitActivity(run_id, line)` via bridge
> 5. Each tool call inside the implementation goes through `dispatcher.dispatch(...)` — which runs through the Approver chain exactly as operator-initiated calls do. Destructive steps will fire `confirmation_request` to the UI; Pursuit pauses until the modal is resolved
> 6. If `stop_event` fires, Pursuit implementation receives `asyncio.CancelledError`; runner catches, emits `PursuitStopped(run_id)`, does cleanup
> 7. On completion, emits `PursuitComplete(run_id, summary, journal_entry_id)` via bridge
>
> Bridge events should be added to `faust/agent/events.py` or a new `faust/pursuits/events.py` — pick one, be consistent with existing patterns. Map them to WS messages in `faust/ui/bridge.py` per §2.4.
>
> **Task D: Individual Pursuits.**
>
> For each of the 7 Pursuits, create a file in `faust/pursuits/pursuits/`:
>
> - `wardrive.py`, `clone_credential.py`, `replay_subghz.py`, `evil_portal.py`, `bluetooth_recon.py`, `subghz_capture_analyze.py`, `hmc_demo.py`
>
> Each exports an async generator:
>
> ```python
> async def run_wardrive(params, dispatcher) -> AsyncIterator[PursuitYield]:
>     # yield PursuitYield(progress=0.0, eta_s=1800, activity="Starting wardrive...")
>     # await dispatcher.dispatch("gps.fix", {})
>     # yield PursuitYield(progress=0.1, activity="GPS fix acquired")
>     # ...
>     # return PursuitResultPartial(summary="47 networks captured", artifacts=["/captures/..."])
> ```
>
> For v1, implement each Pursuit at a stub level that exercises the real skills where available, but simulates long-running behavior in demo mode. Claude Code should write enough implementation that the event stream works end-to-end; full hardware correctness for each Pursuit is a separate concern.
>
> **Task E: Storage.**
>
> In `faust/pursuits/storage.py`, a minimal JSON-file-backed persistence of past runs (timestamp, pursuit_id, params, summary, result). Schema: a list of serialized `PursuitResult` + run metadata. Location: `~/.faust/pursuits.json` (or whatever the existing journal storage uses).
>
> **Task F: Server handlers.**
>
> In `faust/ui/server.py`:
>
> 1. Add handler for `{"type": "pursuit_start", "pursuit_id": ..., "params": ...}`. Spawn a background task calling `run_pursuit(...)` — same background-task pattern as `prompt`/`dispatch` handlers. Store the task in `SimulatorState.active_pursuits` keyed by run_id.
> 2. Add handler for `{"type": "pursuit_stop", "pursuit_id": ...}`. Find active run by pursuit_id; set its stop_event.
> 3. Ensure `confirmation_request` messages continue to work from inside Pursuits — the existing approver chain handles this automatically if Pursuits dispatch through the same `dispatcher.dispatch()` function.
>
> **Task G: State.**
>
> `SimulatorState` gets an `active_pursuits: dict[str, PursuitRunMeta]` field. Update `to_dict()`.
>
> **Task H: Tests.**
>
> 1. `test_pursuits.py`:
>    - `test_registry_has_8_entries`
>    - `test_each_pursuit_has_valid_schema`
>    - `test_runner_emits_events_in_order` (use a mock dispatcher and bridge; drive a Pursuit that yields 3 progress updates; assert sequence matches `Started, Progress(0.0), Activity, Progress(0.3), ..., Complete`)
>    - `test_stop_event_terminates_run`
>    - `test_destructive_step_goes_through_approver` — mock DisclosureApprover; run `replay_subghz` Pursuit; assert approver was called
>    - `test_pursuit_result_persisted_to_storage`
> 2. `test_ui.py`:
>    - `test_pursuit_start_spawns_background_task`
>    - `test_pursuit_start_background_task_does_not_block_receive_loop` — **this is the Pursuits analog of the prompt-handler deadlock guard; it's critical**
>    - `test_pursuit_stop_signals_run`
>    - `test_pursuit_complete_creates_journal_entry`
>
> **Constraints:**
>
> - Pursuits go through the Approver chain — never bypass. Destructive steps inside a Pursuit fire confirmation modals just like manual invocations.
> - Background-task dispatch pattern for `pursuit_start` — CRITICAL. Mirror `server.py:232-235`.
> - Pursuits that are expected to run for >10 min (Wardrive, Evil Portal) must honor `stop_event` promptly — test with a very short fake duration.
> - HMC Demo Pursuit uses a dedicated SSID (`faust-demo` or similar) — note in its docstring but don't hardcode yet.
>
> **When done,** report: diff summary, test count, demonstration of a full Pursuit run including one destructive step with mock approval.

**Verify:**

```bash
pytest -q                                                  # expect ≥ 142 passed
pytest -q faust/tests/test_pursuits.py -v
pytest -q faust/tests/test_ui.py -k pursuit -v
pytest -q faust/tests/test_ui.py::test_prompt_handler_does_not_deadlock_on_approval  # MUST pass
```

In demo mode, send `{"type": "pursuit_start", "pursuit_id": "wardrive", "params": {"duration_minutes": 1}}` via a WebSocket client (wscat) and observe the stream of progress/activity/complete messages.

**Hand-off to Stage 6:** All backend work complete. Agent emits phase markers (Stage 2), categorizes to 7 groups (Stage 3), trust-caches scoped confirmations (Stage 4), runs Pursuits (Stage 5). The frontend can now be rebuilt against a complete server contract.

---

## Stage 6 — UI scaffolding (HTML + JS shell)

**Objective:** Replace `index.html` and `app.js` with the new structure. Preserve every WS contract invariant. All screen containers exist but most are empty; only the scaffolding (top bar, tab bar, power state machine, reconnect, view stack, data-mode wiring) is functional.

**Inputs:**

- `faust-ui-spec.md` §2.4 (WS protocol), §2.5–§2.8 (invariants), §6 (layout grid), §7.1–§7.2 (top bar + tab bar), §11 (state model), §17 (implementation notes)

**Produces:**

- `faust/ui/static/index.html` — REPLACED with new structure
- `faust/ui/static/app.js` — REPLACED with new shell
- `faust/ui/static/index.html.backup` — old version preserved for reference

**Must not touch:**

- `style.css` (done in Stage 1)
- Any Python file
- Any test file (existing tests are Python-only and stay green)

**Tests:**

- All 142+ existing tests green (UI tests don't load the browser; they exercise the WS server directly)
- Manual browser verification is the acceptance for this stage
- **Preserved:** test_ui.py:131 deadlock guard — stays green because backend unchanged

**The prompt:**

> You are implementing Stage 6 — UI scaffolding. Read `faust-ui-spec.md` §2.4 through §2.8, §6 (layout grid), §7.1–§7.2 (top/tab bars), §11 (state model), §17 (implementation notes). Read `faust/ui/static/app.js` and `faust/ui/static/index.html` — the current implementation — before changing anything.
>
> **Task:** Replace `index.html` and `app.js` with a new scaffolding that:
>
> - Renders the top bar and bottom tab bar
> - Wires the power state machine (OFF → POWER ON affordance → BOOTING with boot log → ON)
> - Connects to `ws://${location.host}/ws` and reconnects on close
> - Handles all WS message types (even if handlers just log for now)
> - Preserves `viewStack` + `goBack()` pattern
> - Sets `body.dataset.mode` from state (scholar default; pact when mephisto connected)
> - Preserves `body.active` hook (empty class set during in-flight operations)
> - Shows empty screen containers for dashboard, pursuits, journal, settings, mephisto, tool-group — each just displays its screen name as placeholder text
>
> **HTML structure (`index.html`):**
>
> ```html
> <!DOCTYPE html>
> <html lang="en">
> <head>
>   <meta charset="utf-8">
>   <meta name="viewport" content="width=1280, height=800, initial-scale=1, user-scalable=no">
>   <title>Faust</title>
>   <link rel="stylesheet" href="/style.css">
>   <link rel="stylesheet" href="https://unpkg.com/@phosphor-icons/web@2.1.1/src/regular/style.css">
> </head>
> <body data-mode="scholar">
>   <div id="boot-screen" class="screen screen--boot hidden"><!-- Stage 7 --></div>
>   <div id="power-off-screen" class="screen screen--power-off">
>     <button class="power-on-btn">POWER ON</button>
>   </div>
>   <div id="app-shell" class="app-shell hidden">
>     <header class="top-bar">
>       <div class="top-bar__left">
>         <span class="top-bar__brand">FAUST</span>
>         <span class="top-bar__mode">SCHOLAR</span>
>       </div>
>       <div class="top-bar__center">
>         <button class="scope-label" id="scope-label">NO SCOPE · TAP TO SET</button>
>       </div>
>       <div class="top-bar__right">
>         <span class="top-bar__meta" id="top-meta">BAT 82% · 14:22</span>
>       </div>
>     </header>
>     <main id="app">
>       <div class="screen screen--dashboard" data-view="dashboard">Dashboard (Stage 8)</div>
>       <div class="screen screen--tool-group hidden" data-view="tool-group">Tool group (Stage 8)</div>
>       <div class="screen screen--pursuits hidden" data-view="pursuits">Pursuits (Stage 11)</div>
>       <div class="screen screen--pursuit-detail hidden" data-view="pursuit-detail">Pursuit detail</div>
>       <div class="screen screen--pursuit-running hidden" data-view="pursuit-running">Pursuit running</div>
>       <div class="screen screen--journal hidden" data-view="journal">Journal (Stage 11)</div>
>       <div class="screen screen--journal-entry hidden" data-view="journal-entry">Journal entry</div>
>       <div class="screen screen--mephisto hidden" data-view="mephisto">Mephisto (Stage 10)</div>
>       <div class="screen screen--settings hidden" data-view="settings">Settings (Stage 11)</div>
>     </main>
>     <nav class="tab-bar">
>       <button class="tab" data-tab="dashboard"><i class="ph ph-house"></i><span class="tab__label">DASHBOARD</span></button>
>       <button class="tab" data-tab="pursuits"><i class="ph ph-target"></i><span class="tab__label">PURSUITS</span></button>
>       <button class="tab" data-tab="journal"><i class="ph ph-book"></i><span class="tab__label">JOURNAL</span></button>
>       <button class="tab" data-tab="settings"><i class="ph ph-gear"></i><span class="tab__label">SETTINGS</span></button>
>     </nav>
>     <div id="modal-root"></div>  <!-- Stage 9 -->
>   </div>
>   <script src="/app.js"></script>
> </body>
> </html>
> ```
>
> **JavaScript (`app.js`):**
>
> Vanilla JS, IIFE. Required exports to the DOM:
>
> - `state` — module-level object matching `faust-ui-spec.md` §11.1
> - WS connection with reconnect (spec §17.4)
> - `handleMessage(msg)` — dispatches on `msg.type`, logs each type to console for now
> - `render()` — updates body.dataset.mode, shows/hides screens, updates top-bar content
> - `pushView(name, params)`, `goBack()` (spec §11.4)
> - `setActive(on)` (spec §17.6)
> - Event listeners for tab bar, POWER ON button
> - Boot sequence **stub**: when state.power transitions to 'booting', show #boot-screen (empty for now); on first 'on', hide boot and show app-shell
>
> **Critical invariants to preserve from current `app.js`:**
>
> - The WS receive loop processes messages FIFO and doesn't block on any async user action (the April 2026 deadlock pattern — see `faust-ui-spec.md` §2.5 context)
> - `confirmation` and `plan_approval` replies are always sent promptly, never gated on long-running local work
> - Reconnect re-applies state from the `state` message received on the new connection — do not maintain stale state across reconnects
>
> **Behavior:**
>
> - On load: show #power-off-screen. POWER ON click sends `{type: "power", action: "on"}` and shows #boot-screen.
> - On `state` with `power: "booting"`: show #boot-screen (content coming in Stage 7; for now just a centered "BOOTING..." label).
> - On `state` with `power: "on"`: show #app-shell, render current tab.
> - On `state` with `power: "off"`: show #power-off-screen.
> - On `state` with `mephisto: "connected"`: body.dataset.mode = "pact"; top-bar mode pill shows "PACT".
> - Tab clicks: `pushView(tabName, {})`.
> - Scope label click: log "scope modal not implemented" (Stage 9 will wire).
>
> **Constraints:**
>
> - Do NOT change `style.css` — Stage 1 produced it.
> - Do NOT touch any Python file.
> - Preserve the existing `SMART_DEFAULTS` table by moving it verbatim into the new `app.js` (will be used in Stage 8). Search current `app.js:28-44` for its location.
> - Old `app.js` gets saved as `app.js.backup` in the same directory.
> - Console-log every received WS message (type + truncated payload) — helpful for debugging through Stages 7–11. This is debug output, not user-facing.
>
> **When done,** report: diff summary, manual verification of boot/dashboard/tab-switching flow, screenshot of empty dashboard screen showing the top bar and tab bar with correct styling.

**Verify:**

```bash
pytest -q                       # expect ≥ 142 passed
python -m faust.ui.run --demo   # open browser at http://localhost:8080
```

In the browser:

- [ ] POWER ON button visible on fresh load
- [ ] Clicking it triggers boot (empty boot screen with "BOOTING...")
- [ ] After boot completes, dashboard placeholder shows with top bar + tab bar
- [ ] Tab clicks switch screens
- [ ] Palette is navy (scholar default)
- [ ] Mephisto dock simulation (demo mode's sequence) swaps palette to oxblood
- [ ] Refresh mid-session: UI rehydrates from state message, no errors in console

**Hand-off to Stage 7:** Scaffolding is live; now build the boot sequence with real content.

---

## Stage 7 — Boot sequence

**Objective:** Implement the full boot sequence: splash illustration, wordmark, Goethe rotation, hardware self-check log streaming, post-boot wordmark brighten, crossfade to dashboard.

**Inputs:**

- `faust-ui-spec.md` §10.1 (boot sequence)
- Asset: `faust/ui/static/assets/illustrations/boot-splash.png` (Misha provides before stage runs)

**Produces:**

- Boot-screen DOM + CSS (in existing `style.css` if needed; otherwise all in `app.js` via createElement)
- `app.js` — boot rendering, Goethe rotation, log streaming from `boot_log` messages, completion animation

**Must not touch:**

- Backend (Stage 2 emits boot logs; nothing to change)
- `style.css` except minor additions for boot-specific classes if needed

**Tests:**

- All existing tests green
- Manual browser verification

**The prompt:**

> You are implementing Stage 7 — Boot sequence. Read `faust-ui-spec.md` §10.1 carefully. The boot illustration is at `/assets/illustrations/boot-splash.png` — confirm it exists before starting.
>
> **Task A: Boot-screen content.**
>
> In `app.js`, populate #boot-screen with:
>
> - `<img>` pointing to `/assets/illustrations/boot-splash.png`, width 480px, auto height, centered, 40px from top
> - `<h1 class="type-wordmark-xl">FAUST</h1>` centered, 40px below illustration
> - A Goethe line + translation, rotated on each boot from a pool of 4:
>
>   ```javascript
>   const GOETHE_LINES = [
>     { de: "Grau, teurer Freund, ist alle Theorie.",
>       en: "GREY, DEAR FRIEND, IS ALL THEORY" },
>     { de: "Zwei Seelen wohnen, ach! in meiner Brust.",
>       en: "TWO SOULS DWELL, ALAS, IN MY BREAST" },
>     { de: "Der Worte sind genug gewechselt, laßt mich auch endlich Taten sehn!",
>       en: "ENOUGH WORDS HAVE BEEN EXCHANGED; NOW LET ME SEE DEEDS" },
>     { de: "Das Werdende, das ewig wirkt und lebt.",
>       en: "THE BECOMING, THAT FOREVER ACTS AND LIVES" },
>   ];
>   ```
>
>   Track last-used index in `localStorage.faustBootQuote` to avoid consecutive repeats.
>
>   - German line: Jost Medium 18px, centered, color `var(--accent-scope)`
>   - English translation: Mono XS, centered, color `var(--ink-tertiary)`, 8px below
> - A mono log area (`<pre class="boot-log">`), ~400px wide, centered, 32px below the Goethe translation. Streaming lines appended as they arrive from `boot_log` WS messages.
>
> **Task B: Log styling per line prefix.**
>
> Each `boot_log` message carries a `line` string like `[ ok ] kernel loaded (linux 6.6.x)`. Parse the status prefix and color-code:
>
> - `[ ok ]` prefix: render in `var(--accent-success)`, rest of line in `var(--ink-secondary)`
> - `[fail]` prefix: render in `var(--accent-crimson)`, rest in `var(--ink-primary)`
> - `[warn]` prefix: render in `var(--accent-scope)`, rest in `var(--ink-secondary)`
> - No recognized prefix: whole line in `var(--ink-secondary)`
>
> Type: Mono (12px). Lines append instantly, no per-line animation. Auto-scroll log area to keep newest at bottom.
>
> **Task C: Boot completion animation.**
>
> When state transitions to `power: "on"`:
>
> 1. Fire a 600ms "brighten" animation on the FAUST wordmark: CSS filter goes from `brightness(1.0)` → `brightness(1.1)` → `brightness(1.0)` over 600ms, ease-in-out.
> 2. After the brighten completes, crossfade the entire boot screen out (opacity 1 → 0 over 500ms, ease-in-out).
> 3. At opacity 0, hide #boot-screen and show #app-shell at opacity 0.
> 4. Crossfade app-shell in (0 → 1 over 500ms, ease-in-out).
>
> Total added time: ~1100ms. Do not block boot completion on this animation — if `state` with `power: "on"` arrives, start the animation and transition; don't wait for more logs.
>
> **Task D: Reconnect handling.**
>
> If the page loads and the first `state` message shows `power: "on"`, skip the boot sequence entirely — go directly to app-shell. The boot screen is only for fresh boots (transition OFF → BOOTING → ON observed in the same session).
>
> **Constraints:**
>
> - No changes to backend — existing `boot_log` message format is preserved.
> - Do not animate the dots in the boot log (they're instant per spec §12.3).
> - Do not add a skip-boot button — spec doesn't mention one; operators wait.
>
> **When done,** report manual verification of a fresh boot, a reconnect-during-boot, and a reconnect-while-on.

**Verify:**

Manual browser tests:

- [ ] Fresh POWER ON shows illustration + FAUST + Goethe + translation, log streams in
- [ ] Failures colored crimson; boot continues
- [ ] At boot complete, wordmark brightens, screen crossfades to dashboard
- [ ] Refresh mid-boot shows the boot screen from current state
- [ ] Refresh while ON goes straight to dashboard (no boot replay)
- [ ] Goethe line changes between consecutive boots

**Hand-off to Stage 8:** Boot is complete; dashboard placeholder is empty. Stage 8 populates the dashboard and tool-group screens.

---

## Stage 8 — Dashboard + tool-group screens

**Objective:** Implement the dashboard (7 radio-status tiles + Mephisto tile + session info) and the tool-group detail screen (sigil header + tool cards + recent activity + parameter form view).

**Inputs:**

- `faust-ui-spec.md` §10.2 (dashboard), §10.3 (tool-group), §10.3.1 (parameter form)
- `faust-sigil-spec.md` §4 (tile component)

**Produces:**

- `app.js` — dashboard rendering, tool-group rendering, parameter form rendering, dispatch flow
- Possibly minor additions to `style.css` for screen-specific layout (but most CSS already in Stage 1)

**Must not touch:**

- Backend (skills catalog provides everything needed via the `skills` message)
- Modals (Stage 9)
- Mephisto conversation (Stage 10)

**Tests:**

- All existing tests green
- Manual browser verification

**The prompt:**

> You are implementing Stage 8 — Dashboard + tool-group screens. Read `faust-ui-spec.md` §10.2, §10.3, §10.3.1, and `faust-sigil-spec.md` §4. Read current `app.js` (from Stage 6) and note where the `skills` message is handled. Note the existing `SMART_DEFAULTS` table preserved from current implementation.
>
> **Task A: Dashboard rendering.**
>
> Render dashboard into the `.screen--dashboard` container on every state change where dashboard is the active view.
>
> Layout:
>
> - Radio strip: 7 tiles in a horizontal flex row, gap 4px. Each tile is a `.radio-tile` per `faust-sigil-spec.md` §4. Sigils loaded inline from `/assets/sigils/sigil-<group>.svg` — fetch the SVG content once at boot and inline it into each tile as innerHTML. Group strings: `wifi_ble, sub_ghz, nfc, lf_rfid, ir, vision, meta`.
> - Below radio strip, 24px gap, a row with:
>   - Mephisto tile (scholar state: dim + dashed; pact state: solid + accent). Double-tile width (~348px × 200px).
>   - Session info panel right of Mephisto tile: Mono lines showing session start time, tools invoked count, journal entries count, current scope.
>
> In pact mode, the session info panel is replaced with a Mephisto activity preview — last Mephisto utterance from the conversation, Meta Label `MEPHISTO`, Mono XS `→ TAP TO OPEN`, 3px crimson rule, body text of utterance.
>
> Tile tap → `pushView('tool-group', {group: 'wifi_ble'})`. Mephisto tile tap (pact mode only) → `pushView('mephisto', {})` (mephisto screen empty for now — Stage 10 fills it).
>
> Tile status:
>
> - Read from `state.skills` (the catalog). Each tile's summary shows count of skills in that group: "12 tools available".
> - Tiles with zero skills: render in "disabled" state.
> - Active state is set when a skill from that group is currently executing (track `state.currentToolCall` and match its category).
>
> **Task B: Tool-group screen.**
>
> Entered via `pushView('tool-group', {group})`. Renders:
>
> - Back arrow (`ph-arrow-left` + `BACK` in Mono XS) top-left, calls `goBack()`
> - Header: 24×24 sigil inline + group display name (Display H1). 3px crimson rule 48px wide beneath.
> - Display H3 "Available tools"
> - Grid of `.tool-card` buttons for every skill in that group. Each card:
>   - Skill name (uppercase, Jost Bold 18px)
>   - Sensitivity pill (preserved styling from Stage 1 / `faust-ui-spec.md` §7.11)
>   - One-line description
>   - Mono footer "● ready"
>   - For sensitivity `"disruptive"` or `"active"`: add `.tool-card--destructive` class (crimson border + name)
> - Display H3 "Recent activity"
> - Last 10 journal entries filtered by this group, Mono rows: `HH:MM  skill.name  result-summary`
>
> **Task C: Skill dispatch flow.**
>
> Tap on a tool card:
>
> 1. If skill has no `parameters_schema` or all params are smart-default-fillable: dispatch directly with `{type: "dispatch", skill: <name>, args: <defaults>}`.
> 2. If params exist: `pushView('parameter-form', {skill})`.
>
> Smart defaults: use the preserved `SMART_DEFAULTS` table — before dispatching, fill in any unset params with their default (`interface: "wlan0"`, `duration_s: 30`, etc.).
>
> Destructive skills: dispatch proceeds normally; server will emit `confirmation_request` which Stage 9 will render as a modal. For Stage 8, confirmation-request handler can stay as a console log placeholder.
>
> **Task D: Parameter form view.**
>
> Rendered when `currentView === 'parameter-form'`. Preserved logic from old app.js (dynamic form generation from `parameters_schema`) but restyled:
>
> - Back button top-left
> - Skill name Display H2 with sensitivity pill
> - Description (Body Large)
> - Display H3 "Parameters" + list of labeled inputs, styled:
>   - String: text input, Mono, background `var(--bg-deep)`, padding 12px 16px, no border
>   - Integer: number input with spin controls
>   - Boolean: hard-square toggle (16×16)
>   - Enum: segmented button group
> - Footer row with CANCEL (Secondary) and INVOKE ▶ (Primary) buttons
>
> INVOKE dispatches with the collected params; navigates back to tool-group.
>
> **Task E: Journal wiring (read-only).**
>
> For "recent activity" on the tool-group screen: send a `journal_query` on view-enter with filter `{group: <group>, limit: 10}`. Server will reply with `journal_entries` — render them. For now the journal endpoint may not be implemented on the server; show "No recent activity" placeholder if no entries returned or if the message errors. (Stage 11 implements the journal server-side.)
>
> **Constraints:**
>
> - Preserve `body.active` toggling: set to true on dispatch, clear on `tool_call_executed` or `final` or `error`.
> - Preserve smart-default injection logic.
> - Preserve sensitivity-pill rendering on cards.
>
> **When done,** report manual verification screenshots and any skills that rendered oddly.

**Verify:**

Manual browser tests:

- [ ] Dashboard shows 7 tiles with correct sigils
- [ ] Tiles disabled when no skills in group
- [ ] Tile tap → tool-group screen with back button working
- [ ] Tool cards show sensitivity pills; destructive cards have crimson border
- [ ] Tapping passive skill dispatches directly
- [ ] Tapping parameterized skill opens form; INVOKE dispatches
- [ ] Recent activity shows placeholder (Stage 11 will fill it)
- [ ] Mephisto tile: dim+dashed in scholar, solid in pact (force pact via demo)
- [ ] body.active toggles correctly during dispatch

**Hand-off to Stage 9:** Dashboard + tool-group are live. Dispatch triggers confirmation requests which currently log to console. Stage 9 renders the modals.

---

## Stage 9 — Modals (destructive + plan-approval + scope)

**Objective:** Implement three modals: destructive-action (§10.8), plan-approval (§10.9), scope-change (§10.10). All three correlate by id and preserve the existing queue-based reply path on the server.

**Inputs:**

- `faust-ui-spec.md` §7.10 (base modal CSS), §10.8 (destructive), §10.9 (plan-approval), §10.10 (scope-change)

**Produces:**

- `app.js` — modal rendering infrastructure, three modal types
- Possibly minor CSS additions for modal-specific variants

**Must not touch:**

- Backend (Stages 2/4 already send `confirmation_request`, `plan_approval_request`; Stage 4 handles `scope_change` reply)

**Tests:**

- All existing tests green
- Manual browser verification

**The prompt:**

> You are implementing Stage 9 — Modals. Read `faust-ui-spec.md` §7.10, §10.8, §10.9, §10.10. Read current `app.js` to understand how `confirmation_request` messages were handled previously (for reference, but the Stage 6 scaffolding currently logs them).
>
> **Task A: Modal infrastructure.**
>
> Add to `app.js`:
>
> ```javascript
> function openModal(modalNode) { /* clear #modal-root, append, trigger fade-in */ }
> function closeModal() { /* trigger fade-out, then remove from DOM */ }
> ```
>
> Modal backdrop styles already exist in `style.css` from Stage 1 (`.modal`, `.modal-backdrop`, `.modal__header`, `.modal__body`, `.modal__buttons`). Use those.
>
> Modal nodes are created as DOM (not innerHTML strings — event handlers attach cleanly). Each modal is mounted in `#modal-root`.
>
> Fade-in: 150ms opacity 0 → 1. Fade-out: 150ms opacity 1 → 0, then remove.
>
> **Task B: Destructive-action confirmation modal.**
>
> Triggered by WS message `confirmation_request {call_id, tool_name, arguments, sensitivity}`.
>
> Modal content (per §10.8):
>
> - Header: action name (human-readable) in Jost Black 22px 0.02em UPPER on `var(--accent-crimson)` background. Derive action name from `tool_name` if server doesn't provide one explicitly (e.g., `wifi.deauth` → `DEAUTH A WIFI CLIENT`).
> - Body:
>   - `.mono-block .mono-block--destructive` showing tool call as `tool_name(arg1=val1, arg2=val2)` pretty-printed
>   - 2–3 sentence consequence in Body (14px) `var(--ink-primary)`. Look up by tool_name; if unknown, use a generic "This action may modify the environment. Confirm only if you're authorized."
>   - Hairline divider
>   - Scope line: `Scope · <scope-name-or-NO-SCOPE>` in Mono, scope part colored `var(--accent-scope)`
>   - Trust-window line: `Trust remembered within this scope for 10 minutes.` in Mono XS `var(--ink-tertiary)`
> - Buttons: ABORT (Secondary, flex 1) and CONFIRM (crimson fill, flex 1).
>
> ABORT: send `{type: "confirmation", call_id: <same>, approved: false}`; close modal.
> CONFIRM: send `{type: "confirmation", call_id: <same>, approved: true}`; close modal.
> Escape key: equivalent to ABORT.
> Backdrop tap: no action (prevents accidental dismiss).
>
> **Task C: Plan-approval modal.**
>
> Triggered by WS message `plan_approval_request {plan_id, reasoning, steps, safety_notes}`.
>
> Modal content (per §10.9):
>
> - Header: `MEPHISTO PROPOSES A PLAN` on `var(--accent-thinking)` background. **Exception:** if `plan_id` ends with `-replan<N>`, header reads `MEPHISTO PROPOSES A REVISED PLAN` on `var(--accent-crimson)` background.
> - Body:
>   - Display H3 `Reasoning`
>   - `reasoning` text in Body (14px) `var(--ink-primary)`
>   - Display H3 `Steps`
>   - Numbered list, Mono rows: `N. skill_name        intent`. If step has `critical: true` (the existing PlanStep sensitivity), prefix with `[DESTRUCT]` in `var(--accent-crimson)`.
>   - Display H3 `Safety notes` (if `safety_notes` non-empty)
>   - Each note as a line `⚠ <note>` in Mono, `⚠` in `var(--accent-scope)`
> - Buttons: REJECT (Secondary) and APPROVE PLAN (thinking-purple fill; crimson on re-plan).
>
> REJECT: send `{type: "plan_approval", plan_id, approved: false}`; close.
> APPROVE PLAN: send `{type: "plan_approval", plan_id, approved: true}`; close.
>
> Modal is scrollable if content exceeds viewport (set `max-height: 80vh; overflow-y: auto` on `.modal__body`).
>
> **Task D: Scope-change modal.**
>
> Triggered by tap on the top-bar scope label.
>
> Modal content (per §10.10):
>
> - Header: `SET SCOPE` on crimson.
> - Body: three radio options (custom-styled 16×16 hard squares, selected fills with crimson):
>   - Strictly Recon — "Passive observation only. No transmission."
>   - Testing My Own Devices — "Unlimited actions on hardware you own."
>   - Pentesting — "Requires description of engagement." When selected, reveals a description textarea below.
> - Buttons: CANCEL (Secondary) and SET SCOPE (Primary crimson).
>
> SET SCOPE disabled when Pentesting is selected with empty description.
> CANCEL: close, no change.
> SET SCOPE: send `{type: "scope_change", template: <selected>, description: <textarea or null>}`. Close.
>
> On successful scope change, server emits updated state; top-bar label updates automatically via render(). No need to update manually.
>
> **Task E: Correlation guarantees.**
>
> - Never lose `call_id` or `plan_id` between request and reply. If a new `confirmation_request` arrives while one is already open, queue the new one: store it in a local queue, pop-and-render next modal after current one closes.
> - Do not time out modals — operator can take as long as they need to decide.
> - If the WebSocket disconnects with a modal open: leave the modal up but grey it out. On reconnect, if the server re-emits the same `confirmation_request` (state replay), replace the modal in place. If it doesn't re-emit, the server considered the request resolved — close the modal.
>
> **Constraints:**
>
> - Body styling uses `var(--ink-primary)` for primary text, never raw hex
> - Palette-reactive: in pact mode, modal backdrop tints oxblood (already in style.css from Stage 1)
> - Do not block the WS receive loop on modal reply — the reply goes out as soon as the button is pressed; the receive loop continues processing other messages in the meantime
>
> **When done,** report: three modal types verified manually, correlation preserved across queued modals.

**Verify:**

Manual browser tests:

- [ ] Dispatching a destructive skill (e.g., `wifi.deauth`) fires the destructive modal
- [ ] ABORT/CONFIRM send correct `call_id` (watch browser devtools Network → WS frames)
- [ ] Trust-window behavior: second destructive dispatch within 10 min on same scope does NOT fire modal (server-side TrustCache from Stage 4 handles this; UI just doesn't receive the request)
- [ ] Plan-approval modal fires when Mephisto proposes a plan (send a multi-step prompt in pact mode)
- [ ] Re-plan modal (if you can trigger one) uses crimson header
- [ ] Scope modal opens from top-bar label tap
- [ ] Pentesting requires description; SET SCOPE disabled until text entered
- [ ] After scope change, new destructive action fires modal again (trust invalidated)
- [ ] Queued modals: force two destructive actions in rapid succession; first modal resolves, second appears

**Hand-off to Stage 10:** Modals are live. Confirmation flows are complete. Stage 10 builds the Mephisto conversation screen and the dock animation.

---

## Stage 10 — Mephisto conversation + dock + ceremony

**Objective:** Implement the Mephisto conversation screen (pact-mode only), the dock animation (palette swap + tile fill-in), and the first-dock-per-boot ceremony.

**Inputs:**

- `faust-ui-spec.md` §3.4 (dock transition), §10.7 (Mephisto conversation), §10.12 (dock animation), §10.13 (first-dock ceremony), §17.5 (coalescing behavior)

**Produces:**

- `app.js` — Mephisto conversation rendering, phase-marker coalescing, dock animation triggers, ceremony overlay
- Possibly minor CSS for ceremony overlay and phase-marker chips

**Must not touch:**

- Backend (phase markers already emitted in Stage 2; first_dock_this_boot already tracked in Stage 3)

**Tests:**

- All existing tests green
- Manual browser verification

**The prompt:**

> You are implementing Stage 10 — Mephisto conversation + dock + ceremony. Read `faust-ui-spec.md` §3.4, §10.7, §10.12, §10.13, §17.5. The Mephisto screen is reached from the dashboard Mephisto tile tap (Stage 8) in pact mode.
>
> **Task A: Conversation layout.**
>
> Populate `.screen--mephisto` when view is active. Layout:
>
> - Top bar: back button, `MEPHISTO` Wordmark M (36px), model info Mono XS (`QWEN 2.5-VL-3B · 8.4 T/S` — fetch from state if available, else hardcode for v1)
> - Main area: 50/50 vertical split (each pane ~324px tall given 648px middle region)
>   - Top pane: `.conversation` scrollable column, newest at bottom
>   - Bottom pane: `.tool-output` live streaming output, newest at bottom, dark background (`var(--bg-deep)`)
> - Input row at bottom of conversation pane (above split): text input + SEND button
>
> **Task B: Conversation rendering.**
>
> Conversation state lives in `state.conversation[]`. Each entry: `{role, content, timestamp, key}` where role is one of `operator`, `mephisto`, `planning`, `parameterizing`, `tool`, `result`, `scope`.
>
> Roles render with Meta Label in the role color (per §10.7):
>
> - OPERATOR → `var(--ink-primary)`
> - MEPHISTO → `var(--accent-mephisto)`
> - PLANNING → `var(--accent-thinking)`
> - PARAMETERIZING → `var(--accent-thinking)`
> - TOOL → `var(--accent-crimson)`
> - RESULT → `var(--accent-success)`
> - SCOPE → `var(--accent-scope)`
>
> Body text color matches role color for ambient voices; ink-primary for Operator; crimson-mono for Tool calls.
>
> Entries have a stable `key` (uuid for chat messages, phase-name for phase markers). Re-rendering updates existing entries by key rather than appending.
>
> **Task C: Phase-marker coalescing.**
>
> On `planning_started` message:
>
> - Phase `catalog`: add/update entry with `key: 'phase-catalog'`, role `PLANNING`, content `assembling catalog (Ns)`. Start a 1000ms interval that ticks N upward.
> - Phase `plan`: add/update entry with `key: 'phase-plan'`, role `PLANNING`, content `thinking about steps (Ns)`. Tick counter.
> - Phase `replan`: add entry with `key: 'phase-replan-<attempt>'`, role `PLANNING`, content `RE-PLANNING · adjusting course (Ns)`. Prepend a small warning dot `●` in `var(--accent-crimson)` before the label. Tick counter.
>
> On `parameterizing_step` message:
>
> - Key `phase-parameterizing` (single entry, replaces for each new step)
> - Role PARAMETERIZING
> - Content: `step <step> of <of> · <skill>`
>
> When a phase's follow-up arrives (e.g., `plan_proposed` after `planning_started(plan)`), stop the counter for `phase-plan` and remove the entry — the plan modal or the plan summary takes over.
>
> Coalescing (preserved from existing `pushChatAssistant`): consecutive messages with same role merge unless they have distinct keys. Phase markers always have distinct keys to avoid merging.
>
> **Task D: Input.**
>
> Text input at bottom of conversation pane:
>
> - Mono (14px)
> - Full-width
> - Placeholder `speak to Mephisto...`
> - SEND button to the right (96px wide, Primary button style)
> - Enter key submits (if not shift-enter)
>
> On submit: send `{type: "prompt", text: <input>}`, add an OPERATOR entry to conversation state, clear input.
>
> Set `body.active` true on submit, clear on `final` message.
>
> **Task E: Tool output pane.**
>
> Bottom pane renders live tool execution:
>
> - On `tool_call_proposed`: show header `tool_name(args)` in Mono crimson; clear previous output; set `state.currentToolCall`
> - Streaming output lines (from `tool_call_executed.result` if it's a stream, else render final result): each prefixed `→ ` in Mono ink-primary
> - On `tool_call_executed` terminal: prepend `✓ ` in success green for successful completion, `✗ ` in crimson for error
> - When no tool is active (`state.currentToolCall === null`): show centered `No active tool invocation.` in Mono `var(--ink-quiet)`
>
> **Task F: Dock animation.**
>
> On `state` message where `mephisto` transitions `disconnected → connected`:
>
> 1. Set `body.dataset.mode = 'pact'`. The global 1000ms color transitions in style.css (Stage 1) handle the palette swap automatically.
> 2. On the dashboard: Mephisto tile animates from dim+dashed to solid+accent. This happens via CSS — the `.mephisto-tile` has state-dependent styling driven by `data-mode`. No explicit JS animation needed if CSS is set up correctly; adjust Stage 1 CSS if gaps.
> 3. If `state.first_dock_this_boot === true` (from Stage 3): trigger ceremony (Task G) after a 600ms delay.
>
> On `state` where `mephisto` transitions `connected → disconnected`:
>
> 1. Set `body.dataset.mode = 'scholar'`. Palette reverses over 1000ms.
> 2. No ceremony.
> 3. If currently on the Mephisto screen, navigate back to dashboard automatically (there's no Mephisto to talk to).
>
> **Task G: First-dock ceremony.**
>
> When triggered (first-dock-per-boot detected):
>
> 1. Create a full-screen overlay element at opacity 0:
>    - Background `var(--pact-bg-primary)` (opaque)
>    - Centered content:
>      - `MEPHISTO` in `.type-wordmark-xl`, color `var(--accent-mephisto)`
>      - 3px crimson rule, 120px wide, 24px below
>      - `PACT ESTABLISHED` in `.type-h1`, 28px, color `var(--accent-scope)`, 24px below rule
>      - Diamond mark (24×24 rotated square SVG) in `var(--accent-active)`, 48px below
> 2. Fade in 0 → 1 over 400ms, ease-out
> 3. Hold 2000ms
> 4. Fade out 1 → 0 over 400ms, ease-in
> 5. Remove overlay element
> 6. After the ceremony, the server should have flipped `first_dock_this_boot` to false (Stage 3 behavior) — don't fire ceremony again this boot
>
> **Constraints:**
>
> - Pact mode reachable only via actual dock event — do not trigger via URL or JS for production use (dev-only shortcut Ctrl+D from spec §13 is acceptable for testing)
> - When not in pact mode, the Mephisto screen is unreachable (tile is dim; tap does nothing)
> - Preserve coalescing for consecutive same-role messages
> - Do not animate role labels or chat messages themselves — text appears instantly
>
> **When done,** report manual verification of dock/undock cycle, first-dock ceremony, conversation with phase markers.

**Verify:**

Manual browser tests:

- [ ] In demo mode: force dock → palette swaps over 1s; Mephisto tile fills in
- [ ] First dock per boot → ceremony overlay appears for ~2.8s total
- [ ] Second dock in same boot → palette swap only, no ceremony
- [ ] Undock → palette reverses
- [ ] Tap Mephisto tile (pact mode) → conversation screen
- [ ] Send a prompt → phase markers render (PLANNING · assembling catalog, then PLANNING · thinking about steps)
- [ ] Counter ticks on phase-marker lines
- [ ] Plan-approval modal fires; approve → parameterizing line renders
- [ ] Tool call renders in output pane with streaming
- [ ] `body.active` toggles on prompt send / final receive
- [ ] Phase markers coalesce (same phase updating in place)
- [ ] Replan entry visually distinct

**Hand-off to Stage 11:** Mephisto flow is fully live. The remaining surfaces are Journal, Pursuits UI, Settings, and demo-mode event sequence.

---

## Stage 11 — Journal + Pursuits + Settings + polish

**Objective:** Implement the remaining screens (Journal list and detail, Pursuits tab + detail + running + complete poster, Settings tab + diagnostics subscreens). Update the demo-mode event sequence. Final polish.

**Inputs:**

- `faust-ui-spec.md` §10.4 (Pursuits UI), §10.5 (Journal), §10.6 (Journal entry), §10.11 (Settings), §2.9 (demo mode)

**Produces:**

- `app.js` — journal, pursuits UI, settings
- Server-side: journal endpoint (`journal_query` handler + entries storage), demo-mode event sequence update
- `faust/journal/` — journal storage (if not already present from Stage 5)
- `faust/tests/test_ui.py` — `journal_query` handler test
- `faust/tests/test_journal.py` — storage tests

**Must not touch:**

- Existing approver chain, Pursuits runner, etc. — these are complete
- Core UI patterns from Stages 6–10

**Tests:**

- All existing tests green
- Journal tests: ≥5 new cases
- Total: ≥ 148 or so

**The prompt:**

> You are implementing Stage 11 — Journal + Pursuits UI + Settings + polish. Read `faust-ui-spec.md` §10.4–§10.6, §10.11, and §2.9 (demo mode). Check that Stages 1–10 are landed and passing.
>
> **Task A: Journal server-side.**
>
> 1. Create or extend `faust/journal/` with:
>    - `storage.py` — append-only JSON log of entries at `~/.faust/journal.jsonl`; one entry per line; each entry schema: `{id, timestamp, type, tool_name?, params?, result?, sensitivity?, scope_snapshot, confirmed?, mode, duration_ms?, artifacts?, notes?, pursuit_id?}`
>    - `types.py` — dataclasses for entry types: `tool_invocation`, `scope_set`, `pact_activated`, `pursuit_started`, `pursuit_complete`, `boot`
>    - `query.py` — filter entries by `{group, tool, sensitivity, time_range, scope}` with AND semantics
> 2. Wire existing dispatch flow to create `tool_invocation` entries on every `tool_call_executed`. Previous stages may have left placeholder calls; make sure this is populated.
> 3. Add server handler for `{"type": "journal_query", "filters": {...}}`: call `query.run(filters)`, return `{"type": "journal_entries", "entries": [...], "filters": {...}}`.
> 4. `tool_invocation` entries carry `confirmed: "fresh"` or `confirmed: "remembered"` based on TrustCache state (Stage 4).
>
> **Task B: Journal UI.**
>
> Tab Journal renders:
>
> - Display H1 `JOURNAL` + 3px crimson rule
> - Four filter selectors (Secondary buttons with `ph-caret-down`): scope, tool, sensitivity, time range
> - On filter change: send `journal_query` and render the returned entries
> - Entry rows (48px tall): timestamp (Mono XS tertiary, 60px) · sensitivity dot · tool name (Mono Medium, 160px, crimson if disruptive) · summary (Mono secondary, flex) · scope (right-aligned Mono XS scope accent)
> - Tap row → `pushView('journal-entry', {id})`
>
> Journal-entry detail (§10.6):
>
> - Back button
> - Timestamp Mono XS + `APRIL 15, 2026`
> - Tool name Display H1 + 3px crimson rule
> - Two metadata panels side by side: invoked by, mode, sensitivity | scope, confirmed, duration
> - `Parameters` Display H3 + `.mono-block` with args
> - `Result` Display H3 + Mono content
> - `Artifacts` Display H3 + list of file paths with sizes in Mono (links are not tappable in v1 — just display)
> - `Notes` Display H3 + textarea (Mono, 120px tall, `var(--bg-deep)` background) — on blur, send update to server (add a new WS message `{"type": "journal_update_notes", "id": ..., "notes": ...}` and handler)
>
> **Task C: Pursuits UI.**
>
> Tab Pursuits renders:
>
> - Display H1 `PURSUITS` + 3px crimson rule
> - Grid of 8 `.pursuit-card`: 7 pre-defined + 1 Custom (dashed border, ink-secondary title)
> - Data source: fetch from server — if no endpoint exists yet, add WS `{"type": "pursuits_list"}` handler returning all Pursuit definitions as `{"type": "pursuits", "pursuits": [...]}`. Or hardcode the 7 definitions in `app.js` matching the Stage 5 registry — either works; former is more DRY
>
> Tap a card → `pushView('pursuit-detail', {pursuit_id})`
>
> Pursuit-detail screen (§10.4.1 stopped state):
>
> - Back button
> - Display H1 title + rule
> - Description (Body Large)
> - `Parameters` Display H3 + labeled inputs (identical to skill parameter form in Stage 8)
> - `Tools invoked` line Mono
> - `▶ START PURSUIT` Primary button
>
> On START: send `{type: "pursuit_start", pursuit_id, params}`. Navigate to `pursuit-running` view.
>
> Pursuit-running screen (§10.4.1 running state):
>
> - Back button disabled (or `STOP PURSUIT` button as the footer action; back goes to Pursuits tab without stopping)
> - Display H1 `<PURSUIT> · RUNNING` + full-width crimson rule
> - Mono line: `Started HH:MM · Elapsed MM:SS · ETA MM:SS` (update from `pursuit_progress` messages)
> - Progress bar (3px tall, full-width, var(--accent-active) fill)
> - Display H3 `Live activity`
> - Scrollable Mono list of last 20 activity lines (from `pursuit_activity` messages), newest at top
> - `■ STOP PURSUIT` Secondary button. If Pursuit is stoppable, sends `pursuit_stop` directly; else opens a confirmation modal
>
> On `pursuit_complete`: navigate to `pursuit-complete` view.
>
> Pursuit-complete poster (§10.4.2):
>
> - Full-screen (hides top bar + tab bar temporarily)
> - Centered: Pursuit title in Jost Black 72px, 3px rule, `COMPLETE` in Display H1 `var(--accent-scope)`, summary line Mono, empty crimson circle 240px diameter 4px stroke, diamond mark
> - Hold 2000ms
> - Fade-out 200ms → navigate to `journal-entry` with `id = pursuit_complete.journal_entry_id`
>
> **Task D: Settings UI.**
>
> Tab Settings — scrollable (overflow-y: auto on the `.screen--settings` container).
>
> Sections per §10.11:
>
> - Display (brightness slider, animation toggle)
> - Audio (sound slider)
> - Radio (6 toggles — wifi/ble, sub-ghz, nfc, lf-rfid, ir, vision)
> - Scope history (list of past scopes from journal `scope_set` entries, each with `[switch to →]` button that sends `scope_change`)
> - Diagnostics (4 links to sub-screens)
> - Power (`POWER OFF` button → confirmation modal → `{"type": "power", "action": "off"}`)
> - About (version, model, hardware strings)
> - `FACTORY RESET` button — fires destructive-action modal; if confirmed, send `{"type": "factory_reset"}` — for v1, server may reject this with `error` (factory reset CLI-only); that's acceptable
>
> Section headers: Jost Bold 12px 0.18em UPPER `var(--ink-secondary)`, trailing hairline rule extending right
>
> Settings controls are cosmetic for v1 where backend doesn't exist — sliders and toggles save to `localStorage` but don't drive hardware. Document this limitation in a code comment.
>
> Diagnostics sub-screens (§10.11):
>
> - Hardware health: list of components with Mono status lines
> - Log viewer: `<pre>` element tailing a log stream if backend emits one; else placeholder "Log streaming not yet wired"
> - Temperature history: inline SVG line chart (CPU/Hailo/battery) — if no data, show placeholder
> - Tokens/sec history: inline SVG line chart (Mephisto tokens/sec over last hour) — placeholder when no data
>
> Each sub-screen: back button + Display H1 + 3px rule + content.
>
> **Task E: Demo-mode event sequence.**
>
> `faust/ui/run.py` has a `--demo` flag that scripts an event sequence. **Rewrite the demo sequence** so it exercises the new UI end-to-end:
>
> 1. Wait 1s, send power-on (transition OFF → BOOTING)
> 2. Stream `boot_log` messages (existing sequence is fine)
> 3. Transition to ON
> 4. Wait 2s, send `scope_change` to "Testing my own devices" (tests scope label + scope journal entry)
> 5. Wait 3s, simulate dock (mephisto → connected) → ceremony should fire
> 6. Wait 3s, send a synthetic `planning_started(phase=catalog)` → wait 3s → `planning_started(phase=plan)` → wait 5s → `plan_approval_request`
> 7. Wait for plan approval (demo mode can auto-approve via a timer, or require manual click)
> 8. Stream `parameterizing_step(1,2)` → `tool_call_proposed` → `tool_call_executed` → `parameterizing_step(2,2)` → `confirmation_request` (destructive) → wait for user click → `tool_call_executed` → `final`
> 9. Wait 3s, send `pursuit_start(hmc-demo)` → progress updates → `pursuit_complete` → poster + journal entry
>
> Implement as an async task spawned after server startup when `--demo` flag is set. Use `asyncio.sleep()` for pacing.
>
> **Task F: Final polish.**
>
> 1. Keyboard shortcuts (§13): `Escape` → back/cancel, `Enter` → primary action in context, `Ctrl+D` → toggle `data-mode` for dev
> 2. Context menu disabled on body
> 3. Pinch-zoom disabled via viewport meta
> 4. Hidden scrollbars in all screens except Settings
> 5. `aria-label` on icon-only buttons
> 6. Error toast: when server sends `{type: "error", message: ...}`, show a transient notification (3s) at the top of the screen in `var(--accent-crimson)` Mono
>
> **Tests:**
>
> 1. `test_journal.py`: entry creation, filtering, storage roundtrip
> 2. `test_ui.py`: `journal_query` handler, `journal_update_notes` handler
> 3. All existing tests still green
>
> **Constraints:**
>
> - Do not break any invariant from prior stages
> - `test_ui.py:131` MUST still pass
> - Total test count: ≥ 148
>
> **When done,** report final diff summary, test count, manual verification of a full end-to-end flow (boot → dock → scope change → prompt → plan approval → tool execution → journal view → pursuit run → pursuit complete poster).

**Verify:**

```bash
pytest -q                       # expect ≥ 148 passed
pytest -q faust/tests/test_ui.py::test_prompt_handler_does_not_deadlock_on_approval  # MUST pass
python -m faust.ui.run --demo
```

Full flow in browser:

- [ ] Power on → boot sequence → dashboard
- [ ] Dock → palette swap + ceremony
- [ ] Scope change → top bar updates
- [ ] Send prompt → planning markers → plan-approval modal → parameterizing → tool calls with confirmation modals → final
- [ ] Journal tab shows all entries with correct filters
- [ ] Journal entry detail displays correctly
- [ ] Pursuits tab shows 8 cards
- [ ] Start Pursuit → running screen → completion poster → journal entry
- [ ] Settings scrolls and controls respond
- [ ] Factory reset modal fires (may not succeed backend-side, that's OK)
- [ ] Escape and Enter keyboard shortcuts work
- [ ] Error messages surface as toasts

**Hand-off:** Ship.

---

## Timing + checkpoints

| Stage | Estimated time | Dependency |
|---|---|---|
| 1 — Foundation | 0.5 day | Fonts + boot splash in place |
| 2 — Agent events | 0.5 day | Stage 1 optional |
| 3 — Category remap + state | 0.5 day | Stage 2 |
| 4 — TrustCache + scope | 1 day | Stage 3 |
| 5 — Pursuits | 2 days | Stage 4 |
| 6 — UI scaffolding | 1 day | Stages 1, 2, 3, 4, 5 all must be landed |
| 7 — Boot sequence | 0.5 day | Stage 6 |
| 8 — Dashboard + tool-group | 1 day | Stage 7 |
| 9 — Modals | 1 day | Stage 8 |
| 10 — Mephisto + dock + ceremony | 1.5 days | Stage 9 |
| 11 — Journal + Pursuits UI + Settings + polish | 2 days | Stage 10 |
| **Total** | **~11.5 days of focused work** | ~2.5–3 weeks elapsed |

Misha's calendar target: start of work by the weekend of April 25; dashboard live by May 3; modals by May 7; Mephisto by May 11; polish complete by May 14 to leave a day for final verification before May 15 ship.

---

## What to do if a stage fails

**A backend stage (2–5) breaks existing tests:** fix or revert. Do not advance to UI stages with red tests — UI stages inherit the behavior and compound the bugs.

**A UI stage (6–11) looks wrong but tests pass:** check the spec section carefully. Most visual bugs trace to palette/typography misuse; confirm all colors use CSS variables and all fonts use utility classes.

**`test_ui.py:131` fails:** STOP. This is the deadlock guard. Something is blocking the WS receive loop. Inspect the most recent change for:

- A synchronous call in a WS handler that could block (file I/O, network)
- An `await` that depends on a client reply without being in a background task
- A modification to the background-task spawn pattern in `server.py:232-235`

Revert until green, then re-apply the change in a background task.

**A stage's scope is too big for one session:** split at natural boundaries. Stages 5 and 11 are candidates. Stage 5 can split as (registry + runner) then (7 implementations + tests). Stage 11 can split as (journal) then (pursuits UI) then (settings + polish).

**Specs conflict with reality:** trust the reality. File a note in a TODO comment, flag in commit message, continue. Specs get patched afterward — reality is what ships.

---

## End of document
