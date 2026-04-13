"""
Agent configuration.

Per chunk 3's recommendation: ALL backend specifics live behind LLM_ENDPOINT.
Hardcoding hailo-ollama-isms anywhere outside this file is a bug.

In production this gets read from env / a TOML file. For v0, defaults are fine.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AgentConfig:
    # Backend
    backend: str = "ollama"  # ollama | claude
    llm_endpoint: str = "http://localhost:11434/v1"  # OpenAI-compatible
    model: str = "qwen2.5:1.5b-instruct"  # whatever the backend is serving
    api_key: str = ""  # only used by Claude backend

    # Loop
    max_iterations: int = 10  # hard cap to prevent runaway tool loops
    request_timeout_s: float = 60.0

    # Generation
    temperature: float = 0.2  # low for tool-use reliability
    max_tokens: int = 1024  # response budget; chunk 3 noted 2048 ctx on Hailo
    # Reserve ~256 tokens for response on tight-context backends (Claude
    # Agent SDK pattern; prevents mid-reasoning truncation).
    context_response_reserve: int = 256

    @classmethod
    def from_env(cls) -> "AgentConfig":
        return cls(
            backend=os.environ.get("FAUST_BACKEND", cls.backend),
            llm_endpoint=os.environ.get("FAUST_LLM_ENDPOINT", cls.llm_endpoint),
            model=os.environ.get("FAUST_MODEL", cls.model),
            api_key=os.environ.get("FAUST_API_KEY", ""),
        )
