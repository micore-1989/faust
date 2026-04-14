#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Mephisto USB-ethernet gadget mode setup
#
# Turns Mephisto's USB-C port into an ethernet device so Faust (the USB
# host) sees a network interface. Point-to-point link on 10.66.0.0/30:
#
#   Faust  (host)   → 10.66.0.1
#   Mephisto (gadget) → 10.66.0.2
#
# Mephisto serves hailo-ollama at http://10.66.0.2:8000/v1.
#
# Run once on a fresh Mephisto microSD after imaging Pi OS Lite (64-bit).
# Requires sudo.
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

GADGET_IP="10.66.0.2"
GADGET_MASK="30"
INTERFACE="usb0"

echo "=== Mephisto USB gadget ethernet setup ==="

# ── 1. Enable dwc2 overlay (USB gadget controller) ──────────────────
# Pi 5 uses dwc2 for the USB-C port's device/gadget mode.
if ! grep -q "^dtoverlay=dwc2" /boot/firmware/config.txt; then
    echo "dtoverlay=dwc2" | sudo tee -a /boot/firmware/config.txt
    echo "[+] Added dwc2 overlay to config.txt"
else
    echo "[=] dwc2 overlay already in config.txt"
fi

# Load dwc2 at boot.
if ! grep -q "^dwc2" /etc/modules; then
    echo "dwc2" | sudo tee -a /etc/modules
    echo "[+] Added dwc2 to /etc/modules"
fi

# Load g_ether (CDC Ethernet gadget) at boot.
if ! grep -q "^g_ether" /etc/modules; then
    echo "g_ether" | sudo tee -a /etc/modules
    echo "[+] Added g_ether to /etc/modules"
fi

# ── 2. Static IP on usb0 via systemd-networkd ───────────────────────
# Pi OS Bookworm uses NetworkManager by default, but for a captive
# point-to-point link, systemd-networkd is simpler and more predictable.
# We create a drop-in that only manages usb0; everything else stays
# under NetworkManager.

sudo mkdir -p /etc/systemd/network

sudo tee /etc/systemd/network/10-usb-gadget.network > /dev/null <<EOF
[Match]
Name=${INTERFACE}

[Network]
Address=${GADGET_IP}/${GADGET_MASK}
# No gateway — this is a captive point-to-point link.
# No DNS — Mephisto doesn't need name resolution over this link.
EOF

echo "[+] Created systemd-networkd config for ${INTERFACE} (${GADGET_IP}/${GADGET_MASK})"

# Enable systemd-networkd (it coexists with NetworkManager if only
# managing interfaces NM doesn't claim).
sudo systemctl enable systemd-networkd

# Tell NetworkManager to leave usb0 alone.
sudo tee /etc/NetworkManager/conf.d/99-ignore-usb0.conf > /dev/null <<EOF
[keyfile]
unmanaged-devices=interface-name:usb0
EOF

echo "[+] Configured NetworkManager to ignore ${INTERFACE}"

# ── 3. Firewall: only accept traffic from Faust ─────────────────────
# Mephisto should only accept connections on usb0 from Faust's IP.
# This prevents any other device on any other interface from reaching
# hailo-ollama.

sudo tee /etc/nftables.d/mephisto-usb.conf > /dev/null <<'EOF'
table inet mephisto_usb {
    chain input {
        type filter hook input priority 0; policy accept;

        # Allow all traffic on usb0 from Faust only.
        iifname "usb0" ip saddr 10.66.0.1 accept
        # Drop everything else on usb0.
        iifname "usb0" drop
    }
}
EOF

echo "[+] Created nftables rule: usb0 accepts only 10.66.0.1"
echo "    (Apply with: sudo nft -f /etc/nftables.d/mephisto-usb.conf)"

# ── 4. Summary ───────────────────────────────────────────────────────
echo ""
echo "=== Setup complete. Reboot to activate gadget mode. ==="
echo ""
echo "After reboot:"
echo "  - Mephisto's USB-C port becomes an ethernet gadget"
echo "  - usb0 gets static IP ${GADGET_IP}/${GADGET_MASK}"
echo "  - Faust (host) should configure its side as 10.66.0.1/30"
echo "  - hailo-ollama should bind to ${GADGET_IP}:8000"
echo ""
echo "Test connectivity from Faust:"
echo "  ping ${GADGET_IP}"
echo "  curl http://${GADGET_IP}:8000/v1/models"
