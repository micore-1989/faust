# Faust UI — Full Design Specification

**Project:** Faust (AI-native pentesting handheld) — Operator UI
**Device:** Waveshare 8" DSI 1280×800 capacitive touch on Raspberry Pi 5 (1GB)
**Ship target:** May 15, 2026
**Version:** 2.0 (reconciled against `github.com/micore-1989/faust`)
**Status:** Locked. Ready for staged implementation per `faust-build-plan.md`.

---

## 0. Purpose and how to use this document

This document is the source of truth for the Faust operator UI. It is **intended to be handed to Claude Code in combination with `faust-build-plan.md`**, which sequences the implementation into 11 scoped stages. Read this spec for design; read the build plan for execution order.

This version (2.0) has been reconciled against the existing codebase at `github.com/micore-1989/faust`. It corrects earlier assumptions that conflicted with the actual implementation: backend is aiohttp (not FastAPI), transport is WebSocket (not SSE), frontend is vanilla JS (not Alpine/HTMX), and port is 8080 (not 8000). All of these are preserved as load-bearing decisions with documented rationale.

Conventions:

- **`CODE_STYLE`** for hex values, CSS variables, file paths, identifiers.
- **`TBD-palette-exact`** markers flag values pending the pre-build color-picker pass.
- **Acceptance checklists** at the end of each screen section.
- **"Preserved"** call-outs mark existing functionality that the rewrite must retain.

When in doubt, **prefer the simpler solution**. This ships in weeks, not months.

---

## 1. Pre-build tasks

### 1.1 Color-picker pass

The palette in §4 is an eyeball estimate from the boot-splash illustration. Confirm the exact hex values by sampling from `boot-splash.png` with a color picker (macOS Digital Color Meter, browser dev-tools eyedropper, or coolors.co/image-picker).

Sample these six:

