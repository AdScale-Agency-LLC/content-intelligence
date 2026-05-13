"""/ci-analyze — Analyze a single Reel/TikTok with Gemini 2.5 Flash."""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import asyncio
import json
import logging
import time

from config import get_settings
from db.local_db import get_local_db, make_slug


def setup_logging(level: str = "WARNING") -> None:
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def resolve_client(client_arg: str | None) -> tuple[str | None, str | None]:
    """Resolve client argument to (slug, name). Returns (None, None) if not given.

    Auto-creates client if not found AND --auto-create is implied.
    """
    if not client_arg:
        return None, None

    db = get_local_db()
    s = get_settings()

    # Try exact slug or name match
    slug = make_slug(client_arg)
    client = db.get_client_by_slug(slug)
    if not client:
        client = db.get_client_by_name(client_arg)

    if client:
        return client["slug"], client["name"]

    # Auto-create: silent (Option C from plan)
    new_client = db.upsert_client(
        name=client_arg,
        slug=slug,
        created_by=s.ci_user,
    )
    print(f"[ci-analyze] Auto-created client: '{new_client['name']}' (slug={new_client['slug']})", file=sys.stderr)
    return new_client["slug"], new_client["name"]


def build_client_context(slug: str) -> str | None:
    """Build a short context string for Gemini analysis from client profile."""
    db = get_local_db()
    client = db.get_client_by_slug(slug)
    if not client:
        return None
    parts = []
    parts.append(f"Klient: {client['name']}")
    if client.get("branche"):
        parts.append(f"Branche: {client['branche']}")
    if client.get("zielgruppe"):
        parts.append(f"Zielgruppe: {client['zielgruppe']}")
    if client.get("tonalitaet"):
        parts.append(f"Tonalitaet: {client['tonalitaet']}")
    return ". ".join(parts)


def render_pretty(reel: dict, client_name: str | None = None) -> str:
    """Render the reel analysis for human reading."""
    lines = []
    account = reel.get("account") or "?"
    duration = reel.get("duration_s") or 0
    lang = reel.get("language") or "?"
    src = reel.get("source") or "ig"

    header = f"Reel @{account} · {duration}s · {lang} · {src.upper()}"
    if client_name:
        header += f" · Client: {client_name}"
    lines.append(header)

    views = reel.get("views")
    likes = reel.get("likes")
    posted = reel.get("posted_at") or "?"
    if views or likes:
        lines.append(f"Posted: {posted}  Views: {views or '?'}  Likes: {likes or '?'}")
    lines.append("")

    hs = reel.get("hook_score") or 0
    lines.append(f"HOOK [Score {hs}/100]")
    lines.append(f"  Type: {reel.get('hook_type')}")
    lines.append(f"  Visual: {reel.get('hook_visual')}")
    if reel.get("hook_text"):
        lines.append(f"  Text: {reel['hook_text']!r}")
    lines.append(f"  Why: {reel.get('hook_reasoning')}")
    lines.append("")

    lines.append(f"ANGLE: {reel.get('angle')}")

    emotions = reel.get("emotions") or []
    if emotions:
        emo_str = " > ".join(
            f"{e['emotion']} ({e['start_s']:.0f}-{e['end_s']:.0f}s)" for e in emotions
        )
        lines.append(f"EMOTIONS: {emo_str}")

    ctas = reel.get("cta_elements") or []
    if ctas:
        for cta in ctas:
            ts = cta.get("timestamp_s", 0)
            content = cta.get("content", "")
            strength = cta.get("strength", "")
            lines.append(f"CTA @ {ts:.0f}s: {content!r} ({strength})")

    vp = reel.get("visual_patterns") or {}
    if vp:
        lines.append(f"CUTS: {vp.get('cut_frequency_per_10s', 0):.1f} / 10s")

    cp = reel.get("color_palette") or {}
    if cp.get("primary_hex"):
        lines.append(f"COLORS: {' '.join(cp['primary_hex'])}")
    lines.append("")

    lines.append("SCORE")
    lines.append(f"  Retention-Prediction: {reel.get('score_retention', 0)}%")
    lines.append(f"  Hook-Strength:        {reel.get('score_hook', 0)}/100")
    lines.append(f"  Visual-Quality:       {reel.get('score_visual', 0)}/100")
    lines.append(f"  CTA-Clarity:          {reel.get('score_cta', 0)}/100")
    lines.append("")

    improvements = reel.get("score_improvements") or []
    if improvements:
        lines.append("TOP IMPROVEMENTS:")
        for i, imp in enumerate(improvements, 1):
            lines.append(f"  {i}. {imp}")
        lines.append("")

    themes = reel.get("content_themes") or []
    if themes:
        lines.append(f"THEMES: {', '.join(themes)}")
    if reel.get("target_audience_hint"):
        lines.append(f"TARGET: {reel['target_audience_hint']}")
    lines.append("")
    lines.append(f"Summary: {reel.get('summary')}")
    return "\n".join(lines)


