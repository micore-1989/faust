"""
Mephisto scoper HTTP service.

Wraps LocalEmbeddingScoper behind a tiny aiohttp server so Faust (1GB Pi)
doesn't need sentence-transformers + torch (~400MB RAM). Instead, Faust
calls this service over the USB-ethernet link.

Endpoint:
    POST /v1/scope
    Request body: {"query": "<text>", "k": 12}
    Response:     {"skills": ["wifi_scan", ...]}

Auto-rebuilds the embedding cache when any SKILL.md file changes (same
logic as LocalEmbeddingScoper — this is just a thin transport wrapper).

Run directly:
    python scoper_server.py --skills-dir /path/to/skills --port 8082
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aiohttp import web

# Make the faust package importable when running this script standalone.
_here = Path(__file__).resolve()
sys.path.insert(0, str(_here.parents[2]))

from faust.skills.scoper import LocalEmbeddingScoper


class ScoperService:
    def __init__(self, skills_dir: Path) -> None:
        print(f"[scoper] building index from {skills_dir}")
        self.scoper = LocalEmbeddingScoper(skills_dir)
        print(f"[scoper] indexed {len(self.scoper.all_skills())} skills")

    async def scope(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)

        query = str(data.get("query", ""))
        k = int(data.get("k", 12))
        if not query:
            return web.json_response({"error": "query required"}, status=400)

        names = await self.scoper.top_k(query, k=k)
        return web.json_response({"skills": names})

    async def health(self, request: web.Request) -> web.Response:
        return web.json_response({
            "status": "ok",
            "skills": len(self.scoper.all_skills()),
        })


def main() -> None:
    ap = argparse.ArgumentParser(description="Faust scoper HTTP service")
    ap.add_argument("--skills-dir", type=Path, required=True,
                    help="Path to the skills/ directory")
    ap.add_argument("--host", default="10.66.0.2",
                    help="Bind address (default: Mephisto gadget IP)")
    ap.add_argument("--port", type=int, default=8082,
                    help="Bind port (default: 8082)")
    args = ap.parse_args()

    service = ScoperService(args.skills_dir)

    app = web.Application()
    app.router.add_post("/v1/scope", service.scope)
    app.router.add_get("/v1/health", service.health)

    print(f"[scoper] serving on http://{args.host}:{args.port}")
    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
