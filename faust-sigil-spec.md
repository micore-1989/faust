# Faust UI — Sigil & Dashboard Tile Spec

**Project:** Faust — Companion to `faust-ui-spec.md`
**Version:** 2.0 (aligned with 7-group category remap)

---

## 1. Purpose

Seven geometric SVG sigils, one per tool group. Rendered on dashboard radio-status tiles and throughout the app. Abstract Constructivist glyphs, not illustrations.

| SVG file | Label | Category string |
|---|---|---|
| `sigil-wifi-ble.svg` | `WIFI · BLE` | `wifi_ble` |
| `sigil-sub-ghz.svg` | `SUB-GHZ` | `sub_ghz` |
| `sigil-nfc.svg` | `NFC` | `nfc` |
| `sigil-lf-rfid.svg` | `LF RFID` | `lf_rfid` |
| `sigil-ir.svg` | `IR` | `ir` |
| `sigil-vision.svg` | `VISION` | `vision` |
| `sigil-meta.svg` | `JOURNAL` | `meta` |

Category strings match the rewritten `_categorize()` output (see UI spec §16.2, build plan Stage 3).

---

## 2. SVG source

All sigils:

- 64×64 viewBox
- `stroke="currentColor"` — CSS `color` drives rendering
- `stroke-width="2"` default
- `fill="none"` except filled geometry
- `stroke-linecap="round"` and `stroke-linejoin="round"`

Inline into HTML (not `<img>`) so state colors work via `color` inheritance.

### 2.1 `sigil-wifi-ble.svg`

Broadcast tower + three concentric arcs.

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <line x1="32" y1="38" x2="32" y2="54"/>
  <line x1="26" y1="54" x2="38" y2="54"/>
  <path d="M 24 32 Q 32 26 40 32"/>
  <path d="M 20 32 Q 32 22 44 32"/>
  <path d="M 16 32 Q 32 18 48 32"/>
  <circle cx="32" cy="34" r="2" fill="currentColor" stroke="none"/>
</svg>
```

### 2.2 `sigil-sub-ghz.svg`

Vertical antenna + three expanding horizontal ellipses.

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <line x1="32" y1="18" x2="32" y2="50"/>
  <line x1="24" y1="50" x2="40" y2="50"/>
  <ellipse cx="32" cy="18" rx="8"  ry="3"/>
  <ellipse cx="32" cy="18" rx="14" ry="5"/>
  <ellipse cx="32" cy="18" rx="20" ry="7"/>
  <circle cx="32" cy="18" r="1.5" fill="currentColor" stroke="none"/>
</svg>
```

### 2.3 `sigil-nfc.svg`

Card outline + chip + two corner arcs.

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="16" y="22" width="32" height="20" rx="0"/>
  <rect x="22" y="28" width="8" height="8"/>
  <path d="M 52 20 Q 56 24 52 28"/>
  <path d="M 56 16 Q 62 24 56 32"/>
</svg>
```

### 2.4 `sigil-lf-rfid.svg`

Card + key silhouette overlay.

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="10" y="22" width="32" height="20" rx="0"/>
  <circle cx="50" cy="32" r="6"/>
  <circle cx="50" cy="32" r="2" fill="currentColor" stroke="none"/>
  <line x1="44" y1="32" x2="30" y2="32"/>
  <line x1="34" y1="32" x2="34" y2="36"/>
  <line x1="38" y1="32" x2="38" y2="35"/>
</svg>
```

### 2.5 `sigil-ir.svg`

Emitter + dashed beam + target dot.

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="8" y="26" width="14" height="12" rx="0"/>
  <circle cx="22" cy="32" r="2" fill="currentColor" stroke="none"/>
  <line x1="26" y1="32" x2="50" y2="32" stroke-dasharray="3 3"/>
  <circle cx="54" cy="32" r="3"/>
  <circle cx="54" cy="32" r="1" fill="currentColor" stroke="none"/>
</svg>
```

### 2.6 `sigil-vision.svg`

Concentric circles forming a stylized lens.

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="32" cy="32" r="20"/>
  <circle cx="32" cy="32" r="12"/>
  <circle cx="32" cy="32" r="5" fill="currentColor" stroke="none"/>
</svg>
```

### 2.7 `sigil-meta.svg`

Open book with spine and title band.

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M 10 16 L 32 20 L 54 16 L 54 48 L 32 52 L 10 48 Z"/>
  <line x1="32" y1="20" x2="32" y2="52"/>
  <line x1="14" y1="26" x2="28" y2="28"/>
  <line x1="14" y1="30" x2="28" y2="32"/>
  <line x1="36" y1="28" x2="50" y2="26"/>
  <line x1="36" y1="32" x2="50" y2="30"/>
