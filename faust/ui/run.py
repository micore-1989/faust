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
from ..agent.disclosure import DisclosureApprover, TrustCache, scope_key_from_state
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

def _demo_load_skills_catalog() -> list[dict[str, Any]]:
    """Load the on-disk skill catalog for demo mode.

    Mirrors `wire_live_agent`'s skills-loading step without any of the
    backend/disclosure/agent wiring. The dashboard needs real catalog
    entries so the seven radio tiles can render tool counts even though
    demo mode isn't running the agent loop.
    """
    registry = ToolRegistry()
    skills_dir = Path(__file__).resolve().parent.parent.parent / "skills"
    load_skills_into_registry(skills_dir, registry)
    return _build_skills_catalog(registry)


async def push_demo_events(bridge: EventBridge, server: UIServer | None = None) -> None:
    """Scripted UI walkthrough for the simulator.

    The demo exercises every Stage 1–11 feature:
      - scope change             (§10.10)
      - Mephisto dock ceremony   (§10.13)
      - two-pass phase markers   (§10.7 / §17.5)
      - plan-approval modal      (§10.9)
      - passive + destructive tool calls + confirmation modal (§10.8)
      - a mini Pursuit with progress / activity / complete    (§10.4.1)
      - journal entries landed along the way so the Journal tab fills

    Approval modals open but DO NOT gate the demo timeline — in live
    mode the queued approver awaits the operator, but in demo mode no
    agent is running. We push the follow-on events on a fixed schedule
    so the walkthrough always finishes even if the operator ignores
    the modals. Document this in the stage report.
    """
    from ..pursuits.events import PursuitProgress, PursuitActivity, PursuitComplete

    # 0s: boot already ran (server._power_on called before demo started).
    await asyncio.sleep(2)

    # 2s: scope change to self-test (§10.10). Routes through the real
    # handler so the journal + trust cache get the same treatment as
    # in live mode.
    if server is not None:
        await server._handle_incoming({
            "type": "scope_change",
            "template": "self-test",
            "description": None,
        })

    await asyncio.sleep(3)

    # 5s: Mephisto dock. The server flips state + broadcasts, which
    # triggers the client's first-dock ceremony automatically.
    if server is not None:
        await server._mephisto_connect()

    await asyncio.sleep(4)

    # 9s: two-pass phase markers.
    await bridge.push_raw({"type": "planning_started", "phase": "catalog", "skill_count": 41})
    await asyncio.sleep(3)
    await bridge.push_raw({"type": "planning_started", "phase": "plan", "attempt": 0})
    await asyncio.sleep(5)

    # 17s: plan approval request.
    await bridge.push_raw({
        "type": "plan_approval_request",
        "plan_id": "demo-plan-1",
        "reasoning": "Scan the 2.4 GHz band to identify the target AP, then deauth one client to observe WPA re-association.",
        "steps": [
            {"skill": "wifi_scan",   "intent": "locate the target BSSID", "critical": False},
            {"skill": "wifi_deauth", "intent": "drop one associated client", "critical": True},
        ],
        "safety_notes": ["Only use against the isolated VLAN router you own."],
    })

    # Non-blocking auto-advance: the modal opens for the operator, but
    # the demo timeline pushes follow-ons after a fixed delay.
    await asyncio.sleep(3)

    # 20s: parameterize + run passive skill.
    await bridge.push_raw({"type": "parameterizing_step", "step": 1, "of": 2, "skill": "wifi_scan", "intent": "locate target BSSID"})
    await asyncio.sleep(1)
    await bridge.push_event(ToolCallProposed(
        call_id="demo-1", tool_name="wifi_scan",
        arguments={"interface": "wlan1mon", "band": "2.4GHz"},
        sensitivity="passive",
    ))
    await asyncio.sleep(1)
    await bridge.push_event(ToolCallExecuted(
        call_id="demo-1", tool_name="wifi_scan",
        result={"networks": [
            {"ssid": "lab-ap", "bssid": "aa:bb:cc:dd:ee:ff", "channel": 6, "rssi_dbm": -42},
        ], "scan_duration_s": 8},
        duration_ms=8120,
    ))
    # Log to journal so Journal tab shows something.
    if server is not None and server._journal is not None:
        server._journal.record(
            tool_name="wifi_scan",
            arguments={"interface": "wlan1mon", "band": "2.4GHz"},
            sensitivity="passive",
            decision="auto",
            result_summary="1 network visible (lab-ap · ch6 · -42 dBm)",
            duration_ms=8120,
        )

    await asyncio.sleep(1)

    # 23s: parameterize + propose destructive; fire confirmation_request
    # but don't block — let operator interact or ignore.
    await bridge.push_raw({"type": "parameterizing_step", "step": 2, "of": 2, "skill": "wifi_deauth", "intent": "drop client"})
    await asyncio.sleep(1)
    await bridge.push_event(ToolCallProposed(
        call_id="demo-2", tool_name="wifi_deauth",
        arguments={"bssid": "aa:bb:cc:dd:ee:ff", "client": "11:22:33:44:55:66", "count": 5},
        sensitivity="disruptive",
    ))
    await bridge.push_raw({
        "type": "confirmation_request",
        "call_id": "demo-confirm-1",
        "tool_name": "wifi_deauth",
        "arguments": {"bssid": "aa:bb:cc:dd:ee:ff", "client": "11:22:33:44:55:66", "count": 5},
        "sensitivity": "disruptive",
    })
    await asyncio.sleep(5)
    await bridge.push_event(ToolCallExecuted(
        call_id="demo-2", tool_name="wifi_deauth",
        result={"frames_sent": 5, "target": "11:22:33:44:55:66"},
        duration_ms=1420,
    ))
    if server is not None and server._journal is not None:
        server._journal.record(
            tool_name="wifi_deauth",
            arguments={"bssid": "aa:bb:cc:dd:ee:ff", "client": "11:22:33:44:55:66", "count": 5},
            sensitivity="disruptive",
            decision="approved",
            result_summary="5 deauth frames sent to lab client",
            duration_ms=1420,
        )

    await bridge.push_event(Final(reason="end_turn", text="Deauth complete. Client reconnected after 1.2s."))

    await asyncio.sleep(3)

    # 32s: mini Pursuit run (hmc-demo). No real runner — just push the
    # stream of events the client would see.
    await bridge.push_event(PursuitProgress(run_id="demo-run", pursuit_id="hmc-demo", progress=0.2, elapsed_s=2, eta_s=8))
    await asyncio.sleep(1)
    await bridge.push_event(PursuitActivity(run_id="demo-run", pursuit_id="hmc-demo", line="Starting demo sequence…"))
    await asyncio.sleep(1)
    await bridge.push_event(PursuitProgress(run_id="demo-run", pursuit_id="hmc-demo", progress=0.6, elapsed_s=4, eta_s=3))
    await asyncio.sleep(1)
    await bridge.push_event(PursuitActivity(run_id="demo-run", pursuit_id="hmc-demo", line="Captured 3 demo SSIDs"))
    await asyncio.sleep(1)
    await bridge.push_event(PursuitProgress(run_id="demo-run", pursuit_id="hmc-demo", progress=1.0, elapsed_s=6, eta_s=0))

    # Log the Pursuit to the journal so the complete poster's auto-
    # navigate-to-journal-entry lands on a real entry.
    journal_entry_id = None
    if server is not None and server._journal is not None:
        entry = server._journal.record(
            tool_name="pursuit.hmc-demo",
            arguments={"run_id": "demo-run", "params": {}},
            sensitivity="passive",
            decision="auto",
            result_summary="Demo sequence completed — 3 SSIDs captured, journal entry created",
        )
        journal_entry_id = str(entry.seq)

    await bridge.push_event(PursuitComplete(
        run_id="demo-run", pursuit_id="hmc-demo",
        summary="Demo sequence completed — 3 SSIDs captured",
        journal_entry_id=journal_entry_id or "",
        artifacts=[],
    ))


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
    # Stage 11 operator-notes sidecar (mutable, outside the hash chain).
    from ..agent.journal_notes import JournalNotes
    journal_notes = JournalNotes(str(journal_path) + ".notes.json")
    confirm = UIConfirmation(bridge, server)
    approver = DisclosureApprover(journal, confirm=confirm)
    # TrustCache wraps DisclosureApprover: a successful approval silences the
    # confirmation modal for later calls in the same scope / window. Scope
    # changes invalidate the cache via server._handle_scope_change.
    trust_cache = TrustCache(
        inner=approver,
        scope_key_source=lambda: scope_key_from_state(server.state.scope),
    )
    dispatcher = Dispatcher(registry, approver=trust_cache)
    server.set_disclosure(trust_cache=trust_cache, journal=journal, journal_notes=journal_notes)

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

    # Pre-load the skill catalog in demo mode BEFORE accepting connections,
    # so clients connecting during the startup window still get a non-empty
    # skills message. (Live mode's loader runs inside wire_live_agent below,
    # which is awaited before we enter the `while True` accept loop either.)
    if demo:
        demo_catalog = _demo_load_skills_catalog()
        server.set_skills_catalog(demo_catalog)
        print(f"  loaded skills: {len(demo_catalog)} (demo mode)")
        # Give the demo a throwaway journal so the Journal tab and the
        # Pursuit-complete poster's journal-entry hop find real rows.
        import tempfile
        from ..agent.journal_notes import JournalNotes
        demo_journal_dir = Path(tempfile.mkdtemp(prefix="faust-demo-"))
        demo_journal = Journal(str(demo_journal_dir / "journal.db"))
        demo_notes = JournalNotes(str(demo_journal_dir / "journal.db.notes.json"))
        server.set_disclosure(trust_cache=None, journal=demo_journal, journal_notes=demo_notes)
        print(f"  demo journal: {demo_journal_dir}")

    await server.start()

    print(f"\n  𝑓aust UI running at http://localhost:{port}")
    print(f"  mode: {'demo (layout)' if demo else 'live agent'}")

    resources: dict[str, Any] = {}
    try:
        if demo:
            # In demo mode, bypass the state machine entirely — auto-power-on
            # so you can see the UI without clicking a button.
            await server._power_on()
            asyncio.create_task(push_demo_events(bridge, server))
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
