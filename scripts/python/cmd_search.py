"""/ci-search and /ci-hooks — Vector search + filtered hook library.

/ci-search: free-text query → top similar reels
/ci-hooks:  filter by hook_type / min_score / branche / client
"""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import asyncio
import json
import logging

from config import get_settings
from db.local_db import get_local_db, make_slug


def setup_logging(level: str = "WARNING") -> None:
    logging.basicConfig(level=level, format="[%(asctime)s] %(levelname)s: %(message)s")


def resolve_client_slug(client_arg: str | None) -> str | None:
    if not client_arg:
        return None
    db = get_local_db()
    slug = make_slug(client_arg)
    c = db.get_client_by_slug(slug) or db.get_client_by_name(client_arg)
    if not c:
        return None
    return c["slug"]


async def cmd_search(args: argparse.Namespace) -> int:
    """Semantic search via embedding."""
    setup_logging(args.log_level)
    s = get_settings()
    if not s.has_gemini():
        print("[ci-search] GEMINI_API_KEY required for query embedding", file=sys.stderr)
        return 3

    from clients.gemini import GeminiClient
    from db.vector_search import search

    client_slug = resolve_client_slug(args.client)

    gemini = GeminiClient()
    q_vecs = await gemini.embed([args.query], task_type="RETRIEVAL_QUERY")
    q_emb = q_vecs[0]

    results = search(
        query_embedding=q_emb,
        column=args.column,
        top_k=args.top_k,
        min_score=args.min_score,
        client_id=client_slug,
        filter_hook_type=args.hook_type,
        filter_angle=args.angle,
        filter_min_hook_score=args.min_hook_score,
        filter_min_views=args.min_views,
    )

    if args.output == "json":
        print(json.dumps([r.__dict__ for r in results], indent=2, default=str))
        return 0

    if not results:
        print(f"[ci-search] No results for: {args.query!r}")
        return 0

    print(f"Query: {args.query!r}  (column={args.column})")
    print(f"Top {len(results)} results:")
    print()
    print(f"  {'Sim':>5}  {'Account':<20} {'Shortcode':<14} {'Hook':<28} {'Score':>5}  Summary")
    print(f"  {'-' * 5}  {'-' * 20} {'-' * 14} {'-' * 28} {'-' * 5}  -------")
    for r in results:
        hook = (r.hook_text or "(visual)")[:28]
        summary = (r.summary or "")[:60]
        print(
            f"  {r.similarity:>.2f}  @{r.account:<19} {r.shortcode:<14} "
            f"{hook:<28} {r.hook_score or 0:>5}  {summary}"
        )
    return 0


def cmd_hooks(args: argparse.Namespace) -> int:
    """Filter hook library by type / score / client / branche."""
    db = get_local_db()
    client_slug = resolve_client_slug(args.client)

    reels = db.list_reels(
        client_id=client_slug,
        hook_type=args.hook_type,
        min_score=args.min_score,
        limit=args.limit,
    )

    if args.output == "json":
        out = [
            {
                "shortcode": r["shortcode"],
                "account": r["account"],
                "client_id": r.get("client_id"),
                "hook_type": r.get("hook_type"),
                "hook_text": r.get("hook_text"),
                "hook_visual": r.get("hook_visual"),
                "hook_score": r.get("hook_score"),
                "hook_reasoning": r.get("hook_reasoning"),
                "angle": r.get("angle"),
                "views": r.get("views"),
            }
            for r in reels
        ]
        print(json.dumps(out, indent=2, default=str))
        return 0

    if not reels:
        print("[ci-hooks] No reels match those filters")
        return 0

    print(f"Hook Library — {len(reels)} matches")
    if args.hook_type:
        print(f"  Type:     {args.hook_type}")
    if args.min_score is not None:
        print(f"  Min Score: {args.min_score}")
    if args.client:
        print(f"  Client:    {args.client}")
    print()

    # Sort by score desc
    reels.sort(key=lambda r: r.get("hook_score") or 0, reverse=True)

    for r in reels:
        score = r.get("hook_score", 0)
        htype = r.get("hook_type", "?")
        text = r.get("hook_text") or f"(visual: {r.get('hook_visual', '')[:50]})"
        print(f"  [{score:>3}/100] @{r['account']:<22} [{htype}]")
        print(f"           {text!r}")
        if r.get("hook_reasoning"):
            print(f"           Why: {r['hook_reasoning'][:120]}")
        print(f"           {r['shortcode']} (views: {r.get('views') or '?'})")
        print()
    return 0


async def amain() -> int:
    parser = argparse.ArgumentParser(description="Search reels / Filter hook library")
    sub = parser.add_subparsers(dest="action", required=True)

    # search
    ps = sub.add_parser("search", help="Semantic free-text search")
    ps.add_argument("query", help="Free-text query")
    ps.add_argument("--column", choices=["hook_emb", "transcript_emb", "summary_emb"], default="summary_emb")
    ps.add_argument("--top-k", type=int, default=10)
    ps.add_argument("--min-score", type=float, help="Min cosine similarity (0-1)")
    ps.add_argument("--client", help="Filter by client name")
    ps.add_argument("--hook-type")
    ps.add_argument("--angle")
    ps.add_argument("--min-hook-score", type=int)
    ps.add_argument("--min-views", type=int)
    ps.add_argument("--output", choices=["pretty", "json"], default="pretty")
    ps.add_argument("--log-level", default="WARNING")
    ps.set_defaults(_async=True, func=cmd_search)

    # hooks
    ph = sub.add_parser("hooks", help="Filtered hook library")
    ph.add_argument("--hook-type")
    ph.add_argument("--min-score", type=int)
    ph.add_argument("--client")
    ph.add_argument("--limit", type=int, default=20)
    ph.add_argument("--output", choices=["pretty", "json"], default="pretty")
    ph.set_defaults(_async=False, func=cmd_hooks)

    args = parser.parse_args()
    if getattr(args, "_async", False):
        return await args.func(args)
    return args.func(args)


def main() -> int:
    return asyncio.run(amain())


if __name__ == "__main__":
    sys.exit(main())
