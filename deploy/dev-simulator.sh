#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Dev simulator — spin up Mac-local processes that mirror the Pi production
# architecture. Use this when you want to exercise the full Faust↔Mephisto
# split without plugging in hardware.
#
# Architecture simulated:
#
#   ┌─ Faust side ─────────────────┐   ┌─ Mephisto side ───────────────┐
#   │ Agent + UI   :8080           │   │ Ollama (fast + deep)  :11434  │
#   │   ↓                          │→←─│ Scoper service        :8082   │
#   │ RemoteEmbeddingScoper → 8082 │   │                               │
#   └──────────────────────────────┘   └───────────────────────────────┘
#
# On real hardware, Faust and Mephisto are separate Pi 5s on a /30 link.
# On Mac, everything is localhost but the process boundaries are real —
# the scoper runs in a different Python process from the UI, exercising
# the actual RemoteEmbeddingScoper code path that Faust will use in prod.
#
# Usage:
#   bash deploy/dev-simulator.sh start      # starts all services
#   bash deploy/dev-simulator.sh stop       # stops them
#   bash deploy/dev-simulator.sh status     # checks what's running
#   bash deploy/dev-simulator.sh logs       # tails logs from all services
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_DIR="${REPO_DIR}/.dev-sim"
LOG_DIR="${PID_DIR}/logs"
mkdir -p "${PID_DIR}" "${LOG_DIR}"

SCOPER_PORT=8082
UI_PORT=8080
OLLAMA_PORT=11434

# ── Colors ───────────────────────────────────────────────────────────
YELLOW=$'\033[33m'
GREEN=$'\033[32m'
RED=$'\033[31m'
DIM=$'\033[2m'
BOLD=$'\033[1m'
RESET=$'\033[0m'

# ── Helpers ──────────────────────────────────────────────────────────

check_ollama() {
    if ! command -v ollama > /dev/null; then
        echo "${RED}✗ ollama not installed. brew install ollama${RESET}"
        return 1
    fi
    if ! curl -sS --max-time 2 "http://localhost:${OLLAMA_PORT}/api/tags" > /dev/null 2>&1; then
        echo "${YELLOW}⚠ ollama not running on :${OLLAMA_PORT} — start it with 'ollama serve &'${RESET}"
        return 1
    fi
    local has_fast=$(ollama list 2>/dev/null | grep -c "qwen2.5:1.5b" || true)
    local has_deep=$(ollama list 2>/dev/null | grep -c "qwen2.5:7b" || true)
    if [ "${has_fast}" -eq 0 ]; then
        echo "${YELLOW}⚠ qwen2.5:1.5b-instruct not pulled — run 'ollama pull qwen2.5:1.5b-instruct'${RESET}"
    fi
    if [ "${has_deep}" -eq 0 ]; then
        echo "${YELLOW}⚠ qwen2.5:7b-instruct not pulled — run 'ollama pull qwen2.5:7b-instruct'${RESET}"
    fi
    echo "${GREEN}✓ ollama: localhost:${OLLAMA_PORT}${RESET}"
    return 0
}

start_scoper() {
    local pidfile="${PID_DIR}/scoper.pid"
    if [ -f "${pidfile}" ] && kill -0 "$(cat "${pidfile}")" 2>/dev/null; then
        echo "${DIM}scoper already running (pid $(cat "${pidfile}"))${RESET}"
        return 0
    fi

    echo "${DIM}starting scoper service on :${SCOPER_PORT}...${RESET}"
    cd "${REPO_DIR}"
    PYTHONUNBUFFERED=1 \
    python "${REPO_DIR}/deploy/mephisto/scoper_server.py" \
        --skills-dir "${REPO_DIR}/skills" \
        --host 127.0.0.1 \
        --port "${SCOPER_PORT}" \
        > "${LOG_DIR}/scoper.log" 2>&1 &
    echo $! > "${pidfile}"

    # Wait for it to come up.
    for i in {1..20}; do
        if curl -sS --max-time 1 "http://localhost:${SCOPER_PORT}/v1/health" > /dev/null 2>&1; then
            echo "${GREEN}✓ scoper: localhost:${SCOPER_PORT}${RESET}"
            return 0
        fi
        sleep 0.5
    done
    echo "${RED}✗ scoper failed to start — check ${LOG_DIR}/scoper.log${RESET}"
    return 1
}

