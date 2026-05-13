"""/ci-script (+ from-ref, batch, review) — Script generation."""

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


def resolve_client(name: str) -> tuple[str, str] | None:
    """Returns (slug, name) or None if not found."""
    db = get_local_db()
    slug = make_slug(name)
    c = db.get_client_by_slug(slug) or db.get_client_by_name(name)
    return (c["slug"], c["name"]) if c else None


async def cmd_generate(args: argparse.Namespace) -> int:
    """Generate a new script."""
    setup_logging(args.log_level)
    s = get_settings()
    if not s.has_gemini():
        print("[ci-script] GEMINI_API_KEY required", file=sys.stderr)
        return 3

    resolved = resolve_client(args.client)
    if not resolved:
        print(f"[ci-script] Client not found: '{args.client}'. Create with /ci-client-add first.", file=sys.stderr)
        return 1
    client_slug, client_name = resolved

    from generators.script_gen import generate_script, render_markdown, save_script

    script, referenced = await generate_script(
        thema=args.thema,
        client_slug=client_slug,
        constraint_hook_type=args.hook_type,
        constraint_angle=args.angle,
        temperature=args.temperature,
    )

    md = render_markdown(script, args.thema, client_name)

    if not args.dry_run:
        sid = save_script(
            script=script,
            client_slug=client_slug,
            thema=args.thema,
            full_markdown=md,
            created_by=s.ci_user,
        )
    else:
        sid = "(not saved)"

    if args.output == "json":
        out = script.model_dump(mode="json")
        out["script_id"] = sid
        out["client_slug"] = client_slug
        out["referenced_top_performers"] = referenced
        out["markdown"] = md
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(md)
        print()
        print(f"---")
        print(f"Script ID: {sid}")
        if referenced:
            print(f"Inspired by {len(referenced)} top-performers from DB")
    return 0


async def cmd_from_ref(args: argparse.Namespace) -> int:
    """Generate script based on a specific reference reel."""
    setup_logging(args.log_level)
    s = get_settings()

    resolved = resolve_client(args.client)
    if not resolved:
        print(f"[ci-script-from-ref] Client not found: '{args.client}'", file=sys.stderr)
        return 1
    client_slug, client_name = resolved

    db = get_local_db()

    # Resolve reference reel
    from pipeline.scraper import extract_shortcode
    sc = args.reference
    if "/" in args.reference or "http" in args.reference:
        sc = extract_shortcode(args.reference)
    ref_reel = db.get_reel(sc)
    if not ref_reel:
        print(f"[ci-script-from-ref] Reference reel not in DB: {sc}. Analyze first with /ci-analyze.", file=sys.stderr)
        return 1

    # Build a "from-ref" thema string injecting the reference characteristics
    thema = (
        f"{args.thema}\n\n"
        f"Adaptiere die Struktur dieser Referenz fuer den Klienten:\n"
        f"- Hook-Type: {ref_reel['hook_type']}\n"
        f"- Hook-Text: {ref_reel.get('hook_text') or '(visual)'}\n"
        f"- Angle: {ref_reel['angle']}\n"
        f"- Score: {ref_reel.get('hook_score')}/100\n"
        f"- Was funktionierte: {ref_reel.get('hook_reasoning', '')}\n"
        f"Nutze das selbe Struktur-Prinzip, aber konkret fuer Klient + Thema."
    )

    from generators.script_gen import generate_script, render_markdown, save_script
    script, _referenced = await generate_script(
        thema=thema,
        client_slug=client_slug,
        constraint_hook_type=ref_reel["hook_type"],
        constraint_angle=ref_reel["angle"],
        temperature=args.temperature,
    )

    # Ensure ref shortcode is in referenz_shortcodes
    if sc not in script.referenz_shortcodes:
        script.referenz_shortcodes.insert(0, sc)

    md = render_markdown(script, args.thema, client_name)
    if not args.dry_run:
        sid = save_script(
            script=script,
            client_slug=client_slug,
            thema=args.thema,
            full_markdown=md,
            trend_basis=f"Adapted from {sc}",
            created_by=s.ci_user,
        )
    else:
        sid = "(not saved)"

    if args.output == "json":
        out = script.model_dump(mode="json")
        out["script_id"] = sid
        out["reference_shortcode"] = sc
        out["markdown"] = md
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print(md)
        print()
        print(f"Script ID: {sid} — Adapted from {sc}")
    return 0


