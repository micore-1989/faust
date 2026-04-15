"""
UI runner — starts the web server that drives the Faust simulator.

Boot flow (matches the real device):
  1. Page loads at OFF state — press "Power" button to boot
  2. BOOTING state plays the simulated systemd boot log
  3. FAUST_ONLY state: skill grid works for direct dispatch, agent locked
  4. Toggle "Connect Mephisto" to unlock the AI agent

Usage:
    python -m faust.ui.run                  # live agent (requires Ollama)
    python -m faust.ui.run --demo           # synthetic event stream for layout work
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from ..agent.backends import make_backend, make_deep_backend
from ..agent.catalog import _categorize
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
from .state import SimulatorState


class UIConfirmation:
    def __init__(self, bridge: EventBridge, server: UIServer) -> None:
        self.bridge = bridge
        self.server = server

    async def __call__(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        sensitivity: Sensitivity,
    ) -> bool:
        call_id = f"confirm-{uuid.uuid4().hex[:8]}"
        await self.bridge.push_raw({
            "type": "confirmation_request",
            "call_id": call_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "sensitivity": sensitivity,
        })
        while True:
            resp = await self.server.wait_for_confirmation()
            if resp.get("call_id") == call_id:
                return bool(resp.get("approved", False))


class UIPlanApprover:
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


def _build_skills_catalog(registry: ToolRegistry) -> list[dict[str, Any]]:
    """Serialize the full skill registry for the UI's skill grid."""
    out = []
    for t in registry.all():
        out.append({
            "name": t.name,
            "description": t.description,
            "category": _categorize(t.name),
            "sensitivity": t.sensitivity,
            "parameters_schema": t.parameters_schema,
        })
    # Sort by category then name for consistent rendering.
    out.sort(key=lambda s: (s["category"], s["name"]))
    return out


# ── Demo mode (layout only) ────────────────────────────────────

async def push_demo_events(bridge: EventBridge) -> None:
    await asyncio.sleep(2)
    await bridge.push_event(Thinking(text="Scanning for nearby WiFi networks..."))
    await asyncio.sleep(0.5)
    await bridge.push_event(ToolCallProposed(
        call_id="demo-1",
        tool_name="wifi_scan",
        arguments={"interface": "wlan1mon", "band": "all"},
        sensitivity="passive",
    ))
    await asyncio.sleep(0.3)
    await bridge.push_event(ToolCallExecuted(
        call_id="demo-1",
        tool_name="wifi_scan",
        result={"networks": [
            {"ssid": "TargetNet", "bssid": "aa:bb:cc:dd:ee:ff", "channel": 6,
             "rssi_dbm": -42, "encryption": "WPA2-PSK"},
        ], "scan_duration_s": 10},
        duration_ms=10230,
    ))
    await bridge.push_event(Final(reason="end_turn"))


# ── Live agent wiring ──────────────────────────────────────────

