"""/ci-trends and /ci-viral — Trend aggregation + viral detection."""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import json

from db.local_db import get_local_db, make_slug


def resolve_client_slug(name: str | None) -> str | None:
    if not name:
        return None
    db = get_local_db()
    c = db.get_client_by_slug(make_slug(name)) or db.get_client_by_name(name)
    return c["slug"] if c else None


def cmd_trends(args: argparse.Namespace) -> int:
    from generators.trend_agg import aggregate, render_trend_report
    client_slug = resolve_client_slug(args.client)
    t = aggregate(period_days=args.period, branche=args.branche, client_id=client_slug)

    if args.output == "json":
        print(json.dumps(t.__dict__, indent=2, default=str, ensure_ascii=False))
        return 0
    print(render_trend_report(t))
    return 0


def cmd_viral(args: argparse.Namespace) -> int:
    from generators.trend_agg import detect_viral
    client_slug = resolve_client_slug(args.client)
    virals = detect_viral(
        period_days=args.period,
        branche=args.branche,
        client_id=client_slug,
        viral_threshold=args.threshold,
    )

    if args.output == "json":
        print(json.dumps(virals, indent=2, default=str, ensure_ascii=False))
        return 0

    if not virals:
        print(f"[ci-viral] No viral outliers found (threshold {args.threshold}x median, period {args.period}d)")
        return 0

    print(f"# Viral Outliers (>{args.threshold}x median views/follower ratio)")
    print(f"  Period: {args.period}d  |  Found: {len(virals)}")
    print()
    for v in virals[:20]:
        print(f"@{v['account']}  [{v['hook_type']}/{v.get('hook_score',0)}/100]")
        print(f"  Views: {v['views']:,}  Followers: {v['account_followers']:,}  "
              f"Ratio: {v['ratio']} ({v['factor_above_median']}x median)")
        if v.get("hook_text"):
            print(f"  Hook: {v['hook_text']!r}")
        if v.get("hook_reasoning"):
            print(f"  Why:  {v['hook_reasoning'][:140]}")
        print(f"  {v['shortcode']}")
        print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Trend aggregation + viral detection")
    sub = parser.add_subparsers(dest="action", required=True)

    pt = sub.add_parser("trends", help="Trend report")
    pt.add_argument("--period", type=int, default=30, help="Period in days")
    pt.add_argument("--branche")
    pt.add_argument("--client")
    pt.add_argument("--output", choices=["pretty", "json"], default="pretty")
    pt.set_defaults(func=cmd_trends)

    pv = sub.add_parser("viral", help="Detect viral outliers")
    pv.add_argument("--period", type=int, default=30)
    pv.add_argument("--branche")
    pv.add_argument("--client")
    pv.add_argument("--threshold", type=float, default=2.0, help="x median (default 2.0)")
    pv.add_argument("--output", choices=["pretty", "json"], default="pretty")
    pv.set_defaults(func=cmd_viral)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
