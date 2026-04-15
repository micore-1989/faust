"""
Simulator state machine.

Models the four visible states of the Faust device in the web simulator:

    OFF              nothing running on the screen except a power button
    BOOTING          systemd-style boot console streaming (simulated)
    FAUST_ONLY       unit booted, Mephisto not docked.
                     Skill grid works (direct dispatch). AI agent refuses.
    FAUST_MEPHISTO   Mephisto docked. Full AI agent + skill grid.

The state is server-authoritative — clients that connect/reconnect get
pushed the current state and render accordingly. This mirrors how the
real hardware behaves: Faust remembers whether Mephisto is docked
regardless of how many touchscreens are attached (in practice only one).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Power(str, Enum):
    OFF = "off"
    BOOTING = "booting"
    ON = "on"


class Mephisto(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"


@dataclass
class SimulatorState:
    power: Power = Power.OFF
    mephisto: Mephisto = Mephisto.DISCONNECTED
    # Boot progress 0-100 when BOOTING. Clients render as percentage.
    boot_progress: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "state",
            "power": self.power.value,
            "mephisto": self.mephisto.value,
            "boot_progress": self.boot_progress,
        }

    def can_accept_prompt(self) -> bool:
        """True only when fully booted + Mephisto docked."""
        return self.power == Power.ON and self.mephisto == Mephisto.CONNECTED

    def can_accept_dispatch(self) -> bool:
        """True when booted (Mephisto irrelevant for direct skill dispatch)."""
        return self.power == Power.ON


# Realistic-looking boot log, pacing matches a real Pi 5 + faust.service boot:
#   - kernel stage streams in a fast burst (first ~1s)
#   - short pause while services initialize
#   - userspace services come up in bursts
#   - faust.service takes ~2s to load skills + embeddings
#   - final "ready" after ~6-7s
#
# Times are ms from boot start.
BOOT_LOG: list[tuple[int, str]] = [
    # Kernel boot — fast burst
    (0,    "[    0.000] Linux version 6.6.20-v8+ (pi@faust) 1 SMP PREEMPT"),
    (70,   "[    0.042] Machine model: Raspberry Pi 5 Model B Rev 1.0"),
    (130,  "[    0.128] Booting Linux on physical CPU 0x0000000000 [0x414fd0c1]"),
    (210,  "[    0.211] Memory: 967MB available (Pi 5 1GB, 32MB reserved)"),
    (300,  "[    0.304] CPU: All CPU(s) started in EL2"),
    (400,  "[    0.412] rcu: Preemptible hierarchical RCU implementation"),
    (510,  "[    0.523] rp1-pcie: Raspberry Pi RP1 PCIe 1x4 detected"),
    (640,  "[    0.634] dwc2: USB2 gadget controller online (usb-c)"),
    (760,  "[    0.715] mt76x2u 1-1.2:1.0: wlan1: external WiFi adapter"),
    (880,  "[    0.815] random: crng init done"),

    # Brief pause (disks mounting, etc.)
    (1600, "[    1.572] EXT4-fs (mmcblk0p2): mounted filesystem with ordered data mode"),
    (1800, "[    1.761] systemd[1]: System Initialization."),

    # Services burst
    (2300, "[    2.200] systemd-networkd: Starting..."),
    (2500, "[    2.411] NetworkManager: bringing up wlan0"),
    (2700, "[    2.601] Started systemd-networkd."),
    (2900, "[    2.812] sshd: listening on 0.0.0.0:22"),

    # Faust service
    (3400, "[    3.287] faust.service: Starting..."),
    (3700, "[    3.523] faust: loading skills from /home/pi/faust/skills/"),
    (4400, "[    4.201] faust: loaded 41 skills (23 passive, 11 active, 7 disruptive)"),
    (4900, "[    4.712] faust: disclosure journal initialized (sqlite, hash-chained)"),
    (5400, "[    5.198] faust: scoper embeddings loaded (41 skills, 384-dim)"),
    (5800, "[    5.612] faust: dispatcher ready"),
    (6100, "[    5.895] faust: UI server bound on :8080"),
    (6400, "[    6.167] faust: waiting for Mephisto dock (usb-c gadget)"),
    (6700, "[    6.430] faust: ready (mephisto: disconnected)"),
    (6900, ""),
    (7000, "𝑓aust MK1"),
    (7100, "ready."),
]
BOOT_DURATION_MS = 7100
