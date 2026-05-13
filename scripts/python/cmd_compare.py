"""/ci-compare — Compare 2-5 reels side by side."""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import asyncio
import json

from db.local_db import get_local_db


async def fetch_or_analyze(url_or_shortcode: str, client_slug: str | None = None) -> dict | None:
    """Get reel from DB or analyze it now."""
    db = get_local_db()
    from pipeline.scraper import extract_shortcode

    # Try as shortcode first
    sc = url_or_shortcode
    if "/" in url_or_shortcode or "http" in url_or_shortcode:
        try:
            sc = extract_shortcode(url_or_shortcode)
        except ValueError:
            print(f"[ci-compare] Invalid URL: {url_or_shortcode}", file=sys.stderr)
            return None

    existing = db.get_reel(sc)
    if existing:
        return existing

    # Analyze on-demand
    if not ("http" in url_or_shortcode):
        print(f"[ci-compare] Shortcode {sc} not in DB and not a full URL — cannot fetch", file=sys.stderr)
        return None

    print(f"[ci-compare] Analyzing {sc}...", file=sys.stderr)
    from pipeline.orchestrator import build_pipeline
    pipeline = build_pipeline()
    try:
        await pipeline.process_url(url_or_shortcode, client_id=client_slug)
    except Exception as e:
        print(f"[ci-compare] Analyze failed for {url_or_shortcode}: {e}", file=sys.stderr)
        return None
    return db.get_reel(sc)


async def amain() -> int:
    parser = argparse.ArgumentParser(description="Compare 2-5 reels side by side")
    parser.add_argument("reels", nargs="+", help="URLs or shortcodes (2-5)")
    parser.add_argument("--client", help="Client name (for context)")
    parser.add_argument("--output", choices=["pretty", "json"], default="pretty")
    args = parser.parse_args()

    if not (2 <= len(args.reels) <= 5):
        print("[ci-compare] Need 2-5 reels", file=sys.stderr)
        return 1

    client_slug = None
    if args.client:
        db = get_local_db()
        from db.local_db import make_slug
        c = db.get_client_by_slug(make_slug(args.client)) or db.get_client_by_name(args.client)
        client_slug = c["slug"] if c else None

    fetched = await asyncio.gather(*[fetch_or_analyze(r, client_slug) for r in args.reels])
    valid = [r for r in fetched if r]

    if len(valid) < 2:
        print("[ci-compare] Need at least 2 valid reels to compare", file=sys.stderr)
        return 1

    if args.output == "json":
        print(json.dumps(valid, indent=2, default=str))
        return 0

    # Render side-by-side comparison
    print(f"Comparing {len(valid)} reels:")
    print()

    rows = [
        ("Account", lambda r: f"@{r.get('account', '?')}"),
        ("Shortcode", lambda r: r.get("shortcode", "?")),
        ("Duration", lambda r: f"{r.get('duration_s', 0)}s"),
        ("Views", lambda r: f"{r.get('views') or '?'}"),
        ("Likes", lambda r: f"{r.get('likes') or '?'}"),
        ("ER", lambda r: f"{(r.get('engagement_rate') or 0)*100:.1f}%"),
        ("Hook Type", lambda r: r.get("hook_type", "?")),
        ("Hook Score", lambda r: f"{r.get('hook_score', 0)}/100"),
        ("Angle", lambda r: r.get("angle", "?")),
        ("Retention", lambda r: f"{r.get('score_retention', 0)}%"),
        ("Visual Q.", lambda r: f"{r.get('score_visual', 0)}/100"),
        ("CTA Clarity", lambda r: f"{r.get('score_cta', 0)}/100"),
    ]

    col_w = 22
    header = "  " + "Metric".ljust(15) + "".join(f"{'Reel ' + str(i+1):<{col_w}}" for i in range(len(valid)))
    print(header)
    print("  " + "-" * (15 + col_w * len(valid)))
    for label, getter in rows:
        line = "  " + label.ljust(15) + "".join(f"{str(getter(r))[:col_w-2]:<{col_w}}" for r in valid)
        print(line)

    # Hooks comparison
    print()
    print("HOOKS:")
    for i, r in enumerate(valid):
        ht = r.get("hook_text") or f"(visual: {r.get('hook_visual', '?')[:40]})"
        print(f"  Reel {i+1}: [{r.get('hook_score', 0)}/100] {ht!r}")
        if r.get("hook_reasoning"):
            print(f"           Why: {r['hook_reasoning'][:140]}")

    # Winner
    print()
    winner_idx = max(range(len(valid)), key=lambda i: valid[i].get("hook_score", 0))
    winner = valid[winner_idx]
    print(f"WINNER (Hook Score): Reel {winner_idx + 1} @{winner.get('account')} — {winner.get('hook_score')}/100")

    return 0


def main() -> int:
    return asyncio.run(amain())


if __name__ == "__main__":
    sys.exit(main())