async def wire_live_agent(bridge: EventBridge, server: UIServer) -> dict[str, Any]:
    """Builds all the agent infrastructure and registers handlers on the server.

    Returns a dict of resources the caller should aclose() when shutting down.
    """
    cfg = AgentConfig.from_env()
    backend = make_backend(cfg)

    # Load skills.
    registry = ToolRegistry()
    skills_dir = Path(__file__).resolve().parent.parent.parent / "skills"
    loaded = load_skills_into_registry(skills_dir, registry)
    print(f"  loaded skills: {len(loaded)}")

    # Disclosure layer.
    journal_path = Path(__file__).resolve().parent.parent.parent / "journal.db"
    journal = Journal(str(journal_path))
    confirm = UIConfirmation(bridge, server)
    approver = DisclosureApprover(journal, confirm=confirm)
    dispatcher = Dispatcher(registry, approver=approver)

    # Scoper.
    scoper = None
    if cfg.scoper_enabled:
        scoper = make_scoper(
            skills_dir,
            [t.name for t in registry.all()],
            remote_endpoint=cfg.effective_scoper_endpoint() or None,
        )
        print(f"  scoper={type(scoper).__name__} k={cfg.scoper_k}")

    # Agent (two-pass or single-pass).
    deep_backend = make_deep_backend(cfg) if cfg.mode == "twopass" else None
    if cfg.mode == "twopass":
        plan_approver = UIPlanApprover(bridge, server)
        agent = TwoPassAgent(
            backend, dispatcher, cfg,
            scoper=scoper,
            plan_approver=plan_approver,
            deep_backend=deep_backend,
        )
        print(f"  mode=twopass")
    else:
        agent = AgentLoop(backend, dispatcher, cfg, scoper=scoper, scoper_k=cfg.scoper_k)
        print(f"  mode=single")

    print(f"  backend={cfg.backend} model={cfg.model}")

    # Install the skills catalog on the server so it can push on state ON.
    server.set_skills_catalog(_build_skills_catalog(registry))

    # ── Handlers ──────────────────────────────────────────────

    conversation_history: list[dict[str, Any]] = []

    async def on_prompt(text: str) -> None:
        nonlocal conversation_history
        print(f"  [agent] > {text}")

        turn_plan_reasoning = ""
        turn_step_summaries: list[str] = []
        turn_final_text = ""

        if hasattr(agent, "run"):
            run_kwargs = {}
            # TwoPassAgent supports conversation_history; AgentLoop doesn't.
            if isinstance(agent, TwoPassAgent):
                run_kwargs["conversation_history"] = conversation_history
            async for event in agent.run(text, **run_kwargs):
                await bridge.push_event(event)
                if isinstance(event, PlanProposed) and not turn_plan_reasoning:
                    turn_plan_reasoning = event.reasoning
                elif isinstance(event, ToolCallExecuted):
                    if event.error:
                        turn_step_summaries.append(f"- {event.tool_name}: error: {event.error[:80]}")
                    else:
                        s = json.dumps(event.result, default=str)[:240] if event.result else ""
                        turn_step_summaries.append(f"- {event.tool_name}: {s}")
                elif isinstance(event, Final) and event.text:
                    turn_final_text = event.text[:240]

        # Append to history.
        if isinstance(agent, TwoPassAgent):
            lines = []
            if turn_plan_reasoning:
                lines.append(f"Plan: {turn_plan_reasoning[:240]}")
            lines.extend(turn_step_summaries)
            if turn_final_text:
                lines.append(f"Conclusion: {turn_final_text}")
            if lines:
                conversation_history.append({"role": "user", "content": text})
                conversation_history.append({"role": "assistant", "content": "\n".join(lines)})

    async def on_dispatch(skill: str, args: dict[str, Any]) -> None:
        """Direct skill dispatch — bypass the AI, go straight to the dispatcher.
        Respects disclosure + journals the same as AI-dispatched calls."""
        print(f"  [direct] {skill}({args})")
        tool = registry.get(skill)
        if tool is None:
            await bridge.push_raw({
                "type": "error",
                "message": f"unknown skill: {skill}",
            })
            return

        call_id = f"manual-{uuid.uuid4().hex[:8]}"
        await bridge.push_event(ToolCallProposed(
            call_id=call_id,
            tool_name=skill,
            arguments=args,
            sensitivity=tool.sensitivity,
        ))

        result = await dispatcher.dispatch(skill, args)

        await bridge.push_event(dispatcher.make_executed_event(
            call_id=call_id, tool_name=skill, result=result,
        ))
        # Since direct dispatch isn't part of a plan, we emit a Final so
        # the UI can resume the idle state.
        if result.error == "user_rejected":
            await bridge.push_event(Final(reason="user_abort"))
        else:
            await bridge.push_event(Final(
                reason="end_turn",
                text=f"{skill} completed" if result.executed and not result.error else "",
            ))

    async def on_state_change(state: SimulatorState) -> None:
        # Hook for future: probe Mephisto link on connect, etc.
        # Today just logs.
        print(f"  [state] power={state.power.value} mephisto={state.mephisto.value}")

    server.set_handlers(
        prompt_handler=on_prompt,
        dispatch_handler=on_dispatch,
        state_handler=on_state_change,
    )

    return {
        "journal": journal,
        "backend": backend,
        "deep_backend": deep_backend,
    }


async def main() -> None:
    demo = "--demo" in sys.argv
    port = 8080

    bridge = EventBridge()
    server = UIServer(bridge, port=port)
    await server.start()

    print(f"\n  𝑓aust UI running at http://localhost:{port}")
    print(f"  mode: {'demo (layout)' if demo else 'live agent'}")

    resources: dict[str, Any] = {}
    try:
        if demo:
            # In demo mode, bypass the state machine entirely — auto-power-on
            # so you can see the UI without clicking a button.
            await server._power_on()
            asyncio.create_task(push_demo_events(bridge))
            while True:
                await asyncio.sleep(1)
        else:
            resources = await wire_live_agent(bridge, server)
            print("  ready. open the browser and press Power to boot.\n")
            # Server runs until interrupted.
            while True:
                await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        if resources.get("journal"):
            resources["journal"].close()
        if resources.get("deep_backend") is not None:
            await resources["deep_backend"].aclose()
        if resources.get("backend") is not None:
            await resources["backend"].aclose()
        await server.stop()
        print("\n  server stopped.")


if __name__ == "__main__":
    asyncio.run(main())
