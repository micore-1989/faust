"""
Skill scoper — retrieval-based filtering to fit skill schemas in context.

The problem: every skill's JSON schema goes into the LLM's context window.
With 19+ skills, the schemas alone (~100 tokens each) blow past the Hailo
NPU's 2048-token limit, leaving nothing for conversation.

The fix: pre-filter skills by relevance to the user's prompt. Only the
top-K skills get their schemas injected. The LLM still sees enough tools
to do any task, but not all of them at once.

Architecture:
  SkillScoper is an abstract base with two impls:
    - NoopScoper: returns all skills (no filtering — fallback)
    - LocalEmbeddingScoper: sentence-transformers + cosine similarity

LocalEmbeddingScoper is gated on `sentence-transformers` being installed.
The import is lazy so the core agent package works without ML dependencies.

Embeddings are cached to skills/.embeddings.npz. Cache invalidates on
SKILL.md mtime change.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class SkillScoper(ABC):
    """Ranks skills by relevance to a query. Returns top-K skill names.

    `top_k` is async because remote implementations need to do I/O without
    blocking the agent's event loop. Local implementations that are CPU-bound
    can just be `async def` wrappers around sync work.
    """

    @abstractmethod
    async def top_k(self, query: str, k: int = 8) -> list[str]:
        """Return up to `k` skill names most relevant to the query."""
        ...

    @abstractmethod
    def all_skills(self) -> list[str]:
        """Return every skill name the scoper knows about."""
        ...


class NoopScoper(SkillScoper):
    """Returns all skills unchanged. Fallback when no embedding runtime is available."""

    def __init__(self, skill_names: list[str]) -> None:
        self._names = list(skill_names)

    async def top_k(self, query: str, k: int = 8) -> list[str]:
        return self._names[:k] if k > 0 else list(self._names)

    def all_skills(self) -> list[str]:
        return list(self._names)


class LocalEmbeddingScoper(SkillScoper):
    """Embeds each skill's name+description+body, ranks by cosine similarity.

    Uses sentence-transformers with a small model (MiniLM-L6-v2 by default,
    22MB int8 / 80MB fp32, 384-dim output). Embeddings are computed once at
    construction and cached to disk so subsequent runs start in <100ms.

    Instantiation requires sentence-transformers. If it's not installed,
    raises ImportError — callers should catch this and fall back to Noop.
    """

    DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
    CACHE_FILENAME = ".embeddings.npz"

    def __init__(
        self,
        skills_dir: Path,
        model_name: str = DEFAULT_MODEL,
    ) -> None:
        # Lazy import so this module is importable without ML deps.
        try:
            from sentence_transformers import SentenceTransformer  # noqa: F401
            import numpy as np  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "LocalEmbeddingScoper requires sentence-transformers and numpy. "
                "Install: pip install sentence-transformers"
            ) from e

        self.skills_dir = skills_dir
        self.model_name = model_name
        self._model = None  # Lazy-loaded on first embed.
        self._skill_names: list[str] = []
        self._skill_texts: list[str] = []
        self._embeddings = None  # numpy array (N, 384)
        self._load_or_build()

    # ── Public API ─────────────────────────────────────────────────

    async def top_k(self, query: str, k: int = 8) -> list[str]:
        if not self._skill_names:
            return []
        if k <= 0 or k >= len(self._skill_names):
            return list(self._skill_names)

        import asyncio
        import numpy as np

        # Model may not be loaded if we used the disk cache on init.
        self._ensure_model()
        # Run the CPU-heavy encode on a thread so we don't block the event loop.
        query_vec = (await asyncio.to_thread(
            self._model.encode, [query], normalize_embeddings=True
        ))[0]
        # Cosine similarity = dot product of normalized vectors.
        scores = self._embeddings @ query_vec
        # Top-k indices, descending.
        top_idx = np.argsort(-scores)[:k]
        return [self._skill_names[i] for i in top_idx]

    def all_skills(self) -> list[str]:
        return list(self._skill_names)

    # ── Internals ──────────────────────────────────────────────────

    def _collect_skill_texts(self) -> tuple[list[str], list[str], str]:
        """Walk skills_dir, extract name + text body per skill.

        Returns (names, texts, corpus_hash) where corpus_hash captures
        the content of all SKILL.md files for cache invalidation.
        """
        names: list[str] = []
        texts: list[str] = []
        hasher = hashlib.sha256()

        for child in sorted(self.skills_dir.iterdir()):
            if not child.is_dir():
                continue
            skill_md = child / "SKILL.md"
            if not skill_md.exists():
                continue

            raw = skill_md.read_text(encoding="utf-8")
            hasher.update(raw.encode())

            # Parse the frontmatter to get the canonical name. We reuse the
            # loader's parse to stay consistent.
            from .loader import parse_skill_md
            try:
                fm, body = parse_skill_md(skill_md)
            except Exception:
                continue

            # Combine name, description, and body for richer embedding.
            text = f"{fm.name}\n{fm.description}\n\n{body}"
            names.append(fm.name)
            texts.append(text)

        return names, texts, hasher.hexdigest()

    def _load_or_build(self) -> None:
        """Load cached embeddings if the corpus is unchanged, else rebuild."""
        import numpy as np

        names, texts, corpus_hash = self._collect_skill_texts()
        self._skill_names = names
        self._skill_texts = texts

        if not names:
            self._embeddings = np.empty((0, 384), dtype=np.float32)
            return

        cache_path = self.skills_dir / self.CACHE_FILENAME
        if cache_path.exists():
            try:
                cached = np.load(cache_path, allow_pickle=True)
                if (
                    str(cached["corpus_hash"]) == corpus_hash
                    and str(cached["model_name"]) == self.model_name
                    and list(cached["skill_names"]) == names
                ):
                    self._embeddings = cached["embeddings"]
                    return
            except Exception:
                pass  # Fall through to rebuild.

        # Rebuild.
        self._ensure_model()
        self._embeddings = self._model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).astype(np.float32)

        # Cache.
        np.savez(
            cache_path,
            corpus_hash=corpus_hash,
            model_name=self.model_name,
            skill_names=np.array(names),
            embeddings=self._embeddings,
        )

    def _ensure_model(self) -> None:
        """Lazy-load the embedding model. Reuses the instance across calls."""
        if self._model is not None:
            return
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(self.model_name)


class RemoteEmbeddingScoper(SkillScoper):
    """Calls a remote scoper HTTP endpoint (typically Mephisto's).

    Design: Faust's Pi 5 1GB cannot afford torch + sentence-transformers
    (~400MB RAM) on top of the UI + Chromium + skill runtimes. So the scoper
    runs on Mephisto (Pi 5 16GB, already the ML host), and Faust calls it
    over the same USB-ethernet link as the LLM.

    Endpoint protocol:
        POST /v1/scope
        { "query": "scan the wifi", "k": 12 }
        → { "skills": ["wifi_scan", "wifi_deauth", ...] }

    Falls back to NoopScoper on connection failure so the agent still works
    when Mephisto is disconnected.
    """

    def __init__(
        self,
        endpoint: str,
        skill_names: list[str],
        timeout_s: float = 3.0,
    ) -> None:
        import httpx  # local import — httpx is already a core dep

        self.endpoint = endpoint.rstrip("/")
        self._names = list(skill_names)
        self._client = httpx.AsyncClient(timeout=timeout_s)

    async def top_k(self, query: str, k: int = 8) -> list[str]:
        try:
            resp = await self._client.post(
                f"{self.endpoint}/scope",
                json={"query": query, "k": k},
            )
            resp.raise_for_status()
            data = resp.json()
            names = data.get("skills", [])
            if isinstance(names, list) and names:
                return [n for n in names if n in self._names][:k]
        except Exception:
            pass
        # Fallback: return all names (up to k) so planning still works.
        return self._names[:k] if k > 0 else list(self._names)

    async def aclose(self) -> None:
        await self._client.aclose()

    def all_skills(self) -> list[str]:
        return list(self._names)


def make_scoper(
    skills_dir: Path,
    skill_names: list[str],
    prefer_embedding: bool = True,
    remote_endpoint: str | None = None,
) -> SkillScoper:
    """Factory — chooses the best available scoper.

    Priority:
      1. RemoteEmbeddingScoper if `remote_endpoint` is set (Faust on Pi prod)
      2. LocalEmbeddingScoper if sentence-transformers is installed (Mac dev, Mephisto)
      3. NoopScoper fallback (always works, no retrieval quality)

    Callers never need to handle ML dependency availability — the factory
    degrades gracefully.
    """
    if remote_endpoint:
        try:
            return RemoteEmbeddingScoper(remote_endpoint, skill_names)
        except Exception as e:
            import sys
            print(
                f"[scoper] remote scoper unavailable ({type(e).__name__}); "
                f"trying local: {e}",
                file=sys.stderr,
            )

    if prefer_embedding:
        try:
            return LocalEmbeddingScoper(skills_dir)
        except Exception as e:
            import sys
            print(
                f"[scoper] local embedding scoper unavailable ({type(e).__name__}); "
                f"falling back to NoopScoper: {e}",
                file=sys.stderr,
            )

    return NoopScoper(skill_names)
