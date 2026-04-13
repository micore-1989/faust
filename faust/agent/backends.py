"""
LLM backend abstraction.

Per chunk 3: the loop talks to ONE interface. Hailo (via hailo-ollama),
laptop Ollama, and Claude API all hide behind LLMBackend.

The unit of currency is an OpenAI-style chat completion request returning
a single assistant message that may contain text content and/or tool_calls.

Streaming is intentionally NOT in v0 — adding it later means returning an
async iterator from `complete()` instead of a single message. The event
stream out of the loop already supports streaming via Thinking(is_delta=True).
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class ToolCall:
    """One tool invocation requested by the model."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class AssistantMessage:
    """The structured response from a backend.

    `content` is the assistant text (may be empty if the model went straight
    to tool calls). `tool_calls` is the list of requested tool invocations.
    `finish_reason` is "stop" | "tool_calls" | "length" | other backend-specific.
    """
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"


class LLMBackend(ABC):
    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AssistantMessage:
        """Send a chat completion request. Return the assistant's message."""
        ...

    async def aclose(self) -> None:
        """Override if the backend holds resources."""
        return None


class OllamaBackend(LLMBackend):
    """OpenAI-compatible HTTP backend.

    Works against:
      - Local Ollama (`ollama serve`, OpenAI compat at /v1)
      - hailo-ollama on the AI HAT+ 2 (same OpenAI compat surface)
      - Any other OpenAI-compatible endpoint (vLLM, llama.cpp server, etc)

    URL must point at the /v1 root (e.g. http://localhost:11434/v1).
    """

    def __init__(
        self,
        endpoint: str,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        timeout_s: float = 60.0,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = httpx.AsyncClient(timeout=timeout_s)

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AssistantMessage:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        resp = await self._client.post(
            f"{self.endpoint}/chat/completions",
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

        choice = data["choices"][0]
        msg = choice["message"]

        tool_calls: list[ToolCall] = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            raw_args = fn.get("arguments", "{}")
            # OpenAI spec: arguments is a JSON-encoded string. Some backends
            # return a dict directly. Handle both.
            if isinstance(raw_args, str):
                try:
                    parsed_args = json.loads(raw_args) if raw_args else {}
                except json.JSONDecodeError:
                    # Hallucinated JSON. Surface as empty args; the dispatch
                    # layer will likely error on validation. That's correct.
                    parsed_args = {"_raw": raw_args, "_parse_error": True}
            else:
                parsed_args = raw_args
            tool_calls.append(
                ToolCall(
                    id=tc.get("id", ""),
                    name=fn.get("name", ""),
                    arguments=parsed_args,
                )
            )

        return AssistantMessage(
            content=msg.get("content") or "",
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
        )

    async def aclose(self) -> None:
        await self._client.aclose()


class ClaudeBackend(LLMBackend):
    """Stub for the cloud-fallback case. Translates between Anthropic-style
    tool_use blocks and OpenAI-style tool_calls at THIS boundary, so the rest
    of the loop is backend-agnostic.

    Not implemented in v0 — Faust runs against Ollama for dev, hailo-ollama
    on Mephisto in production. Cloud fallback is a Tier 2 feature.
    """

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5") -> None:
        self.api_key = api_key
        self.model = model

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AssistantMessage:
        raise NotImplementedError(
            "ClaudeBackend not implemented in v0. Use OllamaBackend."
        )


def make_backend(config: "AgentConfig") -> LLMBackend:  # type: ignore[name-defined]
    """Factory dispatching on config.backend."""
    from .config import AgentConfig  # local import to avoid cycles

    assert isinstance(config, AgentConfig)
    if config.backend == "ollama":
        return OllamaBackend(
            endpoint=config.llm_endpoint,
            model=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            timeout_s=config.request_timeout_s,
        )
    if config.backend == "claude":
        return ClaudeBackend(api_key=config.api_key, model=config.model)
    raise ValueError(f"unknown backend: {config.backend}")
