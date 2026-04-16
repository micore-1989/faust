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
    conversation: [],                // Stage 10 — chat entries {key, role, content, variant?}
    currentToolCall: null,           // Stage 8 dashboard radio-tile marker
    toolPane: null,                  // Stage 10 Mephisto tool-output pane {name, args, output}
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
      setModalDisconnected(false);
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
      setModalDisconnected(true);
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

      // ── Agent phase markers (spec §10.7 / §17.5) ──
      case "planning_started":
        handlePlanningStarted(msg);
        break;

      case "parameterizing_step":
        handleParameterizingStep(msg);
        break;

      case "thinking":
        // No Stage 10 rendering — phase markers + tool output cover
        // the user-visible "model is thinking" story. Streaming thinking
        // text would flood the conversation pane in long plans.
        break;

      // ── Agent tool / plan events ──
      case "plan_proposed":
        // The plan has arrived; the planning/replan intervals should stop
        // ticking. The plan-approval modal will surface the actual plan.
        clearPlanPhaseIntervals();
        break;

      case "tool_call_proposed":
        // Stage 8: dashboard radio-tile active marker.
        state.currentToolCall = {
          call_id: msg.call_id,
          name: msg.tool_name,
          args: msg.arguments || {},
        };
        // Stage 10: tool-output pane header + chat entry.
        if (toolPaneClearTimer) { clearTimeout(toolPaneClearTimer); toolPaneClearTimer = null; }
        state.toolPane = {
          name: msg.tool_name,
          args: msg.arguments || {},
          output: [],
        };
        addOrUpdateConversation({
          key: "tool-" + (msg.call_id || msg.tool_name),
          role: "tool",
          content: formatToolCall(msg.tool_name, msg.arguments || {}),
        });
        markViewDirty();
        renderConversation();
        renderToolOutput();
        break;

      case "tool_call_executed":
        // Stage 8: clear dashboard active marker when this call finishes.
        if (state.currentToolCall) {
          const matchesId = msg.call_id && state.currentToolCall.call_id === msg.call_id;
          const matchesName = !msg.call_id && state.currentToolCall.name === msg.tool_name;
          if (matchesId || matchesName) {
            state.currentToolCall = null;
            markViewDirty();
          }
        }
        // Stage 10: append to tool-pane output + chat entry; schedule the
        // pane clear 3 s later so the operator can actually read the result.
        if (state.toolPane) {
          if (msg.error) {
            state.toolPane.output.push({ kind: "error", text: "✗ " + msg.error });
          } else {
            state.toolPane.output.push({
              kind: "success",
              text: "✓ " + truncateJson(msg.result, 500),
            });
          }
        }
        if (toolPaneClearTimer) clearTimeout(toolPaneClearTimer);
        toolPaneClearTimer = setTimeout(() => {
          state.toolPane = null;
          toolPaneClearTimer = null;
          renderToolOutput();
        }, 3000);
        addOrUpdateConversation({
          key: "result-" + (msg.call_id || msg.tool_name),
          role: "result",
          content: msg.error ? String(msg.error) : truncateJson(msg.result, 200),
        });
        renderConversation();
        renderToolOutput();
        break;

      case "final":
        setActive(false);
        state.currentToolCall = null;
        clearAllPhaseIntervals();
        if (msg.text) {
          addOrUpdateConversation({
            key: "meph-" + Date.now(),
            role: "mephisto",
            content: msg.text,
          });
          renderConversation();
        }
        markViewDirty();
        break;

      // ── Approval requests (Stage 9 real modals) ──
      case "confirmation_request":
        enqueueOrOpenModal({ type: "confirmation", msg });
        break;

      case "plan_approval_request":
        // Plan is ready to review — stop the planning counter.
        clearPlanPhaseIntervals();
        enqueueOrOpenModal({ type: "plan", msg });
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
    } else if (view === "mephisto") {
      renderMephisto(screen);
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

    // Mephisto dock transitions (Stage 10, spec §3.4 / §10.12 / §10.13).
    // `document.body.dataset.mode` and the top-bar mode-label are driven
    // by render() from state.mode, so the palette swap runs automatically
    // via the Stage 1 global transition rules. We only need to handle the
    // discrete side-effects here: ceremony on first dock, auto-navigate
    // off the Mephisto screen on undock.
    if (state.mephisto !== prevMephisto) {
      if (state.mephisto === "connected" && prevMephisto === "disconnected") {
        if (state.first_dock_this_boot === true) {
          setTimeout(showFirstDockCeremony, 600);
        }
      } else if (state.mephisto === "disconnected" && prevMephisto === "connected") {
        if (state.currentView === "mephisto") {
          state.currentView = "dashboard";
          state.currentTab = "dashboard";
          state.viewStack = [];
          markViewDirty();
        }
      }
    }

    // Scope change lands in the conversation as a SCOPE entry so the
    // operator's chat history reflects every scope flip (spec §10.7).
    // Skip the initial state hydration so we don't log the starting
    // scope as a change.
    const scopeChanged = JSON.stringify(state.scope) !== prevScope;
    if (scopeChanged) {
      const sc = formatScopeLine(state.scope);
      addOrUpdateConversation({
        key: "scope-" + Date.now(),
        role: "scope",
        content: `Scope now: ${sc.name}${sc.extra}`,
      });
      renderConversation();
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

  // ── Stage 10 — Mephisto conversation + dock (spec §10.7 / §10.12 / §10.13) ─

  // Phase-marker book-keeping. Every active planning / parameterizing
  // phase owns exactly one chat entry (by stable key) plus an interval
  // that ticks the elapsed-seconds counter in its content field. Both
  // the interval id and the phase start time are kept module-local so
  // that a final / plan_proposed / plan_approval_request can quiesce
  // them without reaching into the DOM.
  const phaseIntervals = new Map();   // key → interval id
  const phaseStartTimes = new Map();  // key → Date.now()

  // Scheduled tool-pane clear. On tool_call_executed we append the
  // result line but wait 3 s before blanking the pane so the operator
  // has a chance to actually read it. If a new tool_call_proposed
  // arrives inside the window we cancel the timer.
  let toolPaneClearTimer = null;

  function addOrUpdateConversation({ key, role, content, variant }) {
    const idx = state.conversation.findIndex((e) => e.key === key);
    if (idx >= 0) {
      state.conversation[idx].content = content;
      if (role) state.conversation[idx].role = role;
      if (variant !== undefined) state.conversation[idx].variant = variant;
    } else {
      state.conversation.push({
        key,
        role,
        content,
        variant: variant || null,
        timestamp: Date.now(),
      });
    }
  }

  function startPhaseMarker(key, role, renderContent, variant) {
    phaseStartTimes.set(key, Date.now());
    if (phaseIntervals.has(key)) {
      clearInterval(phaseIntervals.get(key));
      phaseIntervals.delete(key);
    }
    const tick = () => {
      const start = phaseStartTimes.get(key);
      if (!start) return;
      const seconds = Math.floor((Date.now() - start) / 1000);
      addOrUpdateConversation({
        key,
        role,
        content: renderContent(seconds),
        variant,
      });
      renderConversation();
    };
    tick();
    const id = setInterval(tick, 1000);
    phaseIntervals.set(key, id);
  }

  function clearPhaseInterval(key) {
    const id = phaseIntervals.get(key);
    if (id !== undefined) {
      clearInterval(id);
      phaseIntervals.delete(key);
    }
    phaseStartTimes.delete(key);
  }

  function clearAllPhaseIntervals() {
    for (const id of phaseIntervals.values()) clearInterval(id);
    phaseIntervals.clear();
    phaseStartTimes.clear();
  }

  function clearPlanPhaseIntervals() {
    for (const key of [...phaseIntervals.keys()]) {
      if (
        key === "phase-catalog" ||
        key === "phase-plan" ||
        key.startsWith("phase-replan-")
      ) clearPhaseInterval(key);
    }
  }

  function handlePlanningStarted(msg) {
    const attempt = msg.attempt || 0;
    if (msg.phase === "catalog") {
      clearPhaseInterval("phase-catalog");
      startPhaseMarker(
        "phase-catalog",
        "planning",
        (s) => `assembling catalog (${s}s)`,
      );
    } else if (msg.phase === "plan") {
      clearPhaseInterval("phase-catalog");
      startPhaseMarker(
        "phase-plan",
        "planning",
        (s) => `thinking about steps (${s}s)`,
      );
    } else if (msg.phase === "replan") {
      clearPhaseInterval("phase-catalog");
      clearPhaseInterval("phase-plan");
      const key = `phase-replan-${attempt || 1}`;
      startPhaseMarker(
        key,
        "planning",
        (s) => `RE-PLANNING · adjusting course (${s}s)`,
        "replan",
      );
    }
  }

  function handleParameterizingStep(msg) {
    // Single rolling entry — one visible row per turn, step number
    // updates in place as parameterization walks through the plan.
    addOrUpdateConversation({
      key: "phase-param",
      role: "parameterizing",
      content: `step ${msg.step} of ${msg.of} · ${msg.skill}`,
    });
    renderConversation();
  }

  function truncateJson(value, max) {
    if (value == null) return "";
    let s;
    try { s = JSON.stringify(value); } catch { s = String(value); }
    if (s.length > max) s = s.slice(0, max - 1) + "…";
    return s;
  }

  // ── Conversation + tool-output renderers ─────────────────────

  function renderConversation() {
    const container = document.querySelector(".mephisto-conversation");
    if (!container) return;
    container.innerHTML = "";
    for (const entry of state.conversation) {
      const el = document.createElement("div");
      el.className = `chat-entry chat-entry--${entry.role}`;
      if (entry.variant === "replan") el.classList.add("phase-marker--replan");
      el.dataset.key = entry.key;

      const roleEl = document.createElement("div");
      roleEl.className = "chat-entry__role";
      roleEl.textContent = entry.role === "planning" && entry.variant === "replan"
        ? "RE-PLANNING"
        : entry.role.toUpperCase();
      el.appendChild(roleEl);

      const contentEl = document.createElement("div");
      contentEl.className = "chat-entry__content";
      contentEl.textContent = entry.content;
      el.appendChild(contentEl);

      container.appendChild(el);
    }
    container.scrollTop = container.scrollHeight;
  }

  function renderToolOutput() {
    const container = document.querySelector(".mephisto-tool-output");
    if (!container) return;
    container.innerHTML = "";
    if (!state.toolPane) {
      const empty = document.createElement("div");
      empty.className = "mephisto-tool-output__empty";
      empty.textContent = "No active tool invocation.";
      container.appendChild(empty);
      return;
    }
    const header = document.createElement("div");
    header.className = "mephisto-tool-output__header";
    header.textContent = formatToolCall(state.toolPane.name, state.toolPane.args);
    container.appendChild(header);
    for (const line of state.toolPane.output) {
      const row = document.createElement("div");
      row.className = "mephisto-tool-output__line mephisto-tool-output__line--" + line.kind;
      row.textContent = line.text;
      container.appendChild(row);
    }
    container.scrollTop = container.scrollHeight;
  }

  // ── Mephisto screen builder ──────────────────────────────────

  function renderMephisto(screen) {
    // Scholar mode is not a valid state for this screen — the dock
    // transition auto-navigates away, but a stale pushView or dev-tools
    // edit could still land here. Render a helpful lock message.
    if (state.mode !== "pact") {
      screen.innerHTML = "";
      screen.removeAttribute("data-builtFor");
      const lock = document.createElement("div");
      lock.className = "mephisto-screen__locked";
      lock.textContent = "Dock Mephisto to begin.";
      screen.appendChild(lock);
      return;
    }

    // Build the shell once per visit. Subsequent dirty renders only
    // refresh the conversation + tool-output panes (renderConversation
    // / renderToolOutput), so the input retains focus and typed text.
    if (screen.dataset.builtFor === "mephisto") {
      renderConversation();
      renderToolOutput();
      return;
    }
    screen.innerHTML = "";
    screen.dataset.builtFor = "mephisto";

    const wrap = document.createElement("div");
    wrap.className = "mephisto-screen";

    // Header: back + MEPHISTO wordmark + model line.
    const header = document.createElement("div");
    header.className = "mephisto-screen__header";

    const back = document.createElement("button");
    back.type = "button";
    back.className = "back-btn";
    back.innerHTML = '<i class="ph ph-arrow-left"></i><span>BACK</span>';
    back.addEventListener("click", () => goBack());
    header.appendChild(back);

    const brand = document.createElement("span");
    brand.className = "mephisto-screen__brand";
    brand.textContent = "MEPHISTO";
    header.appendChild(brand);

    const model = document.createElement("span");
    model.className = "mephisto-screen__model";
    model.textContent = "QWEN 2.5-VL-3B · 8.4 T/S";
    header.appendChild(model);

    wrap.appendChild(header);

    // Conversation pane.
    const convo = document.createElement("div");
    convo.className = "mephisto-conversation";
    wrap.appendChild(convo);

    // Input row.
    const inputRow = document.createElement("div");
    inputRow.className = "mephisto-input-row";

    const input = document.createElement("input");
    input.type = "text";
    input.className = "mephisto-input__text";
    input.placeholder = "speak to Mephisto...";
    input.autofocus = true;
    inputRow.appendChild(input);

    const sendBtn = document.createElement("button");
    sendBtn.type = "button";
    sendBtn.className = "mephisto-input__send btn-primary";
    sendBtn.textContent = "SEND ⏎";
    inputRow.appendChild(sendBtn);

    const submit = () => {
      const text = input.value.trim();
      if (!text) return;
      addOrUpdateConversation({
        key: "op-" + Date.now(),
        role: "operator",
        content: text,
      });
      input.value = "";
      send({ type: "prompt", text });
      setActive(true);
      renderConversation();
    };

    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        submit();
      }
    });
    sendBtn.addEventListener("click", submit);

    wrap.appendChild(inputRow);

    // Tool-output pane.
    const toolOut = document.createElement("div");
    toolOut.className = "mephisto-tool-output";
    wrap.appendChild(toolOut);

    screen.appendChild(wrap);

    renderConversation();
    renderToolOutput();
    // Autofocus only after the screen is in the DOM + visible.
    setTimeout(() => input.focus(), 0);
  }

  // ── First-dock ceremony (spec §10.13) ────────────────────────

  function showFirstDockCeremony() {
    // If a prior ceremony is still mid-animation, let it finish rather
    // than stacking overlays — the server only flips first_dock_this_boot
    // once per boot anyway.
    if (document.querySelector(".ceremony-overlay")) return;

    const overlay = document.createElement("div");
    overlay.className = "ceremony-overlay";

    const content = document.createElement("div");
    content.className = "ceremony-content";

    const brand = document.createElement("h1");
    brand.className = "type-wordmark-xl";
    brand.textContent = "MEPHISTO";
    content.appendChild(brand);

    const rule = document.createElement("div");
    rule.className = "rule-heavy";
    content.appendChild(rule);

    const pact = document.createElement("h2");
    pact.className = "type-h1";
    pact.textContent = "PACT ESTABLISHED";
    content.appendChild(pact);

    const diamond = document.createElement("div");
    diamond.className = "ceremony-diamond";
    diamond.textContent = "◇";
    content.appendChild(diamond);

    overlay.appendChild(content);
    document.body.appendChild(overlay);

    requestAnimationFrame(() => overlay.classList.add("ceremony-overlay--visible"));

    // 400 ms fade-in → 2000 ms hold → 400 ms fade-out → remove
    setTimeout(() => {
      overlay.classList.remove("ceremony-overlay--visible");
      overlay.classList.add("ceremony-overlay--fading");
      setTimeout(() => overlay.remove(), 400);
    }, 400 + 2000);
  }

  // ── Dev shortcut (spec §13) ──────────────────────────────────
  //
  // DEV ONLY — Ctrl+D simulates a Mephisto dock/undock by sending the
  // same mephisto WS message the future USB detector would issue. The
  // server owns the transition, so the ceremony, palette swap, mode
  // label, and auto-navigate-on-undock behaviors all fall out of the
  // regular applyServerState path.
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && !e.shiftKey && !e.altKey && (e.key === "d" || e.key === "D")) {
      e.preventDefault();
      const action = state.mephisto === "connected" ? "disconnect" : "connect";
      send({ type: "mephisto", action });
    }
  });

  // ── Stage 9 — modals (spec §7.10 / §10.8 / §10.9 / §10.10) ───
  //
  // One modal visible at a time. Server-pushed approval requests
  // (confirmation_request / plan_approval_request) that arrive while
  // another modal is open queue behind it; a user-initiated scope
  // modal bypasses the queue entirely (by design: the operator asked
  // for it).  Correlation ids (call_id / plan_id) live on module
  // state so the Escape key path can send the right reject payload
  // without re-deriving it from the DOM.

  let activeModalType = null; // 'confirmation' | 'plan' | 'scope' | null
  let activeCallId = null;
  let activePlanId = null;
  const pendingModals = [];   // items: { type: 'confirmation' | 'plan', msg }
  let modalKeydownHandler = null;

  function enqueueOrOpenModal(item) {
    // An already-open scope modal does NOT block server approvals in
    // reality, but to preserve one-at-a-time we still queue behind it.
    if (activeModalType !== null) {
      // Drop exact-duplicate re-emits (same call_id/plan_id as active).
      if (
        (item.type === "confirmation" && activeCallId && activeCallId === item.msg.call_id) ||
        (item.type === "plan"         && activePlanId && activePlanId === item.msg.plan_id)
      ) return;
      pendingModals.push(item);
      return;
    }
    if (item.type === "confirmation") openDestructiveModal(item.msg);
    else if (item.type === "plan")    openPlanApprovalModal(item.msg);
  }

  function openModal(backdropEl, type) {
    activeModalType = type;
    const root = document.getElementById("modal-root");
    root.innerHTML = "";
    root.appendChild(backdropEl);
    requestAnimationFrame(() => backdropEl.classList.add("modal-backdrop--visible"));
    modalKeydownHandler = (e) => {
      if (e.key === "Escape") handleModalEscape();
    };
    document.addEventListener("keydown", modalKeydownHandler);
  }

  function closeModal() {
    const root = document.getElementById("modal-root");
    const backdrop = root.querySelector(".modal-backdrop");
    const finalize = () => {
      root.innerHTML = "";
      activeModalType = null;
      activeCallId = null;
      activePlanId = null;
      if (modalKeydownHandler) {
        document.removeEventListener("keydown", modalKeydownHandler);
        modalKeydownHandler = null;
      }
      // Drain the queue: the next queued item opens after this one.
      if (pendingModals.length > 0) {
        const next = pendingModals.shift();
        if (next.type === "confirmation") openDestructiveModal(next.msg);
        else if (next.type === "plan")    openPlanApprovalModal(next.msg);
      }
    };
    if (backdrop) {
      backdrop.classList.remove("modal-backdrop--visible");
      setTimeout(finalize, 150);
    } else {
      finalize();
    }
  }

  function handleModalEscape() {
    if (activeModalType === "confirmation") {
      send({ type: "confirmation", call_id: activeCallId, approved: false });
      closeModal();
    } else if (activeModalType === "plan") {
      send({ type: "plan_approval", plan_id: activePlanId, approved: false });
      closeModal();
    } else if (activeModalType === "scope") {
      closeModal();
    }
  }

  function setModalDisconnected(disconnected) {
    const modal = document.querySelector("#modal-root .modal");
    if (!modal) return;
    modal.classList.toggle("modal--disconnected", !!disconnected);
  }

  // ── Destructive-action confirmation modal (spec §10.8) ───────

  const DESTRUCTIVE_TITLES = {
    wifi_deauth:       "DEAUTH A WIFI CLIENT",
    wifi_deauth_all:   "DEAUTH ALL WIFI CLIENTS",
    wifi_evil_portal:  "LAUNCH EVIL PORTAL",
    subghz_replay:     "REPLAY SUB-GHZ SIGNAL",
    subghz_transmit:   "TRANSMIT ON SUB-GHZ",
    subghz_jam:        "JAM SUB-GHZ BAND",
    nfc_write:         "WRITE NFC TAG",
    nfc_emulate:       "EMULATE NFC TAG",
    rfid_clone:        "CLONE RFID CREDENTIAL",
    rfid_write:        "WRITE RFID CARD",
    ir_transmit:       "TRANSMIT IR",
    ibutton_write:     "WRITE IBUTTON",
    keystroke_inject:  "INJECT KEYSTROKES",
    ble_spoof:         "SPOOF BLE DEVICE",
  };

  const DESTRUCTIVE_CONSEQUENCES = {
    wifi_deauth:       "This transmits forged management frames. In most jurisdictions this is illegal outside your authorized scope.",
    wifi_deauth_all:   "This transmits forged management frames at every client on the target BSSID. In most jurisdictions this is illegal outside your authorized scope.",
    wifi_evil_portal:  "This stands up a rogue access point impersonating a nearby network. In most jurisdictions this is illegal outside your authorized scope.",
    subghz_replay:     "This retransmits a captured RF signal. Use only against hardware you own or are explicitly authorized to test.",
    subghz_transmit:   "This emits RF energy on the selected frequency. Regulated band use without a license may violate local law.",
    subghz_jam:        "This emits continuous noise on the selected band. Jamming is illegal in most jurisdictions.",
    nfc_write:         "This overwrites the tag's data. The original content is lost unless backed up.",
    nfc_emulate:       "This impersonates a tag toward a reader. Only use against systems you own or are authorized to test.",
    rfid_clone:        "This duplicates a credential. Only use against cards you own or are explicitly authorized to clone.",
    rfid_write:        "This overwrites the card's data. Previous content is destroyed.",
    ir_transmit:       "This transmits an IR command. The target device will respond as if the original remote were used.",
    ibutton_write:     "This overwrites the iButton. The original identity is lost.",
    keystroke_inject:  "This sends keystrokes to the connected host. The target receives them as if typed by the operator.",
    ble_spoof:         "This broadcasts a forged BLE advertisement. Only use against devices you own or are authorized to test.",
    default:           "This action may modify the environment. Confirm only if you are authorized.",
  };

  function titleForDestructive(toolName) {
    return DESTRUCTIVE_TITLES[toolName]
      || `CONFIRM: ${String(toolName || "").toUpperCase().replace(/_/g, " ")}`;
  }

  function consequenceForDestructive(toolName) {
    return DESTRUCTIVE_CONSEQUENCES[toolName] || DESTRUCTIVE_CONSEQUENCES.default;
  }

  function formatToolCall(name, args) {
    if (!args || Object.keys(args).length === 0) return `${name}()`;
    const parts = Object.entries(args).map(([k, v]) => {
      let vs;
      if (typeof v === "string") vs = JSON.stringify(v);
      else if (v == null) vs = "null";
      else vs = JSON.stringify(v);
      return `${k}=${vs}`;
    });
    return `${name}(${parts.join(", ")})`;
  }

  function formatScopeLine(scope) {
    if (!scope || scope.template == null) {
      return { name: "NO SCOPE", extra: "" };
    }
    const t = String(scope.template).toUpperCase();
    if (scope.template === "pentesting" && scope.description) {
      const d = scope.description;
      const trimmed = d.length > 40 ? d.slice(0, 37) + "…" : d;
      return { name: "PENTESTING", extra: ` · ${trimmed}` };
    }
    return { name: t, extra: "" };
  }

  function openDestructiveModal(msg) {
    activeCallId = msg.call_id;

    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";

    const modal = document.createElement("div");
    modal.className = "modal";
    // Don't dismiss on backdrop click (touchscreen safety — spec §10.8).
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) e.stopPropagation();
    });

    const header = document.createElement("div");
    header.className = "modal__header modal__header--destructive";
    header.textContent = titleForDestructive(msg.tool_name);
    modal.appendChild(header);

    const body = document.createElement("div");
    body.className = "modal__body";

    const call = document.createElement("div");
    call.className = "mono-block mono-block--destructive";
    call.textContent = formatToolCall(msg.tool_name, msg.arguments || {});
    body.appendChild(call);

    const consequence = document.createElement("p");
    consequence.className = "modal__consequence";
    consequence.textContent = consequenceForDestructive(msg.tool_name);
    body.appendChild(consequence);

    const rule = document.createElement("div");
    rule.className = "rule-hair";
    body.appendChild(rule);

    const scopeLine = document.createElement("div");
    scopeLine.className = "modal__scope-line";
    const sc = formatScopeLine(state.scope);
    const scopeLabel = document.createTextNode("Scope · ");
    const scopeName = document.createElement("strong");
    scopeName.textContent = sc.name;
    scopeLine.appendChild(scopeLabel);
    scopeLine.appendChild(scopeName);
    if (sc.extra) scopeLine.appendChild(document.createTextNode(sc.extra));
    body.appendChild(scopeLine);

    const trust = document.createElement("div");
    trust.className = "modal__trust-line";
    trust.textContent = "Trust remembered within this scope for 10 minutes.";
    body.appendChild(trust);

    modal.appendChild(body);

    const buttons = document.createElement("div");
    buttons.className = "modal__buttons";
    const abort = document.createElement("button");
    abort.type = "button";
    abort.textContent = "ABORT";
    abort.addEventListener("click", () => {
      send({ type: "confirmation", call_id: msg.call_id, approved: false });
      closeModal();
    });
    const confirm = document.createElement("button");
    confirm.type = "button";
    confirm.className = "modal__btn-confirm";
    confirm.textContent = "CONFIRM";
    confirm.addEventListener("click", () => {
      send({ type: "confirmation", call_id: msg.call_id, approved: true });
      closeModal();
    });
    buttons.appendChild(abort);
    buttons.appendChild(confirm);
    modal.appendChild(buttons);

    backdrop.appendChild(modal);
    openModal(backdrop, "confirmation");
  }

  // ── Plan-approval modal (spec §10.9) ─────────────────────────

  function openPlanApprovalModal(msg) {
    activePlanId = msg.plan_id;

    const isReplan = typeof msg.plan_id === "string" && msg.plan_id.includes("-replan");

    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";

    const modal = document.createElement("div");
    modal.className = "modal";

    const header = document.createElement("div");
    header.className = "modal__header " + (isReplan ? "modal__header--replan" : "modal__header--plan");
    header.textContent = isReplan
      ? "MEPHISTO PROPOSES A REVISED PLAN"
      : "MEPHISTO PROPOSES A PLAN";
    modal.appendChild(header);

    const body = document.createElement("div");
    body.className = "modal__body";

    const reasoningTitle = document.createElement("h3");
    reasoningTitle.className = "type-h3 modal__section-title";
    reasoningTitle.textContent = "Reasoning";
    body.appendChild(reasoningTitle);

    const reasoning = document.createElement("p");
    reasoning.className = "type-body";
    reasoning.style.color = "var(--ink-primary)";
    reasoning.textContent = msg.reasoning || "";
    body.appendChild(reasoning);

    const stepsTitle = document.createElement("h3");
    stepsTitle.className = "type-h3 modal__section-title";
    stepsTitle.textContent = "Steps";
    body.appendChild(stepsTitle);

    const steps = document.createElement("ol");
    steps.className = "plan-steps";
    (msg.steps || []).forEach((step, idx) => {
      const row = document.createElement("li");
      row.className = "plan-steps__row";

      const n = document.createElement("span");
      n.className = "plan-steps__n";
      n.textContent = `${idx + 1}.`;
      row.appendChild(n);

      const skillCell = document.createElement("span");
      if (step.critical) {
        const tag = document.createElement("span");
        tag.className = "plan-steps__critical";
        tag.textContent = "[DESTRUCT] ";
        skillCell.appendChild(tag);
      }
      const skill = document.createElement("span");
      skill.className = "plan-steps__skill";
      skill.textContent = step.skill || "";
      skillCell.appendChild(skill);
      row.appendChild(skillCell);

      const intent = document.createElement("span");
      intent.className = "plan-steps__intent";
      intent.textContent = step.intent || "";
      row.appendChild(intent);

      steps.appendChild(row);
    });
    body.appendChild(steps);

    if (Array.isArray(msg.safety_notes) && msg.safety_notes.length > 0) {
      const safetyTitle = document.createElement("h3");
      safetyTitle.className = "type-h3 modal__section-title";
      safetyTitle.textContent = "Safety notes";
      body.appendChild(safetyTitle);

      const notes = document.createElement("div");
      notes.className = "plan-safety-notes";
      for (const note of msg.safety_notes) {
        const row = document.createElement("div");
        row.className = "plan-safety-notes__row";
        const icon = document.createElement("span");
        icon.className = "plan-safety-notes__icon";
        icon.textContent = "⚠";
        const text = document.createElement("span");
        text.textContent = note;
        row.appendChild(icon);
        row.appendChild(text);
        notes.appendChild(row);
      }
      body.appendChild(notes);
    }

    modal.appendChild(body);

    const buttons = document.createElement("div");
    buttons.className = "modal__buttons";
    const reject = document.createElement("button");
    reject.type = "button";
    reject.textContent = "REJECT";
    reject.addEventListener("click", () => {
      send({ type: "plan_approval", plan_id: msg.plan_id, approved: false });
      closeModal();
    });
    const approve = document.createElement("button");
    approve.type = "button";
    approve.className = isReplan ? "modal__btn-confirm--replan" : "modal__btn-confirm--plan";
    approve.textContent = "APPROVE PLAN";
    approve.addEventListener("click", () => {
      send({ type: "plan_approval", plan_id: msg.plan_id, approved: true });
      closeModal();
    });
    buttons.appendChild(reject);
    buttons.appendChild(approve);
    modal.appendChild(buttons);

    backdrop.appendChild(modal);
    openModal(backdrop, "plan");
  }

  // ── Scope-change modal (spec §10.10) ─────────────────────────

  const SCOPE_TEMPLATES = [
    { id: "recon",      title: "Strictly Recon",         desc: "Passive observation only. No transmission." },
    { id: "self-test",  title: "Testing My Own Devices", desc: "Unlimited actions on hardware you own." },
    { id: "pentesting", title: "Pentesting",             desc: "Requires description of engagement." },
  ];

  function openScopeModal() {
    const backdrop = document.createElement("div");
    backdrop.className = "modal-backdrop";

    const modal = document.createElement("div");
    modal.className = "modal";

    const header = document.createElement("div");
    header.className = "modal__header modal__header--scope";
    header.textContent = "SET SCOPE";
    modal.appendChild(header);

    const body = document.createElement("div");
    body.className = "modal__body";

    const options = document.createElement("div");
    options.className = "scope-options";

    let selectedTemplate = state.scope && state.scope.template || null;

    const descField = document.createElement("textarea");
    descField.className = "scope-description-input";
    descField.placeholder = "Describe the engagement (target, authorization, timeframe)…";
    descField.value = (state.scope && state.scope.description) || "";
    descField.style.display = selectedTemplate === "pentesting" ? "" : "none";

    const boxes = {};

    const confirmBtn = document.createElement("button");
    confirmBtn.type = "button";
    confirmBtn.className = "modal__btn-confirm";
    confirmBtn.textContent = "SET SCOPE";

    function updateConfirmEnabled() {
      const needDesc = selectedTemplate === "pentesting";
      const hasDesc = descField.value.trim().length > 0;
      const valid = !!selectedTemplate && (!needDesc || hasDesc);
      confirmBtn.disabled = !valid;
    }

    for (const s of SCOPE_TEMPLATES) {
      const radio = document.createElement("div");
      radio.className = "scope-radio";

      const box = document.createElement("div");
      box.className = "scope-radio__box";
      if (s.id === selectedTemplate) box.classList.add("scope-radio__box--selected");
      boxes[s.id] = box;
      radio.appendChild(box);

      const info = document.createElement("div");
      info.className = "scope-radio__info";
      const title = document.createElement("div");
      title.className = "scope-radio__title";
      title.textContent = s.title;
      const desc = document.createElement("div");
      desc.className = "scope-radio__desc";
      desc.textContent = s.desc;
      info.appendChild(title);
      info.appendChild(desc);
      radio.appendChild(info);

      radio.addEventListener("click", () => {
        selectedTemplate = s.id;
        for (const b of Object.values(boxes)) b.classList.remove("scope-radio__box--selected");
        box.classList.add("scope-radio__box--selected");
        descField.style.display = s.id === "pentesting" ? "" : "none";
        updateConfirmEnabled();
      });

      options.appendChild(radio);
    }
    body.appendChild(options);
    body.appendChild(descField);
    descField.addEventListener("input", updateConfirmEnabled);
    modal.appendChild(body);

    const buttons = document.createElement("div");
    buttons.className = "modal__buttons";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.textContent = "CANCEL";
    cancel.addEventListener("click", () => closeModal());

    confirmBtn.addEventListener("click", () => {
      if (!selectedTemplate) return;
      const desc = descField.value.trim();
      send({
        type: "scope_change",
        template: selectedTemplate,
        description: selectedTemplate === "pentesting" ? desc : null,
      });
      closeModal();
    });

    buttons.appendChild(cancel);
    buttons.appendChild(confirmBtn);
    modal.appendChild(buttons);

    updateConfirmEnabled();

    backdrop.appendChild(modal);
    openModal(backdrop, "scope");
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
      openScopeModal();
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