start_ui() {
    local pidfile="${PID_DIR}/ui.pid"
    if [ -f "${pidfile}" ] && kill -0 "$(cat "${pidfile}")" 2>/dev/null; then
        echo "${DIM}UI already running (pid $(cat "${pidfile}"))${RESET}"
        return 0
    fi

    echo "${DIM}starting UI on :${UI_PORT} with remote scoper...${RESET}"
    cd "${REPO_DIR}"
    # Configure the UI to use the local-simulated "Mephisto" scoper.
    # PYTHONUNBUFFERED makes sure print() output reaches the log in real time.
    PYTHONUNBUFFERED=1 \
    FAUST_SCOPER_ENDPOINT="http://localhost:${SCOPER_PORT}/v1" \
    python -m faust.ui.run \
        > "${LOG_DIR}/ui.log" 2>&1 &
    echo $! > "${pidfile}"

    # UI takes a moment to initialize.
    sleep 2
    if kill -0 "$(cat "${pidfile}")" 2>/dev/null; then
        echo "${GREEN}✓ UI: http://localhost:${UI_PORT}${RESET}"
    else
        echo "${RED}✗ UI failed to start — check ${LOG_DIR}/ui.log${RESET}"
        return 1
    fi
}

stop_one() {
    local name=$1
    local pidfile="${PID_DIR}/${name}.pid"
    if [ ! -f "${pidfile}" ]; then
        return 0
    fi
    local pid=$(cat "${pidfile}")
    if kill -0 "${pid}" 2>/dev/null; then
        kill "${pid}"
        echo "${DIM}stopped ${name} (pid ${pid})${RESET}"
    fi
    rm -f "${pidfile}"
}

status_one() {
    local name=$1
    local port=$2
    local pidfile="${PID_DIR}/${name}.pid"
    if [ -f "${pidfile}" ] && kill -0 "$(cat "${pidfile}")" 2>/dev/null; then
        echo "${GREEN}✓ ${name}: running (pid $(cat "${pidfile}"), port ${port})${RESET}"
    else
        echo "${RED}✗ ${name}: not running${RESET}"
    fi
}

# ── Commands ─────────────────────────────────────────────────────────

cmd_start() {
    echo "${BOLD}Faust dev-simulator starting...${RESET}"
    echo ""
    check_ollama || true  # warn but don't abort — user may be testing without LLM
    echo ""
    start_scoper
    start_ui
    echo ""
    echo "${BOLD}Ready.${RESET} Open ${GREEN}http://localhost:${UI_PORT}${RESET} in your browser."
    echo ""
    echo "${DIM}Logs: ${LOG_DIR}/${RESET}"
    echo "${DIM}Stop: bash $0 stop${RESET}"
}

cmd_stop() {
    stop_one ui
    stop_one scoper
    echo "${DIM}(ollama left running — stop manually if you want)${RESET}"
}

cmd_status() {
    check_ollama || true
    status_one scoper "${SCOPER_PORT}"
    status_one ui "${UI_PORT}"
}

cmd_logs() {
    if command -v multitail > /dev/null; then
        multitail "${LOG_DIR}/scoper.log" "${LOG_DIR}/ui.log"
    else
        tail -f "${LOG_DIR}"/*.log
    fi
}

case "${1:-start}" in
    start)   cmd_start ;;
    stop)    cmd_stop ;;
    status)  cmd_status ;;
    logs)    cmd_logs ;;
    restart) cmd_stop; sleep 1; cmd_start ;;
    *)
        echo "usage: $0 {start|stop|status|logs|restart}"
        exit 2
        ;;
esac