</svg>
```

---

## 3. Rendering sizes

| Size | Usage |
|---|---|
| 48×48 | Dashboard radio-status tiles |
| 24×24 | Tool-group screen header (next to Display H1 title) |
| 20×20 | Journal filter chip when filtered to a group |
| 16×16 | Small inline contexts (rare) |

```css
.sigil { width: 48px; height: 48px; display: inline-block; }
.sigil > svg { width: 100%; height: 100%; }
```

---

## 4. Dashboard radio-status tile component

Canonical spec for the tile that consumes sigils.

### 4.1 Layout

```
┌──────────────────────┐
│                      │
│        [SIGIL]       │   48×48, centered, 24px from top
│                      │
│       WIFI · BLE     │   Meta Label
│                      │
│      ● active        │   Mono S + status dot
│      42 networks     │   Mono S summary (optional)
│                      │
└──────────────────────┘
```

Tile dimensions: ~172×130px (7 tiles with 4px gaps in 1208px available).

### 4.2 States

**Idle:**

- Background `var(--bg-secondary)`
- Border 0.5px solid `var(--tile-border)`
- Sigil color `var(--ink-secondary)`
- Label `var(--ink-primary)`
- Status dot `var(--dot-idle)`, text `idle` in `var(--ink-tertiary)`

**Active:**

- Border 0.5px solid `var(--accent-active)`
- Sigil color `var(--accent-active)`
- Status dot `var(--accent-active)`, text in `var(--ink-primary)`

**Disabled** (via Settings → Radio):

- Opacity 0.4, border dashed, sigil/label `var(--ink-quiet)`
- `cursor: not-allowed`; tap no-op

**Error** (hardware failing):

- Border 0.5px solid `var(--accent-crimson)`
- Sigil color `var(--accent-crimson)`
- Status dot `var(--accent-crimson)`, text `error` in `var(--accent-crimson)`
- Tap opens tool-group with diagnostic banner at top

### 4.3 HTML + CSS

```html
<button class="radio-tile radio-tile--idle" data-group="wifi_ble">
  <div class="radio-tile__sigil"><!-- inlined SVG --></div>
  <div class="radio-tile__label">WIFI · BLE</div>
  <div class="radio-tile__status">
    <span class="dot dot--idle"></span><span>idle</span>
  </div>
  <div class="radio-tile__summary">hardware ready</div>
</button>
```

```css
.radio-tile {
  background: var(--bg-secondary);
  border: 0.5px solid var(--tile-border);
  padding: 24px 12px 16px;
  cursor: pointer;
  color: var(--ink-primary);
  text-align: center;
  display: flex; flex-direction: column; align-items: center;
}
.radio-tile:active { background: var(--bg-deep); }
.radio-tile__sigil { width: 48px; height: 48px; color: var(--ink-secondary); margin-bottom: 12px; }
.radio-tile__label { font: 700 11px/1.2 'Jost'; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-primary); margin-bottom: 16px; }
.radio-tile__status { font: 400 11px/1.4 'JetBrains Mono'; color: var(--ink-tertiary); }
.radio-tile__summary { font: 400 11px/1.4 'JetBrains Mono'; color: var(--ink-tertiary); margin-top: 4px; }

.radio-tile--active { border-color: var(--accent-active); }
.radio-tile--active .radio-tile__sigil { color: var(--accent-active); }
.radio-tile--active .radio-tile__status { color: var(--ink-primary); }

.radio-tile--disabled { opacity: 0.4; cursor: not-allowed; border-style: dashed; }
.radio-tile--disabled .radio-tile__sigil,
.radio-tile--disabled .radio-tile__label { color: var(--ink-quiet); }

.radio-tile--error { border-color: var(--accent-crimson); }
.radio-tile--error .radio-tile__sigil,
.radio-tile--error .radio-tile__status { color: var(--accent-crimson); }
```

---

## 5. Acceptance

- [ ] Seven SVGs saved to `faust/ui/static/assets/sigils/`
- [ ] All use `stroke="currentColor"` and inline cleanly
- [ ] Legible at 48×48 and 24×24
- [ ] Tile component renders all four states
- [ ] State colors key off palette variables (mode-reactive)
- [ ] Category strings match backend output
- [ ] No rounded corners on tile
- [ ] Touch-press feedback works

---

## End of document