- Cream paper border
- Deep navy (darkest sky)
- Mid navy (sky fade)
- Crimson (red sphere, accents)
- Orange-red (scholar's coat)
- Dark red shadow

Update §4.1 before Stage 1 of the build plan runs.

### 1.2 Asset placement

```
faust/ui/static/assets/
├── illustrations/
│   └── boot-splash.png
├── sigils/
│   ├── sigil-wifi-ble.svg
│   ├── sigil-sub-ghz.svg
│   ├── sigil-nfc.svg
│   ├── sigil-lf-rfid.svg
│   ├── sigil-ir.svg
│   ├── sigil-vision.svg
│   └── sigil-meta.svg
└── fonts/
    ├── Jost-Regular.woff2
    ├── Jost-Medium.woff2
    ├── Jost-Bold.woff2
    ├── Jost-Black.woff2
    ├── JetBrainsMono-Regular.woff2
    └── JetBrainsMono-Medium.woff2
```

Fonts: download from Google Fonts as TTF, convert to WOFF2 via transfonter.org. Subset to Latin-1 + Germanic glyphs (ä, ö, ü, ß) + em-dash, middle-dot, ellipsis. Sigil SVGs are generated from `faust-sigil-spec.md` §2 during Stage 1.

### 1.3 Spec + build plan in repo

Commit three files to repo root:

```
faust/
├── faust-ui-spec.md
├── faust-sigil-spec.md
├── faust-build-plan.md
└── (rest of repo)
```

---

## 2. Technology stack & architecture

This section was rewritten in v2.0 to reflect the actual stack. What follows is the real architecture — preserved, not proposed.

### 2.1 Stack (locked, preserved)

- **Backend:** Python 3.11+ with **aiohttp** (not FastAPI). Entry: `faust/ui/server.py`. Event fan-out via `faust/ui/bridge.py`.
- **Frontend:** **Vanilla HTML/CSS/JavaScript** in an IIFE. No build toolchain, no framework. All view state in JS module-level variables.
- **Rendering:** Chromium in kiosk mode at `http://localhost:8080`.
- **Realtime transport:** a **single WebSocket** at `/ws`. All events (server → client) and all actions requiring an agent reply (client → server) travel over this channel.

### 2.2 Why WebSocket, not SSE

The server's `UIConfirmation` and `UIPlanApprover` contracts (`run.py:43`, `run.py:75`) are async callbacks that block on `_confirmation_queue` and `_plan_approval_queue` until the client replies. SSE is server-to-client only; replacing WebSocket would require a paired REST POST for replies or keeping WebSocket for the reply path anyway. Both options are worse.

`test_ui.py:131` (`test_prompt_handler_does_not_deadlock_on_approval`) guards an April 2026 deadlock bug that depended on this pattern. **Do not change transport.**

### 2.3 Kiosk invocation

```bash
chromium-browser \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --no-first-run \
  --disable-features=TranslateUI \
  --disable-dev-shm-usage \
  --memory-pressure-off \
  --app=http://localhost:8080
```

### 2.4 WebSocket message protocol

All messages are JSON objects with a `"type"` field.

#### Client → server

| type | payload | notes |
|---|---|---|
| `power` | `{action: "on"\|"off"}` | Triggers boot or shutdown |
| `mephisto` | `{action: "connect"\|"disconnect"}` | No-op if power off |
| `prompt` | `{text: str}` | Requires power=on AND mephisto=connected; background task |
| `dispatch` | `{skill: str, args: {…}}` | Requires power=on; direct dispatch; background task |
| `confirmation` | `{call_id: str, approved: bool}` | Answers `confirmation_request` |
| `plan_approval` | `{plan_id: str, approved: bool}` | Answers `plan_approval_request` |
| `scope_change` | `{template: "recon"\|"self-test"\|"pentesting", description: str\|null}` | **New v2.0.** Sets scope. |
| `pursuit_start` | `{pursuit_id: str, params: {…}}` | **New v2.0.** |
| `pursuit_stop` | `{pursuit_id: str}` | **New v2.0.** |
| `journal_query` | `{filters: {…}}` | **New v2.0.** Request filtered entries. |

#### Server → client

| type | payload | source |
|---|---|---|
| `state` | `SimulatorState.to_dict()` | On connect and every transition |
| `boot_log` | `{line: str}` | One per streamed line |
| `skills` | `{skills: [...]}` | Once on power-on, on reconnect |
| `thinking` | `{text: str, is_delta: bool}` | Legacy single-pass only |
| `planning_started` | `{phase: "catalog"\|"plan"\|"replan", step?: int, of?: int}` | **New v2.0.** Two-pass phase marker |
| `parameterizing_step` | `{step: int, of: int, skill: str, intent: str}` | **New v2.0.** |
| `plan_proposed` | `{plan_id, reasoning, steps, safety_notes}` | From `PlanProposed` |
| `tool_call_proposed` | `{call_id, tool_name, arguments, sensitivity}` | |
| `tool_call_executed` | `{call_id, tool_name, result, error, duration_ms}` | |
| `final` | `{reason, text, error}` | |
| `confirmation_request` | `{call_id, tool_name, arguments, sensitivity}` | Expects reply |
| `plan_approval_request` | `{plan_id, reasoning, steps, safety_notes}` | Expects reply |
| `pursuit_progress` | `{pursuit_id, progress, elapsed_s, eta_s}` | **New v2.0.** |
| `pursuit_activity` | `{pursuit_id, line}` | **New v2.0.** |
| `pursuit_complete` | `{pursuit_id, summary, journal_entry_id}` | **New v2.0.** |
| `journal_entries` | `{entries, filters}` | **New v2.0.** Reply to query |
| `error` | `{message}` | Guard rejections |

### 2.5 Background-task dispatch (preserved invariant)

`prompt` and `dispatch` handlers spawn background tasks (`server.py:232-235`) so the receive loop can service `confirmation` and `plan_approval` replies. **Any new handler that could block on an agent callback must follow this pattern.** Guarded by `test_ui.py:131`.

### 2.6 Reconnect behavior (preserved)

On reconnect (`server.py:205-208`), server re-sends:

1. Current `state` message
2. Full `skills` catalog (if powered on)

The client rebuilds view state from these messages. The rewrite preserves this — no separate re-sync protocol.

### 2.7 Page architecture

Single-page app. One `index.html`, one `style.css`, one `app.js` (plus assets). All screens render into `<main id="app">`. Routing via a client-side **view stack** (`viewStack` variable in `app.js`), preserved from existing implementation:

- `pushView(name, params)` — push and render
- `goBack()` — pop and render previous
- Drilled-in screens include a back button wired to `goBack()`

Not URL-based. Kiosk has no address bar.

### 2.8 Power state machine (preserved)

Server-authoritative state at `faust/ui/state.py`: `OFF → BOOTING → ON → BOOTING → OFF` (no direct OFF → ON; always goes through BOOTING). The UI must:

- Show a power-on affordance when OFF
- Show boot sequence (§10.1) when BOOTING
- Show dashboard when ON
- Offer a power-off control (footer in existing UI; preserved in Settings or a long-press gesture)

Power-off uses `window.confirm` equivalent or a confirmation modal before sending `power: off`.

### 2.9 Demo mode (preserved)

The `--demo` flag (`run.py:281`) auto-powers on and pushes a synthetic event sequence so the UI can be developed without agent hardware. The rewrite requires a **new demo event sequence** covering:

- Power-on + boot-log streaming
- Mephisto connect
- A `planning_started` → `plan_proposed` → approval → `parameterizing_step` × N → `tool_call_proposed` → `confirmation_request` → `tool_call_executed` → `final` flow
- Scope change
- Optional Pursuit start + progress + complete

Implementation detail for Stage 11. Flag here so it is not forgotten.

---

## 3. Runtime modes

### 3.1 Scholar (undocked)

No Mephisto, no LLM. Operator drives manually via:

- Radio-status tiles → tool-group screens → tool invocation
- Pursuits tab → Pursuit start
- Journal tab → review
- Settings tab → configuration

Full toolset available. Destructive tools fire the confirmation modal. No plan-approval flow — there is no agent to plan.

Visual register: **navy palette, restrained.**

### 3.2 Pact (docked)

Mephisto attached via USB-C + magnets. Two-pass agent running. Operator can:

- Everything scholar offers
- Converse with Mephisto (§10.7 — conversation screen)
- Mephisto plans tool sequences → operator approves the plan (§10.9 — plan-approval modal)
- Mephisto invokes tools; destructive ones still require per-action confirmation (§10.8)

Visual register: **oxblood palette, crimson-magenta accents, active.**

### 3.3 Mode attribute

`<body data-mode="scholar">` or `<body data-mode="pact">`. All mode-dependent styling keys off this.

**Preserved note:** the existing implementation uses `body.mephisto-on` as a boolean. The rewrite replaces with `data-mode="pact"`, semantically equivalent but makes scholar explicit. Update CSS accordingly.

### 3.4 Dock transition

Detected via existing `mephisto` WS message:

- **On dock:** palette swaps scholar → pact over 1000ms. First dock per boot triggers ceremony (§10.13). Subsequent docks in same boot: silent palette swap.
- **On undock:** palette swaps pact → scholar over 1000ms. No ceremony.

---

## 4. Palette

### 4.1 Full tokens

```css
:root {
  /* Scholar backgrounds — desaturated plum/near-black from illustration */
  --scholar-bg-primary:    #3E2E46;
  --scholar-bg-secondary:  #2B1F32;
  --scholar-bg-deep:       #211728;
  --scholar-tile-border:   #5A4665;
  --scholar-dot-idle:      #5A4665;

  /* Pact backgrounds — deepest red-black from illustration */
  --pact-bg-primary:       #420203;
  --pact-bg-secondary:     #2D0102;
  --pact-bg-deep:          #1A0001;
  --pact-tile-border:      #6B1018;
  --pact-dot-idle:         #6B1018;

  /* Shared ink — cream/off-white (not from picker; chosen for legibility on both dark bases) */
  --ink-primary:           #E8DCC0;
  --ink-secondary:         #BCAE92;
  --ink-tertiary:          #857A66;
  --ink-quiet:             #5F574A;

  /* Shared semantic accents — two reds from illustration, rest stylistic */
  --accent-crimson:        #A20C28;  /* destructive — alchemical red from illustration */
  --accent-active:         #931319;  /* live indicator — deeper orange-red from illustration */
  --accent-mephisto:       #D83A7A;  /* Mephisto voice (pact only) — magenta, preserved */
  --accent-thinking:       #8F5FE0;  /* processing state — violet, preserved */
  --accent-scope:          #E5A500;  /* scope label — amber, preserved */
  --accent-success:        #4DC0B5;  /* completed — teal, preserved */
  --accent-scholar:        #8A6FA0;  /* scholar accent — muted purple, harmonizes with plum base */

  /* Mode-switched aliases (used by components) */
  --bg-primary:            var(--scholar-bg-primary);
  --bg-secondary:          var(--scholar-bg-secondary);
  --bg-deep:               var(--scholar-bg-deep);
  --tile-border:           var(--scholar-tile-border);
  --dot-idle:              var(--scholar-dot-idle);
}

body[data-mode="pact"] {
  --bg-primary:            var(--pact-bg-primary);
  --bg-secondary:          var(--pact-bg-secondary);
  --bg-deep:               var(--pact-bg-deep);
  --tile-border:           var(--pact-tile-border);
  --dot-idle:              var(--pact-dot-idle);
}
```

> **`TBD-palette-exact`** — update after color-picker pass.

### 4.2 Rules

- Every color uses a `--*` alias or semantic accent. No raw hex in component CSS.
- No color keywords.
- Semantic accents are mode-independent.

### 4.3 Transition

1000ms `ease-in-out` on `background-color`, `border-color`, `color`. See §12.

---

## 5. Typography

### 5.1 Typefaces

- **Jost** — sans-serif display and UI. Weights: 400, 500, 700, 900.
- **JetBrains Mono** — monospace for data, tool output, code, labels where letterspacing consistency matters. Weights: 400, 500.

No other typefaces. No italics anywhere.

### 5.2 Font-face declarations

```css
@font-face { font-family: 'Jost'; src: url('/assets/fonts/Jost-Regular.woff2') format('woff2'); font-weight: 400; font-style: normal; font-display: swap; }
@font-face { font-family: 'Jost'; src: url('/assets/fonts/Jost-Medium.woff2') format('woff2'); font-weight: 500; font-style: normal; font-display: swap; }
@font-face { font-family: 'Jost'; src: url('/assets/fonts/Jost-Bold.woff2') format('woff2'); font-weight: 700; font-style: normal; font-display: swap; }
@font-face { font-family: 'Jost'; src: url('/assets/fonts/Jost-Black.woff2') format('woff2'); font-weight: 900; font-style: normal; font-display: swap; }
@font-face { font-family: 'JetBrains Mono'; src: url('/assets/fonts/JetBrainsMono-Regular.woff2') format('woff2'); font-weight: 400; font-style: normal; font-display: swap; }
@font-face { font-family: 'JetBrains Mono'; src: url('/assets/fonts/JetBrainsMono-Medium.woff2') format('woff2'); font-weight: 500; font-style: normal; font-display: swap; }
```

### 5.3 Type hierarchy

| Role | Family | Weight | Size | Letter-spacing | Case | Usage |
|---|---|---|---|---|---|---|
| Wordmark XL | Jost | 900 | 96px | -0.02em | UPPER | Boot splash (FAUST) |
| Wordmark L | Jost | 900 | 56px | -0.02em | UPPER | Top-bar FAUST; pact ceremony MEPHISTO |
| Wordmark M | Jost | 900 | 36px | -0.02em | UPPER | Mephisto conversation header |
| Wordmark S | Jost | 900 | 18px | 0.16em | UPPER | Top-bar device label |
| Display H1 | Jost | 700 | 28px | -0.005em | mixed | Section titles |
| Display H2 | Jost | 700 | 22px | -0.005em | mixed | Modal headers |
| Display H3 | Jost | 700 | 18px | -0.005em | mixed | Tile section labels |
| Body Large | Jost | 400 | 16px | 0em | mixed | Pursuit descriptions |
| Body | Jost | 400 | 14px | 0em | mixed | Modal prose, Mephisto messages |
| Body Medium | Jost | 500 | 14px | 0em | mixed | Emphasis within body |
| Meta Label | Jost | 500 | 12px | 0.14em | UPPER | Tile labels, inline meta |
| Button | Jost | 700 | 13px | 0.22em | UPPER | Modal and primary buttons |
| Tab Label | Jost | 700 | 11px | 0.14em | UPPER | Bottom tab labels |
| Mono L | JBM | 400 | 14px | 0em | mixed | Code blocks, tool calls |
| Mono | JBM | 400 | 12px | 0em | mixed | Tool output, journal data |
| Mono S | JBM | 400 | 11px | 0em | mixed | Tile status text |
| Mono XS | JBM | 400 | 10px | 0.12em | UPPER | Top-bar state strip, timestamps |
| Mono Medium | JBM | 500 | 12px | 0em | mixed | Emphasis in mono |

**Line-heights:** body 1.5, mono 1.6, display/wordmark 1.

### 5.4 Utility classes

```css
.type-wordmark-xl { font: 900 96px/1 'Jost'; letter-spacing: -0.02em; text-transform: uppercase; }
.type-wordmark-l  { font: 900 56px/1 'Jost'; letter-spacing: -0.02em; text-transform: uppercase; }
.type-wordmark-m  { font: 900 36px/1 'Jost'; letter-spacing: -0.02em; text-transform: uppercase; }
.type-wordmark-s  { font: 900 18px/1 'Jost'; letter-spacing:  0.16em; text-transform: uppercase; }

.type-h1 { font: 700 28px/1.1 'Jost';  letter-spacing: -0.005em; }
.type-h2 { font: 700 22px/1.15 'Jost'; letter-spacing: -0.005em; }
.type-h3 { font: 700 18px/1.2 'Jost';  letter-spacing: -0.005em; }

.type-body-l      { font: 400 16px/1.5 'Jost'; }
.type-body        { font: 400 14px/1.5 'Jost'; }
.type-body-medium { font: 500 14px/1.5 'Jost'; }

.type-meta-label { font: 500 12px/1.4 'Jost'; letter-spacing: 0.14em; text-transform: uppercase; }
.type-button     { font: 700 13px/1.4 'Jost'; letter-spacing: 0.22em; text-transform: uppercase; }
.type-tab-label  { font: 700 11px/1.4 'Jost'; letter-spacing: 0.14em; text-transform: uppercase; }

.type-mono-l      { font: 400 14px/1.6 'JetBrains Mono'; }
.type-mono        { font: 400 12px/1.6 'JetBrains Mono'; }
.type-mono-s      { font: 400 11px/1.55 'JetBrains Mono'; }
.type-mono-xs     { font: 400 10px/1.4 'JetBrains Mono'; letter-spacing: 0.12em; text-transform: uppercase; }
.type-mono-medium { font: 500 12px/1.6 'JetBrains Mono'; }
```

### 5.5 Color-by-role defaults

Unless specified, text inherits from context. Defaults:

- Body → `var(--ink-primary)`
- Meta labels → `var(--ink-secondary)`
- Timestamps / tertiary → `var(--ink-tertiary)`
- Disabled / quiet → `var(--ink-quiet)`
- Mephisto voice → `var(--accent-mephisto)`
- Tool call / destructive → `var(--accent-crimson)`
- Thinking / processing → `var(--accent-thinking)`
- Success / confirmed → `var(--accent-success)`
- Scope labels → `var(--accent-scope)`

---

## 6. Layout grid & spacing

### 6.1 Screen

1280 × 800, landscape, physical pixels. Viewport set identically:

```html
<meta name="viewport" content="width=1280, height=800, initial-scale=1, user-scalable=no">
```

No responsive design. One screen.

### 6.2 Regions

Every screen uses three vertical regions:

```
┌─────────────────────────────────────────────────┐  Top bar: 64px
├─────────────────────────────────────────────────┤
│                                                 │
│         MAIN CONTENT (flexes per screen)        │  Middle: 648px
│                                                 │
├─────────────────────────────────────────────────┤
│         BOTTOM TAB BAR                          │  Bottom: 88px
└─────────────────────────────────────────────────┘
```

Total: 64 + 648 + 88 = 800px.

### 6.3 Horizontal

- Full width: 1280px
- Content padding: 24px left/right
- Max content width: 1232px

Modals ignore this padding and center in viewport.

### 6.4 Spacing scale

```css
:root {
  --space-1:  4px;
  --space-2:  8px;
  --space-3:  12px;
  --space-4:  16px;  /* default gap between related elements */
  --space-5:  24px;  /* default between sections */
  --space-6:  32px;
  --space-7:  48px;
  --space-8:  64px;
}
```

Do not use values outside this scale.

### 6.5 Borders & radii

- **Borders: 0.5px unless specified otherwise** (Constructivist hairline).
- **Heavy rules: 3px.** Used for section accents, modal headers, rule dividers.
- **Radius: 0 everywhere.** Sharp corners on every component, including status dots (which are hard squares, not circles).

Only rounded shapes: the sigils themselves, which contain semantic circles (broadcast arcs, lens, etc.).

---

## 7. Components

### 7.1 Top bar

64px tall, every screen (except boot).

Layout — horizontal flex, split-justified:

```
┌─── Left ───┬───── Center ─────┬──── Right ────┐
│ FAUST MODE │   SCOPE LABEL    │  BAT · 14:22  │
└────────────┴──────────────────┴───────────────┘
```

**Left section** — device identity + mode strip:

Two adjacent blocks:

1. **FAUST block** — 88px × 40px. Background `var(--ink-primary)`, text `var(--bg-primary)`. Jost Black 16px letter-spacing 0.16em UPPER, centered.
2. **Mode block** — 104px × 40px, butted against FAUST. Background `var(--accent-scholar)` in scholar or `var(--accent-crimson)` in pact. Text `var(--ink-primary)`, Jost Black 16px letter-spacing 0.18em UPPER. Content: `SCHOLAR` or `PACT`.

**Center section** — scope label:

Tappable button → opens scope-change modal (§10.10).

- Jost Medium 14px letter-spacing 0.08em
- Color `var(--accent-scope)` when scope set, `var(--ink-tertiary)` when unset
- Displayed text: scope template name (`STRICTLY RECON`, `TESTING MY OWN DEVICES`) or for pentesting `PENTESTING · <description>` truncated as needed
- Unset: `NO SCOPE · TAP TO SET`
- Tap feedback: background tint `var(--bg-secondary)` for 100ms

**Right section** — battery + clock + dock indicator:

Right-aligned Mono XS strip, color `var(--ink-secondary)`. Middle-dot separators:

```
BAT 82% · 14:22
BAT 82% · 14:22 · MEPHISTO    (pact mode)
```

**CSS:**

```css
.top-bar {
  height: 64px;
  background: var(--bg-primary);
  border-bottom: 0.5px solid var(--tile-border);
  padding: 0 var(--space-5);
  display: flex; align-items: center; justify-content: space-between;
}
```

### 7.2 Bottom tab bar

88px tall, four equal columns via `grid-template-columns: repeat(4, 1fr)`.

Four tabs: **Dashboard**, **Pursuits**, **Journal**, **Settings**.

Each:

```
┌────────────────┐
│   [icon 24px]  │   ← 20px from top
│                │
│   DASHBOARD    │   ← 12px below icon
└────────────────┘
```

- Icons: Phosphor regular, 24×24
  - Dashboard → `ph-house`
  - Pursuits → `ph-target`
  - Journal → `ph-book`
  - Settings → `ph-gear`
- Label: Tab Label type (Jost Bold 11px 0.14em UPPER)
- Default color: `var(--ink-tertiary)`
- Active tab: color `var(--ink-primary)` + 3px crimson bottom bar full-width
- Touch-press: background `var(--bg-secondary)` for 100ms

Top border: `0.5px solid var(--tile-border)`.

### 7.3 Button

**Primary (filled):**

```css
.btn-primary {
  font: 700 13px/1.4 'Jost';
  letter-spacing: 0.22em; text-transform: uppercase;
  padding: 16px 24px;
  background: var(--accent-crimson);
  color: var(--ink-primary);
  border: none; cursor: pointer;
}
.btn-primary:active { background: #8B0F20; }
```

**Secondary (ghost):**

```css
.btn-secondary {
  font: 700 13px/1.4 'Jost';
  letter-spacing: 0.22em; text-transform: uppercase;
  padding: 16px 24px;
  background: transparent;
  color: var(--ink-secondary);
  border: 0.5px solid var(--ink-secondary);
  cursor: pointer;
}
.btn-secondary:active { background: var(--bg-secondary); }
```

No radius. No hover transitions. No loading states on the button itself — destination screen shows loading.

### 7.4 Panel / tile

```css
.panel {
  background: var(--bg-secondary);
  border: 0.5px solid var(--tile-border);
  padding: var(--space-4);
}
```

### 7.5 Status dot

8×8 hard square, not a circle:

```css
.dot {
  display: inline-block;
  width: 8px; height: 8px;
  margin-right: 6px;
  vertical-align: 1px;
}
.dot--active { background: var(--accent-active); }
.dot--idle   { background: var(--dot-idle); }
.dot--error  { background: var(--accent-crimson); }
```

**Never animate the dot.** State changes are instant.

### 7.6 Radio-status tile

Canonical spec in `faust-sigil-spec.md`. Summary:

- 48×48 sigil centered in upper region
- Jost Bold 11px UPPER label below
- Two-line Mono S status block below label
- States: idle, active, disabled, error
- Mode-reactive via palette aliases

### 7.7 Heavy rule

```css
.rule-heavy          { height: 3px; background: var(--accent-crimson); }
.rule-heavy-scholar  { height: 3px; background: var(--accent-scholar); }
.rule-heavy-scope    { height: 3px; background: var(--accent-scope); }
```

Widths: 32, 48, 72, 80, 120, or full-width. Use sparingly — one per screen region.

### 7.8 Hairline

```css
.rule-hair { height: 0.5px; background: var(--tile-border); }
```

### 7.9 Mono code block

```css
.mono-block {
  background: var(--bg-deep);
  color: var(--accent-active);
  font: 400 12px/1.6 'JetBrains Mono';
  padding: 12px 16px;
  border-left: 3px solid var(--accent-active);
  word-break: break-all;
  margin: var(--space-3) 0;
}
.mono-block--neutral {
  color: var(--ink-primary);
  border-left-color: var(--ink-secondary);
}
.mono-block--destructive {
  color: var(--accent-crimson);
  border-left-color: var(--accent-crimson);
}
```

### 7.10 Modal

```css
.modal-backdrop {
  position: fixed; inset: 0;
  background: rgba(6, 14, 34, 0.7);  /* scholar */
  display: flex; align-items: center; justify-content: center;
  z-index: 100;
}
body[data-mode="pact"] .modal-backdrop {
  background: rgba(26, 8, 6, 0.7);  /* pact */
}
.modal {
  background: var(--bg-secondary);
  border: 1px solid var(--accent-crimson);
  width: 60%; max-width: 640px;
}
.modal__header {
  background: var(--accent-crimson);
  color: var(--ink-primary);
  padding: 14px 24px;
  font: 900 22px/1 'Jost';
  letter-spacing: 0.02em; text-transform: uppercase;
}
.modal__body   { padding: 24px; }
.modal__buttons {
  display: flex; border-top: 0.5px solid var(--tile-border);
}
.modal__buttons > button {
  flex: 1; border: none; padding: 18px 24px;
  font: 700 13px/1.4 'Jost';
  letter-spacing: 0.22em; text-transform: uppercase;
  cursor: pointer; background: transparent;
}
```

Destructive modal detail: §10.8. Plan-approval modal detail: §10.9.

### 7.11 Sensitivity pill (preserved)

The existing UI surfaces sensitivity as a colored pill on category and skill header rows (`app.js:352, 370`). **Preserved in the rewrite.** Pill design:

```css
.sensitivity-pill {
  display: inline-block;
  padding: 2px 8px;
  font: 500 10px/1.4 'JetBrains Mono';
  letter-spacing: 0.12em; text-transform: uppercase;
  margin-left: var(--space-2);
}
.sensitivity-pill--passive     { background: var(--ink-quiet);      color: var(--bg-primary); }
.sensitivity-pill--active      { background: var(--accent-active);  color: var(--ink-primary); }
.sensitivity-pill--disruptive  { background: var(--accent-crimson); color: var(--ink-primary); }
```

`disruptive` is the same tier as the spec's "destructive" — the codebase uses three classes: `passive`, `active`, `disruptive` (see `disclosure.py:45-51`). The spec's §10.8 "destructive-action modal" fires for both `active` and `disruptive`.

### 7.12 Body.active breathing-glow hook (preserved)

The existing UI sets `body.active` during any in-flight operation (`app.js:470, 593`) and uses it to drive ambient glow intensity. **Preserved.** Add to new CSS:

```css
body.active {
  /* optional glow effect — leave empty or add subtle box-shadow on panels */
}
```

Set by JS on: prompt send, dispatch, pursuit start. Cleared on: `final`, `tool_call_executed` terminal, pursuit complete, error.

---

---

## 10. Screens

### 10.0 OFF state (power-off screen) `[PRESERVED]`

Entered on initial load (`SimulatorState.power === "off"`) or after operator powers off from Settings.

**Layout:** no top bar, no tab bar. Centered content, full viewport. Background `var(--scholar-bg-primary)`.

```
┌───────────────────────────────────────────────────────────┐
│                                                           │
│                                                           │
│                                                           │
│                          FAUST                            │   ← Wordmark XL, ink-quiet
│                                                           │
│                                                           │
│                      [POWER ON]                           │   ← Primary button, centered
│                                                           │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

- FAUST wordmark: Jost Black 96px, `var(--ink-quiet)` (dimmed to signal dormancy), centered.
- Power-on button: Primary style, 240px wide, centered 80px below wordmark.
- On tap: client sends `{type: "power", action: "on"}`. Server responds by entering BOOTING state and starting the boot_log stream.

**Acceptance:**
- [ ] Shown on first load.
- [ ] Only interactive element is the Power-on button.
- [ ] Tap transitions to boot screen (section 10.1).

### 10.1 Boot sequence `[CHANGED]`

Entered when operator taps Power-on. `SimulatorState.power === "booting"`. Server streams `boot_log` messages at ~200–400ms intervals per `state.py:68-104`.

**Total duration:** ~6–7s at default simulator speed. This is preserved from the existing implementation — earlier v1.0 claim of "4.5–5s" was aspirational.

**Layout:**

```
┌───────────────────────────────────────────────────────────┐
│                                                           │
│              [boot-splash.png — 480×640]                  │
│                     centered                              │
│                                                           │
│                      FAUST                                │  ← Wordmark XL, ink-primary
│                                                           │
│        Grau, teurer Freund, ist alle Theorie.             │  ← Goethe line, accent-scope
│        GREY, DEAR FRIEND, IS ALL THEORY                   │  ← Translation, ink-tertiary
│                                                           │
│        [ ok ] kernel loaded (linux 6.6.x)                 │  ← mono log, appended live
│        [ ok ] display detected (waveshare 8" dsi rev 2.2) │
│        ...                                                │
└───────────────────────────────────────────────────────────┘
```

- **Background:** `var(--scholar-bg-primary)`.
- **Illustration:** `width: 480px; height: auto;` centered horizontally, 40px from top.
- **FAUST wordmark:** Jost Black 96px, `var(--ink-primary)`, centered, 40px below illustration.
- **Goethe line + translation:** centered, pool of four per §10.1.1 below; random selection per boot (server decides; UI may receive via `state.goethe_quote` field or render client-side).
- **Hardware self-check log:** `boot_log` messages append to a `<pre>` element, Mono Default 12px. `[ ok ]` prefix colored `var(--accent-success)`; line content in `var(--ink-secondary)`. Failure lines: `[fail]` in `var(--accent-crimson)`, line content in `var(--ink-primary)`.

**Transition:** On final boot_log line (or on `state.power === "on"` transition), crossfade (500ms) to the dashboard. **Preserve** the existing `playBootCompleteThenHome()` animation from app.js:251-274, adapted to the new palette and typography.

#### 10.1.1 Goethe quote pool

```javascript
const GOETHE_LINES = [
  { de: "Grau, teurer Freund, ist alle Theorie.",
    en: "GREY, DEAR FRIEND, IS ALL THEORY" },
  { de: "Zwei Seelen wohnen, ach! in meiner Brust.",
    en: "TWO SOULS DWELL, ALAS, IN MY BREAST" },
  { de: "Der Worte sind genug gewechselt, laßt mich auch endlich Taten sehn!",
    en: "ENOUGH WORDS HAVE BEEN EXCHANGED; NOW LET ME SEE DEEDS" },
  { de: "Das Werdende, das ewig wirkt und lebt.",
    en: "THE BECOMING, THAT FOREVER ACTS AND LIVES" },
];
```

Random per boot, no repeat of immediately-previous line.

**Acceptance:**
- [ ] Illustration loads and displays.
- [ ] FAUST wordmark renders below.
- [ ] Random Goethe line + translation shown.
- [ ] Hardware self-check log streams via `boot_log` messages.
- [ ] `[ ok ]` colored green-teal, `[fail]` crimson.
- [ ] Crossfade to dashboard on boot complete.

### 10.2 Dashboard (scholar mode)

Landing screen after boot. `SimulatorState.power === "on"` and `mephisto_connected === false`.

**Layout:**

```
┌─────────────────────────────────────────────────────────────┐
│ FAUST [SCHOLAR]     NO SCOPE · TAP TO SET    BAT 82% 14:22  │   ← top bar
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ ┌──────┬──────┬──────┬──────┬──────┬──────┬──────┐          │
│ │ WiFi │ Sub- │ NFC  │ LF   │ IR   │ Vis- │ Jour │          │   ← 7 radio tiles
│ │ BLE  │ GHz  │      │ RFID │      │ ion  │ nal  │          │
│ └──────┴──────┴──────┴──────┴──────┴──────┴──────┘          │
│                                                             │
│ ┌─────────────────────────┐                                 │
│ │   MEPHISTO (dim)        │   Session started 13:45         │   ← mephisto tile
│ │   AWAITING DOCK         │   Tools invoked: 12             │     (undocked/dim)
│ │                         │   Journal entries: 4            │   + session status
│ │                         │   Current scope: NO SCOPE       │
│ └─────────────────────────┘                                 │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ [tab bar]                                                   │
└─────────────────────────────────────────────────────────────┘
```

**Radio-status strip:** 7 tiles, equal width, 4px gap. Each ~172px wide. Content per `faust-sigil-spec.md` §4.

- Idle: `dot--idle` + `hardware ready` or similar meta.
- Active: `dot--active` + live data (`3 networks visible`).
- Disabled: `dot--idle` + `disabled` meta text, reduced opacity.
- Error: `dot--error` + error message.

Tiles are live — updates via `state` messages. Tapping a tile navigates to the tool-group screen (§10.3).

**Mephisto tile (double-width, lower-left) — scholar mode:**
- Size: ~348×200.
- Background: `var(--bg-secondary)` at 60% opacity.
- Border: `0.5px dashed var(--tile-border)`.
- Content: `MEPHISTO` in Jost Black 24px letter-spacing 0.08em UPPER, color `var(--ink-quiet)`. Below: `AWAITING DOCK` in Mono XS.
- Not clickable. `cursor: default`.

**Session status (right of Mephisto tile, scholar only):**
- Mono Default, color `var(--ink-secondary)`.
- Content: session start time, tool invocation count, journal entry count, current scope.
- Values populated from `state.session` fields.

**Acceptance:**
- [ ] 7 radio tiles with sigils, labels, dots, status.
- [ ] Mephisto tile dim, not clickable in scholar mode.
- [ ] Session status displayed to the right.

### 10.2.1 Dashboard (pact mode)

Same layout. `body[data-mode="pact"]` toggles palette. Two differences:

**Mephisto tile (docked):**
- Background: `var(--bg-secondary)` full opacity.
- Border: `0.5px solid var(--accent-crimson)`.
- Content: `MEPHISTO` in Jost Black 24px, color `var(--accent-mephisto)`. Below: `ONLINE · QWEN2.5-VL-3B · 8.4 T/S` in Mono XS. Below that: 3px crimson rule, 48px wide.
- Clickable. Tap navigates to Mephisto conversation screen (§10.6).
- Glow applied when `body.active` (see §7.12).

**Mephisto activity preview (replaces session status in pact):**

```
MEPHISTO                                    → TAP TO OPEN
─────────
3 networks in scope. Ready to deauth home-lab-ap?
```

- Header: `MEPHISTO` in Meta Label, `var(--accent-mephisto)`. Right: `→ TAP TO OPEN` in Mono XS, `var(--ink-tertiary)`.
- 3px crimson rule.
- Most recent Mephisto utterance: Body Default, `var(--accent-mephisto)`, max 2 lines (truncate with ellipsis).
- Tapping navigates to Mephisto conversation.

**Acceptance:**
- [ ] `data-mode="pact"` switches palette globally.
- [ ] Mephisto tile active, clickable.
- [ ] Activity preview updates within 1s of new utterances.

### 10.3 Tool-group screen `[CHANGED]`

Entered by tapping a radio tile. Shows the tools for that group and recent activity for it.

This screen integrates with the **existing direct-dispatch flow** — the dynamic parameter-form generation at app.js:386-437 and SMART_DEFAULTS injection at app.js:28-44 are preserved as-is.

**Layout:**

```
┌─────────────────────────────────────────────────────────────┐
│ [top bar]                                                   │
├─────────────────────────────────────────────────────────────┤
│ [← back]                                                    │
│                                                             │
│ [sigil 24px]  WIFI · BLE                                    │   ← Display H1
│ ─────                                                       │
│                                                             │
│ Available tools                                             │   ← Display H3
│ ┌────────────────┬────────────────┬────────────────┐        │
│ │ Scan           │ Capture PMKID  │ Deauth client  │        │   ← tool cards
│ │ passive        │ active         │ disruptive     │        │
│ │                │                │  [crimson]     │        │
│ └────────────────┴────────────────┴────────────────┘        │
│                                                             │
│ Recent activity                                             │
│ 14:19  wifi.scan       3 networks visible                   │   ← mono list
│ 14:05  wifi.deauth     5 frames · home-lab-ap               │
│ ...                                                         │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ [tab bar]                                                   │
└─────────────────────────────────────────────────────────────┘
```

**Tool card:**

```html
<button class="tool-card" data-tool-id="wifi.scan">
  <div class="tool-card__name">SCAN</div>
  <span class="sensitivity-pill sensitivity-pill--passive">PASSIVE</span>
  <div class="tool-card__desc">Passive scan of nearby networks</div>
</button>
```

```css
.tool-card {
  padding: 20px; background: var(--bg-secondary);
  border: 0.5px solid var(--tile-border); text-align: left; cursor: pointer;
}
.tool-card:active { background: var(--bg-deep); }
.tool-card--disruptive { border-color: var(--accent-crimson); }
.tool-card--disruptive .tool-card__name { color: var(--accent-crimson); }
.tool-card__name { font-family: 'Jost'; font-weight: 700; font-size: 18px; letter-spacing: 0.02em; text-transform: uppercase; margin-bottom: 8px; }
.tool-card__desc { font-family: 'Jost'; font-weight: 400; font-size: 14px; color: var(--ink-secondary); margin-top: 12px; }
```

**Tap flow — preserved from existing dispatch path:**

1. Tap tool card.
2. If the tool's `parameters_schema` has required parameters: open a parameter-form overlay (preserved from app.js:386-437). SMART_DEFAULTS pre-fill common fields (interface=wlan0, duration_s=10, etc.). Operator fills or accepts defaults, taps INVOKE.
3. Client sends `{type: "dispatch", skill: "<tool_id>", args: <filled-params>}`.
4. Server emits `tool_call_proposed` → Approver runs → if sensitivity active/disruptive, emits `confirmation_request` → destructive-action modal fires (§10.8) → operator approves or aborts → Dispatcher runs tool → `tool_call_executed`.
5. UI displays result inline on the tool-group screen (preserved result rendering from app.js:475-493).

**Recent activity:** list of last 10 journal entries for this tool group. Server responds to `journal_query` with `tool_group` filter. Mono Small rows. Destructive entries highlight the tool name in `var(--accent-crimson)`.

**Acceptance:**
- [ ] Back button returns to dashboard via `viewStack.pop()` (preserved).
- [ ] Tool cards render with sensitivity pill.
- [ ] Disruptive cards have crimson border.
- [ ] Parameter form appears for tools with required params.
- [ ] Recent activity list populates.

### 10.4 Pursuits tab `[NEW — FULL SCOPE]`

Grid of launchable Pursuit templates. Full subsystem: registry, runner, storage.

#### 10.4.1 Pursuit list

```
┌─────────────────────────────────────────────────────────────┐
│ PURSUITS                                                    │
│ ─────                                                       │
│                                                             │
│ ┌────────────────┬────────────────┬────────────────┐        │
│ │ Wardrive       │ Clone Access   │ Replay Sub-GHz │        │
│ │                │ Credential     │ Remote         │        │
│ │ [desc]         │ [desc]         │ [desc]         │        │
│ └────────────────┴────────────────┴────────────────┘        │
│ ┌────────────────┬────────────────┬────────────────┐        │
│ │ Evil Portal    │ Bluetooth      │ Sub-GHz        │        │
│ │                │ Recon          │ Capture+Analyze│        │
│ └────────────────┴────────────────┴────────────────┘        │
│ ┌────────────────┬────────────────┐                         │
│ │ Harvey Mudd    │ + CUSTOM       │                         │
│ │ Demo           │ PURSUIT        │                         │
│ └────────────────┴────────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

**Pursuit card:**

```css
.pursuit-card {
  padding: 24px; background: var(--bg-secondary);
  border: 0.5px solid var(--tile-border); text-align: left;
  cursor: pointer; min-height: 180px;
  display: flex; flex-direction: column;
}
.pursuit-card:active { background: var(--bg-deep); }
.pursuit-card--custom { border-style: dashed; }
.pursuit-card__title { font-family: 'Jost'; font-weight: 700; font-size: 22px; letter-spacing: -0.005em; text-transform: uppercase; margin: 0 0 12px; }
.pursuit-card__desc { font-family: 'Jost'; font-weight: 400; font-size: 14px; line-height: 1.5; color: var(--ink-secondary); flex: 1; margin: 0 0 16px; }
.pursuit-card__meta { font-family: 'JetBrains Mono'; font-size: 11px; color: var(--ink-tertiary); letter-spacing: 0.08em; display: flex; gap: 16px; }
```

**The seven v1 Pursuits:**

```javascript
const PURSUITS = [
  { id: 'wardrive', title: 'Wardrive',
    desc: 'Drive or walk while capturing WiFi and GPS simultaneously. Exports a geo-tagged network map.',
    duration: '~30 min', tools: 'WIFI · GPS',
    params: [
      { key: 'duration_min', label: 'Duration', type: 'select', options: [15, 30, 60, 120], default: 30 },
      { key: 'band', label: 'Frequency', type: 'select', options: ['2.4GHz', '5GHz', 'both'], default: 'both' },
      { key: 'gps_required', label: 'GPS required', type: 'checkbox', default: true },
    ]},
  { id: 'clone-credential', title: 'Clone Access Credential',
    desc: 'Read an LF RFID card (T5577/EM4100/HID Prox) and write its data to a blank card.',
    duration: '~2 min', tools: 'LF RFID',
    params: [] },
  { id: 'replay-subghz', title: 'Replay Sub-GHz Remote',
    desc: 'Capture a garage door or keyfob transmission, analyze, and replay.',
    duration: '~5 min', tools: 'SUB-GHZ',
    params: [
      { key: 'frequency', label: 'Frequency', type: 'select', options: ['315MHz','433.92MHz','868MHz','915MHz','auto'], default: 'auto' },
    ]},
  { id: 'evil-portal', title: 'Evil Portal',
    desc: 'Stand up a captive portal on a rogue AP to observe credential-submission behavior in a controlled environment.',
    duration: 'open-ended', tools: 'WIFI',
    params: [
      { key: 'ssid', label: 'Portal SSID', type: 'text', default: 'FreeWiFi' },
      { key: 'template', label: 'Portal page', type: 'select', options: ['starbucks','airport','generic'], default: 'generic' },
    ]},
  { id: 'bluetooth-recon', title: 'Bluetooth Recon',
    desc: 'Passively survey nearby BLE devices, log advertisements, classify vendor and role.',
    duration: '~10 min', tools: 'WIFI · BLE',
    params: [] },
  { id: 'subghz-capture-analyze', title: 'Sub-GHz Capture + Analyze',
    desc: 'Capture IQ data on a chosen frequency, demodulate, extract recognizable signal patterns.',
    duration: '~15 min', tools: 'SUB-GHZ',
    params: [
      { key: 'frequency', label: 'Frequency', type: 'text', default: '433.92MHz' },
      { key: 'duration_s', label: 'Duration (s)', type: 'number', default: 30 },
    ]},
  { id: 'hmc-demo', title: 'Harvey Mudd Demo',
    desc: 'Scripted demonstration sequence for the student showcase: scan, capture, Pursuit-complete. Uses a dedicated demo SSID.',
    duration: '~3 min', tools: 'WIFI · JOURNAL',
    params: [] },
];
```

**Custom Pursuit:** dashed-border card. For v1 ship, tapping it opens a minimal builder (select tools, set params). If time is tight, the builder can be deferred to v1.1 with a `Coming soon` state on this card — but Pursuits subsystem itself ships.

#### 10.4.2 Pursuit detail (stopped)

```
┌─────────────────────────────────────────────────────────────┐
│ [← back]                                                    │
│                                                             │
│ WARDRIVE                                                    │
│ ─────                                                       │
│ Drive or walk while capturing WiFi and GPS simultaneously.  │
│ ...full description...                                      │
│                                                             │
│ Parameters:                                                 │
│   Duration:      [30 minutes     ▾]                         │
│   Frequency:     [both           ▾]                         │
│   GPS required:  [☑]                                        │
│                                                             │
│ Tools invoked:   WIFI · GPS · JOURNAL                       │
│                                                             │
│                                       [START PURSUIT ▶]     │
└─────────────────────────────────────────────────────────────┘
```

- Parameter form generated from `params` array. Controls match existing parameter-form component (reuse from tool-group flow).
- START button: Primary, with `ph-play` icon.
- On tap: client sends `{type: "pursuit_start", pursuit_id, params: {...}}`.

#### 10.4.3 Pursuit running

On start, screen transitions to running layout:

```
┌─────────────────────────────────────────────────────────────┐
│ [← back]                                                    │
│                                                             │
│ WARDRIVE · RUNNING                                          │
│ ─── (crimson heavy rule, full width)                        │
│                                                             │
│ Started 14:22 · Elapsed 00:04:18 · ETA 00:25:42             │
│                                                             │
│ ████████████░░░░░░░░░░░░░░░░░░░░ 18%                        │   ← progress bar
│                                                             │
│ Live activity:                                              │
│   14:26:12  wifi.scan completed                  42 networks │
│   14:26:08  gps fix acquired                                │
│   14:26:04  wifi.scan completed                  39 networks │
│   ...                                                       │
│                                                             │
│                                            [STOP PURSUIT ⏹] │
└─────────────────────────────────────────────────────────────┘
```

- Progress bar: 3px tall, filled in `var(--accent-active)`, unfilled in `var(--bg-deep)`. Full width.
- Live activity: Mono Default, newest at top, last 20 lines visible.
- Updates via `pursuit_progress` messages.
- STOP button: Secondary. Confirmation modal if stopping would lose state.

Tapping back while running does NOT stop the Pursuit — it returns to the list and the Pursuit continues in background. Returning to the Pursuit's card shows the running state. This matches tool-dispatch behavior.

#### 10.4.4 Pursuit complete poster

On `pursuit_complete` message, screen transitions to ceremony:

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│                         WARDRIVE                            │   ← Jost Black 72px
│                                                             │
│                   ████                                      │   ← 3px crimson rule, 80px
│                                                             │
│                       COMPLETE                              │   ← Jost Bold 28px accent-scope
│                                                             │
│                47 networks · 2h 14m                         │   ← Mono Default
│                                                             │
│                                                             │
│                    (empty crimson circle 240px)             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

- Background: `var(--bg-primary)`.
- Pursuit name: Jost Black 72px, `var(--ink-primary)`, centered.
- Crimson rule below.
- `COMPLETE`: Jost Bold 28px, `var(--accent-scope)`, centered.
- Result summary: from `pursuit_complete.result_summary`, Mono Default, `var(--ink-secondary)`.
- Empty crimson circle: 240px radius, 4px stroke `var(--accent-crimson)`, no fill.
- Small diamond mark lower-right if asset present (24×24, `var(--accent-active)`).

**Duration:** 2000ms hold, then 200ms crossfade to the corresponding journal entry detail (§10.5.1).

**Acceptance:**
- [ ] All 7 Pursuit cards + Custom render on tab.
- [ ] Detail screen generates parameter form from schema.
- [ ] Start sends `pursuit_start`, transitions to running.
- [ ] Progress bar, elapsed, ETA, activity feed update from `pursuit_progress`.
- [ ] STOP sends `pursuit_stop`, with confirmation where needed.
- [ ] Complete poster holds 2s, routes to journal entry.

### 10.5 Journal tab `[NEW]`

Lab-notebook view of all tool invocations, Pursuit runs, scope changes.

**Layout:**

```
┌─────────────────────────────────────────────────────────────┐
│ JOURNAL                                                     │
│ ─────                                                       │
│ Filter: [all scopes ▾] [all tools ▾] [all sensitivity ▾]    │
│         [today ▾]                                           │
│                                                             │
│ 14:22  ● wifi.deauth      frames=5  scope: TESTING MY OWN   │   ← rows
│ 14:19    wifi.scan        42 networks                       │
│ 14:18    gps.fix          37.109°N, 118.321°W               │
│ 14:15  ● sub-ghz.replay   433.92 MHz, 2.1s                  │
│ ...                                                         │
└─────────────────────────────────────────────────────────────┘
```

**Filters (4 dropdowns, Secondary button style):**
- Scope: `all` | each seen scope
- Tool: `all` | each tool group | individual tools
- Sensitivity: `all` | `passive` | `active` | `disruptive`
- Time: `all time` | `today` | `last 24h` | `last 7 days` | `this session`

Changing a filter sends `journal_query` with updated filter set. Server replies with `journal_entries`.

**Row format:**

```
14:22  ● wifi.deauth      frames=5  scope: TESTING MY OWN DEVICES
```

- Time: Mono XS, `var(--ink-tertiary)`, 60px fixed.
- Sensitivity dot: color per sensitivity (passive = `--ink-quiet`, active = `--accent-active`, disruptive = `--accent-crimson`).
- Tool: Mono Medium, `var(--ink-primary)`, 160px fixed.
- Summary: Mono Default, `var(--ink-secondary)`, flex.
- Scope (right): Mono XS UPPER, `var(--accent-scope)`, truncates.

Row height 40px. Touch-press tints `var(--bg-secondary)`. Tap navigates to detail.

### 10.5.1 Journal entry detail

Full view of one entry:

```
┌─────────────────────────────────────────────────────────────┐
│ [← back]                                                    │
│                                                             │
│ 14:22 · APRIL 15, 2026                                      │
│ wifi.deauth                                                 │
│ ─────                                                       │
│                                                             │
│ ┌──────────────────────────┐ ┌────────────────────────────┐ │
│ │ Invoked by:   OPERATOR   │ │ Scope: TESTING MY OWN ...  │ │
│ │ Mode:         SCHOLAR    │ │ Confirmed: YES (fresh)     │ │
│ │ Sensitivity:  DISRUPTIVE │ │ Duration: 1.4s             │ │
│ └──────────────────────────┘ └────────────────────────────┘ │
│                                                             │
│ Parameters:                                                 │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ wifi.deauth(                                        │   │
│   │   bssid=AA:BB:CC:DD:EE:01,                          │   │
│   │   client=CC:DD:EE:FF:00:01,                         │   │
│   │   count=5                                           │   │
│   │ )                                                   │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│ Result:                                                     │
│   5 deauth frames sent. Client reconnected after 1.2s.      │
│                                                             │
│ Artifacts:                                                  │
│   /captures/2026-04-15-142203.pcap  (2.4 MB)                │
│                                                             │
│ Notes:                                                      │
│   [textarea — Mono Default, editable, empty by default]     │
└─────────────────────────────────────────────────────────────┘
```

Metadata in two `.panel` components side-by-side. Parameters in `.mono-block`. Notes: textarea saves on blur via `journal_note` message (or setting, TBD by build plan stage 4).

**Acceptance:**
- [ ] List renders reverse-chronological.
- [ ] All 4 filters work (AND-combined).
- [ ] Sensitivity dots color rows.
- [ ] Tap opens detail.
- [ ] Notes persist.

### 10.6 Mephisto conversation screen `[CHANGED]`

Pact mode only. Entered from dashboard Mephisto tile or activity preview.

**Layout — split-view:**

```
┌─────────────────────────────────────────────────────────────┐
│ [← back]  MEPHISTO                 qwen 2.5-vl-3b · 8.4 t/s │   ← top bar variant
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ CONVERSATION (top ~50%, ~324px)                             │
│                                                             │
│ PLANNING                                                    │   ← phase marker
│   assembling catalog…                                       │
│                                                             │
│ PLANNING                                                    │
│   thinking about steps (22s)…                               │
│                                                             │
│ MEPHISTO                                                    │
│   3 networks in scope. Ready to deauth home-lab-ap?         │
│                                                             │
│ OPERATOR                                                    │
│   yes, deauth home-lab-ap                                   │
│                                                             │
│ PARAMETERIZING STEP 1/3                                     │   ← phase marker
│   generating args for wifi.deauth…                          │
│                                                             │
│ [input field — Mono, placeholder: "speak to Mephisto..."]   │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ LIVE TOOL OUTPUT (bottom ~50%)                              │
│                                                             │
│ wifi.deauth(bssid=AA:BB:CC:DD:EE:01, count=5)               │
│                                                             │
│   → transmitting frame 1/5                                  │
│   → transmitting frame 2/5                                  │
│   → transmitting frame 3/5                                  │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ [tab bar]                                                   │
└─────────────────────────────────────────────────────────────┘
```

**Role labels + message bodies:**

| Role | Label color | Body color | Body type | Source event |
|---|---|---|---|---|
| `PLANNING` | `--accent-thinking` | `--accent-thinking` | Mono Default | `planning_started`, `catalog_build_started` |
| `PARAMETERIZING STEP N/M` | `--accent-thinking` | `--accent-thinking` | Mono Default | `parameterizing_step` |
| `MEPHISTO` | `--accent-mephisto` | `--accent-mephisto` | Body Default | (future; two-pass doesn't emit free text yet — reserved for a later agent extension that emits user-visible narration) |
| `OPERATOR` | `--ink-primary` | `--ink-primary` | Body Default | Operator sends `prompt` |
| `TOOL` | `--accent-crimson` | `--accent-crimson` | Mono Default | `tool_call_proposed` |
| `RESULT` | `--accent-success` | `--ink-primary` | Mono Default | `tool_call_executed` |
| `SCOPE` | `--accent-scope` | `--accent-scope` | Mono Default | Scope change during conversation |

Role label: Mono XS 10px letter-spacing 0.18em UPPER. 12px spacing between messages.

**Phase marker rendering:** `PLANNING` and `PARAMETERIZING STEP N/M` lines show a small live timer (e.g., `(22s)`) that updates while the phase is in progress, disappearing when replaced by the next event. On `final`, any in-progress phase markers clear.

**Consecutive-thinking coalescing `[PRESERVED]`:** if multiple thinking/planning events arrive in sequence without an intervening event type, merge them into a single bubble rather than generating many separate ones. Preserved from existing `pushChatAssistant` logic at app.js:515-524.

**Input field:**

```html
<form class="mephisto-input" onsubmit="sendPrompt(event)">
  <input type="text" class="mephisto-input__text"
         placeholder="speak to Mephisto..." autofocus>
  <button type="submit" class="mephisto-input__send">SEND ⏎</button>
</form>
```

Mono Default, full-width, padding 12px 16px, background `var(--bg-deep)`. Send button: 96px wide, Primary style.

**Live tool output panel:**
- Header: current tool call in mono, `var(--accent-crimson)`. Updates as agent invokes tools.
- Body: Mono Default, `var(--ink-primary)`. Lines prefix with `→`, `✓`, `✗`.
- Background: `var(--bg-deep)`.
- Empty state: `No active tool invocation.` in Mono Default, `var(--ink-quiet)`, centered.

**Acceptance:**
- [ ] Split 50/50 between conversation and tool output.
- [ ] Role labels color-coded per table.
- [ ] Phase markers render for `planning_started`, `catalog_build_started`, `parameterizing_step`. Live timers update.
- [ ] Consecutive-thinking coalescing preserved.
- [ ] Input field accepts text, submits via Enter or button.
- [ ] Live tool output streams via `tool_call_executed`.
- [ ] Back button returns to dashboard.
- [ ] Unreachable in scholar mode (Mephisto tile not clickable).

### 10.7 Scope-change modal `[NEW]`

Opens when operator taps the scope label in top bar.

**Layout:**

```
┌───────────────────────────────────────────────────┐
│ SET SCOPE                                         │
├───────────────────────────────────────────────────┤
│ Choose a scope for this session:                  │
│                                                   │
│ ○ Strictly Recon                                  │
│   Passive observation only. No transmission.      │
│                                                   │
│ ○ Testing My Own Devices                          │
│   Unlimited actions on hardware you own.          │
│                                                   │
│ ◉ Pentesting                                      │
│   Requires description of engagement.             │
│                                                   │
│   Description: [free-text input]                  │
├───────────────────────────────────────────────────┤
│                          [CANCEL]  [SET SCOPE]    │
└───────────────────────────────────────────────────┘
```

- Three radio options, custom-styled as 16×16 hard squares (filled with `--accent-crimson` when selected, outline when not).
- Description field: Mono Default, 48px tall, `var(--bg-deep)` background. Appears only when "Pentesting" selected.
- `SET SCOPE` (Primary) disabled when Pentesting + empty description.
- `CANCEL` (Secondary) closes modal.

On SET SCOPE: client sends `{type: "scope", template, description}`. Server persists, broadcasts updated `state`, writes journal entry `scope.set` with previous and new values. Trust memory invalidates on scope change.

**Acceptance:**
- [ ] Modal opens on scope-label tap.
- [ ] Three exclusive radios.
- [ ] Description appears only for Pentesting.
- [ ] SET SCOPE disabled appropriately.
- [ ] Journal entry created.
- [ ] Top-bar scope label updates.
- [ ] Trust memory invalidated.

### 10.8 Destructive-action confirmation modal `[CHANGED]`

Fires on active/disruptive tool invocation (via the existing `UIConfirmation` in `run.py:43`). Appears whether the tool is operator-invoked (scholar) or Mephisto-invoked (pact).

**Correlation by `call_id` `[CHANGED]`:** the server's `confirmation_request` message carries a `call_id`. The UI must echo it back in the `confirmation` reply. The modal tracks its current `call_id` and ignores replies that don't match.

**Layout:**

```
┌───────────────────────────────────────────────────────────┐
│ DEAUTH A WIFI CLIENT                       [disruptive]   │
├───────────────────────────────────────────────────────────┤
│   ┌───────────────────────────────────────────────────┐   │
│   │ wifi.deauth(                                      │   │
│   │   bssid=AA:BB:CC:DD:EE:01,                        │   │
│   │   client=CC:DD:EE:FF:00:01,                       │   │
│   │   count=5                                         │   │
│   │ )                                                 │   │
│   └───────────────────────────────────────────────────┘   │
│                                                           │
│ This transmits forged management frames.                  │
│ In most jurisdictions this is illegal outside your        │
│ authorized scope.                                         │
│                                                           │
│ ─────                                                     │
│                                                           │
│ Scope · TESTING MY OWN DEVICES                            │
│ Trust remembered within this scope for 10 minutes.        │
├───────────────────────────────────────────────────────────┤
│                              [ABORT]  [CONFIRM]           │
└───────────────────────────────────────────────────────────┘
```

**Header:** human-readable action label, right-aligned sensitivity pill (`active` or `disruptive`).

**Body:**
- `.mono-block` with the tool call, `--accent-crimson` variant.
- Plain-English consequence: Body Default, `var(--ink-primary)`, 2–3 sentences.
- Hairline.
- Scope line: `Scope · ` (`--ink-tertiary`) + scope name (`--accent-scope`).
- Trust-window line: Mono XS, `--ink-tertiary`.

**Buttons:**
- `ABORT`: Secondary, flex 1. Sends `{type: "confirmation", call_id, approved: false}`.
- `CONFIRM`: Primary (crimson), flex 1. Sends `{type: "confirmation", call_id, approved: true}`.
- No gap between buttons.
- `Escape` / hardware BACK button → ABORT.
- Tapping outside modal: no action.

**Interaction details `[CHANGED]`:**

- **ABORT** sends `approved: false`. Server's Dispatcher returns `DispatchResult(executed=False, error="user_rejected")`. Journal entry records `aborted: true`. This is handled by the existing contract — the UI just sends `approved: false`.
- **CONFIRM** sends `approved: true`. Tool executes. Journal entry records `confirmed: fresh` (first in the trust window) or `confirmed: remembered` (within trust window) — determined server-side by `TrustCache`.

**Trust-memory behavior `[NEW — server-side]`:**

`TrustCache` is a new class wrapping `DisclosureApprover` (see build-plan stage 4). Behavior:
- On CONFIRM, records `(scope, timestamp)`.
- On subsequent active/disruptive invocations within 10 minutes *and same scope*, auto-approves without firing `confirmation_request`. Journal records `confirmed: remembered`.
- Scope change resets the cache.
- Power-off (exit from ON state) clears the cache.

The UI does not need to track trust — it just responds to whether the server emits a `confirmation_request` or not.

**Acceptance:**
- [ ] Modal fires on first active/disruptive invocation in a scope.
- [ ] Within 10 minutes + same scope: server auto-approves, no modal.
- [ ] Scope change resets trust.
- [ ] Power-off resets trust.
- [ ] ABORT → journal records `aborted: true` + user sees tool not executed.
- [ ] CONFIRM → journal records `confirmed: fresh` or `confirmed: remembered` appropriately.
- [ ] `call_id` correlation enforced.
- [ ] Backdrop dims background 70% (navy or oxblood per mode).

### 10.9 Plan-approval modal `[NEW]`

**Distinct from the destructive-action modal.** Fires on `plan_approval_request`, which the agent sends after Pass 1 produces a plan. The modal shows the entire proposed plan (multi-step), not a single tool call.

The existing UI collapses this into the shared destructive modal (app.js:603-665). The v1.1 design splits them for clarity.

**Correlation by `plan_id`:** echo back in `plan_approval` reply.

**Layout:**

```
┌───────────────────────────────────────────────────────────────┐
│ MEPHISTO PROPOSES A PLAN                                      │
├───────────────────────────────────────────────────────────────┤
│ Reasoning:                                                    │
│                                                               │
│ The operator wants to test WiFi deauth on their home lab AP.  │
│ I'll scan first to find the target BSSID, then deauth once    │
│ targeted.                                                     │
│                                                               │
│ Steps:                                                        │
│   1. wifi.scan                       passive                  │
│      Locate the home lab AP's BSSID.                          │
│                                                               │
│   2. wifi.deauth                     disruptive  ◼ critical   │
│      Send deauth frames to the target.                        │
│                                                               │
│ Safety notes:                                                 │
│   · Step 2 is disruptive. You will be asked to confirm again  │
│     before it runs.                                           │
│   · This plan assumes scope permits WiFi attack on your own   │
│     hardware.                                                 │
│                                                               │
│ Scope · TESTING MY OWN DEVICES                                │
├───────────────────────────────────────────────────────────────┤
│                              [REJECT]  [APPROVE PLAN]         │
└───────────────────────────────────────────────────────────────┘
```

**Header:** `MEPHISTO PROPOSES A PLAN` in Jost Black 22px, `--accent-crimson` header background.

**Body:**
- **Reasoning:** Body Default, `--ink-primary`. Rendered from `plan_proposed.reasoning`.
- **Steps:** numbered list. Each step:
  - Row 1: `N. skill_name` (Mono Medium, `--ink-primary`) + sensitivity pill + `◼ critical` marker if step has `critical: true`
  - Row 2: intent text (Body Default, `--ink-secondary`, indented 24px)
- **Safety notes:** bulleted list from `plan_proposed.safety_notes`. Mono Default, `--accent-scope`.
- **Scope line:** same as destructive modal.

**Replan visual variant `[NEW]`:** if `plan_id` ends in `-replanN`, modal header reads `MEPHISTO PROPOSES A REVISED PLAN` (replacing the initial label), and a small line under the header reads `(revised after surprise on step K)` in Mono XS, `--ink-tertiary`.

**Buttons:**
- `REJECT`: Secondary. Sends `{type: "plan_approval", plan_id, approved: false}`. Agent emits `final` with `reason: "user_abort"`.
- `APPROVE PLAN`: Primary. Sends `{type: "plan_approval", plan_id, approved: true}`. Agent proceeds to Pass 2.

**Visual distinction from destructive modal:**
- Destructive modal header is tight and alarmed (single action label); plan-approval header is broader (multi-step proposal).
- Destructive modal body is one code block; plan-approval body is a structured list.
- Both use crimson header fill for consistency (this is the "approval-required" signal).

**Acceptance:**
- [ ] Modal fires on `plan_approval_request`.
- [ ] Reasoning, steps, safety notes render from payload.
- [ ] Critical steps marked.
- [ ] Replan variant visible when `plan_id` matches pattern.
- [ ] APPROVE/REJECT correlate by `plan_id`.
- [ ] Deadlock-free (WS receive loop stays free per §2.5).

### 10.10 Settings tab `[NEW]`

Config and diagnostics.

Only screen that scrolls vertically beyond 648px.

```
┌─────────────────────────────────────────────────────────────┐
│ SETTINGS                                                    │
│ ─────                                                       │
│                                                             │
│ ── Display ────────────────────────────────────────────────│
│ Brightness        [━━━━━━━━━━━━○━━━━]  85%                  │
│ Animation         [●]                                       │
│                                                             │
│ ── Audio ──────────────────────────────────────────────────│
│ Sound             [○] muted (default v1)                    │
│                                                             │
│ ── Radio ──────────────────────────────────────────────────│
│ WiFi/BLE          [●] enabled                               │
│ Sub-GHz           [●]                                       │
│ NFC               [●]                                       │
│ LF RFID           [●]                                       │
│ IR                [●]                                       │
│ Vision            [●]                                       │
│                                                             │
│ ── Scope history ──────────────────────────────────────────│
│ 14:05  Testing my own devices              (switch to) →   │
│ 13:42  Pentesting · home-lab-audit         (switch to) →   │
│                                                             │
│ ── Diagnostics ────────────────────────────────────────────│
│ Hardware health                           [view →]          │
│ Log viewer                                [view →]          │
│ Temperature history                       [view →]          │
│ Tokens/sec history                        [view →]          │
│                                                             │
│ ── About ──────────────────────────────────────────────────│
│ Faust v1.0.0 · build 2026-04-15                             │
│ Model: Qwen 2.5-VL 3B (Mephisto)                            │
│ Hardware: Pi 5 + AI HAT+ 2                                  │
│                                                             │
│ [ POWER OFF ]                                               │
│ [ FACTORY RESET ]                                           │
└─────────────────────────────────────────────────────────────┘
```

**Section headers:** Jost Bold 12px letter-spacing 0.18em UPPER, `--ink-secondary`, with hairline rule filling the remaining line width.

**Controls:**
- Sliders: range inputs styled with 4px track (`--bg-deep` unfilled, `--accent-active` filled), 16×16 hard-square thumb (`--ink-primary`).
- Toggles: hard-square 16×16, filled `--accent-active` when enabled, outlined when disabled.
- Action links: `[view →]` Secondary button, 24px tall.

Each setting change sends `{type: "setting", key, value}`.

**Power Off button `[PRESERVED]`:** preserved from existing UI (index.html:54). Primary button, fires window.confirm-style modal ("Power off? Session state will be cleared.") via the existing `DESTRUCTIVE_CONFIRM` pattern but re-styled as the destructive-action modal (section 10.8). On CONFIRM: sends `{type: "power", action: "off"}`. Server transitions to OFF. UI shows section 10.0.

**Factory Reset:** Primary (crimson) button at the bottom. Same confirmation modal flow: "All journal entries, scope history, and settings will be erased. This cannot be undone." On CONFIRM: server wipes persisted state, transitions to OFF.

**Diagnostics sub-screens:** each `[view →]` opens a detail view with back button, H1 title, 3px rule, and content:
1. **Hardware health:** live list of components with status/temp/last-activity.
2. **Log viewer:** tail of app log, Mono XS, auto-scrolls, can pause.
3. **Temperature history:** inline SVG line chart, last hour, CPU/Hailo/battery lines.
4. **Tokens/sec history:** inline SVG line chart, Mephisto tok/s over time. Empty state: `No data — Mephisto was not active in the last hour.` in scholar mode.

**Acceptance:**
- [ ] Settings page scrolls.
- [ ] All controls functional.
- [ ] Diagnostics sub-screens open.
- [ ] Power Off + Factory Reset require confirmation.

### 10.11 Dock animation `[CHANGED]`

On dock detected (real hardware) or `mephisto` message with `action: "connect"` (dev):

**0ms:** `SimulatorState.mephisto_connected = true`. Server emits `state` message with new value (and `first_dock_this_boot` if applicable).

**0–200ms:** Frontend sets `body[data-mode="pact"]`. Global 1000ms CSS transition begins on all palette-dependent properties.

**0–400ms:** Mephisto tile: dashed border solidifies to crimson.

**100–500ms:** Mephisto tile: `MEPHISTO` text color transitions from `--ink-quiet` to `--accent-mephisto`.

**200–800ms:** Mephisto tile: `AWAITING DOCK` fades out; model-info line fades in.

**300–1000ms:** Mephisto tile: background opacity rises 60% → 100%.

**600–1000ms (first dock per boot only):** Ceremony overlay (section 10.12) fades in on top of dashboard.

**1000–3000ms (first dock per boot only):** Ceremony holds.

**3000–3400ms (first dock per boot only):** Ceremony fades out.

**After:** Mephisto tile in active state. Session status replaced by activity preview. `first_dock_this_boot = false` persisted.

**Undock:** reverse palette transition. No ceremony. Mephisto tile returns to dim state.

**Acceptance:**
- [ ] Palette transitions smoothly, no flash.
- [ ] Duration ~1000ms.
- [ ] First dock per boot shows ceremony; subsequent docks do not.
- [ ] Undock reverses cleanly.

### 10.12 First-dock-per-boot ceremony `[NEW]`

Overlay on top of transitioning dashboard, one time per boot.

**Layout:**

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│                         MEPHISTO                            │   ← Jost Black 96px
│                                                             │
│                         ████                                │   ← 3px crimson rule, 120px
│                                                             │
│                    PACT ESTABLISHED                         │   ← Jost Bold 28px accent-scope
│                                                             │
│                             ◇                               │   ← diamond mark, 24px
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

- Background: opaque `var(--pact-bg-primary)`.
- MEPHISTO: Jost Black 96px, centered, `--accent-mephisto`.
- Crimson rule: 3px × 120px.
- `PACT ESTABLISHED`: Jost Bold 28px letter-spacing 0.02em UPPER, `--accent-scope`.
- Diamond mark: 24px, `--accent-active`.

**Timing:** 400ms fade-in → 2000ms hold → 400ms fade-out.

**Journal entry `[NEW]`:** on fire, server writes `pact.activated(mode: pact, scope: <current>, timestamp: ...)`.

**Acceptance:**
- [ ] Fires only on first dock after boot.
- [ ] Fade in → hold → fade out.
- [ ] Journal entry written.
- [ ] Does not re-trigger until next boot.


---

## 11. State model `[CHANGED]`

Application state is mirrored from `SimulatorState.to_dict()` + event streams. Full shape:

### 11.1 State shape received from server

```javascript
{
  // ── existing fields (preserved from current state.py) ──
  power: 'off' | 'booting' | 'on',
  mephisto_connected: boolean,
  boot_progress: number,           // 0-1 during booting
  session: {
    started_at: number,            // epoch seconds
    tool_invocations: number,
    journal_entries: number,
  },

  // ── new fields (added in build-plan stage 3) ──
  scope: {
    template: 'recon' | 'self-test' | 'pentesting' | null,
    description: string | null,
    set_at: number | null,
  } | null,
  battery: {
    percent: number,
    charging: boolean,
  },
  trust: {
    last_confirmed_scope: string | null,
    last_confirmed_timestamp: number | null,
  },
  first_dock_this_boot: boolean,
  goethe_quote: { de: string, en: string } | null,  // set at boot, cleared after first dashboard render

  // ── radio group states (derived from new 7-category _categorize()) ──
  radios: {
    wifi_ble:  { enabled: boolean, state: 'idle'|'active'|'error', last_event: {...} },
    sub_ghz:   { ... },
    nfc:       { ... },
    lf_rfid:   { ... },
    ir:        { ... },
    vision:    { ... },
    meta:      { ... },
  },

  // ── pursuit state ──
  active_pursuit: {
    id: string,
    started_at: number,
    progress: number,              // 0-1
    stop_requested: boolean,
  } | null,

  // ── mephisto runtime ──
  mephisto: {
    model: string,
    tokens_per_sec: number,
    last_utterance: string,
    current_tool_call: { name, params, output } | null,
    phase: 'idle' | 'planning' | 'parameterizing' | 'executing' | 'done',
    phase_step: { index: number, total: number } | null,
  },
}
```

### 11.2 Client-only state

The UI tracks some state not mirrored from the server:

```javascript
{
  currentView: string,             // dashboard, tool-group, pursuit-detail, etc.
  currentViewParams: object,       // view-specific params
  viewStack: string[],             // navigation history for goBack()
  pendingConfirmation: { call_id, ... } | null,
  pendingPlanApproval: { plan_id, ... } | null,
  conversation: [...],             // accumulated Mephisto conversation messages
  recentActivity: {...},           // per-tool-group recent events cache
}
```

### 11.3 Trust-memory is server-side `[CHANGED]`

The client does NOT track trust windows. The server's `TrustCache` (build-plan stage 4) decides whether to fire `confirmation_request` or auto-approve. This is the only design consistent with `CLAUDE.md` rule 3 ("Disclosure goes through the dispatch seam").

The `trust.last_confirmed_*` fields in state are informational (for UI display if desired), not authoritative.

---

## 12. Animation rules

### 12.1 Global transition

```css
* {
  transition-property: background-color, border-color, color;
  transition-duration: 1000ms;
  transition-timing-function: ease-in-out;
}
```

Mode swaps work automatically — `data-mode` flip causes every palette-derived property on every element to transition smoothly without per-component code.

### 12.2 Specific animations

| Animation | Duration | Easing | Trigger |
|---|---|---|---|
| Screen crossfade | 200ms | ease-out | Tab switch or drill-in |
| Modal open | 150ms | ease-out | Modal appears |
| Modal close | 150ms | ease-in | Modal dismissed |
| Mode palette swap | 1000ms | ease-in-out | Dock/undock |
| Mephisto tile fill-in | 1000ms | ease-in-out | Dock detection |
| First-pact ceremony fade-in | 400ms | ease-out | First dock per boot |
| First-pact ceremony hold | 2000ms | — | After fade-in |
| First-pact ceremony fade-out | 400ms | ease-in | After hold |
| Pursuit-complete hold | 2000ms | — | Pursuit finishes |
| Pursuit-complete fade-out | 200ms | ease-in | After hold |
| Boot screen fade-in | 500ms | ease-out | Chromium paint |
| Boot to dashboard | 500ms | ease-in-out | Boot sequence end |
| Boot log line append | per `boot_log` arrival | — | Server-streamed |
| Phase-marker timer tick | 1000ms | — | Live during planning/parameterizing |

### 12.3 What NOT to animate

- No spinners.
- No pulsing dots.
- No hover transitions (only instant touch-press state).
- No parallax, no scroll-triggered animation, no ambient motion.

### 12.4 Disable-all setting

Settings → Display → Animation toggles all transitions. When off:
- Transitions set to `0ms`.
- Fades become instant cuts.
- Ceremonies snap in/out instead of fading.
- Mode swap is instant.

Default: on.

---

## 13. Keyboard / hardware button mapping

Faust has 6 physical tactile buttons + a hardware RF kill toggle.

Hardware button events are delivered by the backend (TBD for v1 — not currently wired). For v1 implement keyboard equivalents for development/demo:

| Physical | Keyboard | Action |
|---|---|---|
| HOME | `Home` | Navigate to Dashboard |
| BACK | `Escape` | Dismiss modal / `goBack()` |
| SELECT | `Enter` | Activate focused element (reserved) |
| UP | `ArrowUp` | Focus traversal (reserved) |
| DOWN | `ArrowDown` | Focus traversal (reserved) |
| ACTION | `F2` | Current screen's primary button |

RF kill toggle is hardware-only — cuts power to radio peripherals. Radios report unavailable in `state.radios[*].enabled`.

Dev-only: `Ctrl+D` toggles `data-mode` scholar/pact for preview.

---

## 14. Accessibility

- WCAG AA contrast met by all text combos in spec.
- `--ink-quiet` on `--bg-primary` is at the edge — use for meta only.
- Motion sensitivity: Animation disable toggle in Settings.
- Touch targets ≥ 48×48 for all tappable elements. Journal entry rows are 40px — bump to 48 on build.
- `aria-label` on icon-only buttons and tabs for screen-reader safety. No further screen-reader testing for v1.

---

## 15. Consolidated acceptance criteria

Final verification checklist.

**Global:**
- [ ] Fonts load and render correctly
- [ ] `data-mode` switches scholar/pact palette globally
- [ ] All palette variables defined and used
- [ ] Bottom tab bar visible on all screens, active tab has crimson bottom rule
- [ ] Top bar visible on all screens (except OFF + boot), shows identity/mode/scope/battery/time

**OFF state:** operator sees Power-on button; tap starts boot.

**Boot sequence:** illustration loads, FAUST wordmark renders, random Goethe + translation, self-check log streams, crossfade to dashboard.

**Dashboard:** 7 sigil tiles + Mephisto tile + session status (scholar) or activity preview (pact).

**Tool-group screen:** back, tool cards with sensitivity pills, parameter form on tap, recent activity list.

**Pursuits tab:** 7 + Custom cards; detail with parameters; running with progress + activity; complete poster → journal.

**Journal tab:** filterable list, detail view with notes textarea.

**Mephisto conversation (pact only):** split-view, role-colored, phase markers with live timers, consecutive-thinking coalescing preserved, live tool output streams, back to dashboard.

**Scope modal:** three radios, Pentesting description, SET SCOPE disable logic, journal entry, trust reset.

**Destructive-action modal:** fires on active/disruptive, call_id correlation, ABORT/CONFIRM per contract, TrustCache behavior correct.

**Plan-approval modal:** fires on plan_approval_request, reasoning+steps+safety rendered, replan variant, plan_id correlation, deadlock-free.

**Settings:** scrolls, all controls functional, diagnostics sub-screens, Power Off + Factory Reset confirmed.

**Dock/undock:** smooth 1000ms palette transition, Mephisto tile animates, first dock ceremony, undock reverses.

**Animations:** global transition works, no spinners/pulsing, disable toggle works.

**Preserved behaviors:**
- [ ] Power state machine
- [ ] viewStack + goBack()
- [ ] Reconnect-resume
- [ ] Deadlock-free dispatch (test_ui.py:131 still passes)
- [ ] Demo mode (`--demo` flag) still works with new event sequence
- [ ] `body.active` CSS hook
- [ ] Consecutive-thinking coalescing
- [ ] Post-boot reveal animation (adapted)

**Agent extensions:**
- [ ] `PlanningStarted`, `CatalogBuildStarted`, `ParameterizingStep`, `ParameterizingDone` events fire in order
- [ ] `_categorize()` returns one of 7 sigil groups
- [ ] `SimulatorState` has scope/battery/trust/first_dock_this_boot
- [ ] `TrustCache` wraps `DisclosureApprover`
- [ ] Pursuit registry + runner functional for all 7 Pursuits

---

## 16. Implementation notes

### 16.1 File structure `[CHANGED]`

The new UI lives entirely within `faust/ui/static/`, matching the existing repo layout:

```
faust/ui/
├── server.py                 # aiohttp — modified, not replaced
├── run.py                    # modified, not replaced
├── state.py                  # modified, not replaced
├── bridge.py                 # untouched
└── static/
    ├── index.html            # REPLACED
    ├── app.js                # REPLACED
    ├── style.css             # REPLACED
    └── assets/
        ├── illustrations/
        │   └── boot-splash.png
        ├── sigils/*.svg      # 7 files
        ├── fonts/*.woff2     # 6 files
        └── marks/
            └── diamond-mark.svg (optional)
```

**Frontend CSS organization (optional but recommended):** can be a single `style.css` or split into modules. If splitting, suggested modules:
- `base.css` — palette, font-face, typography utilities
- `layout.css` — top bar, tab bar, grid
- `components.css` — buttons, tiles, panels, modals, sensitivity pill
- `screens.css` — per-screen styles
- `animations.css`

All loaded from a single `<link>` tag via `@import` or concatenated at build (there's no build toolchain, so concatenate manually or use `<link>` tags in order).

### 16.2 Build and run `[CHANGED]`

```bash
# Backend
python -m faust.ui.run          # starts aiohttp on :8080
# OR
python -m faust.ui.run --demo   # synthetic events, no Ollama required

# Frontend served as static files by the aiohttp backend at /
```

No build step.

### 16.3 JS architecture `[CHANGED]`

Preserve the IIFE pattern from the existing `app.js`. No Alpine, no HTMX.

```javascript
(function() {
  'use strict';

  const state = {
    power: 'off',
    mephisto_connected: false,
    currentView: 'off',
    viewStack: [],
    // ... full state shape from §11
  };

  let ws = null;

  function connect() {
    ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onmessage = onMessage;
    ws.onclose = () => setTimeout(connect, 1000);  // reconnect resume
  }

  function onMessage(event) {
    const msg = JSON.parse(event.data);
    switch (msg.type) {
      case 'state': handleState(msg); break;
      case 'boot_log': handleBootLog(msg); break;
      case 'skills': handleSkills(msg); break;
      case 'planning_started': handlePlanningStarted(msg); break;
      case 'catalog_build_started': handleCatalogBuildStarted(msg); break;
      case 'parameterizing_step': handleParameterizingStep(msg); break;
      case 'parameterizing_done': handleParameterizingDone(msg); break;
      case 'plan_proposed': handlePlanProposed(msg); break;
      case 'plan_proposed_replan': handlePlanProposedReplan(msg); break;
      case 'tool_call_proposed': handleToolCallProposed(msg); break;
      case 'tool_call_executed': handleToolCallExecuted(msg); break;
      case 'confirmation_request': handleConfirmationRequest(msg); break;
      case 'plan_approval_request': handlePlanApprovalRequest(msg); break;
      case 'pursuit_progress': handlePursuitProgress(msg); break;
      case 'pursuit_complete': handlePursuitComplete(msg); break;
      case 'journal_entries': handleJournalEntries(msg); break;
      case 'final': handleFinal(msg); break;
      case 'error': handleError(msg); break;
    }
  }

  // Navigation (preserved from existing)
  function navigate(view, params = {}) {
    state.viewStack.push(state.currentView);
    state.currentView = view;
    state.currentViewParams = params;
    render();
  }

  function goBack() {
    if (state.viewStack.length === 0) return;
    state.currentView = state.viewStack.pop();
    render();
  }

  // Render (preserve body.active hook)
  function render() {
    document.body.dataset.mode = state.mephisto_connected ? 'pact' : 'scholar';
    document.body.classList.toggle('active', isBusy());
    // ... view-specific rendering
  }

  connect();
  render();
})();
```

### 16.4 Chromium kiosk quirks

- `user-select: none` on body; re-enable for inputs.
- `document.addEventListener('contextmenu', e => e.preventDefault())`.
- `<meta name="viewport" content="width=1280, initial-scale=1, user-scalable=no">`.
- Hide scrollbars: `::-webkit-scrollbar { display: none; } * { scrollbar-width: none; }`.
- Full-screen: `html, body { overflow: hidden; height: 100vh; }`. Specific scroll areas override.

### 16.5 Performance

- No bundler, good.
- Prefer CSS over JS animations.
- Journal list: truncate to last 50 entries in memory; "load more" fetches older via `journal_query` with `before_ts`.
- `will-change` sparingly on Mephisto tile and modal backdrop.
- Pre-size images.

---

## 17. Open items

- `TBD-palette-exact` — pending color-picker pass.
- Diamond-mark asset — extract from boot splash or synthesize inline SVG.
- Pre-Chromium framebuffer splash — systemd concern, not UI.
- Hardware button wiring — backend delivery TBD for v1; keyboard dev-equivalents in spec.
- Custom Pursuit builder — can defer to v1.1 if build pressure.
- Scope-change during running Pursuit — behavior TBD. Recommend blocking the scope modal while a Pursuit is active; operator must stop to switch.

---

**End of document.** Approximately 13,000 words. This document plus `faust-sigil-spec.md` and `faust-build-plan.md` is the complete specification for the Faust operator interface, reconciled with the actual repository state.

## 8. Icon & sigil system

### 8.1 Phosphor icons

Utility icons use Phosphor at `regular` weight. Install via CDN:

```html
<link rel="stylesheet" href="https://unpkg.com/@phosphor-icons/web@2.1.1/src/regular/style.css">
```

Icons used:

| Usage | Class |
|---|---|
| Dashboard tab | `ph-house` |
| Pursuits tab | `ph-target` |
| Journal tab | `ph-book` |
| Settings tab | `ph-gear` |
| Back navigation | `ph-arrow-left` |
| Close modal | `ph-x` |
| Battery | `ph-battery-high`/`-medium`/`-low` |
| Dock indicator | `ph-link` |
| Expand/detail | `ph-caret-right` |
| Scope edit | `ph-pencil-simple` |
| Start Pursuit | `ph-play` |
| Stop Pursuit | `ph-stop` |
| Power on/off | `ph-power` |

### 8.2 Sigils

Seven group sigils, source in `faust-sigil-spec.md` §2.

| File | Label | Group (backend) |
|---|---|---|
| `sigil-wifi-ble.svg` | `WIFI · BLE` | `wifi_ble` |
| `sigil-sub-ghz.svg` | `SUB-GHZ` | `sub_ghz` |
| `sigil-nfc.svg` | `NFC` | `nfc` |
| `sigil-lf-rfid.svg` | `LF RFID` | `lf_rfid` |
| `sigil-ir.svg` | `IR` | `ir` |
| `sigil-vision.svg` | `VISION` | `vision` |
| `sigil-meta.svg` | `JOURNAL` | `meta` |

Group identifiers match the remapped output of `faust/agent/catalog._categorize()` (see §16 and build plan Stage 3).

### 8.3 Category remapping (new)

The current `_categorize()` returns 11 categories. The rewrite remaps these to the 7 sigil groups as follows:

| Current category | Remaps to | Sigil |
|---|---|---|
| `wifi` | `wifi_ble` | WIFI · BLE |
| `ble` | `wifi_ble` | WIFI · BLE |
| `nfc` | `nfc` | NFC |
| `rfid` | `lf_rfid` | LF RFID |
| `subghz` | `sub_ghz` | SUB-GHZ |
| `rf` | `sub_ghz` | SUB-GHZ |
| `ir` | `ir` | IR |
| `usb` | `meta` | JOURNAL |
| `network` | `wifi_ble` | WIFI · BLE |
| `analysis` | `meta` | JOURNAL |
| `defense` | `meta` | JOURNAL |

Camera-based or vision-specific skills classify to `vision`. The remap is implemented in the backend so there is one source of truth; the UI always receives one of exactly seven category strings. See build plan Stage 3.

---

## 9. Assets inventory

**Illustrations:**

- `assets/illustrations/boot-splash.png` — scholar on rooftop. Min 1024×1366.

**Sigils (7):** see §8.2.

**Fonts (6):** Jost 400/500/700/900, JetBrainsMono 400/500. Subset per §1.2.

**Phosphor:** CDN link, `regular` weight only.

**Optional diamond mark:** `assets/marks/diamond-mark.svg` for Pursuit-complete and ceremony moments. Synthesize as a 12×12 rotated-square SVG in `--accent-active` if not extracted from the boot splash.

No other asset files. Everything else is CSS/SVG generated.

---

## 10. Screens

Each screen is specified with layout, copy, states, interactions, and an acceptance checklist.

### 10.1 Boot sequence

**Total duration: ~5 seconds from power-on WS message to usable dashboard.**

The sequence is gated by the power state machine. Two entry paths:

1. **Fresh Chromium load with power=OFF** — the boot sequence does not auto-start. User sees a power-on affordance (a large centered crimson `POWER ON` button on a navy background). Click/tap sends `{type: "power", action: "on"}` to the server.
2. **Fresh Chromium load with power=ON (e.g., reconnect)** — client sees state message with `power: "on"` and renders the dashboard directly; no boot sequence.
3. **After POWER ON click** — server transitions OFF → BOOTING, begins streaming `boot_log` messages. UI shows the boot sequence below.

**Layout during BOOTING:**

```
┌───────────────────────────────────────────────────────────┐
│                                                           │
│              [boot-splash.png — 480×640]                  │  centered,
│                     centered                              │  40px from top
│                                                           │
│                                                           │
│                      FAUST                                │  Wordmark XL
│                                                           │
│        Grau, teurer Freund, ist alle Theorie.            │  Jost Medium 18px
│        GREY, DEAR FRIEND, IS ALL THEORY                   │  Mono XS
│                                                           │
│        [ ok ] kernel loaded (linux 6.6.x)                │  mono log,
│        [ ok ] display detected (waveshare 8" dsi...)     │  streaming
│        [ ok ] esp32-marauder attached (/dev/ttyUSB0)     │
│        ...                                                │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

**Background:** `var(--scholar-bg-primary)`.

**Illustration:** `<img src="/assets/illustrations/boot-splash.png" alt="">`, `width: 480px; height: auto;` centered, 40px from top.

**Wordmark:** `FAUST`, Wordmark XL, centered, 40px below illustration.

**Goethe line:** Jost Medium 18px letter-spacing 0.02em, color `var(--accent-scope)`, centered. 24px below wordmark.

**Translation:** Mono XS, color `var(--ink-tertiary)`. 8px below Goethe line.

**Goethe pool:** rotate on boot, no repeat-in-a-row:

```javascript
const GOETHE_LINES = [
  { de: "Grau, teurer Freund, ist alle Theorie.",
    en: "GREY, DEAR FRIEND, IS ALL THEORY" },
  { de: "Zwei Seelen wohnen, ach! in meiner Brust.",
    en: "TWO SOULS DWELL, ALAS, IN MY BREAST" },
  { de: "Der Worte sind genug gewechselt, laßt mich auch endlich Taten sehn!",
    en: "ENOUGH WORDS HAVE BEEN EXCHANGED; NOW LET ME SEE DEEDS" },
  { de: "Das Werdende, das ewig wirkt und lebt.",
    en: "THE BECOMING, THAT FOREVER ACTS AND LIVES" },
];
```

**Hardware self-check log:** streamed from server via `boot_log` messages (existing message type; `state.py:68-104`). The current server emits a 30-line simulated systemd log over ~6s at `speed=0.85`. **Preserved.** The rewrite does not change the log content — only its styling:

- Type: Mono (12px)
- Each line starts with a status prefix: `[ ok ]`, `[fail]`, `[warn]`
- `[ ok ]` in `var(--accent-success)`; `[fail]` in `var(--accent-crimson)`; `[warn]` in `var(--accent-scope)`
- Line content color: `var(--ink-secondary)`; on fail, escalate content to `var(--ink-primary)`
- Boot continues on failure — degraded tools display as disabled in the dashboard

**Post-boot reveal (preserved):** the existing implementation has a `playBootCompleteThenHome()` animation at `app.js:251-274` that unrolls "aust" after "𝑓" and shows a Goethe quote for ~2.8s. **Adapt this animation to the new palette/typography.** In the new design:

- The `FAUST` wordmark is already present during boot — no "unroll"
- Instead, at boot completion: briefly (600ms) brighten the wordmark from `var(--ink-primary)` to 110% via a CSS filter, then settle back
- Crossfade to dashboard over 500ms

**Transition to dashboard:** on receipt of final `boot_log` line indicating readiness, or when server sends `state` with `power: "on"`, client crossfades (200ms opacity) to the dashboard (Dashboard tab active).

**Acceptance:**

- [ ] Power=OFF shows a power-on affordance, not a boot screen
- [ ] POWER ON click sends `{type: "power", action: "on"}`
- [ ] Boot illustration, wordmark, Goethe, translation render in order
- [ ] Hardware self-check log streams from server messages with correct status coloring
- [ ] Failures coded crimson; boot continues
- [ ] Total boot time ~5–7s matching existing server timing
- [ ] Crossfade to dashboard on completion
- [ ] Reconnect with power=ON skips boot sequence

### 10.2 Dashboard (scholar)

Landing screen after boot.

```
┌─────────────────────────────────────────────────────────────┐
│ FAUST [SCHOLAR]    NO SCOPE · TAP TO SET    BAT 82% · 14:22 │   top bar
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ ┌──────┬──────┬──────┬──────┬──────┬──────┬──────┐          │
│ │ WiFi │ Sub- │ NFC  │ LF   │ IR   │ Vis- │ Jour │          │   radio strip
│ │ BLE  │ GHz  │      │ RFID │      │ ion  │ nal  │          │   (7 tiles)
│ └──────┴──────┴──────┴──────┴──────┴──────┴──────┘          │
│                                                             │
│ ┌─────────────────────────┐                                 │
│ │                         │                                 │
│ │     MEPHISTO TILE       │   Session started 13:45         │   mephisto tile
│ │     (double-width)      │   Tools invoked: 12             │   + session info
│ │     dim + empty         │   Journal entries: 4            │
│ │                         │   Current scope: NO SCOPE       │
│ └─────────────────────────┘                                 │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ [home] DASHBOARD  [target] PURSUITS  [book] JOURNAL  [gear] │   tab bar
└─────────────────────────────────────────────────────────────┘
```

**Radio strip:** 7 tiles in a grid. Width math: `1232 − 6×4 = 1208`, so each tile ≈ 172px × 130px. Gap 4px.

Each tile follows §7.6. Populated from the `skills` message: each tile is a sigil group, and the tile's status text shows the count of available skills in that group plus a summary of recent activity (from journal).

Tapping a tile → navigates to the tool-group screen (§10.3).

**Mephisto tile:**

**Size:** 2-tile-width = ~348px × 200px, positioned lower-left.

**Scholar state:**

- Background `var(--bg-secondary)`, 60% opacity
- Border 0.5px **dashed** `var(--tile-border)`
- Content: `MEPHISTO` in Jost Black 24px letter-spacing 0.08em UPPER, color `var(--ink-quiet)`. Below: Mono XS `AWAITING DOCK`
- Not clickable; `cursor: default`

**Pact state:**

- Background `var(--bg-secondary)` 100% opacity
- Border 0.5px **solid** `var(--accent-crimson)`
- Content: `MEPHISTO` Jost Black 24px, color `var(--accent-mephisto)`. Below: Mono XS `ONLINE · QWEN2.5-VL-3B · 8.4 T/S`. Below: crimson heavy-rule 48px wide
- Clickable → conversation screen (§10.7)

**Session status (scholar mode):** right of Mephisto tile, Mono, color `var(--ink-secondary)`.

**Mephisto activity preview (pact mode):** replaces session status. Shows most recent Mephisto utterance:

```
MEPHISTO                                    → TAP TO OPEN
─────
3 networks in scope. Ready to deauth home-lab-ap?
```

- Meta Label `MEPHISTO` in `var(--accent-mephisto)`
- Mono XS `→ TAP TO OPEN` in `var(--ink-tertiary)`
- 3px crimson rule
- Body (14px) most recent utterance in `var(--accent-mephisto)`, max 2 lines (ellipsis overflow)
- Entire region tappable → conversation screen

**Acceptance:**

- [ ] 7 tiles, sigils + labels + status + dot
- [ ] Tap → tool-group screen
- [ ] Mephisto tile dim+dashed in scholar, active+solid in pact
- [ ] Session info shows in scholar; activity preview in pact
- [ ] `data-mode` drives palette swap

### 10.3 Tool-group screen

Entered from a radio-strip tile tap.

```
┌─────────────────────────────────────────────────────────────┐
│ [top bar]                                                   │
├─────────────────────────────────────────────────────────────┤
│ [← BACK]                                                    │
│                                                             │
│ [sigil 24]  WIFI · BLE                                      │   Display H1
│ ████                                                        │   heavy rule 48px
│                                                             │
│ Available tools                                             │   Display H3
│ ┌────────────┬────────────┬────────────┬────────────┐       │
│ │ Scan       │ Capture    │ Deauth     │ ...        │       │   tool cards
│ │            │ PMKID      │ [DESTRUCT] │            │       │
│ └────────────┴────────────┴────────────┴────────────┘       │
│                                                             │
│ Recent activity                                             │
│ 14:19  wifi.scan                 42 networks                │
│ 14:05  wifi.deauth (confirmed)   5 frames · home-lab-ap     │
│ ...                                                         │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ [tab bar]                                                   │
└─────────────────────────────────────────────────────────────┘
```

**Header:** 24×24 sigil inline (color `var(--ink-primary)`) + group name Display H1. 3px crimson rule 48px beneath.

**Back:** `ph-arrow-left` 20px + Mono XS `BACK`, top-left. Tap calls `goBack()`.

**Tool action cards:** grid of all skills in this group. Each card:

```html
<button class="tool-card" data-skill="wifi.scan">
  <div class="tool-card__header">
    <span class="tool-card__name">SCAN</span>
    <span class="sensitivity-pill sensitivity-pill--passive">PASSIVE</span>
  </div>
  <div class="tool-card__desc">Passive scan of nearby networks</div>
  <div class="tool-card__meta"><span class="dot dot--idle"></span>ready</div>
</button>
```

```css
.tool-card {
  padding: 20px;
  background: var(--bg-secondary);
  border: 0.5px solid var(--tile-border);
  text-align: left; cursor: pointer;
}
.tool-card:active { background: var(--bg-deep); }
.tool-card--destructive {
  border-color: var(--accent-crimson);
}
.tool-card--destructive .tool-card__name {
  color: var(--accent-crimson);
}
.tool-card__header {
  display: flex; align-items: center; gap: var(--space-2);
  margin-bottom: var(--space-2);
}
.tool-card__name { font: 700 18px/1.2 'Jost'; letter-spacing: 0.02em; text-transform: uppercase; }
.tool-card__desc { font: 400 14px/1.5 'Jost'; color: var(--ink-secondary); margin-bottom: var(--space-3); }
.tool-card__meta { font: 400 11px/1.55 'JetBrains Mono'; color: var(--ink-tertiary); }
```

Destructive cards (`sensitivity === "disruptive"` or `"active"`) get `tool-card--destructive` class.

**Tap behavior (preserved flow from existing app.js):**

1. If skill has `parameters_schema`, navigate to a parameter-form view (§10.3.1).
2. If skill has no parameters or only smart-default-filled parameters, dispatch directly: send `{type: "dispatch", skill: "wifi.scan", args: {…}}`.
3. Destructive skills: dispatch triggers a `confirmation_request` from the server; UI shows destructive-action modal (§10.8).

**Smart defaults (preserved):** the existing `SMART_DEFAULTS` table (`app.js:28-44`) injects common defaults (`interface`, `duration_s`) when missing from args. Preserve this logic.

**Recent activity:** last 10 journal entries filtered by this tool group. Mono S, one per row:

```
14:19  wifi.scan                   3 networks visible
14:05  wifi.deauth (confirmed)     5 frames sent · home-lab-ap
```

Columns: timestamp (`var(--ink-tertiary)`, 60px), tool name (`var(--ink-primary)`, 160px), result (`var(--ink-secondary)`, flexes). Destructive actions use `var(--accent-crimson)` for tool name.

### 10.3.1 Parameter form view

Entered when a skill with `parameters_schema` is tapped and args aren't fully defaulted.

**Preserved from existing:** dynamic form generation from `parameters_schema` (`app.js:386-437`). The rewrite restyles this but keeps the generator. Each param becomes a labeled input:

- String → text input, Mono Default
- Integer → number input with spin controls
- Boolean → hard-square toggle
- Enum → segmented button group

Layout:

```
┌─────────────────────────────────────────────────────────────┐
│ [← BACK]                                                    │
│                                                             │
│ WIFI.DEAUTH                                                 │   Display H2
│ ────  [DESTRUCT] pill                                       │
│                                                             │
│ Transmit forged management frames to disconnect a client.   │   Body Large
│                                                             │
│ Parameters:                                                 │   Display H3
│   BSSID:      [____________________]                        │
│   Client MAC: [____________________]                        │
│   Count:      [  5 ]                                        │
│                                                             │
│                                    [CANCEL]  [INVOKE ▶]     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**INVOKE** dispatches. For destructive skills, server responds with `confirmation_request` → modal.

**Acceptance:**

- [ ] Back returns to tool group
- [ ] Sigil + group name + heavy rule present
- [ ] Tool cards render with correct sensitivity styling
- [ ] Tapping passive skills dispatches directly
- [ ] Tapping parameterized skills opens parameter form
- [ ] Destructive skills trigger confirmation modal
- [ ] Recent activity list updates live from journal events

---

### 10.4 Pursuits tab

Grid of 8 Pursuit cards: 7 predefined + Custom.

```
┌─────────────────────────────────────────────────────────────┐
│ [top bar]                                                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ PURSUITS                                                    │   Display H1
│ ████                                                        │   heavy rule
│                                                             │
│ ┌────────────┬────────────┬────────────┐                    │
│ │ Wardrive   │ Clone      │ Replay     │                    │
│ │            │ Access     │ Sub-GHz    │                    │
│ │ [desc]     │ Credential │ Remote     │                    │
│ │            │ [desc]     │ [desc]     │                    │
│ └────────────┴────────────┴────────────┘                    │
│ ┌────────────┬────────────┬────────────┐                    │
│ │ Evil Portal│ Bluetooth  │ Sub-GHz    │                    │
│ │            │ Recon      │ Capture    │                    │
│ │ [desc]     │ [desc]     │ + Analyze  │                    │
│ └────────────┴────────────┴────────────┘                    │
│ ┌────────────┬────────────┐                                 │
│ │ Harvey     │ + CUSTOM   │                                 │
│ │ Mudd Demo  │ PURSUIT    │                                 │
│ └────────────┴────────────┘                                 │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ [tab bar]                                                   │
└─────────────────────────────────────────────────────────────┘
```

**Card CSS:**

```css
.pursuit-card {
  padding: 24px;
  background: var(--bg-secondary);
  border: 0.5px solid var(--tile-border);
  text-align: left; cursor: pointer;
  min-height: 180px;
  display: flex; flex-direction: column;
}
.pursuit-card:active { background: var(--bg-deep); }
.pursuit-card__title {
  font: 700 22px/1.1 'Jost';
  letter-spacing: -0.005em; text-transform: uppercase;
  color: var(--ink-primary); margin: 0 0 12px;
}
.pursuit-card__desc {
  font: 400 14px/1.5 'Jost';
  color: var(--ink-secondary); flex: 1;
  margin: 0 0 16px;
}
.pursuit-card__meta {
  font: 400 11px/1.4 'JetBrains Mono';
  color: var(--ink-tertiary);
  letter-spacing: 0.08em;
  display: flex; gap: 16px;
}
.pursuit-card--custom {
  border-style: dashed;
}
.pursuit-card--custom .pursuit-card__title {
  color: var(--ink-secondary);
}
```

**Seven v1 Pursuits:**

```javascript
const PURSUITS = [
  { id: 'wardrive',
    title: 'Wardrive',
    desc: 'Drive or walk while capturing WiFi and GPS simultaneously. Exports a geo-tagged network map.',
    duration: '~30 min', tools: 'WIFI · GPS' },
  { id: 'clone-credential',
    title: 'Clone Access Credential',
    desc: 'Read an LF RFID card (T5577/EM4100/HID Prox) and write its data to a blank card.',
    duration: '~2 min', tools: 'LF RFID' },
  { id: 'replay-subghz',
    title: 'Replay Sub-GHz Remote',
    desc: 'Capture a garage door or keyfob transmission, analyze, and replay.',
    duration: '~5 min', tools: 'SUB-GHZ' },
  { id: 'evil-portal',
    title: 'Evil Portal',
    desc: 'Stand up a captive portal on a rogue AP to observe credential-submission behavior in a controlled environment.',
    duration: 'open-ended', tools: 'WIFI' },
  { id: 'bluetooth-recon',
    title: 'Bluetooth Recon',
    desc: 'Passively survey nearby BLE devices, log advertisements, classify vendor and role.',
    duration: '~10 min', tools: 'WIFI · BLE' },
  { id: 'subghz-capture-analyze',
    title: 'Sub-GHz Capture + Analyze',
    desc: 'Capture IQ data on a chosen frequency, demodulate, and extract recognizable signal patterns.',
    duration: '~15 min', tools: 'SUB-GHZ' },
  { id: 'hmc-demo',
    title: 'Harvey Mudd Demo',
    desc: 'Scripted demonstration sequence for the student showcase: scan, capture, Pursuit-complete. Uses a dedicated demo SSID.',
    duration: '~3 min', tools: 'WIFI · JOURNAL' },
];
```

**Custom card (8th slot):** dashed border, ink-secondary title. Tap → placeholder view explaining custom-Pursuit builder is v1.1 (*or* full builder if implemented; spec allows either).

Tapping a Pursuit card → Pursuit-detail screen (§10.4.1).

### 10.4.1 Pursuit detail / running

**Stopped state (before start):**

```
┌─────────────────────────────────────────────────────────────┐
│ [← BACK]                                                    │
│                                                             │
│ WARDRIVE                                                    │   Display H1
│ ████                                                        │
│                                                             │
│ Drive or walk while capturing WiFi and GPS simultaneously...│   Body Large
│                                                             │
│ Parameters:                                                 │
│   Duration:      [30 minutes     ▾]                         │
│   Frequency:     [2.4 GHz only   ▾]                         │
│   GPS required:  [☑]                                        │
│                                                             │
│ Tools invoked:   WIFI · GPS · JOURNAL                       │
│                                                             │
│                                        [▶ START PURSUIT]    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**START PURSUIT:** Primary button with `ph-play` before label. Sends `{type: "pursuit_start", pursuit_id, params: {…}}`.

**Running state:**

Server pushes `pursuit_progress` (every 1–5s) and `pursuit_activity` (as events happen). UI transitions to:

```
┌─────────────────────────────────────────────────────────────┐
│ [← BACK]                                                    │
│                                                             │
│ WARDRIVE · RUNNING                                          │
│ ████████████████████████  (full-width crimson rule)         │
│                                                             │
│ Started 14:22 · Elapsed 00:04:18 · ETA 00:25:42             │
│                                                             │
│ ████████████░░░░░░░░░░░░░░░░░░░░ 18%                        │   progress bar
│                                                             │
│ Live activity:                                              │
│   14:26:12  wifi.scan completed                  42 networks │
│   14:26:08  gps fix acquired                                │
│   14:26:04  wifi.scan completed                  39 networks │
│   ...                                                       │
│                                                             │
│                                           [■ STOP PURSUIT]  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Progress bar:**

```css
.pursuit-progress {
  height: 3px; width: 100%;
  background: var(--bg-deep);
  position: relative;
}
.pursuit-progress__fill {
  height: 100%;
  background: var(--accent-active);
  transition: width 300ms ease-out;
}
```

Width set from `pursuit_progress.progress` (0.0–1.0).

**Live activity:** Mono, newest at top. Truncates at 20 entries (older scrolls off). Lines come from `pursuit_activity` messages.

**STOP PURSUIT:** Secondary button with `ph-stop` icon. On tap:

1. If the Pursuit has stated "stoppable: true" in its metadata: sends `{type: "pursuit_stop", pursuit_id}`, server handles cleanup
2. If "stoppable: false" or the Pursuit's state would be lost: show a small confirmation modal: "Stopping will abandon partial capture. Confirm?"

**Completion:** server sends `pursuit_complete`. UI transitions to §10.4.2.

### 10.4.2 Pursuit-complete poster

2-second ceremonial screen. Pure geometric, no illustration (one narrative illustration per project — the boot splash).

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│                                                             │
│                         WARDRIVE                            │   Jost Black 72px
│                                                             │
│                  ████                                       │   3px crimson rule, 80px
│                                                             │
│                       COMPLETE                              │   Jost Bold 28px
│                                                             │                          accent-scope
│                                                             │
│             47 networks · 2 hours 14 minutes                │   Mono
│                                                             │
│                                                             │
│        ┌───────────────────────────────────────────┐        │
│        │              large crimson                 │        │
│        │              circle 240px                  │        │   geometric
│        │              centered                      │        │   composition
│        └───────────────────────────────────────────┘        │
│                                                             │
│                            ◇                                │   diamond mark
│                                                             │                          (optional, accent-active)
└─────────────────────────────────────────────────────────────┘
```

- Background: `var(--bg-primary)` (mode-appropriate)
- Pursuit name: Jost Black 72px, `var(--ink-primary)`, centered
- 3px crimson rule 80px below
- `COMPLETE` in Jost Bold 28px 0.02em UPPER, `var(--accent-scope)`, centered
- Summary: from `pursuit_complete.summary`, Mono, `var(--ink-secondary)`, centered
- Large crimson circle: 240px diameter, centered, empty fill, 4px stroke `var(--accent-crimson)`
- Diamond mark (optional asset): 24×24, `var(--accent-active)`, centered below

**Timing:** hold 2000ms, crossfade 200ms to journal entry detail (§10.6) for the Pursuit's journal entry ID returned in `pursuit_complete`.

**Acceptance:**

- [ ] Pursuits tab: 8 cards (7 + Custom)
- [ ] Tap → detail screen
- [ ] START PURSUIT sends `pursuit_start` with params
- [ ] Running screen shows progress + elapsed + ETA + live activity
- [ ] STOP PURSUIT works with confirmation if needed
- [ ] Completion poster holds 2s → journal entry
- [ ] `pursuit_complete` persists a journal entry server-side

### 10.5 Journal tab

Filterable list of all tool invocations and Pursuit completions.

```
┌─────────────────────────────────────────────────────────────┐
│ [top bar]                                                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ JOURNAL                                                     │   Display H1
│ ████                                                        │
│                                                             │
│ Filter: [all ▾] [all tools ▾] [all sens ▾] [today ▾]        │
│                                                             │
│ 14:22  ● wifi.deauth      frames=5       TESTING MY OWN...  │
│ 14:19    wifi.scan        42 networks                       │
│ 14:18    gps.fix          37.109°N, 118.321°W               │
│ 14:15  ● subghz.replay    433.92 MHz, 2.1s                  │
│ 14:12    wifi.scan        3 networks                        │
│ ...                                                         │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ [tab bar]                                                   │
└─────────────────────────────────────────────────────────────┘
```

**Filter controls:** four dropdown selectors styled as Secondary buttons with `ph-caret-down`:

1. **Scope:** `all scopes` | each scope ever used
2. **Tool:** `all tools` | each sigil group | individual tool names
3. **Sensitivity:** `all` | `passive` | `active` | `disruptive`
4. **Time range:** `all time` | `today` | `last 24h` | `last 7 days` | `this session`

On filter change, UI sends `{type: "journal_query", filters: {…}}` to server. Server replies with `journal_entries` message. Client renders the returned list.

**Entry rows:** 40px tall each (spec-updated for touch accessibility). Columns:

1. Time: Mono XS, `var(--ink-tertiary)`, 60px
2. Sensitivity dot (§7.5): passive=`var(--ink-quiet)`, active=`var(--accent-active)`, disruptive=`var(--accent-crimson)`
3. Tool name: Mono Medium, `var(--ink-primary)` (or `var(--accent-crimson)` if disruptive), 160px
4. Summary: Mono, `var(--ink-secondary)`, flexes
5. Scope (right-aligned): Mono XS UPPER, `var(--accent-scope)`, truncates with ellipsis if needed

Hover/active row: background `var(--bg-secondary)`.

Tap → journal entry detail (§10.6).

### 10.6 Journal entry detail

Full view of one entry.

```
┌─────────────────────────────────────────────────────────────┐
│ [← BACK]                                                    │
│                                                             │
│ 14:22 · APRIL 15, 2026                                      │   Mono XS
│ wifi.deauth                                                 │   Display H1
│ ████                                                        │
│                                                             │
│ ┌────────────────────────┐ ┌────────────────────────────┐   │
│ │ Invoked by:   OPERATOR │ │ Scope: TESTING MY OWN...   │   │
│ │ Mode:         SCHOLAR  │ │ Confirmed: YES (fresh)     │   │
│ │ Sensitivity:  DISRUPTIVE │ Duration: 1.4s             │   │
│ └────────────────────────┘ └────────────────────────────┘   │
│                                                             │
│ Parameters:                                                 │
│   ┌─────────────────────────────────────────────────────┐   │
│   │ wifi.deauth(                                        │   │   mono-block
│   │   bssid=AA:BB:CC:DD:EE:01,                          │   │   destructive variant
│   │   client=CC:DD:EE:FF:00:01,                         │   │
│   │   count=5                                           │   │
│   │ )                                                   │   │
│   └─────────────────────────────────────────────────────┘   │
│                                                             │
│ Result:                                                     │
│   5 deauth frames sent. Client reconnected after 1.2s.      │
│                                                             │
│ Artifacts:                                                  │
│   /captures/2026-04-15-142203.pcap  (2.4 MB)                │
│                                                             │
│ Notes:                                                      │
│   [Textarea — editable, Mono]                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

Two metadata panels side-by-side, each a `.panel` with 3–4 key-value rows. Parameters in a `.mono-block` (destructive variant if applicable). Notes is a textarea — saves on blur via a journal-update WS message (or extend `journal_query` protocol for writes; detail in build plan Stage 5).

**Acceptance:**

- [ ] Journal list populates from `journal_entries` message
- [ ] Four filters combine via AND
- [ ] Sensitivity dots color rows correctly
- [ ] Tap → detail view
- [ ] Notes textarea saves on blur
- [ ] Pursuit-complete entries show a "Pursuit" badge in the row

### 10.7 Mephisto conversation screen

Accessible only in pact mode.

```
┌─────────────────────────────────────────────────────────────┐
│ [← BACK]  MEPHISTO             qwen 2.5-vl-3b · 8.4 t/s     │   top bar variant
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ CONVERSATION (top 50%)                                      │
│                                                             │
│ MEPHISTO                                                    │
│   3 networks in scope. Ready to deauth home-lab-ap?         │
│                                                             │
│ OPERATOR                                                    │
│   yes, deauth home-lab-ap                                   │
│                                                             │
│ PLANNING · thinking about steps (22s)                       │
│                                                             │
│ [input — "speak to Mephisto..."]                [SEND ⏎]    │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ LIVE TOOL OUTPUT (bottom 50%)                               │
│                                                             │
│ wifi.deauth(bssid=AA:BB:CC:DD:EE:01, count=5)               │
│   → transmitting frame 1/5                                  │
│   → transmitting frame 2/5                                  │
│   ...                                                       │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ [tab bar]                                                   │
└─────────────────────────────────────────────────────────────┘
```

**Split:** 50/50 vertical = 324px each (given 648px main region).

**Conversation panel (top):** scrollable, newest at bottom.

**Role labels:** Meta Label type, color-coded:

- `OPERATOR` → `var(--ink-primary)`
- `MEPHISTO` → `var(--accent-mephisto)`
- `PLANNING` → `var(--accent-thinking)` — new, driven by `planning_started` events
- `PARAMETERIZING` → `var(--accent-thinking)` — new, driven by `parameterizing_step` events
- `TOOL` → `var(--accent-crimson)` — driven by `tool_call_proposed`
- `RESULT` → `var(--accent-success)` — driven by `tool_call_executed`
- `SCOPE` → `var(--accent-scope)` — for scope changes

**Content color:** matches label color for ambient voices (Mephisto/Planning/Parameterizing), `var(--ink-primary)` for Operator, `var(--accent-crimson)` in mono for Tool calls.

**Phase-marker rendering:** the new `planning_started` and `parameterizing_step` events render as discrete in-chat lines:

- `planning_started {phase: "catalog"}` → `PLANNING · assembling catalog (Ns)` — N counts up in real time; line replaces itself in place via a stable key
- `planning_started {phase: "plan"}` → `PLANNING · thinking about steps (Ns)`
- `planning_started {phase: "replan"}` → `RE-PLANNING · adjusting course (Ns)` — visually distinct from initial plan; add a small warning dot next to it
- `parameterizing_step {step: 2, of: 5, skill: "wifi.scan", intent: "..."}` → `PARAMETERIZING · step 2 of 5 · wifi.scan`

**Coalescing (preserved):** `pushChatAssistant` merges adjacent lines of the same role to avoid flooding the chat. Preserve for consecutive thinking/planning lines.

**Input field:**

```html
<form class="mephisto-input">
  <input type="text" class="mephisto-input__text" placeholder="speak to Mephisto..." autofocus>
  <button type="submit" class="mephisto-input__send">SEND ⏎</button>
</form>
```

- Input: Mono, full-width flex, padding 12px 16px, background `var(--bg-deep)`, color `var(--ink-primary)`, no border on focus
- Send: 96px wide, Primary button style

Submit sends `{type: "prompt", text: <input>}`.

**Live tool output panel (bottom):** streams from `tool_call_proposed` + `tool_call_executed`:

- Header: current tool call in mono, color `var(--accent-crimson)`
- Content: Mono, `var(--ink-primary)`, prefixed `→ ` for normal, `✓ ` for success, `✗ ` for error
- Background: `var(--bg-deep)`
- When no tool active: `No active tool invocation.` in Mono `var(--ink-quiet)` centered

**Acceptance:**

- [ ] 50/50 split between conversation and tool output
- [ ] All six role labels color-coded correctly
- [ ] `planning_started` / `parameterizing_step` events render as discrete in-chat lines
- [ ] Replan phase visually distinguishable from initial plan
- [ ] Input submits prompts
- [ ] Tool output streams live
- [ ] `body.active` set during in-flight operation, cleared on `final`
- [ ] Back returns to dashboard
- [ ] Unreachable in scholar mode

### 10.8 Destructive-action confirmation modal

Fires when server emits `confirmation_request`.

```
┌───────────────────────────────────────────────────────────┐
│ DEAUTH A WIFI CLIENT                                      │   H2 on crimson
├───────────────────────────────────────────────────────────┤
│                                                           │
│   ┌───────────────────────────────────────────────────┐   │
│   │ wifi.deauth(                                      │   │   mono-block
│   │   bssid=AA:BB:CC:DD:EE:01,                        │   │   destructive
│   │   client=CC:DD:EE:FF:00:01,                       │   │
│   │   count=5                                         │   │
│   │ )                                                 │   │
│   └───────────────────────────────────────────────────┘   │
│                                                           │
│ This transmits forged management frames.                  │
│ In most jurisdictions this is illegal outside your        │
│ authorized scope.                                         │
│                                                           │
│ ────                                                      │
│                                                           │
│ Scope · TESTING MY OWN DEVICES                            │
│ Trust remembered within this scope for 10 minutes.        │
│                                                           │
├───────────────────────────────────────────────────────────┤
│                              [ABORT]  [CONFIRM]           │
└───────────────────────────────────────────────────────────┘
```

**Header:** `var(--accent-crimson)` background, Jost Black 22px 0.02em UPPER `var(--ink-primary)`. Copy is the human-readable action name, loaded from the tool's metadata (derived on server; WS message carries it or client maps from `tool_name`).

**Body:**

- Tool call in `.mono-block .mono-block--destructive`
- Plain-English consequence: Body (14px) `var(--ink-primary)`, 2–3 sentences max, loaded from tool metadata
- Hairline divider
- Scope line: Mono, `Scope · ` in `var(--ink-tertiary)`, scope name in `var(--accent-scope)`
- Trust-window line: Mono XS in `var(--ink-tertiary)`

**Buttons:** flush, 50/50 split at bottom. ABORT = Secondary style; CONFIRM = crimson fill.

**Correlation (critical):** the modal receives `call_id` in the `confirmation_request`. ABORT/CONFIRM send `{type: "confirmation", call_id: <same>, approved: false|true}`. **Do not send without correlating `call_id`** — the server's `UIConfirmation.__call__` waits on a queue matching by id.

**Trust memory (server-side):** a `TrustCache` wrapping `DisclosureApprover` (new middleware, build plan Stage 4) remembers confirmations for 10 minutes within the current scope. If trust is valid, the server does not emit `confirmation_request` at all — the dispatch proceeds silently, and the journal entry is marked `confirmed: remembered`. UI does not need to implement trust memory — it just renders the modal whenever the server asks.

**Timeline:**

- Server sends `confirmation_request` → modal opens (150ms fade)
- CONFIRM → `{type: "confirmation", call_id, approved: true}` → modal closes (150ms)
- ABORT → `{type: "confirmation", call_id, approved: false}` → modal closes (150ms)
- Tapping outside the modal: no action
- Escape or hardware BACK: same as ABORT

**Acceptance:**

- [ ] Fires on `confirmation_request`
- [ ] ABORT sends `{approved: false}` with correlating `call_id`
- [ ] CONFIRM sends `{approved: true}` with correlating `call_id`
- [ ] Modal closes on reply
- [ ] Trust window respected by server — no modal on re-invocation within 10 min

### 10.9 Plan-approval modal (new in v2.0)

Fires when server emits `plan_approval_request`. Distinct from the destructive-action modal — larger, scrollable, shows the full plan.

```
┌───────────────────────────────────────────────────────────┐
│ MEPHISTO PROPOSES A PLAN                                  │   H2 on thinking-purple
├───────────────────────────────────────────────────────────┤
│                                                           │
│ Reasoning:                                                │
│ To find the target keyfob's rolling code, I'll capture    │
│ the 433 MHz band during an expected transmission,         │
│ demodulate, then look up the protocol family...           │
│                                                           │
│ Steps:                                                    │
│   1. subghz.capture         Capture 2s of 433 MHz traffic │
│   2. subghz.demodulate      Demodulate to bitstream       │
│   3. subghz.replay          [DESTRUCT] Replay transmission│
│                                                           │
│ Safety notes:                                             │
│   ⚠ Step 3 retransmits captured signal. Ensure your       │
│     authorization covers this device.                     │
│                                                           │
├───────────────────────────────────────────────────────────┤
│                              [REJECT]  [APPROVE PLAN]     │
└───────────────────────────────────────────────────────────┘
```

**Header:** `var(--accent-thinking)` background, `MEPHISTO PROPOSES A PLAN`. On a re-plan (detected by `plan_id` containing `-replan`), header becomes `MEPHISTO PROPOSES A REVISED PLAN` with `var(--accent-crimson)` background so re-plans are visually distinct.

**Body:**

- Reasoning: Body (14px) `var(--ink-primary)`. Server supplies this text.
- Steps: numbered list, Mono. Each line: `N. skill_name        intent`. Disruptive steps prefix with `[DESTRUCT]` in crimson.
- Safety notes: Mono with `⚠` prefix in `var(--accent-scope)`. Each note is a line.

**Buttons:** flush, 50/50. REJECT = Secondary; APPROVE PLAN = thinking-purple fill (or crimson on re-plan, matching header).

**Correlation:** `plan_id` in the request. Buttons send `{type: "plan_approval", plan_id, approved: true|false}`.

**Behavior after approval:**

- APPROVE → modal closes; server begins executing steps; `parameterizing_step` and `tool_call_proposed` events flow; individual destructive steps still fire their own confirmation modals (§10.8)
- REJECT → modal closes; server emits `final {reason: "user_abort"}`; agent turn ends

**Behavior on re-plan:**

The server may emit a second `plan_approval_request` mid-turn with a `plan_id` ending in `-replan1`, `-replan2`, etc. UI reopens the modal with the re-plan header treatment. Treat as a fresh approval — previous approval does not carry.

**Acceptance:**

- [ ] Fires on `plan_approval_request`
- [ ] Steps and safety notes render correctly
- [ ] Destructive steps marked with `[DESTRUCT]` in crimson
- [ ] Re-plans visually distinguishable from initial plan
- [ ] APPROVE/REJECT correlate by `plan_id`
- [ ] In-plan destructive steps fire per-action confirmation modal (§10.8)

---

### 10.10 Scope-change modal

Opens on scope-label tap in top bar.

```
┌───────────────────────────────────────────────────┐
│ SET SCOPE                                         │   H2 on crimson
├───────────────────────────────────────────────────┤
│                                                   │
│ Choose a scope for this session:                  │
│                                                   │
│ ☐ Strictly Recon                                  │
│   Passive observation only. No transmission.      │
│                                                   │
│ ☐ Testing My Own Devices                          │
│   Unlimited actions on hardware you own.          │
│                                                   │
│ ☑ Pentesting                                      │
│   Requires description of engagement.             │
│                                                   │
│   Description: [_________________________]        │
│                                                   │
├───────────────────────────────────────────────────┤
│                          [CANCEL]  [SET SCOPE]    │
└───────────────────────────────────────────────────┘
```

**Three radio options** — custom-styled as 16×16 hard squares (not circles). Selected fills with `var(--accent-crimson)`; unselected is outlined.

**Pentesting reveals description input below it.** Description: full-width, Mono, 48px tall, background `var(--bg-deep)`, padding 12px 16px.

**Buttons:**

- CANCEL: Secondary. Close modal, no change.
- SET SCOPE: Primary (crimson). **Disabled** if Pentesting selected with empty description.

**On SET SCOPE:**

1. Client sends `{type: "scope_change", template: "pentesting", description: "..."}`
2. Server persists new scope to `SimulatorState`, pushes updated `state` message
3. Modal closes (150ms fade)
4. Top-bar scope label updates from new `state`
5. Server creates journal entry `scope.set` with prev + new values
6. **Server-side trust memory is invalidated** — next destructive action re-fires confirmation modal

**Acceptance:**

- [ ] Modal opens on scope-label tap
- [ ] Three radio options, mutually exclusive
- [ ] Description appears only for Pentesting
- [ ] SET SCOPE disabled when Pentesting + empty description
- [ ] Scope-change journal entry created
- [ ] Top-bar label updates
- [ ] Trust memory reset (server-side)

### 10.11 Settings tab

Configuration + diagnostics. Only screen with vertical scrolling.

```
┌─────────────────────────────────────────────────────────────┐
│ [top bar]                                                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ SETTINGS                                                    │
│ ████                                                        │
│                                                             │
│ ── DISPLAY ────────────────────────────────────────────────│
│ Brightness        [━━━━━━━━━━━━○━━━━]  85%                  │
│ Animation         [●] enabled                               │
│                                                             │
│ ── AUDIO ──────────────────────────────────────────────────│
│ Sound             [━○───────────────]  muted                │
│                                                             │
│ ── RADIO ──────────────────────────────────────────────────│
│ WiFi/BLE          [●] enabled                               │
│ Sub-GHz           [●] enabled                               │
│ NFC               [●] enabled                               │
│ LF RFID           [●] enabled                               │
│ IR                [●] enabled                               │
│ Vision            [●] enabled                               │
│                                                             │
│ ── SCOPE HISTORY ──────────────────────────────────────────│
│ 14:05  Testing my own devices              [switch to →]   │
│ 13:42  Pentesting · home-lab-audit         [switch to →]   │
│ ...                                                         │
│                                                             │
│ ── DIAGNOSTICS ────────────────────────────────────────────│
│ Hardware health                           [view →]          │
│ Log viewer                                [view →]          │
│ Temperature history                       [view →]          │
│ Tokens/sec history                        [view →]          │
│                                                             │
│ ── POWER ──────────────────────────────────────────────────│
│ [POWER OFF]                                                 │
│                                                             │
│ ── ABOUT ──────────────────────────────────────────────────│
│ Faust v1.0.0 · build 2026-04-15                             │
│ Model: Qwen 2.5-VL 3B (Mephisto)                            │
│ Hardware: Pi 5 + AI HAT+ 2                                  │
│                                                             │
│ [FACTORY RESET]                                             │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ [tab bar]                                                   │
└─────────────────────────────────────────────────────────────┘
```

**Section headers:** Jost Bold 12px 0.18em UPPER `var(--ink-secondary)`. Trailing hairline rule extends to the right edge of the content area.

**Controls:**

- **Sliders:** range inputs. Track 4px `var(--bg-deep)`; fill `var(--accent-active)`; thumb 16×16 hard square `var(--ink-primary)`
- **Toggles:** hard squares 16×16. Filled = enabled (`var(--accent-active)`); empty outlined = disabled
- **Action links:** `[view →]` styled as small Secondary buttons (24px tall, 12px padding) with `ph-caret-right`

**Power Off:**

Secondary button styled with crimson border + crimson text. Tap fires a confirmation modal: "Power off the device?" → CONFIRM sends `{type: "power", action: "off"}`.

**Preserved note:** the existing UI has a power-off button in its footer (`index.html:54`). The rewrite moves it to Settings and hides the persistent footer control. Reasoning: footer real estate is taken by the tab bar; power-off is rare enough to live in Settings; confirmation modal protects against accidental taps.

**Diagnostics sub-screens:** each `[view →]` opens a full-screen detail:

- Back button, Display H1 title, 3px crimson rule, then content
- **Hardware health:** mono list of all hardware components with live status + temp + last-activity — essentially a live version of the boot log
- **Log viewer:** tailing app log, Mono XS, auto-scrolls, pause button
- **Temperature history:** inline-SVG line chart of CPU/Hailo/battery temps over the last hour
- **Tokens/sec history:** inline-SVG line chart of Mephisto tokens/sec over last hour (pact mode only; scholar shows "No data — Mephisto was not active in the last hour")

**Factory Reset:**

Primary (crimson) button. Tap → destructive-action modal with header `FACTORY RESET`, consequence "All journal entries, scope history, and settings will be erased. This cannot be undone." Requires CONFIRM. On confirm: sends a new WS message `{type: "factory_reset"}` (not currently in protocol — add in build plan Stage 11 or skip and make factory reset a CLI-only operation for v1).

**Acceptance:**

- [ ] Settings page scrolls when content exceeds viewport
- [ ] All controls functional (backend wiring optional for some)
- [ ] Power off button with confirmation
- [ ] Diagnostics sub-screens open and render
- [ ] Factory Reset requires confirmation

### 10.12 Dock animation

Fires on Mephisto dock detection (existing `mephisto` WS message pattern).

**Sequence — on dock:**

**0ms (detected):**

- Server sends updated `state` with `mephisto: connected`
- Client receives, sets `body[data-mode="pact"]`

**0–1000ms:**

- Global 1000ms CSS transition on `background-color`, `border-color`, `color` runs — every palette-dependent element shifts toward pact palette

**0–400ms (Mephisto tile specifically):**

- Dashed border solidifies
- Border color transitions to `var(--accent-crimson)`

**100–500ms:**

- `MEPHISTO` text color transitions from `var(--ink-quiet)` to `var(--accent-mephisto)`

**200–800ms:**

- `AWAITING DOCK` text fades out
- Model-info line (`ONLINE · QWEN2.5-VL-3B · 8.4 T/S`) fades in

**500–1000ms:**

- Mephisto tile background opacity rises from 0.6 to 1.0

**1000ms onward (first-dock-per-boot only):**

- Ceremony overlay (§10.13) fades in — sits above everything for 2s, then fades out

**Sequence — on undock:**

Reverse of the above, no ceremony. Total 1000ms.

**Acceptance:**

- [ ] Palette transitions smooth, no flash
- [ ] ~1000ms total
- [ ] Mephisto tile updates in sync
- [ ] Ceremony only on first dock per boot
- [ ] Undock reverses cleanly

### 10.13 First-dock-per-boot ceremony

One-time overlay on first dock after boot.

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│                                                             │
│                                                             │
│                         MEPHISTO                            │   Wordmark XL (96px)
│                                                             │
│                           ████                              │   3px crimson rule
│                                                             │                            120px wide
│                       PACT ESTABLISHED                      │   Display H1 28px
│                                                             │                            accent-scope
│                                                             │
│                                                             │
│                            ◇                                │   diamond mark
│                                                             │                            accent-active
└─────────────────────────────────────────────────────────────┘
```

- Background: opaque `var(--pact-bg-primary)`
- `MEPHISTO`: Wordmark XL (96px), `var(--accent-mephisto)`, centered
- 3px crimson rule 120px wide beneath
- `PACT ESTABLISHED`: Display H1 Jost Bold 28px 0.02em UPPER, `var(--accent-scope)`, centered
- Diamond mark: 24px below, `var(--accent-active)`

**Timing:**

- Fade-in: 400ms starting at ~600ms into dock animation
- Hold: 2000ms
- Fade-out: 400ms, revealing updated dashboard

**Journal entry:** on first-dock-per-boot, server creates `pact.activated` journal entry (`SimulatorState.first_dock_this_boot` gates this).

**Preserved check:** the `state` field `first_dock_this_boot` is set to `true` at boot (see §11 state model). The ceremony fires only if this flag is true; upon firing, the server sets it to `false`.

**Acceptance:**

- [ ] Ceremony triggers only on first dock per boot
- [ ] Fade-in 400ms, hold 2s, fade-out 400ms
- [ ] `pact.activated` journal entry created
- [ ] Does not re-trigger on subsequent docks until next boot

---

## 11. State model

The client's state mirrors the server's `SimulatorState.to_dict()` output plus some view-only additions.

### 11.1 State shape

```javascript
{
  /* from server state message */
  power: 'off' | 'booting' | 'on',
  mephisto: 'disconnected' | 'connected',
  first_dock_this_boot: boolean,
  battery: { percent: number, charging: boolean },
  scope: {
    template: 'recon' | 'self-test' | 'pentesting' | null,
    description: string | null,
  },
  skills: [ /* full catalog from `skills` message */ ],

  /* derived / view-only */
  mode: 'scholar' | 'pact',          // derived from mephisto
  currentView: 'boot' | 'dashboard' | 'tool-group' | 'parameter-form'
             | 'pursuits' | 'pursuit-detail' | 'pursuit-running' | 'pursuit-complete'
             | 'journal' | 'journal-entry' | 'mephisto' | 'settings'
             | 'settings-diagnostics' | 'power-off',
  currentViewParams: { /* varies by view */ },
  viewStack: [ /* history for goBack() */ ],

  /* agent session state */
  conversation: [ /* {role, content, timestamp, key} messages */ ],
  currentToolCall: { name, params, output: [...] } | null,
  inflightCallId: string | null,
  inflightPlanId: string | null,
  currentPursuit: { pursuit_id, progress, elapsed_s, eta_s, activity: [...] } | null,

  /* recently-received phase markers (keyed by phase for coalescing) */
  phaseMarkers: {
    'catalog': { startedAt: number, visible: boolean },
    'plan':    { startedAt: number, visible: boolean },
    'replan':  { startedAt: number, visible: boolean, attempt: number },
  },
}
```

### 11.2 Mode derivation

```javascript
state.mode = state.mephisto === 'connected' ? 'pact' : 'scholar';
```

Setting this triggers the body attribute swap:

```javascript
document.body.dataset.mode = state.mode;
```

### 11.3 Trust memory

**Client does NOT implement trust memory.** It lives server-side in the `TrustCache` middleware (build plan Stage 4). Client simply renders a modal whenever the server sends a `confirmation_request`. If the server's trust window is valid, no modal is requested and the call proceeds silently.

This is intentional: the journal needs to distinguish `confirmed: fresh` from `confirmed: remembered`, and that semantic must be stamped server-side. Client-side trust would break the journal's auditability (CLAUDE.md rule 3).

### 11.4 View stack

```javascript
function pushView(name, params = {}) {
  state.viewStack.push({ name: state.currentView, params: state.currentViewParams });
  state.currentView = name;
  state.currentViewParams = params;
  render();
}

function goBack() {
  const prev = state.viewStack.pop();
  if (prev) {
    state.currentView = prev.name;
    state.currentViewParams = prev.params;
    render();
  }
}
```

Modals do not go on the view stack — they overlay and dismiss independently.

---

## 12. Animation

### 12.1 Global transition

Applied to every color-inheriting element:

```css
* {
  transition-property: background-color, border-color, color, opacity;
  transition-duration: 1000ms;
  transition-timing-function: ease-in-out;
}
```

Overridden per-component where a shorter duration is needed (see table below).

### 12.2 Specific animations

| Animation | Duration | Easing | Trigger |
|---|---|---|---|
| Screen crossfade | 200ms | ease-out | Navigation between tabs or detail drill |
| Modal open (backdrop dim) | 150ms | ease-out | Modal appears |
| Modal close | 150ms | ease-in | Modal dismissed |
| Mode palette swap | 1000ms | ease-in-out | Dock/undock |
| Mephisto tile fill-in | 1000ms | ease-in-out | Dock |
| First-pact ceremony fade-in | 400ms | ease-out | First dock per boot |
| First-pact ceremony hold | 2000ms | — | After fade-in |
| First-pact ceremony fade-out | 400ms | ease-in | After hold |
| Pursuit-complete poster hold | 2000ms | — | Pursuit finishes |
| Pursuit-complete poster fade-out | 200ms | ease-in | After hold |
| Boot log line append | 0ms (instant) | — | `boot_log` message received |
| Post-boot wordmark brighten | 600ms (ease→peak→settle) | ease-in-out | Boot complete |
| Boot to dashboard crossfade | 500ms | ease-in-out | Boot complete |

### 12.3 What NOT to animate

- No spinners anywhere
- No pulsing dots
- No hover transitions
- No parallax, no scroll-triggered motion, no decorative ambient motion
- No text-level animations except the post-boot brighten

### 12.4 Disable-all setting

Settings → Display → Animation toggles a body class `body.reduced-motion` that overrides all transitions:

```css
body.reduced-motion * {
  transition-duration: 0ms !important;
  animation-duration: 0ms !important;
}
```

Default: animations on.

---

## 13. Keyboard & hardware button mapping

Faust has six tactile buttons + a physical RF kill toggle. RF kill is hardware-only — no UI event.

**Preserved from existing:** the current UI has no hardware button handling. The rewrite adds skeleton handlers for future wiring.

**For v1:**

- **Button 1 (HOME):** always navigates to Dashboard tab
- **Button 2 (BACK):** dismisses modals if any open, else calls `goBack()`, else no-op
- **Button 6 (ACTION):** equivalent to the current screen's primary button (Start Pursuit, Confirm, Send, etc.)

Buttons 3/4/5 (SELECT, UP, DOWN): no-op in v1.

Hardware button events arrive via a new WS message type (optional): `{type: "button", button: "home"|"back"|"action"|...}`. If the backend doesn't emit these (v1 reality), the handlers are harmless no-ops.

**Dev keyboard:**

- `Escape` → Button 2 equivalent
- `Enter` → Button 6 equivalent in appropriate contexts
- `Ctrl+D` → toggle `data-mode` between scholar and pact for preview (dev-only)

---

## 14. Accessibility

- **Contrast:** all text/bg combinations meet WCAG AA (4.5:1 for 14px body, 3:1 for ≥18px). The cream-on-navy and cream-on-oxblood combinations pass comfortably. Edge case: `--ink-quiet` (#6A6558) on `--bg-primary` (#060E22) is borderline AA for 14px — acceptable for meta labels and dim secondary content but not primary messages.
- **Motion sensitivity:** disable toggle (§12.4).
- **Touch targets:** all tappable elements ≥48×48 px. Journal rows bumped to 48px tall from my earlier 40px for field use.
- **Screen readers:** not priority for v1 (single-operator touchscreen device). Add `aria-label` to icon-only buttons and tab items as cheap insurance.

---

## 15. Consolidated acceptance

**Global:**

- [ ] Fonts load without FOUT beyond boot splash
- [ ] `data-mode` drives palette globally
- [ ] Top bar + tab bar present on all screens (except boot)
- [ ] WebSocket connects at `ws://localhost:8080/ws` with reconnect

**Boot sequence:**

- [ ] Power OFF → shows POWER ON button
- [ ] POWER ON click sends `{type: "power", action: "on"}`
- [ ] Boot illustration + FAUST + Goethe + translation all render
- [ ] Hardware self-check log streams from `boot_log` messages
- [ ] Failure lines coded crimson; boot continues
- [ ] Crossfade to dashboard on completion

**Dashboard:**

- [ ] 7 radio-status tiles, correct sigils + labels + status
- [ ] Tap → tool-group screen
- [ ] Mephisto tile dim+dashed in scholar, active+solid in pact
- [ ] Session info (scholar) / activity preview (pact) visible

**Tool-group:**

- [ ] Back returns to dashboard
- [ ] Tool cards render with sensitivity pills
- [ ] Passive dispatches directly
- [ ] Parameterized opens form
- [ ] Destructive triggers confirmation

**Pursuits:**

- [ ] 8 cards (7 + Custom)
- [ ] Detail screen + parameters + START
- [ ] Running screen shows progress + elapsed + ETA + activity
- [ ] STOP works
- [ ] Completion poster → journal entry

**Journal:**

- [ ] List from `journal_entries` message
- [ ] Four filters combine via AND
- [ ] Sensitivity dots color rows
- [ ] Tap → detail
- [ ] Notes save on blur

**Mephisto conversation (pact only):**

- [ ] 50/50 split
- [ ] Six role labels color-coded
- [ ] Phase-marker events render as discrete lines
- [ ] Re-plan visually distinct
- [ ] Input submits prompts
- [ ] Tool output streams
- [ ] `body.active` toggles correctly

**Modals:**

- [ ] Destructive modal fires on `confirmation_request`
- [ ] Plan-approval modal fires on `plan_approval_request`
- [ ] Both correlate by id
- [ ] Trust window (server-side) — no modal within 10 min of same scope
- [ ] Scope change invalidates trust

**Settings:**

- [ ] Scrolls when content exceeds
- [ ] All controls functional
- [ ] Power off with confirmation
- [ ] Factory reset with confirmation
- [ ] Diagnostics sub-screens render

**Dock / ceremony:**

- [ ] Palette swap 1000ms
- [ ] Mephisto tile fills in
- [ ] First-dock ceremony triggers once per boot
- [ ] Subsequent docks silent
- [ ] Undock reverses

**Preserved behaviors:**

- [ ] Power state machine preserved (OFF → BOOTING → ON)
- [ ] Demo mode `--demo` works with updated event sequence
- [ ] Reconnect re-sends state + catalog, view rehydrates
- [ ] `body.active` hook preserved
- [ ] Sensitivity pills preserved
- [ ] Consecutive-thinking coalescing preserved
- [ ] `viewStack` + `goBack()` preserved
- [ ] Smart-default injection preserved
- [ ] 111 existing tests green (except updated `test_ui.py` assertions and extended `test_simulator_state.py`)

---

## 16. Backend integration summary (what the UI expects)

This section is reference-only; build plan stages 2–5 implement these.

### 16.1 New events on `TwoPassAgent`

```python
# faust/agent/events.py additions

@dataclass
class PlanningStarted:
    phase: Literal["catalog", "plan", "replan"]
    attempt: int = 0                     # for replan, increments each re-plan

@dataclass
class CatalogBuildStarted:
    skill_count: int

@dataclass
class ParameterizingStep:
    step: int
    of: int
    skill: str
    intent: str

@dataclass
class ParameterizingDone:
    step: int
    of: int
```

Emitted from `TwoPassAgent.run()`:

- At entry into catalog build → `CatalogBuildStarted` then `PlanningStarted(phase="catalog")`
- At start of planner call → `PlanningStarted(phase="plan")`
- Before each `_parameterize_step` call → `ParameterizingStep(...)`
- After parameterization returns → `ParameterizingDone(...)`
- On re-plan trigger → `PlanningStarted(phase="replan", attempt=N)`

Server bridges these as `planning_started` / `parameterizing_step` WS messages (with appropriate payload mapping — `CatalogBuildStarted` can be merged into `planning_started` with `phase="catalog"`).

### 16.2 Category remap

```python
# faust/agent/catalog.py — _categorize() rewrite

SIGIL_GROUP_MAP = {
    "wifi": "wifi_ble",
    "ble": "wifi_ble",
    "network": "wifi_ble",
    "nfc": "nfc",
    "rfid": "lf_rfid",
    "subghz": "sub_ghz",
    "rf": "sub_ghz",
    "ir": "ir",
    "vision": "vision",  # new category from camera/VLM skills
    "usb": "meta",
    "analysis": "meta",
    "defense": "meta",
}

def _categorize(skill) -> str:
    raw = _raw_categorize(skill)  # existing 11-category logic, renamed
    return SIGIL_GROUP_MAP.get(raw, "meta")
```

Skills emitting to `skills` WS message now have `category ∈ {wifi_ble, sub_ghz, nfc, lf_rfid, ir, vision, meta}` — exactly seven values.

### 16.3 `SimulatorState` additions

```python
# faust/ui/state.py additions

@dataclass
class SimulatorState:
    # existing fields preserved
    scope: ScopeState = field(default_factory=lambda: ScopeState(template=None, description=None))
    battery: BatteryState = field(default_factory=lambda: BatteryState(percent=82, charging=False))
    first_dock_this_boot: bool = True
    # trust memory state lives in TrustCache middleware, not here

    def to_dict(self) -> dict:
        # add new fields to serialization
        ...
```

`test_simulator_state.py` gets new cases for the dict roundtrip with scope/battery/first_dock.

### 16.4 `TrustCache` middleware

```python
# faust/agent/disclosure.py addition

class TrustCache:
    """Wraps an Approver. Auto-approves if same scope within window_s."""
    def __init__(self, inner: Approver, window_s: int = 600):
        self._inner = inner
        self._window_s = window_s
        self._last_ok: Optional[Tuple[str, float]] = None  # (scope_key, timestamp)

    async def __call__(self, tool_name, args, sensitivity) -> bool:
        scope_key = current_scope_key()  # reads from state
        now = time.monotonic()
        if (self._last_ok and self._last_ok[0] == scope_key
            and now - self._last_ok[1] < self._window_s):
            return True  # trust remembered
        result = await maybe_await(self._inner(tool_name, args, sensitivity))
        if result:
            self._last_ok = (scope_key, now)
        return result

    def invalidate(self):
        self._last_ok = None
```

Invalidated on scope change. Installed above `DisclosureApprover` in `run.py`.

Journal entries stamped `confirmed: remembered` when TrustCache auto-approves, `confirmed: fresh` when the inner DisclosureApprover runs the modal.

### 16.5 Pursuit subsystem

Full subsystem in `faust/pursuits/`:

```
faust/pursuits/
├── __init__.py
├── registry.py       # 7 + custom Pursuit definitions
├── runner.py         # execute a Pursuit, emit progress/activity/complete
├── models.py         # Pursuit dataclass, PursuitRun, PursuitResult
├── storage.py        # persist in-flight + completed Pursuits
└── pursuits/         # individual Pursuit implementations
    ├── wardrive.py
    ├── clone_credential.py
    ├── replay_subghz.py
    ├── evil_portal.py
    ├── bluetooth_recon.py
    ├── subghz_capture_analyze.py
    └── hmc_demo.py
```

Each Pursuit implements an async function that:

1. Takes params from start message
2. Emits `pursuit_progress`, `pursuit_activity` via bridge
3. May invoke existing skills through the Dispatcher (which still runs through the Approver chain — destructive steps fire confirmation modal even inside a Pursuit)
4. Emits `pursuit_complete` with a summary and journal entry id

Full detail in build plan Stage 5.

---

## 17. Implementation notes for Claude Code

### 17.1 File structure (recommended, aligns with existing layout)

```
faust/
├── faust-ui-spec.md
├── faust-sigil-spec.md
├── faust-build-plan.md
├── CLAUDE.md
├── faust/
│   ├── agent/
│   │   ├── catalog.py       # category remap
│   │   ├── disclosure.py    # + TrustCache
│   │   ├── dispatch.py      # unchanged
│   │   ├── events.py        # + PlanningStarted, ParameterizingStep, etc.
│   │   ├── twopass.py       # emit new events
│   │   └── ...
│   ├── pursuits/            # new subsystem
│   ├── ui/
│   │   ├── server.py        # + scope_change, pursuit_*, journal_query handlers
│   │   ├── run.py           # + install TrustCache, + handlers
│   │   ├── state.py         # + scope, battery, first_dock_this_boot fields
│   │   └── static/
│   │       ├── index.html   # REPLACE
│   │       ├── app.js       # REPLACE
│   │       ├── style.css    # REPLACE
│   │       └── assets/
│   │           ├── illustrations/boot-splash.png
│   │           ├── sigils/     (7 svgs)
│   │           └── fonts/      (6 woff2)
│   └── tests/               # mostly preserved; 2 modules updated
└── skills/                  # untouched
```

Server static-file handler serves everything in `faust/ui/static/`. If the existing handler doesn't already serve `assets/` subdirectories, extend it in Stage 6.

### 17.2 Build approach

No frontend build tool. Serve plain HTML/CSS/JS from `faust/ui/static/`. `style.css` can be split into multiple files (`base.css`, `components.css`, `screens.css`) at implementation discretion — concatenate via multiple `<link>` tags or keep as one big file. Either is fine.

### 17.3 State management pattern

Vanilla JS. Module-level state object. `render()` re-draws the DOM for the current view when state changes.

Minimal pattern:

```javascript
(function() {
  const state = { /* see §11.1 */ };
  let ws = null;

  function connect() {
    ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onopen = () => { /* request state */ };
    ws.onmessage = (e) => handleMessage(JSON.parse(e.data));
    ws.onclose = () => setTimeout(connect, 1000);
  }

  function handleMessage(msg) {
    switch (msg.type) {
      case 'state':                 applyState(msg); break;
      case 'boot_log':              appendBootLog(msg.line); break;
      case 'skills':                applySkills(msg.skills); break;
      case 'planning_started':      pushPhaseMarker(msg); break;
      case 'parameterizing_step':   pushParameterizing(msg); break;
      case 'plan_proposed':         /* legacy; plan_approval_request is the new path */ break;
      case 'plan_approval_request': openPlanModal(msg); break;
      case 'tool_call_proposed':    pushToolCall(msg); break;
      case 'tool_call_executed':    pushToolResult(msg); break;
      case 'confirmation_request':  openConfirmModal(msg); break;
      case 'final':                 clearInflight(msg); break;
      case 'pursuit_progress':      updatePursuit(msg); break;
      case 'pursuit_activity':      appendPursuitActivity(msg); break;
      case 'pursuit_complete':      showPursuitPoster(msg); break;
      case 'journal_entries':       renderJournal(msg); break;
      case 'error':                 showError(msg.message); break;
    }
    render();
  }

  function render() {
    document.body.dataset.mode = state.mode;
    renderCurrentView();
  }

  // ... (handlers, renderers)
  connect();
})();
```

### 17.4 WebSocket reconnect

On disconnect, attempt reconnect every 1000ms. On reconnect, server re-sends state + catalog automatically (preserved behavior). Do NOT request state manually — it arrives unsolicited.

### 17.5 Coalescing phase markers

Phase markers update in-place. Each phase has a stable key (`catalog`, `plan`, `replan-1`, `replan-2`, ...). The first occurrence pushes a chat entry with that key. Subsequent occurrences of the same phase (for counter updates) find the existing entry by key and update its content rather than appending a new row.

Tick the elapsed counter in the phase-marker row with a 1000ms `setInterval` while the phase is active. Clear the interval when a subsequent event from a different phase arrives or a `final` message fires.

### 17.6 Handling `body.active`

```javascript
function setActive(on) {
  document.body.classList.toggle('active', on);
}
```

Call `setActive(true)` on:
- `prompt` send
- `dispatch` send
- `pursuit_start`

Call `setActive(false)` on:
- `final` received
- `pursuit_complete` received
- `error` received
- manual stop/cancel

### 17.7 Chromium kiosk quirks

- Disable text selection: `user-select: none` on body; re-enable for inputs
- Disable context menu: `document.addEventListener('contextmenu', e => e.preventDefault())`
- Prevent pinch-zoom: viewport meta with `user-scalable=no`
- Hide scrollbars but allow scrolling:
  ```css
  ::-webkit-scrollbar { display: none; }
  * { scrollbar-width: none; }
  ```

### 17.8 Performance

On Pi 5 1GB with Chromium as primary memory consumer:

- No build toolchain, good
- Prefer CSS over JS animations
- Truncate journal list to last 50 entries, "load more" for older
- `will-change` sparingly on Mephisto tile, modal backdrop
- Boot splash pre-sized to display dimensions; 1024×1366 is fine, 2000×3000 wastes RAM

---

## 18. Open items / TBD

- **`TBD-palette-exact`** — pending color-picker pass (§1.1)
- **Diamond mark asset** — optional decorative element; if not extracted from boot splash, synthesize as 12×12 rotated-square SVG
- **Pre-Chromium framebuffer splash** — systemd-level, separate from UI
- **Custom Pursuit builder** — the 8th card's builder UI is v1.1 work; v1 can show a placeholder or full builder
- **Factory reset protocol** — add `factory_reset` WS message or defer to CLI-only for v1
- **Hardware button events** — spec adds a `button` WS message type; backend may not emit these in v1 reality; handlers should be harmless no-ops
- **OLED firmware spec** — separate project

---

## End of document

Length: ~13,500 words.
Version: 2.0 (reconciled against the actual codebase).
Use `faust-build-plan.md` for execution order.