async def cmd_batch(args: argparse.Namespace) -> int:
    """Generate N script variants for the same thema."""
    setup_logging(args.log_level)

    resolved = resolve_client(args.client)
    if not resolved:
        print(f"[ci-script-batch] Client not found: '{args.client}'", file=sys.stderr)
        return 1
    client_slug, client_name = resolved

    from generators.script_gen import generate_script, render_markdown, save_script
    s = get_settings()

    # Run N parallel generations with different temperatures + hook-type rotation
    from schemas.reel import HookType
    hook_rotation = [
        HookType.PATTERN_INTERRUPT,
        HookType.QUESTION,
        HookType.PROBLEM,
        HookType.SHOCK,
        HookType.DEMONSTRATION,
    ][: args.count]

    async def one(ht_constraint: HookType, idx: int):
        try:
            sc, _ref = await generate_script(
                thema=args.thema,
                client_slug=client_slug,
                constraint_hook_type=ht_constraint.value,
                temperature=0.5 + (idx * 0.1),
            )
            return ht_constraint, sc
        except Exception as e:
            return ht_constraint, e

    results = await asyncio.gather(*[one(ht, i) for i, ht in enumerate(hook_rotation)])

    out_list = []
    for ht, res in results:
        if isinstance(res, Exception):
            print(f"[variant {ht.value}] FAILED: {str(res)[:120]}", file=sys.stderr)
            continue
        md = render_markdown(res, args.thema, client_name)
        if not args.dry_run:
            sid = save_script(
                script=res,
                client_slug=client_slug,
                thema=args.thema,
                full_markdown=md,
                created_by=s.ci_user,
            )
        else:
            sid = "(not saved)"
        out_list.append({"script_id": sid, "hook_type": ht.value, "score_prediction": res.score_prediction, "markdown": md})

    # Sort by predicted score desc
    out_list.sort(key=lambda x: x["score_prediction"], reverse=True)

    if args.output == "json":
        print(json.dumps(out_list, indent=2, ensure_ascii=False))
    else:
        print(f"# {len(out_list)} Skript-Varianten fuer '{args.thema}' — {client_name}")
        print()
        print("## Score-Ranking")
        for i, v in enumerate(out_list, 1):
            print(f"{i}. **{v['hook_type']}** — Score {v['score_prediction']}/100 (ID: {v['script_id']})")
        print()
        for v in out_list:
            print("---")
            print()
            print(v["markdown"])
            print()
    return 0


