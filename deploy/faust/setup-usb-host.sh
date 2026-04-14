#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Faust USB host-side network config
#
# When Mephisto docks via USB-C, it appears as a CDC Ethernet gadget.
# Faust (the USB host) sees a new interface (usb0). This script assigns
# a static IP on the matching /30 subnet:
#
#   Faust  (host)   → 10.66.0.1
#   Mephisto (gadget) → 10.66.0.2
#
# Run once on a fresh Faust microSD after imaging Pi OS (64-bit).
# Requires sudo.
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

HOST_IP="10.66.0.1"
HOST_MASK="30"
INTERFACE="usb0"

echo "=== Faust USB host-side network setup ==="

# ── 1. Static IP on usb0 via systemd-networkd ───────────────────────
sudo mkdir -p /etc/systemd/network

sudo tee /etc/systemd/network/10-usb-mephisto.network > /dev/null <<EOF
[Match]
Name=${INTERFACE}

[Network]
Address=${HOST_IP}/${HOST_MASK}
# No gateway — captive point-to-point link to Mephisto.
# No DNS — inference traffic only.
EOF

echo "[+] Created systemd-networkd config for ${INTERFACE} (${HOST_IP}/${HOST_MASK})"

sudo systemctl enable systemd-networkd

# Tell NetworkManager to leave usb0 alone.
sudo mkdir -p /etc/NetworkManager/conf.d
sudo tee /etc/NetworkManager/conf.d/99-ignore-usb0.conf > /dev/null <<EOF
[keyfile]
unmanaged-devices=interface-name:usb0
EOF

echo "[+] Configured NetworkManager to ignore ${INTERFACE}"

# ── 2. Convenience: add mephisto to /etc/hosts ──────────────────────
if ! grep -q "mephisto" /etc/hosts; then
    echo "10.66.0.2  mephisto" | sudo tee -a /etc/hosts
    echo "[+] Added 'mephisto' to /etc/hosts (10.66.0.2)"
else
    echo "[=] 'mephisto' already in /etc/hosts"
fi

# ── 3. Summary ───────────────────────────────────────────────────────
echo ""
echo "=== Setup complete ==="
echo ""
echo "When Mephisto is docked:"
echo "  - usb0 appears with IP ${HOST_IP}/${HOST_MASK}"
echo "  - Mephisto reachable at 10.66.0.2 (or 'mephisto')"
echo "  - LLM endpoint: http://mephisto:8000/v1"
echo ""
echo "Set in your environment or .env:"
echo "  FAUST_LLM_ENDPOINT=http://10.66.0.2:8000/v1"
echo ""
echo "Test connectivity:"
echo "  ping mephisto"
echo "  curl http://mephisto:8000/v1/models"
