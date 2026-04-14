"""
The agent loop. Ring 4 pattern from Anthropic's tool-use tutorial, async,
backend-agnostic, emits a structured event stream.

Architecture (per chunk 2):
  - Roll-our-own loop, NOT Claude Agent SDK or OpenClaw runtime
  - Speaks OpenAI-compatible HTTP via LLMBackend
  - Tool dispatch goes through Dispatcher (disclosure seam)
  - Hard cap on iterations to prevent runaway tool loops
  - Event-stream output: same stream feeds CLI dev runner AND the touchscreen UI

Faust↔Mephisto split:
  - This loop runs ON FAUST.
  - The LLM call (backend.complete) is an HTTP request; in production it goes
    over USB-ethernet to Mephisto:8000/v1. In dev, it's localhost Ollama.
  - Mephisto NEVER touches dispatch — the architecture's "Mephisto advises,
    Faust executes" rule falls out for free.

Usage:
    cfg = AgentConfig.from_env()
    backend = make_backend(cfg)
    registry = ToolRegistry()
    # ... register tools ...
    dispatcher = Dispatcher(registry)
    loop = AgentLoop(backend, dispatcher, cfg)

    async for event in loop.run("scan for nearby networks"):
        match event:
            case Thinking(text=t):       print(t, end="")
            case ToolCallProposed(...):  ...
            case ToolCallExecuted(...):  ...
            case Final(reason=r):        print(f"\n[done: {r}]")
"""

from __future__ import annotations

import json
import uuid
from typing import Any, AsyncIterator

from .backends import LLMBackend, AssistantMessage
from .config import AgentConfig
from .dispatch import Dispatcher
from .events import (
    Event,
    Thinking,
    ToolCallProposed,
    Final,
)
from ..skills.scoper import SkillScoper


DEFAULT_SYSTEM_PROMPT = """You are faust, an AI-native pentesting handheld.

You operate physical RF tools (WiFi, BLE, NFC, sub-GHz, IR, RFID) and software
recon tools through a tool-call interface. The user is an authorized operator
who has accepted the device's disclosure terms.

Rules:
  - Use tools only when needed. Many questions can be answered without one.
  - Prefer passive reconnaissance before active probing.
  - When unsure of scope or target, ASK before acting.
  - Disruptive actions (deauth, evil portal, replay) require explicit user
    confirmation per call — your tool call WILL be intercepted and surfaced
    to the operator. Phrase intent clearly so they can confirm or reject.
"""


class AgentLoop:
    def __init__(
        self,
        backend: LLMBackend,
        dispatcher: Dispatcher,
        config: AgentConfig,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        scoper: SkillScoper | None = None,
        scoper_k: int = 8,
    ) -> None:
        self.backend = backend
        self.dispatcher = dispatcher
        self.config = config
        self.system_prompt = system_prompt
        self.scoper = scoper
        self.scoper_k = scoper_k

    async def run(self, user_input: str) -> AsyncIterator[Event]:
        """Run the loop to completion. Yields events as they occur.

        Termination:
          - finish_reason == "stop" / "end_turn" → Final(reason="end_turn")
          - iteration cap hit                     → Final(reason="max_iterations")
          - approver rejected a tool call         → Final(reason="user_abort")
          - backend raised                         → Final(reason="error")
        """

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_input},
        ]

        # Scope tool_schemas down to the top-K most relevant skills for this
        # prompt. Keeps the tool-schema section of context manageable on
        # tight-window backends (Hailo 2048 tok). The registry still holds
        # every tool — dispatch is not restricted, only what the model sees.
        if self.scoper is not None:
            relevant = set(await self.scoper.top_k(user_input, k=self.scoper_k))
            tool_schemas = [
                t.to_openai_schema()
                for t in self.dispatcher.registry.all()
                if t.name in relevant
            ]
        else:
            tool_schemas = self.dispatcher.registry.to_openai_schemas()

        for iteration in range(self.config.max_iterations):
            # --- 1. Call the model ---
            try:
                msg: AssistantMessage = await self.backend.complete(
                    messages=messages,
                    tools=tool_schemas,
                )
            except Exception as e:
                yield Final(
                    reason="error",
                    error=f"backend error: {type(e).__name__}: {e}",
                )
                return

            # --- 2. Emit any text content the assistant produced ---
            if msg.content:
                yield Thinking(text=msg.content, is_delta=False)

            # --- 3. If no tool calls, we're done ---
            if not msg.tool_calls:
                # Append the assistant message to history for completeness.
                messages.append({"role": "assistant", "content": msg.content})
                yield Final(reason="end_turn", text=msg.content)
                return

            # --- 4. Append assistant message WITH tool_calls to history ---
            # OpenAI protocol requires this exact shape so subsequent
            # role:"tool" messages can be linked by tool_call_id.
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )

            # --- 5. Dispatch each tool call ---
            user_aborted = False
            for tc in msg.tool_calls:
                tool = self.dispatcher.registry.get(tc.name)
                sensitivity = tool.sensitivity if tool else "passive"

                yield ToolCallProposed(
                    call_id=tc.id,
                    tool_name=tc.name,
                    arguments=tc.arguments,
                    sensitivity=sensitivity,
                )

                # Disclosure hook fires inside dispatch.
                result = await self.dispatcher.dispatch(tc.name, tc.arguments)

                yield self.dispatcher.make_executed_event(
                    call_id=tc.id,
                    tool_name=tc.name,
                    result=result,
                )

                # Build the tool-result message to feed back to the model.
                if result.executed and result.error is None:
                    tool_content = _serialize_result(result.result)
                elif result.error == "user_rejected":
                    tool_content = "[user rejected this tool call]"
                    user_aborted = True
                else:
                    tool_content = f"[error] {result.error}"

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_content,
                    }
                )

            if user_aborted:
                yield Final(reason="user_abort")
                return

            # Loop continues: model now sees the tool results and decides
            # whether to call more tools or produce a final answer.

        # Iteration cap exhausted.
        yield Final(reason="max_iterations")


def _serialize_result(result: Any) -> str:
    """Tool results must be strings to feed back into the chat. JSON-encode
    structured data; stringify everything else."""
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, default=str)
    except (TypeError, ValueError):
        return str(result)
