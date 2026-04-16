/**
 * Faust UI — Stage 6 shell scaffolding.
 *
 * Wires the WebSocket + power state machine + top/tab bars + view stack.
 * Screen contents are placeholders filled in by later stages:
 *     Stage 7  — boot sequence
 *     Stage 8  — dashboard / tool-group / parameter-form
 *     Stage 9  — confirmation + plan-approval modals (removes auto-reject)
 *     Stage 10 — Mephisto conversation view
 *     Stage 11 — Pursuits, Journal, Settings, demo mode
 *
 * Invariants preserved:
 *   - WS reconnect every 1000ms on close (spec §17.4)
 *   - Server re-sends `state` + `skills` on connect; client does NOT request
 *   - confirmation / plan_approval replies go back within seconds so the
 *     server's queue-backed approvers don't hang (Stage 6 auto-rejects with
 *     a clearly-labelled shim — MUST be removed in Stage 9)
 *   - `body.active` hook toggled on prompt/dispatch/pursuit_start and
 *     released on final / pursuit_complete / error
 *   - contextmenu prevented (kiosk)
 */

(function () {
  "use strict";

  // ── Smart defaults for parameter fields ──────────────────────
  // Consumed by Stage 8's dispatch flow; kept here as a module-level
  // constant so the table is one-source-of-truth across the refactor.
  const SMART_DEFAULTS = {
    interface: "wlan1mon",
    duration_s: 30,
    timeout_s: 10,
    channel: 6,
    band: "all",
    count: 5,
    threads: 10,
    wordlist: "common",
    sample_rate: 2000000,
    repeat: 3,
    typing_speed_wpm: 400,
    delay_ms: 500,
    timing: 3,
    threshold_db: 15,
    threshold: 5,
  };

  // ── Goethe quote pool (spec §10.1.1) ─────────────────────────
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

  function pickGoetheLine() {
    const lastIndex = parseInt(localStorage.getItem("faustBootQuote") ?? "-1", 10);
    let next;
    do {
      next = Math.floor(Math.random() * GOETHE_LINES.length);
    } while (GOETHE_LINES.length > 1 && next === lastIndex);
    localStorage.setItem("faustBootQuote", String(next));
    return GOETHE_LINES[next];
  }

  // ── Boot-screen session flags ────────────────────────────────
  // hasReceivedInitialState distinguishes fresh page load (first state msg)
  // from live transitions. bootAnimationInProgress prevents double-trigger
  // if a second `state{power:on}` arrives during the fade-out window.
  // bootSessionQuote caches the current boot's Goethe pick so repeated
  // renders don't flicker the line.
  let hasReceivedInitialState = false;
  let bootAnimationInProgress = false;
  let bootSessionQuote = null;

  // ── Stage 8 session / sigil caches ───────────────────────────
  // SIGILS: inlined SVG sources keyed by sigil-spec §4 category slug
  //   (wifi_ble | sub_ghz | nfc | lf_rfid | ir | vision | meta).
  //   Inlined (not <img>) so stroke="currentColor" picks up tile color.
  // sessionStartedAt: first moment state.power transitions to "on" in
  //   this JS session — used by the scholar-mode dashboard session panel.
  // viewDirty: set when the currently-visible view needs a DOM rebuild.
  //   Clock-tick renders do NOT flip this, so form input / scroll
  //   position survives the 1-Hz refresh.
  const SIGILS = {};
  const SIGIL_GROUPS = ["wifi_ble", "sub_ghz", "nfc", "lf_rfid", "ir", "vision", "meta"];
  let sessionStartedAt = null;
  let viewDirty = true;
  function markViewDirty() { viewDirty = true; }

  async function loadSigils() {
    const loads = SIGIL_GROUPS.map(async (g) => {
      const slug = g.replace("_", "-");
      try {
        const res = await fetch(`/assets/sigils/sigil-${slug}.svg`);
        SIGILS[g] = await res.text();
      } catch (err) {
        console.warn(`[sigils] failed to load ${g}`, err);
        SIGILS[g] = "";
      }
    });
    await Promise.all(loads);
    markViewDirty();
    render();
  }

  const RADIO_LABELS = {
    wifi_ble: "WIFI · BLE",
    sub_ghz:  "SUB-GHZ",
    nfc:      "NFC",
    lf_rfid:  "LF RFID",
    ir:       "IR",
    vision:   "VISION",
    meta:     "JOURNAL",
  };

  // ── State (spec §11.1) ───────────────────────────────────────
  const state = {
    power: "off",                    // off | booting | on
    mephisto: "disconnected",        // disconnected | connected
    boot_progress: 0,
    first_dock_this_boot: true,
    battery: { percent: 82, charging: false },
    scope: { template: null, description: null },
    active_pursuits: [],
    skills: [],
    journalEntries: [],
    mode: "scholar",                 // derived from mephisto
    currentView: "dashboard",
    currentTab: "dashboard",
    currentViewParams: {},
    viewStack: [],
    conversation: [],                // used by Stage 10
    currentToolCall: null,           // used by Stage 10
    active: false,                   // body.active hook
  };

  // ── DOM refs ─────────────────────────────────────────────────
  const $ = (id) => document.getElementById(id);
  const powerOffScreen = $("power-off-screen");
  const bootScreen = $("boot-screen");
  const appShell = $("app-shell");
  const modeLabel = $("mode-label");
  const scopeLabel = $("scope-label");
  const topMeta = $("top-meta");

  // ── WebSocket with reconnect (spec §17.4) ────────────────────
  let ws = null;
  let reconnectTimer = null;

  function connect() {
    ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onopen = () => {
      clearTimeout(reconnectTimer);
      console.log("[ws] open");
    };
    ws.onmessage = (e) => {
      try {
        handleMessage(JSON.parse(e.data));
      } catch (err) {
        console.error("[ws] bad payload", err, e.data);
      }
    };
    ws.onclose = () => {
      console.log("[ws] close — reconnecting in 1s");
      reconnectTimer = setTimeout(connect, 1000);
    };
    ws.onerror = (e) => { console.warn("[ws] error", e); };
  }

  function send(obj) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(obj));
    } else {
      console.warn("[ws] send dropped (socket not open)", obj);
    }
  }

  // ── Server-message routing ───────────────────────────────────
  function handleMessage(msg) {
    console.log("[ws]", msg.type, JSON.stringify(msg).slice(0, 200));

    switch (msg.type) {
      case "state":
        applyServerState(msg);
        break;

      case "skills":
        state.skills = msg.skills || [];
        console.log("[ws] received", state.skills.length, "skills");
        markViewDirty();
        break;

      case "boot_log":
        appendBootLogLine(msg.line ?? "");
        break;

      // ── Agent phase markers (Stage 10 renders) ──
      case "planning_started":
      case "parameterizing_step":
      case "thinking":
        break;

      // ── Agent tool / plan events (Stage 10 renders plans) ──
      case "plan_proposed":
        break;

      case "tool_call_proposed":
        // Track the in-flight call so the radio-tile for its category
        // can render in the "active" state (sigil spec §4.2).
        state.currentToolCall = {
          call_id: msg.call_id,
          name: msg.tool_name,
          args: msg.arguments || {},
        };
        markViewDirty();
        break;

      case "tool_call_executed":
        // Mid-plan executions are NOT terminal — a multi-step plan emits
        // several of these before `final`. Do not release body.active here;
        // the release happens on `final`. Stage 8 uses the event only to
        // clear the per-tile "active" marker when the current call completes.
        if (state.currentToolCall) {
          const matchesId = msg.call_id && state.currentToolCall.call_id === msg.call_id;
          const matchesName = !msg.call_id && state.currentToolCall.name === msg.tool_name;
          if (matchesId || matchesName) {
            state.currentToolCall = null;
            markViewDirty();
          }
        }
        break;

      case "final":
        setActive(false);
        state.currentToolCall = null;
        markViewDirty();
        break;

      // ── Approval requests ──
      // STAGE 6 AUTO-REJECT: auto-reject these after 2s so the server's
      // queue-backed approvers don't hang while the real modals are still
      // being built. MUST be removed in Stage 9 when UIConfirmationModal
      // and UIPlanApprovalModal land.
      case "confirmation_request":
        console.warn("[STAGE 6 AUTO-REJECT] confirmation_request", msg);
        setTimeout(() => {
          send({ type: "confirmation", call_id: msg.call_id, approved: false });
        }, 2000);
        break;

      case "plan_approval_request":
        console.warn("[STAGE 6 AUTO-REJECT] plan_approval_request", msg);
        setTimeout(() => {
          send({ type: "plan_approval", plan_id: msg.plan_id, approved: false });
        }, 2000);
        break;

      // ── Pursuit events (Stage 11 renders) ──
      case "pursuit_progress":
      case "pursuit_activity":
        break;
      case "pursuit_stopped":
      case "pursuit_complete":
        setActive(false);
        break;

      // ── Journal ──
      case "journal_entries":
        state.journalEntries = msg.entries || [];
        console.log("[ws] received", state.journalEntries.length, "journal entries");
        markViewDirty();
        break;

      case "error":
        console.error("[server error]", msg.message);
        setActive(false);
        break;

      default:
        console.warn("[ws] unhandled message type:", msg.type, msg);
    }

    render();
  }

  // ── Boot-screen helpers (spec §10.1) ─────────────────────────

  function initBootScreen() {
    // Rebuilds the boot-screen DOM, picks a fresh Goethe line, and
    // clears any stale animation state. Called when power enters the
    // booting state — either as a live transition or as the initial
    // state message from a page load that happened mid-boot.
    bootAnimationInProgress = false;
    bootScreen.classList.remove("boot-fading");

    const quote = pickGoetheLine();
    bootSessionQuote = quote;

    bootScreen.innerHTML = "";

    const layout = document.createElement("div");
    layout.className = "boot-layout";

    const img = document.createElement("img");
    img.className = "boot-splash";
    img.src = "/assets/illustrations/boot-splash.png";
    img.alt = "";
    layout.appendChild(img);

    const wordmark = document.createElement("h1");
    wordmark.className = "boot-wordmark type-wordmark-xl";
    wordmark.textContent = "FAUST";
    layout.appendChild(wordmark);

    const quoteBox = document.createElement("div");
    quoteBox.className = "boot-quote";
    const de = document.createElement("div");
    de.className = "boot-quote__de";
    de.textContent = quote.de;
    const en = document.createElement("div");
    en.className = "boot-quote__en";
    en.textContent = quote.en;
    quoteBox.appendChild(de);
    quoteBox.appendChild(en);
    layout.appendChild(quoteBox);

    const log = document.createElement("pre");
    log.className = "boot-log";
    log.id = "boot-log";
    layout.appendChild(log);

    bootScreen.appendChild(layout);
  }

  function resetBootScreen() {
    bootAnimationInProgress = false;
    bootSessionQuote = null;
    bootScreen.classList.remove("boot-fading");
  }

  function appendBootLogLine(line) {
    const bootLogEl = document.getElementById("boot-log");
    if (!bootLogEl) return;

    const lineEl = document.createElement("span");
    lineEl.className = "boot-log__line";

    const match = line.match(/^(\[\s*(ok|fail|warn)\s*\])(.*)$/i);
    if (match) {
      const prefix = match[1];
      const status = match[2].toLowerCase();
      const rest = match[3];

      const prefixSpan = document.createElement("span");
      prefixSpan.className = `boot-log__prefix boot-log__prefix--${status}`;
      prefixSpan.textContent = prefix;
      lineEl.appendChild(prefixSpan);

      const contentSpan = document.createElement("span");
      contentSpan.className = "boot-log__content" + (status === "fail" ? " boot-log__content--fail" : "");
      contentSpan.textContent = rest;
      lineEl.appendChild(contentSpan);
    } else {
      lineEl.textContent = line;
    }

    bootLogEl.appendChild(lineEl);
    bootLogEl.appendChild(document.createTextNode("\n"));
    bootLogEl.scrollTop = bootLogEl.scrollHeight;
  }

  function startBootCompletionAnimation() {
    if (bootAnimationInProgress) return;
    bootAnimationInProgress = true;

    const wordmark = bootScreen.querySelector(".boot-wordmark");
    if (wordmark) {
      wordmark.classList.add("boot-wordmark--bright");
      setTimeout(() => wordmark.classList.remove("boot-wordmark--bright"), 300);
    }

    setTimeout(() => {
      bootScreen.classList.add("boot-fading");
    }, 600);

    setTimeout(() => {
      bootAnimationInProgress = false;
      render();
    }, 1100);
  }

  // ── Stage 8 helpers ──────────────────────────────────────────

  function categoryOf(skillName) {
    const s = state.skills.find((t) => t.name === skillName);
    return s ? s.category : "meta";
  }

  // Server sends JSON-Schema objects: { properties: {...}, required: [...] }.
  // Every accessor goes through this helper so a missing / ill-formed
  // schema degrades to "no params" rather than a crash.
  function schemaProps(skill) {
    return (skill && skill.parameters_schema && skill.parameters_schema.properties) || {};
  }
  function schemaRequired(skill) {
    const r = skill && skill.parameters_schema && skill.parameters_schema.required;
    return Array.isArray(r) ? new Set(r) : new Set();
  }

  function injectSmartDefaults(skill) {
    const defaults = {};
    const props = schemaProps(skill);
    for (const key of Object.keys(props)) {
      if (key in SMART_DEFAULTS) defaults[key] = SMART_DEFAULTS[key];
    }
    return defaults;
  }

  function dispatchSkill(skillName, args) {
    setActive(true);
    send({ type: "dispatch", skill: skillName, args });
  }

  function onToolCardClick(skill) {
    const props = schemaProps(skill);
    const keys = Object.keys(props);
    const defaults = injectSmartDefaults(skill);
    const required = schemaRequired(skill);
    // Open the form unless (a) the skill has zero parameters, or
    // (b) every required parameter is covered by SMART_DEFAULTS.
    const noParams = keys.length === 0;
    const requiredAllDefaulted =
      required.size > 0 && [...required].every((k) => k in defaults);
    if (noParams || requiredAllDefaulted) {
      dispatchSkill(skill.name, defaults);
    } else {
      pushView("parameter-form", { skill, prefilledArgs: defaults });
    }
  }

  // ── Dashboard (spec §10.2) ───────────────────────────────────

  function renderRadioTile(group) {
    const skillsInGroup = state.skills.filter((s) => s.category === group);
    const count = skillsInGroup.length;
    const active =
      state.currentToolCall && categoryOf(state.currentToolCall.name) === group;
    const disabled = count === 0;

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "radio-tile";
    btn.dataset.group = group;
    if (active) btn.classList.add("radio-tile--active");
    if (disabled) btn.classList.add("radio-tile--disabled");

    const sigil = document.createElement("div");
    sigil.className = "radio-tile__sigil";
    sigil.innerHTML = SIGILS[group] || "";
    btn.appendChild(sigil);

    const label = document.createElement("div");
    label.className = "radio-tile__label";
    label.textContent = RADIO_LABELS[group] || group.toUpperCase();
    btn.appendChild(label);

    const status = document.createElement("div");
    status.className = "radio-tile__status";
    const dot = document.createElement("span");
    dot.className = "dot " + (active ? "dot--active" : "dot--idle");
    const statusText = document.createElement("span");
    statusText.textContent = disabled ? "disabled" : (active ? "running" : "idle");
    status.appendChild(dot);
    status.appendChild(statusText);
    btn.appendChild(status);

    const summary = document.createElement("div");
    summary.className = "radio-tile__summary";
    if (disabled) summary.textContent = "no tools available";
    else if (active) summary.textContent = state.currentToolCall.name;
    else summary.textContent = `${count} tool${count === 1 ? "" : "s"} available`;
    btn.appendChild(summary);

    btn.addEventListener("click", () => {
      if (disabled) return;
      pushView("tool-group", { group });
    });
    return btn;
  }

  function renderMephistoTile() {
    const tile = document.createElement("div");
    tile.className = "mephisto-tile";

    const brand = document.createElement("div");
    brand.className = "mephisto-tile__brand";
    brand.textContent = "MEPHISTO";
    tile.appendChild(brand);

    const status = document.createElement("div");
    status.className = "mephisto-tile__status";
    status.textContent = state.mephisto === "connected"
      ? "ONLINE · QWEN2.5-VL-3B · 8.4 T/S"
      : "AWAITING DOCK";
    tile.appendChild(status);

    const rule = document.createElement("div");
    rule.className = "mephisto-tile__rule";
    tile.appendChild(rule);

    if (state.mephisto === "connected") {
      tile.addEventListener("click", () => pushView("mephisto", {}));
    }
    return tile;
  }

  function renderSessionInfo() {
    const panel = document.createElement("div");
    panel.className = "session-info";

    if (state.mephisto === "connected") {
      // Activity preview — last Mephisto utterance (populated in Stage 10).
      const header = document.createElement("div");
      header.className = "session-info__pact-header";
      const lbl = document.createElement("span");
      lbl.className = "session-info__pact-label";
      lbl.textContent = "MEPHISTO";
      const hint = document.createElement("span");
      hint.className = "session-info__pact-hint";
      hint.textContent = "→ TAP TO OPEN";
      header.appendChild(lbl);
      header.appendChild(hint);
      panel.appendChild(header);

      const rule = document.createElement("div");
      rule.className = "session-info__pact-rule";
      panel.appendChild(rule);

      const body = document.createElement("div");
      body.className = "session-info__pact-body";
      const last = [...state.conversation]
        .reverse()
        .find((m) => m && m.role === "assistant" && m.content);
      if (last) {
        body.classList.add("session-info__pact-body--has-text");
        body.textContent = last.content;
      } else {
        body.textContent = "No recent activity.";
      }
      panel.appendChild(body);

      panel.addEventListener("click", () => pushView("mephisto", {}));
      return panel;
    }

    // Scholar mode: session stats.
    const rows = [
      ["SESSION STARTED", sessionStartedAt ? formatHHMM(sessionStartedAt) : "—"],
      [
        "TOOLS INVOKED",
        String(
          (state.journalEntries || []).filter((e) => e && e.type === "tool_invocation").length
        ),
      ],
      ["JOURNAL ENTRIES", String((state.journalEntries || []).length)],
      ["CURRENT SCOPE", formatScopeForSession(state.scope)],
    ];
    for (const [k, v] of rows) {
      const row = document.createElement("div");
      row.className = "session-info__row";
      const key = document.createElement("span");
      key.className = "session-info__key";
      key.textContent = k;
      const val = document.createElement("span");
      val.className = "session-info__val";
      val.textContent = v;
      row.appendChild(key);
      row.appendChild(val);
      panel.appendChild(row);
    }
    return panel;
  }

  function formatScopeForSession(scope) {
    if (!scope || scope.template == null) return "NO SCOPE";
    const t = String(scope.template).toUpperCase();
    if (scope.template === "pentesting" && scope.description) {
      const d = scope.description;
      return "PENTESTING · " + (d.length > 20 ? d.slice(0, 17) + "…" : d);
    }
    return t;
  }

  function formatHHMM(d) {
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return `${hh}:${mm}`;
  }

  function renderDashboard(screen) {
    screen.innerHTML = "";

    const wrap = document.createElement("div");
    wrap.className = "dashboard";

    const strip = document.createElement("div");
    strip.className = "radio-strip";
    for (const g of SIGIL_GROUPS) strip.appendChild(renderRadioTile(g));
    wrap.appendChild(strip);

    const bottom = document.createElement("div");
    bottom.className = "dashboard-bottom";
    bottom.appendChild(renderMephistoTile());
    bottom.appendChild(renderSessionInfo());
    wrap.appendChild(bottom);

    screen.appendChild(wrap);
  }

  // ── Tool-group screen (spec §10.3) ───────────────────────────

  function renderToolGroup(screen) {
    const group = state.currentViewParams.group;
    if (!group) { screen.innerHTML = ""; return; }
    const skillsInGroup = state.skills.filter((s) => s.category === group);

    screen.innerHTML = "";

    const wrap = document.createElement("div");
    wrap.className = "tool-group";

    const back = document.createElement("button");
    back.type = "button";
    back.className = "back-btn";
    back.innerHTML = '<i class="ph ph-arrow-left"></i><span>BACK</span>';
    back.addEventListener("click", () => goBack());
    wrap.appendChild(back);

    const header = document.createElement("div");
    header.className = "tool-group__header";
    const sigilBox = document.createElement("div");
    sigilBox.className = "tool-group__sigil";
    sigilBox.innerHTML = SIGILS[group] || "";
    header.appendChild(sigilBox);
    const title = document.createElement("h1");
    title.className = "tool-group__title type-h1";
    title.textContent = RADIO_LABELS[group] || group.toUpperCase();
    header.appendChild(title);
    wrap.appendChild(header);

    const rule = document.createElement("div");
    rule.className = "rule-heavy--short";
    wrap.appendChild(rule);

    const availableLabel = document.createElement("h3");
    availableLabel.className = "type-h3";
    availableLabel.textContent = "Available tools";
    wrap.appendChild(availableLabel);

    const cards = document.createElement("div");
    cards.className = "tool-cards";
    for (const skill of skillsInGroup) cards.appendChild(renderToolCard(skill));
    wrap.appendChild(cards);

    const recentLabel = document.createElement("h3");
    recentLabel.className = "type-h3";
    recentLabel.textContent = "Recent activity";
    wrap.appendChild(recentLabel);
    wrap.appendChild(renderRecentActivity(group));

    screen.appendChild(wrap);
  }

  function renderToolCard(skill) {
    const destructive = skill.sensitivity === "disruptive" || skill.sensitivity === "active";

    const card = document.createElement("button");
    card.type = "button";
    card.className = "tool-card";
    if (destructive) card.classList.add("tool-card--destructive");
    card.dataset.skill = skill.name;

    const header = document.createElement("div");
    header.className = "tool-card__header";
    const name = document.createElement("span");
    name.className = "tool-card__name";
    name.textContent = skill.name;
    header.appendChild(name);
    const pill = document.createElement("span");
    pill.className = `sensitivity-pill sensitivity-pill--${skill.sensitivity || "passive"}`;
    pill.textContent = (skill.sensitivity || "passive").toUpperCase();
    header.appendChild(pill);
    card.appendChild(header);

    const desc = document.createElement("div");
    desc.className = "tool-card__desc";
    desc.textContent = skill.description || "";
    card.appendChild(desc);

    const meta = document.createElement("div");
    meta.className = "tool-card__meta";
    const active = state.currentToolCall && state.currentToolCall.name === skill.name;
    const dot = document.createElement("span");
    dot.className = "dot " + (active ? "dot--active" : "dot--idle");
    meta.appendChild(dot);
    meta.appendChild(document.createTextNode(active ? "running" : "ready"));
    card.appendChild(meta);

    card.addEventListener("click", () => onToolCardClick(skill));
    return card;
  }

  function renderRecentActivity(group) {
    const box = document.createElement("div");
    box.className = "recent-activity";
    const entries = (state.journalEntries || []).filter(
      (e) => e && e.tool_name && categoryOf(e.tool_name) === group,
    );
    if (entries.length === 0) {
      const empty = document.createElement("div");
      empty.className = "recent-activity__empty";
      empty.textContent = "No recent activity";
      box.appendChild(empty);
      return box;
    }
    for (const e of entries.slice(0, 10)) {
      const row = document.createElement("div");
      row.className = "recent-activity__row";
      const destructive = e.sensitivity === "disruptive" || e.sensitivity === "active";
      if (destructive) row.classList.add("recent-activity__row--destructive");

      const time = document.createElement("span");
      time.className = "recent-activity__time";
      time.textContent = e.time_hhmm || "";
      const tool = document.createElement("span");
      tool.className = "recent-activity__tool";
      tool.textContent = e.tool_name || "";
      const result = document.createElement("span");
      result.className = "recent-activity__result";
      result.textContent = e.summary || "";
      row.appendChild(time);
      row.appendChild(tool);
      row.appendChild(result);
      box.appendChild(row);
    }
    return box;
  }

  // ── Parameter-form screen (spec §10.3.1) ─────────────────────

  function renderParameterForm(screen) {
    const skill = state.currentViewParams.skill;
    if (!skill) { screen.innerHTML = ""; return; }

    // Guard: if we already built the form for this exact skill visit,
    // don't rebuild — that would clobber any edits the operator has
    // typed into the fields. Visits push a fresh view, so data-skill
    // only changes when we're landing on a new skill.
    if (screen.dataset.builtFor === skill.name) return;

    screen.innerHTML = "";
    screen.dataset.builtFor = skill.name;

    const wrap = document.createElement("div");
    wrap.className = "parameter-form";

    const back = document.createElement("button");
    back.type = "button";
    back.className = "back-btn";
    back.innerHTML = '<i class="ph ph-arrow-left"></i><span>BACK</span>';
    back.addEventListener("click", () => goBack());
    wrap.appendChild(back);

    const titleRow = document.createElement("div");
    titleRow.className = "parameter-form__title-row";
    const title = document.createElement("h2");
    title.className = "type-h2";
    title.textContent = skill.name;
    titleRow.appendChild(title);
    const pill = document.createElement("span");
    pill.className = `sensitivity-pill sensitivity-pill--${skill.sensitivity || "passive"}`;
    pill.textContent = (skill.sensitivity || "passive").toUpperCase();
    titleRow.appendChild(pill);
    wrap.appendChild(titleRow);

    const rule = document.createElement("div");
    rule.className = "rule-heavy--short";
    wrap.appendChild(rule);

    if (skill.description) {
      const desc = document.createElement("p");
      desc.className = "parameter-form__desc type-body-l";
      desc.textContent = skill.description;
      wrap.appendChild(desc);
    }

    const paramsLabel = document.createElement("h3");
    paramsLabel.className = "type-h3";
    paramsLabel.textContent = "Parameters";
    wrap.appendChild(paramsLabel);

    const form = document.createElement("form");
    form.className = "parameter-form__fields";
    form.addEventListener("submit", (e) => e.preventDefault());

    const prefilled = state.currentViewParams.prefilledArgs || {};
    renderFormFields(skill.parameters_schema || {}, prefilled, form);
    wrap.appendChild(form);

    const actions = document.createElement("div");
    actions.className = "parameter-form__actions";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "btn-secondary";
    cancel.textContent = "CANCEL";
    cancel.addEventListener("click", () => goBack());
    const invoke = document.createElement("button");
    invoke.type = "button";
    invoke.className = "btn-primary";
    invoke.textContent = "INVOKE ▶";
    invoke.addEventListener("click", () => {
      const args = collectFormArgs(skill.parameters_schema || {}, form);
      dispatchSkill(skill.name, args);
      goBack();
    });
    actions.appendChild(cancel);
    actions.appendChild(invoke);
    wrap.appendChild(actions);

    screen.appendChild(wrap);
  }

  function renderFormFields(schema, prefilledArgs, container) {
    const props = schema.properties || {};
    for (const [key, spec] of Object.entries(props)) {
      const row = document.createElement("div");
      row.className = "param-row";

      const label = document.createElement("label");
      label.textContent = key;
      row.appendChild(label);

      const current = key in prefilledArgs ? prefilledArgs[key] : spec.default;
      let input;

      if (Array.isArray(spec.enum)) {
        input = document.createElement("div");
        input.className = "segmented";
        input.dataset.name = key;
        const initial = current ?? spec.enum[0];
        for (const choice of spec.enum) {
          const b = document.createElement("button");
          b.type = "button";
          b.textContent = String(choice);
          b.className = "segmented__btn";
          if (String(choice) === String(initial)) b.classList.add("segmented__btn--active");
          b.addEventListener("click", () => {
            input.querySelectorAll(".segmented__btn").forEach((x) =>
              x.classList.remove("segmented__btn--active"),
            );
            b.classList.add("segmented__btn--active");
            input.dataset.value = String(choice);
          });
          input.appendChild(b);
        }
        input.dataset.value = String(initial);
      } else if (spec.type === "boolean") {
        input = document.createElement("div");
        input.className = "toggle";
        input.dataset.name = key;
        const initial = current === true || current === "true";
        input.dataset.value = String(initial);
        if (initial) input.classList.add("toggle--on");
        input.addEventListener("click", () => {
          const on = input.dataset.value !== "true";
          input.dataset.value = String(on);
          input.classList.toggle("toggle--on", on);
        });
      } else if (spec.type === "integer" || spec.type === "number") {
        input = document.createElement("input");
        input.type = "number";
        input.name = key;
        input.dataset.name = key;
        input.dataset.ptype = spec.type;
        if (current != null) input.value = current;
      } else {
        input = document.createElement("input");
        input.type = "text";
        input.name = key;
        input.dataset.name = key;
        input.dataset.ptype = spec.type || "string";
        if (current != null) input.value = current;
        if (spec.type) input.placeholder = spec.type;
      }
      row.appendChild(input);

      if (spec.description) {
        const hint = document.createElement("div");
        hint.className = "param-row__hint";
        hint.textContent = spec.description;
        row.appendChild(hint);
      }
      container.appendChild(row);
    }
  }

  function collectFormArgs(schema, container) {
    const args = {};
    const props = schema.properties || {};
    for (const [key, spec] of Object.entries(props)) {
      const el = container.querySelector(`[data-name="${CSS.escape(key)}"]`);
      if (!el) continue;
      if (Array.isArray(spec.enum)) {
        args[key] = el.dataset.value;
      } else if (spec.type === "boolean") {
        args[key] = el.dataset.value === "true";
      } else if (spec.type === "integer") {
        const n = Number(el.value);
        if (el.value !== "" && !Number.isNaN(n)) args[key] = Math.round(n);
      } else if (spec.type === "number") {
        const n = Number(el.value);
        if (el.value !== "" && !Number.isNaN(n)) args[key] = n;
      } else {
        if (el.value !== "") args[key] = el.value;
      }
    }
    return args;
  }

  // ── View dispatcher (Stage 8 screens only) ───────────────────
  function renderCurrentView() {
    if (!viewDirty) return;
    const view = state.currentView;
    const screen = appShell.querySelector(`.screen[data-view="${view}"]`);
    if (!screen) { viewDirty = false; return; }
    if (view === "dashboard") {
      renderDashboard(screen);
    } else if (view === "tool-group") {
      renderToolGroup(screen);
    } else if (view === "parameter-form") {
      renderParameterForm(screen);
    }
    // If the next render lands on a different screen, we want to start
    // fresh. `builtFor` tracks the parameter-form case where we also
    // avoid rebuilds within the same visit.
    const others = appShell.querySelectorAll("#app > .screen[data-view]");
    others.forEach((el) => {
      if (el.dataset.view !== view) delete el.dataset.builtFor;
    });
    viewDirty = false;
  }

  // ── applyServerState: merge server state 1:1 into local state ─
  // Shape matches faust/ui/state.py SimulatorState.to_dict() as of Stage 4.
  function applyServerState(msg) {
    const prevPower = state.power;
    const prevMephisto = state.mephisto;
    const prevScope = JSON.stringify(state.scope);

    if (typeof msg.power !== "undefined") state.power = msg.power;
    if (typeof msg.mephisto !== "undefined") state.mephisto = msg.mephisto;
    if (typeof msg.boot_progress !== "undefined") state.boot_progress = msg.boot_progress;
    if (typeof msg.first_dock_this_boot !== "undefined") state.first_dock_this_boot = msg.first_dock_this_boot;
    if (msg.battery) state.battery = msg.battery;
    if (msg.scope) state.scope = msg.scope;
    if (Array.isArray(msg.active_pursuits)) state.active_pursuits = msg.active_pursuits;
    state.mode = state.mephisto === "connected" ? "pact" : "scholar";

    // Capture session start on the first power=on observed this JS
    // session; used by the scholar-mode session-info panel.
    if (state.power === "on" && sessionStartedAt === null) {
      sessionStartedAt = new Date();
    }

    // Any of these can change what the dashboard/tool-group shows.
    if (
      state.power !== prevPower ||
      state.mephisto !== prevMephisto ||
      JSON.stringify(state.scope) !== prevScope
    ) {
      markViewDirty();
    }

    // Boot transition detection (spec §10.1).
    if (!hasReceivedInitialState) {
      // First state message of the JS session. Do NOT play the
      // booting→on animation, even if we arrived mid-boot: the boot
      // screen is shown as-is, and the eventual `on` transition will
      // trigger the animation chain normally.
      hasReceivedInitialState = true;
      if (state.power === "booting") {
        initBootScreen();
      }
      return;
    }

    if (msg.power !== undefined && msg.power !== prevPower) {
      if (state.power === "booting") {
        initBootScreen();
      } else if (state.power === "on" && prevPower === "booting") {
        startBootCompletionAnimation();
      } else if (state.power === "off") {
        resetBootScreen();
      }
    }
  }

  // ── View stack (spec §11.4) ──────────────────────────────────
  function pushView(name, params = {}) {
    state.viewStack.push({ name: state.currentView, params: state.currentViewParams });
    state.currentView = name;
    state.currentViewParams = params || {};
    markViewDirty();
    render();
  }

  function goBack() {
    const prev = state.viewStack.pop();
    if (prev) {
      state.currentView = prev.name;
      state.currentViewParams = prev.params;
    }
    markViewDirty();
    render();
  }

  // ── body.active hook (spec §17.6) ────────────────────────────
  // Hoisted above the navigation-surface export so setActive is defined
  // when window.__faust is assigned below.
  function setActive(on) {
    state.active = !!on;
    document.body.classList.toggle("active", state.active);
  }

  // Expose a minimal navigation + send surface so later stages can call
  // into the shell without rewiring imports. Stages 8/10/11 will call
  // window.__faust.setActive(true) on prompt / dispatch / pursuit_start
  // sends; Stage 6 does not issue those sends itself.
  window.__faust = { pushView, goBack, send, setActive, state };

  // ── Render: apply state to DOM ───────────────────────────────
  function render() {
    document.body.dataset.mode = state.mode;

    const isOff = state.power === "off";
    const isBooting = state.power === "booting";
    const isOn = state.power === "on";

    // During the boot-completion animation window (power already === "on"
    // but the fade-out hasn't finished), keep the boot screen visible and
    // the app shell hidden. The animation chain flips the flag after
    // 1100ms and re-invokes render() to finalize.
    const showBoot = isBooting || (isOn && bootAnimationInProgress);
    const showApp = isOn && !bootAnimationInProgress;

    powerOffScreen.classList.toggle("hidden", !isOff);
    bootScreen.classList.toggle("hidden", !showBoot);
    appShell.classList.toggle("hidden", !showApp);

    if (showApp) {
      // Rebuild the visible view's DOM if something consequential
      // changed (state, skills, tool-call activity, navigation). The
      // parameter-form guards itself inside its builder so the 1-Hz
      // clock tick doesn't clobber user input.
      renderCurrentView();

      // Show exactly one inner screen.
      const screens = appShell.querySelectorAll("#app > .screen[data-view]");
      screens.forEach((el) => {
        el.classList.toggle("hidden", el.dataset.view !== state.currentView);
      });

      // Active tab highlight.
      const tabs = appShell.querySelectorAll(".tab");
      tabs.forEach((el) => {
        el.classList.toggle("tab--active", el.dataset.tab === state.currentTab);
      });

      // Mode label.
      modeLabel.textContent = state.mode === "pact" ? "PACT" : "SCHOLAR";

      // Scope label.
      if (!state.scope || state.scope.template == null) {
        scopeLabel.textContent = "NO SCOPE · TAP TO SET";
        scopeLabel.classList.remove("scope-label--set");
      } else {
        const t = String(state.scope.template).toUpperCase();
        if (state.scope.template === "pentesting") {
          const desc = state.scope.description || "";
          const trimmed = desc.length > 24 ? desc.slice(0, 21) + "…" : desc;
          scopeLabel.textContent = trimmed ? `PENTESTING · ${trimmed}` : "PENTESTING";
        } else {
          scopeLabel.textContent = t;
        }
        scopeLabel.classList.add("scope-label--set");
      }

      // Top meta: battery + clock, plus MEPHISTO marker in pact.
      const clockStr = clockHHMM();
      const bat = (state.battery && typeof state.battery.percent === "number")
        ? state.battery.percent : "??";
      let meta = `BAT ${bat}% · ${clockStr}`;
      if (state.mode === "pact") meta += " · MEPHISTO";
      topMeta.textContent = meta;
    }
  }

  function clockHHMM() {
    const d = new Date();
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return `${hh}:${mm}`;
  }

  // ── Event listeners ──────────────────────────────────────────
  document.addEventListener("click", (e) => {
    const target = e.target;

    if (target.closest(".power-on-btn")) {
      send({ type: "power", action: "on" });
      return;
    }

    const tabBtn = target.closest(".tab");
    if (tabBtn && tabBtn.dataset.tab) {
      const tab = tabBtn.dataset.tab;
      state.currentTab = tab;
      state.currentView = tab;
      state.currentViewParams = {};
      state.viewStack = [];
      markViewDirty();
      render();
      return;
    }

    if (target.closest("#scope-label")) {
      // Stage 9 opens the scope modal here. Logged for now.
      console.log("[scope] Stage 9 modal not yet wired");
      return;
    }
  });

  document.addEventListener("contextmenu", (e) => e.preventDefault());

  // ── Initialization ───────────────────────────────────────────
  connect();
  // Sigil fetch is async; tiles render with empty boxes until it
  // resolves, then loadSigils() flips viewDirty and re-renders.
  loadSigils();
  // 1s clock tick drives the top-bar time display. render() is cheap
  // enough that this doubles as a periodic refresh for anything that
  // depends on wall time.
  setInterval(render, 1000);
  render();
})();
