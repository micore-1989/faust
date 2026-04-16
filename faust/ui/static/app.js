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
        break;

      case "boot_log":
        appendBootLogLine(msg.line ?? "");
        break;

      // ── Agent phase markers (Stage 10 renders) ──
      case "planning_started":
      case "parameterizing_step":
      case "thinking":
        break;

      // ── Agent tool / plan events (Stage 10 renders) ──
      case "plan_proposed":
      case "tool_call_proposed":
        break;

      case "tool_call_executed":
        // Mid-plan executions are NOT terminal — a multi-step plan emits
        // several of these before `final`. Do not release body.active here;
        // the release happens on `final`. Stage 8/10 will additionally use
        // this event to render per-step results.
        break;

      case "final":
        setActive(false);
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

  // ── applyServerState: merge server state 1:1 into local state ─
  // Shape matches faust/ui/state.py SimulatorState.to_dict() as of Stage 4.
  function applyServerState(msg) {
    const prevPower = state.power;

    if (typeof msg.power !== "undefined") state.power = msg.power;
    if (typeof msg.mephisto !== "undefined") state.mephisto = msg.mephisto;
    if (typeof msg.boot_progress !== "undefined") state.boot_progress = msg.boot_progress;
    if (typeof msg.first_dock_this_boot !== "undefined") state.first_dock_this_boot = msg.first_dock_this_boot;
    if (msg.battery) state.battery = msg.battery;
    if (msg.scope) state.scope = msg.scope;
    if (Array.isArray(msg.active_pursuits)) state.active_pursuits = msg.active_pursuits;
    state.mode = state.mephisto === "connected" ? "pact" : "scholar";

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
    render();
  }

  function goBack() {
    const prev = state.viewStack.pop();
    if (prev) {
      state.currentView = prev.name;
      state.currentViewParams = prev.params;
    }
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
  // 1s clock tick drives the top-bar time display. render() is cheap
  // enough that this doubles as a periodic refresh for anything that
  // depends on wall time.
  setInterval(render, 1000);
  render();
})();
