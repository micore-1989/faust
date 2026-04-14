"""
UI runner — starts the web server and agent loop together.

Serves the three-zone shell at http://localhost:8080.
WebSocket at /ws streams agent events to the browser and receives prompts
+ confirmation responses back.

Usage:
    python -m faust.ui.run                  # live agent mode (default)
    python -m faust.ui.run --demo           # layout prototyping with synthetic events

Live agent mode requires an LLM backend — Ollama on Mac for dev, hailo-ollama
on Mephisto in production. Set FAUST_BACKEND=mephisto when running on Faust.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from typing import Any

from ..agent.backends import make_backend, make_deep_backend
from ..agent.config import AgentConfig
from ..agent.disclosure import DisclosureApprover
from ..agent.dispatch import Dispatcher
from ..agent.events import Final, PlanProposed, Thinking, ToolCallExecuted, ToolCallProposed
from ..agent.journal import Journal
from ..agent.loop import AgentLoop
from ..agent.plan import Plan
from ..agent.twopass import TwoPassAgent
from ..skills.loader import load_skills_into_registry
from ..skills.scoper import make_scoper
from ..tools.registry import Sensitivity, ToolRegistry
from ..transport.link import LinkState, MephistoLink
from .bridge import EventBridge
from .server import UIServer


class UIConfirmation:
    """Bridges DisclosureApprover's confirmation callback through the UI.

    When called, pushes a confirmation_request event to the bridge (which
    renders the banner in the browser), then awaits the server's confirmation
    queue, matching responses by call_id.
    """

    def __init__(self, bridge: EventBridge, server: UIServer) -> None:
        self.bridge = bridge
        self.server = server

    async def __call__(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        sensitivity: Sensitivity,
    ) -> bool:
        # DisclosureApprover doesn't pass call_id, so we generate one and
        # include it in the prompt. The JS client echoes whatever call_id
        # it received back in the response.
        call_id = f"confirm-{uuid.uuid4().hex[:8]}"

        await self.bridge.push_raw({
            "type": "confirmation_request",
            "call_id": call_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "sensitivity": sensitivity,
        })

        # Wait for a matching response. Ignore stray responses with wrong id.
        while True:
            resp = await self.server.wait_for_confirmation()
            if resp.get("call_id") == call_id:
                return bool(resp.get("approved", False))


class UIPlanApprover:
    """Plan-level approval through the WebSocket — user sees the whole plan
    and approves/rejects it as a unit before execution begins."""

    def __init__(self, bridge: EventBridge, server: UIServer) -> None:
        self.bridge = bridge
        self.server = server

    async def __call__(self, plan: Plan) -> bool:
        plan_id = f"plan-{uuid.uuid4().hex[:8]}"
        await self.bridge.push_raw({
            "type": "plan_approval_request",
            "plan_id": plan_id,
            "reasoning": plan.reasoning,
            "steps": [
                {"skill": s.skill, "intent": s.intent, "critical": s.critical}
                for s in plan.steps
            ],
            "safety_notes": plan.safety_notes,
        })
        while True:
            resp = await self.server.wait_for_plan_approval()
            if resp.get("plan_id") == plan_id:
                return bool(resp.get("approved", False))


async def push_demo_events(bridge: EventBridge) -> None:
    """Send synthetic events for layout prototyping without an LLM."""
    await asyncio.sleep(2)

    await bridge.push_event(Thinking(text="Scanning for nearby WiFi networks..."))
    await asyncio.sleep(0.5)
    await bridge.push_event(ToolCallProposed(
        call_id="demo-1",
        tool_name="wifi_scan",
        arguments={"interface": "wlan1mon", "duration_s": 10, "band": "all"},
        sensitivity="passive",
    ))
    await asyncio.sleep(0.3)
    await bridge.push_event(ToolCallExecuted(
        call_id="demo-1",
        tool_name="wifi_scan",
        result={"networks": [
            {"ssid": "TargetNet", "bssid": "aa:bb:cc:dd:ee:ff", "channel": 6,
             "rssi_dbm": -42, "encryption": "WPA2-PSK"},
            {"ssid": "GuestWiFi", "bssid": "11:22:33:44:55:66", "channel": 11,
             "rssi_dbm": -67, "encryption": "Open"},
        ], "scan_duration_s": 10},
        duration_ms=10230,
    ))
    await asyncio.sleep(0.5)
    await bridge.push_event(Thinking(
        text="Found 2 networks. TargetNet (WPA2-PSK, ch6, -42dBm) looks like "
             "the strongest. GuestWiFi is open. Would you like me to capture "
             "a handshake from TargetNet?"
    ))
    await asyncio.sleep(0.3)
    await bridge.push_event(ToolCallProposed(
        call_id="demo-2",
        tool_name="wifi_deauth",
        arguments={"bssid": "aa:bb:cc:dd:ee:ff", "client": "ff:ff:ff:ff:ff:ff",
                   "interface": "wlan1mon", "count": 5},
        sensitivity="disruptive",
    ))
    await asyncio.sleep(0.3)
    await bridge.push_event(ToolCallExecuted(
        call_id="demo-2",
        tool_name="wifi_deauth",
        error="user_rejected",
        duration_ms=0,
    ))
    await asyncio.sleep(0.3)
    await bridge.push_event(Final(reason="user_abort"))


async def run_agent_loop(
    bridge: EventBridge,
    server: UIServer,
) -> None:
    """Live agent loop: reads prompts from the UI, runs the agent, pushes events."""
    cfg = AgentConfig.from_env()
    backend = make_backend(cfg)

    # Load skills from skills/ directory (project root).
    registry = ToolRegistry()
    skills_dir = Path(__file__).resolve().parent.parent.parent / "skills"
    loaded = load_skills_into_registry(skills_dir, registry)
    print(f"  loaded skills: {', '.join(loaded) if loaded else '(none)'}")

    # Disclosure layer: journal + UI confirmation callback.
    journal_path = Path(__file__).resolve().parent.parent.parent / "journal.db"
    journal = Journal(str(journal_path))
    confirm = UIConfirmation(bridge, server)
    approver = DisclosureApprover(journal, confirm=confirm)
    dispatcher = Dispatcher(registry, approver=approver)

    scoper = None
    if cfg.scoper_enabled:
        scoper = make_scoper(
            skills_dir,
            [t.name for t in registry.all()],
            remote_endpoint=cfg.effective_scoper_endpoint() or None,
        )
        print(f"  scoper={type(scoper).__name__} k={cfg.scoper_k}")

    if cfg.mode == "twopass":
        plan_approver = UIPlanApprover(bridge, server)
        deep_backend = make_deep_backend(cfg)
        if deep_backend is not None:
            print(f"  deep planner: {cfg.planning_model} @ {cfg.effective_planning_endpoint()}")
        agent = TwoPassAgent(
            backend, dispatcher, cfg,
            scoper=scoper,
            plan_approver=plan_approver,
            deep_backend=deep_backend,
        )
        print(f"  mode=twopass (plan → per-step parameterize → dispatch)")
    else:
        agent = AgentLoop(
            backend, dispatcher, cfg,
            scoper=scoper, scoper_k=cfg.scoper_k,
        )
        print(f"  mode=single (classic single-pass loop)")

    # If using Mephisto backend, probe the link.
    link: MephistoLink | None = None
    if cfg.backend == "mephisto":
        from ..agent.config import MEPHISTO_ENDPOINT
        link = MephistoLink(endpoint=MEPHISTO_ENDPOINT)
        status = await link.check()
        await bridge.push_raw({
            "type": "link_status",
            "state": status.state.value,
            "label": f"mephisto {status.state.value}",
            "model": status.model or cfg.model,
        })
    else:
        # Assume the local ollama is up; the first request will tell us.
        await bridge.push_raw({
            "type": "link_status",
            "state": "connected",
            "label": f"{cfg.backend} ready",
            "model": cfg.model,
        })

    print(f"  backend={cfg.backend} model={cfg.model} endpoint={cfg.llm_endpoint}")
    print("  ready. type a prompt in the browser.\n")

    try:
        while True:
            prompt = await server.wait_for_prompt()
            print(f"  > {prompt}")

            async for event in agent.run(prompt):
                await bridge.push_event(event)
    finally:
        journal.close()
        if link is not None:
            await link.aclose()
        db = getattr(agent, "deep_backend", None)
        if db is not None:
            await db.aclose()
        await backend.aclose()


async def main() -> None:
    demo = "--demo" in sys.argv
    port = 8080

    bridge = EventBridge()
    server = UIServer(bridge, port=port)
    await server.start()

    print(f"\n  𝑓aust UI running at http://localhost:{port}")
    print(f"  mode: {'demo (layout prototyping)' if demo else 'live agent'}")

    try:
        if demo:
            asyncio.create_task(push_demo_events(bridge))
            while True:
                await asyncio.sleep(1)
        else:
            await run_agent_loop(bridge, server)
    except KeyboardInterrupt:
        pass
    finally:
        await server.stop()
        print("\n  server stopped.")


if __name__ == "__main__":
    asyncio.run(main())
