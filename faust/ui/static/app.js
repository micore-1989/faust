/**
 * Faust UI — WebSocket client + event renderer.
 *
 * Connects to the agent's WebSocket bridge, renders events in the
 * three-zone shell, and sends confirmation responses back.
 */

(function () {
    "use strict";

    // ── DOM refs ────────────────────────────────────────────────────
    const eventStream   = document.getElementById("event-stream");
    const promptInput   = document.getElementById("prompt-input");
    const sendBtn       = document.getElementById("send-btn");
    const linkDot       = document.getElementById("link-dot");
    const linkLabel     = document.getElementById("link-label");
    const modelLabel    = document.getElementById("model-label");
    const loopLabel     = document.getElementById("loop-label");
    const overlay       = document.getElementById("confirmation-overlay");
    const confirmTitle  = document.getElementById("confirm-title");
    const confirmDetails = document.getElementById("confirm-details");
    const confirmApprove = document.getElementById("confirm-approve");
    const confirmReject  = document.getElementById("confirm-reject");
    const categoryBtns  = document.querySelectorAll(".category-btn");

    let ws = null;
    let pendingConfirmation = null;

    // ── WebSocket connection ────────────────────────────────────────

    function connect() {
        const protocol = location.protocol === "https:" ? "wss:" : "ws:";
        const url = `${protocol}//${location.host}/ws`;
        ws = new WebSocket(url);

        ws.onopen = () => {
            setLinkStatus("connected", "ws connected");
        };

        ws.onclose = () => {
            setLinkStatus("disconnected", "ws closed");
            // Reconnect after 2 seconds.
            setTimeout(connect, 2000);
        };

        ws.onerror = () => {
            setLinkStatus("disconnected", "ws error");
        };

        ws.onmessage = (evt) => {
            try {
                const data = JSON.parse(evt.data);
                handleEvent(data);
            } catch (e) {
                console.error("bad ws message:", e);
            }
        };
    }

    // ── Event handling ──────────────────────────────────────────────

    function handleEvent(data) {
        const type = data.type;

        switch (type) {
            case "thinking":
                renderThinking(data);
                break;
            case "plan_proposed":
                renderPlanProposed(data);
                break;
            case "tool_call_proposed":
                renderToolProposed(data);
                break;
            case "tool_call_executed":
                renderToolExecuted(data);
                break;
            case "final":
                renderFinal(data);
                break;
            case "link_status":
                updateLinkStatus(data);
                break;
            case "confirmation_request":
                showConfirmation(data);
                break;
            case "plan_approval_request":
                showPlanApproval(data);
                break;
            default:
                console.log("unknown event type:", type, data);
        }
    }

    // ── Renderers ───────────────────────────────────────────────────

    function renderPlanProposed(data) {
        const card = document.createElement("div");
        card.className = "event-card event-plan-proposed";
        card.dataset.planId = data.plan_id;

        const steps = (data.steps || []).map((s, i) => {
            const crit = s.critical ? ' <span class="crit-badge">critical</span>' : '';
            return `<li>
                <span class="plan-step-skill">${esc(s.skill)}</span>${crit}
                <div class="plan-step-intent">${esc(s.intent)}</div>
            </li>`;
        }).join("");

        const notes = (data.safety_notes || []).map(n =>
            `<div class="plan-safety-note">⚠ ${esc(n)}</div>`
        ).join("");

        card.innerHTML = `
            <div class="plan-title">Proposed plan <span class="plan-id">${esc(data.plan_id)}</span></div>
            <div class="plan-reasoning">${esc(data.reasoning)}</div>
            <ol class="plan-steps">${steps}</ol>
            ${notes}
        `;
        eventStream.appendChild(card);
        scrollToBottom();
    }

    let pendingPlanApproval = null;

    function showPlanApproval(data) {
        pendingPlanApproval = data;
        confirmTitle.textContent = `PLAN: approve ${data.steps.length} step(s)?`;
        confirmDetails.textContent = (data.steps || [])
            .map((s, i) => `${i + 1}. ${s.skill} — ${s.intent}${s.critical ? ' [critical]' : ''}`)
            .join("\n");
        overlay.className = "visible";
        confirmApprove.className = "btn btn-approve";
        confirmApprove.textContent = "Approve plan";
    }

    function sendPlanApproval(approved) {
        if (!pendingPlanApproval || !ws) return;
        ws.send(JSON.stringify({
            type: "plan_approval",
            plan_id: pendingPlanApproval.plan_id,
            approved: approved,
        }));
        hideConfirmation();
        pendingPlanApproval = null;
    }

    function renderThinking(data) {
        // If the last card is a thinking card, append to it (streaming).
        const last = eventStream.lastElementChild;
        if (last && last.classList.contains("event-thinking") && data.is_delta) {
            last.textContent += data.text;
        } else {
            const card = document.createElement("div");
            card.className = "event-card event-thinking";
            card.textContent = data.text;
            eventStream.appendChild(card);
        }
        scrollToBottom();
        setLoopStatus("thinking");
    }

    function renderToolProposed(data) {
        const sens = data.sensitivity || "passive";
        const card = document.createElement("div");
        card.className = `event-card event-tool-proposed ${sens}`;
        card.innerHTML = `
            <span class="tool-name">${esc(data.tool_name)}</span>
            <span class="sensitivity-badge ${sens}">${sens}</span>
            <div class="args">${esc(JSON.stringify(data.arguments, null, 2))}</div>
        `;
        eventStream.appendChild(card);
        scrollToBottom();
        setLoopStatus(`→ ${data.tool_name}`);
    }

    function renderToolExecuted(data) {
        const isErr = data.error != null;
        const card = document.createElement("div");
        card.className = `event-card event-tool-executed ${isErr ? "error" : "success"}`;

        const symbol = isErr ? "✗" : "✓";
        const content = isErr ? data.error : JSON.stringify(data.result);
        card.innerHTML = `
            <span>${symbol} ${esc(data.tool_name)}</span>
            <span class="duration">${data.duration_ms}ms</span>
            <div class="args">${esc(content)}</div>
        `;
        eventStream.appendChild(card);
        scrollToBottom();
    }

    function renderFinal(data) {
        const card = document.createElement("div");
        card.className = "event-card event-final";
        let text = `[${data.reason}]`;
        if (data.text) text = data.text;
        if (data.error) text += ` — ${data.error}`;
        card.textContent = text;
        eventStream.appendChild(card);
        scrollToBottom();
        setLoopStatus("idle");
        promptInput.disabled = false;
        sendBtn.disabled = false;
        promptInput.focus();
    }

    // ── Confirmation UI ─────────────────────────────────────────────

    function showConfirmation(data) {
        pendingConfirmation = data;
        const sens = data.sensitivity || "active";

        confirmTitle.textContent = `${sens.toUpperCase()}: ${data.tool_name}`;
        confirmDetails.textContent = JSON.stringify(data.arguments, null, 2);

        overlay.className = sens === "disruptive" ? "disruptive visible" : "visible";
        confirmApprove.className = sens === "disruptive"
            ? "btn btn-approve disruptive"
            : "btn btn-approve";

        confirmApprove.textContent = sens === "disruptive" ? "Hold to confirm" : "Approve";
    }

    function hideConfirmation() {
        overlay.className = "";
        pendingConfirmation = null;
    }

    function sendConfirmation(approved) {
        if (!pendingConfirmation || !ws) return;
        ws.send(JSON.stringify({
            type: "confirmation",
            call_id: pendingConfirmation.call_id,
            approved: approved,
        }));
        hideConfirmation();
    }

    confirmApprove.addEventListener("click", () => {
        if (pendingPlanApproval) sendPlanApproval(true);
        else sendConfirmation(true);
    });
    confirmReject.addEventListener("click", () => {
        if (pendingPlanApproval) sendPlanApproval(false);
        else sendConfirmation(false);
    });

    // ── Status bar updates ──────────────────────────────────────────

    function setLinkStatus(state, label) {
        linkDot.className = `status-dot ${state}`;
        linkLabel.textContent = label || state;
    }

    function setLoopStatus(text) {
        loopLabel.textContent = text;
    }

    function updateLinkStatus(data) {
        setLinkStatus(data.state, data.label || data.state);
        if (data.model) {
            modelLabel.textContent = data.model;
        }
    }

    // ── Prompt input ────────────────────────────────────────────────

    function sendPrompt() {
        const text = promptInput.value.trim();
        if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;

        // Clear previous events.
        eventStream.innerHTML = "";

        // Show user message.
        const card = document.createElement("div");
        card.className = "event-card event-thinking";
        card.style.color = "var(--goethe-gold)";
        card.textContent = `> ${text}`;
        eventStream.appendChild(card);

        ws.send(JSON.stringify({ type: "prompt", text: text }));
        promptInput.value = "";
        promptInput.disabled = true;
        sendBtn.disabled = true;
        setLoopStatus("running...");
    }

    sendBtn.addEventListener("click", sendPrompt);
    promptInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") sendPrompt();
    });

    // ── Category nav ────────────────────────────────────────────────

    categoryBtns.forEach((btn) => {
        btn.addEventListener("click", () => {
            categoryBtns.forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");
            // Category filtering will be wired when skill scoping is built.
        });
    });

    // ── Helpers ─────────────────────────────────────────────────────

    function scrollToBottom() {
        eventStream.scrollTop = eventStream.scrollHeight;
    }

    function esc(str) {
        const el = document.createElement("span");
        el.textContent = str;
        return el.innerHTML;
    }

    // ── Init ────────────────────────────────────────────────────────
    connect();

})();