async def cmd_review(args: argparse.Namespace) -> int:
    """Review a user-pasted script against DB benchmarks."""
    setup_logging(args.log_level)
    s = get_settings()

    if not s.has_gemini():
        print("[ci-script-review] GEMINI_API_KEY required", file=sys.stderr)
        return 3

    resolved = resolve_client(args.client) if args.client else None
    client_slug = resolved[0] if resolved else None
    client_name = resolved[1] if resolved else None

    # Read script from arg or stdin
    if args.text:
        script_text = args.text
    elif args.file:
        script_text = Path(args.file).read_text(encoding="utf-8")
    else:
        print("[ci-script-review] Provide --text or --file", file=sys.stderr)
        return 1

    # Build review prompt
    db = get_local_db()
    benchmark_reels = db.list_reels(client_id=client_slug, min_score=70, limit=5) if client_slug else db.list_reels(min_score=80, limit=5)

    bench_text = "\n".join(
        f"- @{r['account']} [{r['hook_type']}/{r.get('hook_score',0)}/100]: {r.get('hook_text') or '(visual)'}"
        for r in benchmark_reels
    ) or "(no benchmark reels in DB)"

    review_prompt = f"""Du bist ein Performance-Content-Reviewer. Bewerte das folgende Skript und vergleiche es mit den Top-Performern aus der DB.

## Skript zu reviewen

{script_text}

## Benchmark-Performer (Top-Reels {f'fuer {client_name}' if client_name else ''})

{bench_text}

## Aufgabe

Gib eine strukturierte Bewertung als JSON:
{{
  "hook_score": 0-100,
  "angle_fit": 0-100,
  "cta_clarity": 0-100,
  "overall_score": 0-100,
  "staerken": ["..."],
  "schwaechen": ["..."],
  "verbesserungen": ["konkrete actionable improvements"],
  "benchmark_vergleich": "wie performt es relativ zu den Top-Reels"
}}
"""

    from clients.gemini import GeminiClient

    gemini = GeminiClient()
    try:
        review = await gemini.generate_structured(
            prompt=review_prompt,
            schema=None,  # free-form JSON, no Pydantic schema enforcement
            temperature=0.3,
            max_output_tokens=2048,
        )
    except Exception as e:
        print(f"[ci-script-review] Gemini call failed: {str(e)[:300]}", file=sys.stderr)
        return 1

    if args.output == "json":
        print(json.dumps(review, indent=2, ensure_ascii=False))
        return 0

    print(f"# Skript-Review {f'({client_name})' if client_name else ''}")
    print()
    print(f"**Overall Score:** {review.get('overall_score', 0)}/100")
    print(f"  Hook: {review.get('hook_score', 0)}/100  |  Angle: {review.get('angle_fit', 0)}/100  |  CTA: {review.get('cta_clarity', 0)}/100")
    print()
    if review.get("staerken"):
        print("## Staerken")
        for x in review["staerken"]:
            print(f"- {x}")
        print()
    if review.get("schwaechen"):
        print("## Schwaechen")
        for x in review["schwaechen"]:
            print(f"- {x}")
        print()
    if review.get("verbesserungen"):
        print("## Verbesserungen")
        for x in review["verbesserungen"]:
            print(f"- {x}")
        print()
    if review.get("benchmark_vergleich"):
        print("## Benchmark-Vergleich")
        print(review["benchmark_vergleich"])
    return 0


async def amain() -> int:
    parser = argparse.ArgumentParser(description="Generate / review reel scripts")
    sub = parser.add_subparsers(dest="action", required=True)

    # generate
    pg = sub.add_parser("generate", help="Generate a new script")
    pg.add_argument("--client", required=True)
    pg.add_argument("--thema", required=True, help="What the reel should be about")
    pg.add_argument("--hook-type", help="Constrain hook type")
    pg.add_argument("--angle", help="Constrain angle")
    pg.add_argument("--temperature", type=float, default=0.4)
    pg.add_argument("--dry-run", action="store_true", help="Don't save to DB")
    pg.add_argument("--output", choices=["pretty", "json"], default="pretty")
    pg.add_argument("--log-level", default="WARNING")
    pg.set_defaults(func=cmd_generate)

    # from-ref
    pf = sub.add_parser("from-ref", help="Adapt a reference reel's structure")
    pf.add_argument("--client", required=True)
    pf.add_argument("--thema", required=True)
    pf.add_argument("--reference", required=True, help="Reference reel URL or shortcode")
    pf.add_argument("--temperature", type=float, default=0.3)
    pf.add_argument("--dry-run", action="store_true")
    pf.add_argument("--output", choices=["pretty", "json"], default="pretty")
    pf.add_argument("--log-level", default="WARNING")
    pf.set_defaults(func=cmd_from_ref)

    # batch
    pb = sub.add_parser("batch", help="Generate N variants for same thema")
    pb.add_argument("--client", required=True)
    pb.add_argument("--thema", required=True)
    pb.add_argument("--count", type=int, default=3, choices=range(2, 6))
    pb.add_argument("--dry-run", action="store_true")
    pb.add_argument("--output", choices=["pretty", "json"], default="pretty")
    pb.add_argument("--log-level", default="WARNING")
    pb.set_defaults(func=cmd_batch)

    # review
    pr = sub.add_parser("review", help="Review a pasted script against DB benchmarks")
    pr.add_argument("--client")
    pr.add_argument("--text", help="Skript-Text inline")
    pr.add_argument("--file", help="Skript-Text aus Datei")
    pr.add_argument("--output", choices=["pretty", "json"], default="pretty")
    pr.add_argument("--log-level", default="WARNING")
    pr.set_defaults(func=cmd_review)

    args = parser.parse_args()
    return await args.func(args)


def main() -> int:
    return asyncio.run(amain())


if __name__ == "__main__":
    sys.exit(main())
