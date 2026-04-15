/**
 * Faust UI v2 — hierarchical navigation (home → category → skill; separate chat).
 * Minimal, scientific. Blue ambient / red when Mephisto docked.
 */

(function () {
    "use strict";

    // ── Quotes from Goethe's "Faust" (Walter Kaufmann / Bayard Taylor translations) ──
    const FAUST_QUOTES = [
        { text: "In the beginning was the deed.", src: "Faust I, Scene 3" },
        { text: "Two souls, alas! dwell within my breast.", src: "Faust I, Scene 2" },
        { text: "I am part of that power which would ever work evil, yet forever works the good.", src: "Mephistopheles, Faust I" },
        { text: "Man errs as long as he strives.", src: "Prologue in Heaven" },
        { text: "All theory, dear friend, is gray; the golden tree of life springs ever green.", src: "Mephistopheles, Faust I" },
        { text: "Whoever strives with all his might, that man we can redeem.", src: "Faust II, Act V" },
        { text: "The deed is all, the glory nothing.", src: "Faust II" },
        { text: "Feeling is all; names are but sound and smoke.", src: "Faust I, Scene 16" },
        { text: "What is it that in the end we gain?", src: "Faust I" },
        { text: "The spirits that I summoned, I now cannot rid myself of again.", src: "Der Zauberlehrling (Goethe)" },
    ];

    function pickQuote() {
        return FAUST_QUOTES[Math.floor(Math.random() * FAUST_QUOTES.length)];
    }

    // ── Smart defaults for parameter fields ────────────────────────
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

    // ── Category metadata (glyphs + display names) ─────────────────
    const CATEGORIES = [
        { id: "wifi",      name: "Wi-Fi",    glyph: "◉", sub: "wireless" },
        { id: "ble",       name: "Bluetooth", glyph: "◎", sub: "short-range" },
        { id: "nfc",       name: "NFC",      glyph: "▣", sub: "13.56 MHz" },
        { id: "rfid",      name: "RFID",     glyph: "▤", sub: "125 kHz LF" },
        { id: "subghz",    name: "Sub-GHz",  glyph: "≋", sub: "ISM bands" },
        { id: "rf",        name: "Spectrum", glyph: "⋿", sub: "wideband RF" },
        { id: "ir",        name: "Infrared", glyph: "◈", sub: "remote signals" },
        { id: "usb",       name: "USB / HID", glyph: "⌨", sub: "BadUSB" },
        { id: "network",   name: "Network",  glyph: "⇌", sub: "IP / web" },
        { id: "analysis",  name: "Analysis", glyph: "⊜", sub: "offline tools" },
        { id: "defense",   name: "Defense",  glyph: "⊘", sub: "counter-surveillance" },
    ];

    // ── DOM refs ───────────────────────────────────────────────────
    const body = document.body;
    const $ = (id) => document.getElementById(id);

    // Controls present in every state
    const powerOnBtn   = $("power-on-btn");
    const powerOffBtn  = $("power-off-btn");
    const mephistoBtn  = $("mephisto-toggle");
    const mephistoDot  = $("mephisto-dot");
    const mephistoLab  = $("mephisto-label");
    const mephistoTglDot = $("mephisto-toggle-dot");
    const mephistoTglLab = $("mephisto-toggle-label");
    const bootLog      = $("boot-log");
    const bootProgress = $("boot-progress");
    const splashQuote  = $("splash-quote");
    const homeGrid     = $("home-grid");
    const skillList    = $("skill-list");
    const categoryTitle = $("category-title");
    const skillTitle    = $("skill-title");
    const skillSens     = $("skill-sensitivity");
    const skillDesc     = $("skill-description");
    const skillForm     = $("skill-form");
    const skillResult   = $("skill-result");
    const skillRunBtn   = $("skill-run-btn");
    const chatMessages  = $("chat-messages");
    const chatEmpty     = $("chat-empty");
    const chatInput     = $("chat-input");
    const chatSend      = $("chat-send");
    const chatMepDot    = $("chat-mephisto-dot");
    const chatMepLab    = $("chat-mephisto-label");
    const modal         = $("modal");
    const modalTitle    = $("modal-title");
    const modalBody     = $("modal-body");
    const modalApprove  = $("modal-approve");
    const modalReject   = $("modal-reject");

    // ── State ──────────────────────────────────────────────────────
    let ws = null;
    const sendQueue = [];
    let powerState = "off";
    let mephistoState = "disconnected";
    let allSkills = [];
    let currentView = "off";
    let currentSkill = null;  // {name, description, sensitivity, parameters_schema}
    let pendingConfirmation = null;
    let pendingPlanApproval = null;
    let currentSkillCallId = null;  // used to route the result back to skill-view UI

    // ── Navigation ────────────────────────────────────────────────
    const viewStack = ["off"];

    function setView(name) {
        currentView = name;
        body.classList.remove(
            "view-splash", "view-home",
            "view-category", "view-skill", "view-chat"
        );
        body.classList.add("view-" + name);
    }

    function setStage(stage) {
        // Splash sub-stages: off, booting, complete
        body.classList.remove("stage-off", "stage-booting", "stage-complete");
        if (stage) body.classList.add("stage-" + stage);
    }

    function navigate(name) {
        if (viewStack[viewStack.length - 1] !== name) viewStack.push(name);
        setView(name);
    }

    function goBack() {
        if (viewStack.length > 1) viewStack.pop();
        const target = viewStack[viewStack.length - 1];
        setView(target);
        // Clear per-screen state when leaving.
        if (target !== "skill") {
            skillResult.innerHTML = "";
            currentSkillCallId = null;
        }
    }

    // Back buttons
    document.querySelectorAll("[data-back]").forEach(el =>
        el.addEventListener("click", goBack));

    // ── WebSocket ──────────────────────────────────────────────────
    function connect() {
        const protocol = location.protocol === "https:" ? "wss:" : "ws:";
        ws = new WebSocket(`${protocol}//${location.host}/ws`);

        ws.onopen = () => {
            console.log("[faust] ws open");
            while (sendQueue.length) ws.send(sendQueue.shift());
        };
        ws.onclose = () => {
            console.log("[faust] ws closed — reconnecting in 2s");
            setTimeout(connect, 2000);
        };
        ws.onerror = (e) => console.error("[faust] ws error", e);
        ws.onmessage = (evt) => {
            try { handleMessage(JSON.parse(evt.data)); }
            catch (e) { console.error("[faust] bad message", e); }
        };
    }

    function send(msg) {
        const payload = JSON.stringify(msg);
        if (ws && ws.readyState === WebSocket.OPEN) ws.send(payload);
        else sendQueue.push(payload);
    }

    // ── Server messages ───────────────────────────────────────────
    function handleMessage(data) {
        switch (data.type) {
            case "state":                applyState(data); break;
            case "boot_log":             appendBoot(data.line); break;
            case "skills":               applySkills(data.skills); break;
            case "thinking":             pushChatAssistant(data.text); break;
            case "plan_proposed":        pushChatPlanProposed(data); break;
            case "tool_call_proposed":   pushChatToolProposed(data); break;
            case "tool_call_executed":   handleToolExecuted(data); break;
            case "final":                handleFinal(data); break;
            case "confirmation_request": showConfirmationModal(data); break;
            case "plan_approval_request": showPlanApprovalModal(data); break;
            case "error":                pushChatAssistant("⚠ " + data.message); break;
            default: console.log("[faust] unknown message", data);
        }
    }

    // ── State transitions ─────────────────────────────────────────
    function applyState(data) {
        powerState = data.power;
        mephistoState = data.mephisto;

        body.classList.remove("mephisto-on", "active");
        if (mephistoState === "connected") body.classList.add("mephisto-on");

        // Refresh dots / labels
        const dotClass = "dot " + (mephistoState === "connected" ? "connected" : "disconnected");
        [mephistoDot, chatMepDot, mephistoTglDot].forEach(el => el && (el.className = dotClass.replace("dot ", "dot ")));
        const label = "mephisto: " + (mephistoState === "connected" ? "docked" : "undocked");
        [mephistoLab, chatMepLab].forEach(el => el && (el.textContent = label));
        mephistoTglLab.textContent = mephistoState === "connected" ? "Disconnect Ψ" : "Connect Ψ";

        // Chat input availability
        const aiReady = (powerState === "on") && (mephistoState === "connected");
        chatInput.disabled = !aiReady;
        chatSend.disabled = !aiReady;
        chatInput.placeholder = aiReady ? "Ask anything…" : "Connect Ψ to enable";

        // View transitions driven by power state.
        if (powerState === "off") {
            viewStack.length = 0; viewStack.push("splash");
            setView("splash");
            setStage("off");
            splashQuote.innerHTML = "";
            powerOnBtn.disabled = false;
            powerOnBtn.textContent = "Power on";
        } else if (powerState === "booting") {
            // Stay on the splash view, switch stage to 'booting' (animates f up).
            if (currentView !== "splash") setView("splash");
            setStage("booting");
            bootLog.innerHTML = "";
            bootProgress.style.width = "0%";
            splashQuote.innerHTML = "";
        } else if (powerState === "on") {
            // If we came from booting, play the post-boot reveal, then go home.
            if (currentView === "splash") {
                playBootCompleteThenHome();
            } else if (currentView !== "home"
                       && currentView !== "category"
                       && currentView !== "skill"
                       && currentView !== "chat") {
                // Reconnect on a running server — drop straight into home.
                setView("home");
            }
        }

        if (typeof data.boot_progress === "number") {
            bootProgress.style.width = data.boot_progress + "%";
        }

        // Refresh home grid AI tile enabled state
        refreshHomeGrid();
    }

    // Post-boot reveal: transition stage 'booting' → 'complete',
    // show the random Faust quote + unroll 'aust', then navigate to home.
    let bootCompleteTimers = [];
    function playBootCompleteThenHome() {
        bootCompleteTimers.forEach(clearTimeout);
        bootCompleteTimers = [];

        const q = pickQuote();
        splashQuote.innerHTML = "";
        const text = document.createElement("span");
        text.textContent = `\u201C${q.text}\u201D`;
        const attr = document.createElement("span");
        attr.className = "attribution";
        attr.textContent = q.src;
        splashQuote.appendChild(text);
        splashQuote.appendChild(attr);

        // Transition: stage-booting → stage-complete. CSS handles the visuals.
        setStage("complete");

        // After the reveal animation (~1500ms for aust + quote), jump to home.
        bootCompleteTimers.push(setTimeout(() => {
            setStage(null);
            viewStack.length = 0; viewStack.push("home");
            setView("home");
        }, 2800));
    }

    function appendBoot(line) {
        const el = document.createElement("div");
        el.className = "boot-line";
        if (line === "𝑓aust MK1") el.classList.add("brand");
        el.textContent = line || " ";
        bootLog.appendChild(el);
        bootLog.scrollTop = bootLog.scrollHeight;
    }

    function applySkills(skills) {
        allSkills = skills || [];
        refreshHomeGrid();
    }

    // ── Home grid ─────────────────────────────────────────────────
    function refreshHomeGrid() {
        if (!homeGrid) return;
        homeGrid.innerHTML = "";

        // Ask-Faust tile (spans 2 cols).
        const aiReady = (mephistoState === "connected") && (powerState === "on");
        const ai = document.createElement("div");
        ai.className = "tile tile-ai" + (aiReady ? "" : " disabled");
        ai.innerHTML = `
            <div class="tile-top">
                <div class="tile-glyph">Ψ</div>
                <div class="tile-count">${aiReady ? "online" : "offline"}</div>
            </div>
            <div>
                <div class="tile-label">Ask 𝑓aust</div>
                <div class="tile-sub">${aiReady ? "plan → execute with AI" : "dock Mephisto"}</div>
            </div>
        `;
        if (aiReady) {
            ai.addEventListener("click", () => navigate("chat"));
        }
        homeGrid.appendChild(ai);

        // Category tiles
        CATEGORIES.forEach(cat => {
            const count = allSkills.filter(s => s.category === cat.id).length;
            if (count === 0) return;
            const tile = document.createElement("div");
            tile.className = "tile";
            tile.innerHTML = `
                <div class="tile-top">
                    <div class="tile-glyph">${cat.glyph}</div>
                    <div class="tile-count">${count}</div>
                </div>
                <div>
                    <div class="tile-label">${cat.name}</div>
                    <div class="tile-sub">${cat.sub}</div>
                </div>
            `;
            tile.addEventListener("click", () => openCategory(cat.id));
            homeGrid.appendChild(tile);
        });
    }

    // ── Category view ─────────────────────────────────────────────
    function openCategory(catId) {
        const cat = CATEGORIES.find(c => c.id === catId);
        categoryTitle.textContent = cat ? cat.name : catId;

        skillList.innerHTML = "";
        const inCat = allSkills.filter(s => s.category === catId);
        if (inCat.length === 0) {
            skillList.innerHTML = '<div class="chat-empty">No skills in this category.</div>';
        } else {
            inCat.forEach(skill => {
                const row = document.createElement("div");
                row.className = "skill-row";
                row.innerHTML = `
                    <div>
                        <div class="skill-head">
                            <span class="skill-name">${esc(skill.name)}</span>
                            <span class="sensitivity-pill ${skill.sensitivity}">${skill.sensitivity}</span>
                        </div>
                        <div class="skill-desc">${esc(firstSentence(skill.description))}</div>
                    </div>
                    <div class="skill-arrow" style="color: var(--text-3); font-size: 18px;">›</div>
                `;
                row.addEventListener("click", () => openSkill(skill));
                skillList.appendChild(row);
            });
        }
        navigate("category");
    }

    // ── Skill detail view ─────────────────────────────────────────
    function openSkill(skill) {
        currentSkill = skill;
        currentSkillCallId = null;
        skillTitle.textContent = skill.name;
        skillSens.className = "sensitivity-pill " + skill.sensitivity;
        skillSens.textContent = skill.sensitivity;
        skillDesc.textContent = skill.description || "";

        // Build params form.
        skillForm.innerHTML = "";
        const schema = skill.parameters_schema || { properties: {}, required: [] };
        const required = new Set(schema.required || []);
        const props = schema.properties || {};
        const names = Object.keys(props);

        if (names.length === 0) {
            const empty = document.createElement("div");
            empty.className = "params-empty";
            empty.textContent = "This skill takes no parameters. Press Run.";
            skillForm.appendChild(empty);
        } else {
            names.forEach(name => {
                const def = props[name] || {};
                const row = document.createElement("div");
                row.className = "form-field";
                // Boolean and longer descriptions span both columns.
                if (def.type === "boolean" || (def.description && def.description.length > 80)) {
                    row.classList.add("full");
                }

                const lab = document.createElement("label");
                lab.innerHTML = esc(name) + (required.has(name)
                    ? ' <span class="req">*</span>' : "");
                row.appendChild(lab);

                let input;
                if (def.enum && Array.isArray(def.enum)) {
                    input = document.createElement("select");
                    def.enum.forEach(opt => {
                        const o = document.createElement("option");
                        o.value = opt; o.textContent = opt;
                        input.appendChild(o);
                    });
                    const dflt = SMART_DEFAULTS[name] ?? def.default;
                    if (dflt != null) input.value = dflt;
                } else if (def.type === "boolean") {
                    input = document.createElement("select");
                    ["true", "false"].forEach(opt => {
                        const o = document.createElement("option");
                        o.value = opt; o.textContent = opt;
                        input.appendChild(o);
                    });
                    input.value = String(def.default ?? false);
                } else {
                    input = document.createElement("input");
                    input.type = (def.type === "integer" || def.type === "number") ? "number" : "text";
                    const dflt = SMART_DEFAULTS[name] ?? def.default;
                    if (dflt != null) input.value = dflt;
                    input.placeholder = def.type || "string";
                }
                input.dataset.name = name;
                input.dataset.type = def.type || "string";
                row.appendChild(input);

                if (def.description) {
                    const hint = document.createElement("div");
                    hint.className = "hint";
                    hint.textContent = def.description;
                    row.appendChild(hint);
                }
                skillForm.appendChild(row);
            });
        }

        // Clear previous run results.
        skillResult.innerHTML = "";

        navigate("skill");
    }

    function collectFormArgs() {
        const args = {};
        skillForm.querySelectorAll("[data-name]").forEach(el => {
            const name = el.dataset.name;
            const type = el.dataset.type;
            const raw = el.value;
            if (raw === "" || raw == null) return;
            if (type === "integer") {
                const n = Number(raw); if (!isNaN(n)) args[name] = Math.round(n);
            } else if (type === "number") {
                const n = Number(raw); if (!isNaN(n)) args[name] = n;
            } else if (type === "boolean") {
                args[name] = raw === "true";
            } else {
                args[name] = raw;
            }
        });
        return args;
    }

    skillRunBtn.addEventListener("click", () => {
        if (!currentSkill) return;
        const args = collectFormArgs();
        currentSkillCallId = "run";  // mark that a skill result is expected
        body.classList.add("active");
        skillResult.innerHTML = '<div class="result-card">Running…</div>';
        send({ type: "dispatch", skill: currentSkill.name, args });
    });

    function renderSkillResult(data) {
        const isErr = data.error != null;
        const card = document.createElement("div");
        card.className = "result-card " + (isErr ? "error" : "success-border");
        if (isErr) {
            card.textContent = "Error: " + data.error;
        } else {
            const pre = document.createElement("pre");
            try {
                pre.textContent = JSON.stringify(data.result, null, 2);
            } catch (e) {
                pre.textContent = String(data.result);
            }
            card.appendChild(pre);
        }
        skillResult.innerHTML = "";
        skillResult.appendChild(card);
        body.classList.remove("active");
    }

    // ── Chat view ─────────────────────────────────────────────────
    function clearChatEmpty() {
        if (chatEmpty && chatEmpty.parentNode) chatEmpty.parentNode.removeChild(chatEmpty);
    }

    function pushChatMsg(klass, content) {
        clearChatEmpty();
        const el = document.createElement("div");
        el.className = "chat-msg " + klass;
        if (typeof content === "string") el.textContent = content;
        else el.appendChild(content);
        chatMessages.appendChild(el);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return el;
    }

    function pushChatUser(text) {
        pushChatMsg("user", "> " + text);
    }

    function pushChatAssistant(text) {
        // Combine consecutive thinking into one bubble.
        const last = chatMessages.lastElementChild;
        if (last && last.classList.contains("assistant")) {
            last.textContent += text;
            chatMessages.scrollTop = chatMessages.scrollHeight;
            return;
        }
        pushChatMsg("assistant", text);
    }

    function pushChatToolProposed(data) {
        const content = document.createElement("div");
        content.innerHTML = `
            <div class="chat-head">→ ${esc(data.tool_name)} · ${esc(data.sensitivity || "passive")}</div>
            <div>${esc(JSON.stringify(data.arguments))}</div>
        `;
        pushChatMsg("tool-proposed", content);
    }

    function pushChatToolExecuted(data) {
        const ok = data.error == null;
        const content = document.createElement("div");
        const body = ok
            ? (typeof data.result === "string" ? data.result : JSON.stringify(data.result))
            : data.error;
        content.innerHTML = `
            <div class="chat-head">${ok ? "✓" : "✗"} ${esc(data.tool_name)} · ${data.duration_ms || 0}ms</div>
            <div>${esc(truncate(body, 400))}</div>
        `;
        const el = pushChatMsg("tool-executed" + (ok ? "" : " error"), content);
    }

    function pushChatPlanProposed(data) {
        const content = document.createElement("div");
        const stepsHtml = (data.steps || []).map(s =>
            `<div style="padding:4px 0;">· ${esc(s.skill)}${s.critical ? ' <span style="color:var(--red);">[!]</span>' : ''} — ${esc(s.intent)}</div>`
        ).join("");
        const notes = (data.safety_notes || []).map(n =>
            `<div style="color: var(--red); margin-top:8px;">⚠ ${esc(n)}</div>`
        ).join("");
        content.innerHTML = `
            <div class="chat-head">plan proposed</div>
            <div style="color: var(--text); margin-bottom:6px;">${esc(data.reasoning)}</div>
            ${stepsHtml}
            ${notes}
        `;
        pushChatMsg("plan-proposed", content);
    }

    function handleToolExecuted(data) {
        // Route to skill screen if a direct dispatch is in flight and we're on skill view
        if (currentSkillCallId && currentView === "skill") {
            renderSkillResult(data);
            currentSkillCallId = null;
        } else {
            pushChatToolExecuted(data);
        }
    }

    function handleFinal(data) {
        if (currentView === "skill" && currentSkillCallId) {
            body.classList.remove("active");
            currentSkillCallId = null;
            return;
        }
        const content = document.createElement("div");
        const msg = data.text || `[${data.reason}]`;
        content.innerHTML = `<div class="chat-head">${esc(data.reason || "done")}</div><div>${esc(msg)}</div>`;
        pushChatMsg("final", content);
        body.classList.remove("active");
    }

    function sendChatPrompt() {
        const text = chatInput.value.trim();
        if (!text || chatInput.disabled) return;
        pushChatUser(text);
        chatInput.value = "";
        body.classList.add("active");
        send({ type: "prompt", text });
    }

    chatSend.addEventListener("click", sendChatPrompt);
    chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") sendChatPrompt();
    });

    // ── Modal (confirmation + plan approval) ──────────────────────
    function showConfirmationModal(data) {
        pendingConfirmation = data;
        pendingPlanApproval = null;
        const sens = data.sensitivity || "active";
        modalTitle.textContent = `${sens.toUpperCase()}: ${data.tool_name}`;
        modalBody.textContent = JSON.stringify(data.arguments, null, 2);
        modal.className = "modal visible" + (sens === "disruptive" ? " disruptive" : "");
        modalApprove.textContent = sens === "disruptive" ? "Hold to confirm" : "Approve";
        modalReject.textContent = "Reject";
    }

    function showPlanApprovalModal(data) {
        pendingPlanApproval = data;
        pendingConfirmation = null;
        modalTitle.textContent = `Plan — ${data.steps.length} step${data.steps.length === 1 ? "" : "s"}`;
        const lines = data.steps.map((s, i) =>
            `${i + 1}. ${s.skill}${s.critical ? " [critical]" : ""} — ${s.intent}`);
        const notes = (data.safety_notes || []).map(n => `\n⚠ ${n}`).join("");
        modalBody.textContent = (data.reasoning || "") + "\n\n" + lines.join("\n") + notes;
        modal.className = "modal visible";
        modalApprove.textContent = "Approve plan";
        modalReject.textContent = "Reject";
    }

    function hideModal() {
        modal.className = "modal";
        pendingConfirmation = null;
        pendingPlanApproval = null;
    }

    modalApprove.addEventListener("click", () => {
        if (pendingPlanApproval) {
            send({
                type: "plan_approval",
                plan_id: pendingPlanApproval.plan_id,
                approved: true,
            });
        } else if (pendingConfirmation) {
            send({
                type: "confirmation",
                call_id: pendingConfirmation.call_id,
                approved: true,
            });
        }
        hideModal();
    });

    modalReject.addEventListener("click", () => {
        if (pendingPlanApproval) {
            send({
                type: "plan_approval",
                plan_id: pendingPlanApproval.plan_id,
                approved: false,
            });
        } else if (pendingConfirmation) {
            send({
                type: "confirmation",
                call_id: pendingConfirmation.call_id,
                approved: false,
            });
        }
        hideModal();
    });

    // ── Power & Mephisto controls ─────────────────────────────────
    powerOnBtn.addEventListener("click", () => {
        console.log("[faust] power on");
        powerOnBtn.disabled = true;
        powerOnBtn.textContent = "Booting…";
        send({ type: "power", action: "on" });
    });
    powerOffBtn.addEventListener("click", () => {
        if (confirm("Power off the unit?")) send({ type: "power", action: "off" });
    });
    mephistoBtn.addEventListener("click", () => {
        const action = mephistoState === "connected" ? "disconnect" : "connect";
        send({ type: "mephisto", action });
    });

    // ── Helpers ───────────────────────────────────────────────────
    function esc(s) {
        const el = document.createElement("span");
        el.textContent = s == null ? "" : String(s);
        return el.innerHTML;
    }

    function firstSentence(s) {
        if (!s) return "";
        const p = s.indexOf(".");
        return (p > 0 && p < 140) ? s.slice(0, p + 1) : s.slice(0, 140);
    }

    function truncate(s, n) {
        if (!s) return "";
        return s.length > n ? s.slice(0, n) + "…" : s;
    }

    // ── Init ──────────────────────────────────────────────────────
    connect();
})();
