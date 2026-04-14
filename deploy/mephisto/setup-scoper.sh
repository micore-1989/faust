#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Mephisto scoper HTTP service setup
#
# Runs the embedding-based skill scoper on Mephisto (Pi 5 16GB) instead
# of Faust (Pi 5 1GB) to save ~400MB of Faust RAM.
#
# Architecture:
#   Faust (1GB) → RemoteEmbeddingScoper over USB-ethernet
#   Mephisto (16GB) → scoper_server.py wrapping LocalEmbeddingScoper
#
# Runs alongside hailo-ollama (port 8000) and the deep planner (8081).
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="${REPO_DIR:-/home/${USER}/faust}"
VENV_DIR="${REPO_DIR}/.venv"
PORT=8082
BIND_ADDR="10.66.0.2"

echo "=== Mephisto scoper service setup ==="

# ── 1. Install Python venv + requirements ───────────────────────────
if [ ! -d "${VENV_DIR}" ]; then
    echo "[+] Creating venv at ${VENV_DIR}"
    python3 -m venv "${VENV_DIR}"
fi

echo "[+] Installing Python dependencies"
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install -r "${REPO_DIR}/requirements-mephisto.txt"

# ── 2. Warm the embedding cache ─────────────────────────────────────
# Precompute embeddings so the systemd service starts fast.
echo "[+] Pre-computing skill embeddings"
"${VENV_DIR}/bin/python" -c "
from pathlib import Path
from faust.skills.scoper import LocalEmbeddingScoper
LocalEmbeddingScoper(Path('${REPO_DIR}/skills'))
print('embeddings cached')
"

# ── 3. Systemd unit ─────────────────────────────────────────────────
SERVICE_FILE=/etc/systemd/system/faust-scoper.service
sudo tee "${SERVICE_FILE}" > /dev/null <<EOF
[Unit]
Description=Faust skill scoper HTTP service
After=network-online.target systemd-networkd.service
Wants=network-online.target

[Service]
Type=simple
User=${USER}
WorkingDirectory=${REPO_DIR}
ExecStart=${VENV_DIR}/bin/python ${REPO_DIR}/deploy/mephisto/scoper_server.py \\
    --skills-dir ${REPO_DIR}/skills \\
    --host ${BIND_ADDR} \\
    --port ${PORT}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "[+] Created ${SERVICE_FILE}"

sudo systemctl daemon-reload
sudo systemctl enable faust-scoper
sudo systemctl start faust-scoper

sleep 3
if sudo systemctl is-active --quiet faust-scoper; then
    echo "[+] faust-scoper is running"
else
    echo "[!] faust-scoper failed to start. Check: sudo journalctl -u faust-scoper"
    exit 1
fi

# ── 4. Smoke test ───────────────────────────────────────────────────
echo ""
echo "[+] Testing scoper endpoint..."
sleep 1
curl -sS -X POST "http://${BIND_ADDR}:${PORT}/v1/scope" \
    -H "Content-Type: application/json" \
    -d '{"query": "scan for nearby wifi networks", "k": 5}'
echo ""

# ── 5. Summary ──────────────────────────────────────────────────────
echo ""
echo "=== Scoper service ready ==="
echo ""
echo "  Endpoint: http://${BIND_ADDR}:${PORT}/v1"
echo "  Model:    sentence-transformers/all-MiniLM-L6-v2"
echo "  RAM:      ~80 MB resident"
echo ""
echo "  On Faust, set: FAUST_SCOPER_ENDPOINT=http://${BIND_ADDR}:${PORT}/v1"
echo "  (or use FAUST_BACKEND=mephisto which auto-routes)"
echo ""
echo "  Monitor: sudo systemctl status faust-scoper"
echo "  Logs:    sudo journalctl -u faust-scoper -f"
