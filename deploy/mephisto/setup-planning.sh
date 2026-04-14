#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Mephisto deep-planner (llama.cpp + Qwen 2.5 7B int4) setup
#
# Adds the "deep thinking" backend used by Pass 1 of TwoPassAgent. Runs
# Qwen 2.5 7B quantized to int4 on Mephisto's Pi 5 CPU via llama.cpp's
# OpenAI-compatible server. ~4.5GB RAM, ~2-4 tok/s (about 60s per plan).
#
# The Hailo NPU keeps running Qwen 2.5 1.5B for fast Pass 2 parameterize
# calls on port 8000. This script adds a second endpoint on port 8081.
#
# Run once on Mephisto after setup-gadget.sh.
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

LLAMA_CPP_DIR="${HOME}/llama.cpp"
MODEL_DIR="${HOME}/models"
MODEL_URL="https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf"
MODEL_FILE="${MODEL_DIR}/qwen2.5-7b-instruct-q4_k_m.gguf"
PORT=8081
BIND_ADDR="10.66.0.2"

echo "=== Mephisto deep-planner setup ==="

# ── 1. Install build deps ────────────────────────────────────────────
echo "[+] Installing build dependencies"
sudo apt update
sudo apt install -y build-essential cmake git libcurl4-openssl-dev wget

# ── 2. Clone and build llama.cpp ─────────────────────────────────────
if [ ! -d "${LLAMA_CPP_DIR}" ]; then
    echo "[+] Cloning llama.cpp"
    git clone https://github.com/ggerganov/llama.cpp.git "${LLAMA_CPP_DIR}"
fi

echo "[+] Building llama.cpp (CPU-only, Pi 5 ARMv8.2 with SVE)"
cd "${LLAMA_CPP_DIR}"
git pull --ff-only
cmake -B build -DGGML_NATIVE=ON -DLLAMA_CURL=ON
cmake --build build --config Release -j $(nproc)

# ── 3. Download Qwen 2.5 7B int4 GGUF ────────────────────────────────
mkdir -p "${MODEL_DIR}"
if [ ! -f "${MODEL_FILE}" ]; then
    echo "[+] Downloading Qwen 2.5 7B Q4_K_M (~4.5GB, this takes a while)"
    wget -O "${MODEL_FILE}" "${MODEL_URL}"
else
    echo "[=] Qwen 2.5 7B already downloaded at ${MODEL_FILE}"
fi

# ── 4. Systemd unit for llama-server ─────────────────────────────────
SERVICE_FILE=/etc/systemd/system/faust-deep-planner.service
sudo tee "${SERVICE_FILE}" > /dev/null <<EOF
[Unit]
Description=Faust deep-planner (llama.cpp, Qwen 2.5 7B)
After=network-online.target systemd-networkd.service
Wants=network-online.target

[Service]
Type=simple
User=${USER}
ExecStart=${LLAMA_CPP_DIR}/build/bin/llama-server \\
    --model ${MODEL_FILE} \\
    --host ${BIND_ADDR} \\
    --port ${PORT} \\
    --ctx-size 8192 \\
    --n-predict 512 \\
    --threads $(nproc) \\
    --jinja
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "[+] Created ${SERVICE_FILE}"

sudo systemctl daemon-reload
sudo systemctl enable faust-deep-planner
sudo systemctl start faust-deep-planner

sleep 3
if sudo systemctl is-active --quiet faust-deep-planner; then
    echo "[+] faust-deep-planner is running"
else
    echo "[!] faust-deep-planner failed to start. Check: sudo journalctl -u faust-deep-planner"
    exit 1
fi

# ── 5. Smoke test ────────────────────────────────────────────────────
echo ""
echo "[+] Testing OpenAI-compatible endpoint..."
sleep 2
curl -sS -X POST "http://${BIND_ADDR}:${PORT}/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d '{
        "model": "qwen2.5:7b-instruct",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 20
    }' | head -c 400
echo ""

# ── 6. Summary ───────────────────────────────────────────────────────
echo ""
echo "=== Deep-planner ready ==="
echo ""
echo "  Endpoint: http://${BIND_ADDR}:${PORT}/v1 (Mephisto Pi 5 CPU)"
echo "  Model:    Qwen 2.5 7B Q4_K_M (${MODEL_FILE})"
echo "  RAM:      ~4.5GB resident"
echo "  Speed:    ~2-4 tok/s on Pi 5 CPU"
echo ""
echo "  Faust config — planning auto-routes to this endpoint when"
echo "  FAUST_BACKEND=mephisto. Override with FAUST_PLANNING_ENDPOINT."
echo ""
echo "  Monitor: sudo systemctl status faust-deep-planner"
echo "  Logs:    sudo journalctl -u faust-deep-planner -f"