async def amain() -> int:
    parser = argparse.ArgumentParser(description="Analyze an IG Reel or TikTok with Gemini 2.5")
    parser.add_argument("url", help="Reel/TikTok URL")
    parser.add_argument("--client", help="Client name (auto-create if new)")
    parser.add_argument("--is-own", action="store_true", help="Mark as own content (vs. competitor)")
    parser.add_argument("--output", choices=["pretty", "json"], default="pretty")
    parser.add_argument("--log-level", default="WARNING")
    parser.add_argument("--force", action="store_true", help="Re-analyze even if already in DB")
    args = parser.parse_args()

    setup_logging(args.log_level)

    s = get_settings()
    if not (s.has_gemini() and s.has_apify()):
        missing = []
        if not s.has_gemini():
            missing.append("GEMINI_API_KEY (https://aistudio.google.com/apikey)")
        if not s.has_apify():
            missing.append("APIFY_API_TOKEN (https://console.apify.com/account/integrations)")
        print(f"[ci-analyze] Missing required keys:\n  - " + "\n  - ".join(missing), file=sys.stderr)
        print("\nFix:  /ci-setup --interactive", file=sys.stderr)
        return 3

    db = get_local_db()

    # Resolve client (auto-create if needed)
    client_slug, client_name = resolve_client(args.client)
    client_context = build_client_context(client_slug) if client_slug else None

    # Check if reel already analyzed (idempotency)
    from pipeline.scraper import extract_shortcode
    shortcode = extract_shortcode(args.url)
    existing = db.get_reel(shortcode)
    if existing and not args.force:
        print(f"[ci-analyze] Reel already analyzed: {shortcode} (use --force to re-analyze)", file=sys.stderr)
        # Update client linkage if not set
        if client_slug and not existing.get("client_id"):
            # Re-upsert with client_id (preserves other fields via SQL coalesce)
            with db._conn() as c:
                c.execute(
                    "UPDATE reels SET client_id = ?, is_own = ? WHERE shortcode = ?",
                    (client_slug, 1 if args.is_own else 0, shortcode),
                )
            print(f"[ci-analyze] Linked existing reel to client: {client_name}", file=sys.stderr)
        if args.output == "json":
            print(json.dumps(existing, indent=2, default=str))
        else:
            print(render_pretty(existing, client_name=client_name))
        return 0

    # Run pipeline
    from pipeline.orchestrator import build_pipeline
    pipeline = build_pipeline()

    start_ms = int(time.time() * 1000)
    try:
        result = await pipeline.process_url(
            args.url,
            client_id=client_slug,
            is_own=args.is_own,
            client_context=client_context,
        )
    except Exception as e:
        elapsed = int(time.time() * 1000) - start_ms
        db.log_invocation(
            "ci-analyze",
            args={"url": args.url, "client": args.client},
            status="failed",
            error=str(e)[:300],
            duration_ms=elapsed,
        )
        print(f"[ci-analyze] FAILED: {str(e)[:300]}", file=sys.stderr)
        return 1

    elapsed = int(time.time() * 1000) - start_ms
    db.log_invocation(
        "ci-analyze",
        args={"url": args.url, "client": args.client, "shortcode": result.shortcode},
        status="ok",
        duration_ms=elapsed,
    )

    # Read back the stored reel
    stored = db.get_reel(result.shortcode)

    if args.output == "json":
        print(json.dumps(stored, indent=2, default=str))
    else:
        print(render_pretty(stored, client_name=client_name))
        print()
        print(f"[stored in {elapsed} ms]")
    return 0


def main() -> int:
    return asyncio.run(amain())


if __name__ == "__main__":
    sys.exit(main())
