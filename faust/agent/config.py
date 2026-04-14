"""
Agent configuration.

Per chunk 3's recommendation: ALL backend specifics live behind LLM_ENDPOINT.
Hardcoding hailo-ollama-isms anywhere outside this file is a bug.

In production this gets read from env / a TOML file. For v0, defaults are fine.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


MEPHISTO_ENDPOINT = "http://10.66.0.2:8000/v1"
MEPHISTO_PLANNING_ENDPOINT = "http://10.66.0.2:8081/v1"  # llama.cpp on Pi 5 CPU
MEPHISTO_SCOPER_ENDPOINT = "http://10.66.0.2:8082/v1"   # embedding scoper service


@dataclass
class AgentConfig:
    # Fast backend — used for Pass 2 parameterize calls (frequent, routine).
    # Runs on Hailo NPU in production, local Ollama in dev.
    backend: str = "ollama"
    llm_endpoint: str = "http://localhost:11434/v1"  # OpenAI-compatible
    model: str = "qwen2.5:1.5b-instruct"  # whatever the backend is serving
    api_key: str = ""  # only used by Claude backend

    # Deep backend — used for Pass 1 planning calls (rare, benefits from reasoning).
    # Runs Qwen 2.5 7B int4 on Mephisto's Pi 5 CPU via llama.cpp in production,
    # local Ollama with 7B pulled in dev. Falls back to the fast backend if
    # unavailable or disabled.
    planning_enabled: bool = True
    planning_endpoint: str = ""  # empty = use llm_endpoint
    planning_model: str = "qwen2.5:7b-instruct"
    planning_timeout_s: float = 120.0  # planning can be slow on CPU

    # Loop
    max_iterations: int = 10  # hard cap to prevent runaway tool loops
    request_timeout_s: float = 60.0

    # Generation
    temperature: float = 0.2  # low for tool-use reliability
    max_tokens: int = 1024  # response budget; chunk 3 noted 2048 ctx on Hailo
    # Reserve ~256 tokens for response on tight-context backends (Claude
    # Agent SDK pattern; prevents mid-reasoning truncation).
    context_response_reserve: int = 256

    # Skill scoping — embedding-based retrieval to keep tool_schemas small
    # when the skill library grows past ~20 tools. Default k=12 is tuned
    # for a ~40-skill registry; scale up with registry size.
    #
    # scoper_endpoint: when set, Faust calls a remote scoper (e.g. Mephisto)
    # instead of running sentence-transformers locally. Saves ~400MB RAM
    # on Faust's 1GB Pi. Empty = run locally (Mac dev, Mephisto).
    scoper_enabled: bool = True
    scoper_k: int = 12  # top-K skills surfaced per prompt
    scoper_endpoint: str = ""  # empty = local

    # Agent mode: "single" (AgentLoop, legacy) or "twopass" (TwoPassAgent,
    # plan-then-execute — preferred for Mephisto+Faust split).
    mode: str = "twopass"

    @classmethod
    def from_env(cls) -> "AgentConfig":
        return cls(
            backend=os.environ.get("FAUST_BACKEND", cls.backend),
            llm_endpoint=os.environ.get("FAUST_LLM_ENDPOINT", cls.llm_endpoint),
            model=os.environ.get("FAUST_MODEL", cls.model),
            api_key=os.environ.get("FAUST_API_KEY", ""),
            planning_enabled=_envbool("FAUST_PLANNING_ENABLED", cls.planning_enabled),
            planning_endpoint=os.environ.get("FAUST_PLANNING_ENDPOINT", cls.planning_endpoint),
            planning_model=os.environ.get("FAUST_PLANNING_MODEL", cls.planning_model),
            planning_timeout_s=float(os.environ.get("FAUST_PLANNING_TIMEOUT_S", cls.planning_timeout_s)),
            scoper_enabled=_envbool("FAUST_SCOPER_ENABLED", cls.scoper_enabled),
            scoper_k=int(os.environ.get("FAUST_SCOPER_K", cls.scoper_k)),
            scoper_endpoint=os.environ.get("FAUST_SCOPER_ENDPOINT", cls.scoper_endpoint),
            mode=os.environ.get("FAUST_MODE", cls.mode),
        )

    def effective_planning_endpoint(self) -> str:
        """Planning endpoint, defaulting to the main endpoint if unset."""
        return self.planning_endpoint or self.llm_endpoint

    def effective_scoper_endpoint(self) -> str:
        """Scoper endpoint. Auto-routes to Mephisto's scoper service when
        FAUST_BACKEND=mephisto and no explicit endpoint is set. Empty string
        means run the scoper locally."""
        if self.scoper_endpoint:
            return self.scoper_endpoint
        if self.backend == "mephisto":
            return MEPHISTO_SCOPER_ENDPOINT
        return ""


def _envbool(key: str, default: bool) -> bool:
    v = os.environ.get(key)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes", "on")
