"""/ci-report and /ci-export — Reports + data exports."""

from __future__ import annotations

import sys
import json
import csv
import io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse

from db.local_db import get_local_db, make_slug


PERIOD_DAYS = {"weekly": 7, "monthly": 30, "quarterly": 90}


def cmd_report(args: argparse.Namespace) -> int:
    db = get_local_db()
    slug = make_slug(args.client)
    client = db.get_client_by_slug(slug) or db.get_client_by_name(args.client)
    if not client:
        print(f"[ci-report] Client not found: '{args.client}'", file=sys.stderr)
        return 1

    period_days = PERIOD_DAYS.get(args.period, 7)
    from generators.report_gen import generate_report, render_report
    data = generate_report(client["slug"], period_days=period_days)
    md = render_report(data)

    if args.output == "json":
        out = {"data": data, "markdown": md}
        print(json.dumps(out, indent=2, default=str, ensure_ascii=False))
        return 0

    print(md)

    if args.save:
        path = Path(args.save).expanduser()
        path.write_text(md, encoding="utf-8")
        print(f"\n[ci-report] Saved to {path}", file=sys.stderr)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    db = get_local_db()
    client_slug = None
    if args.client:
        c = db.get_client_by_slug(make_slug(args.client)) or db.get_client_by_name(args.client)
        if not c:
            print(f"[ci-export] Client not found: '{args.client}'", file=sys.stderr)
            return 1
        client_slug = c["slug"]

    reels = db.list_reels(client_id=client_slug, limit=args.limit)

    out_path = Path(args.out).expanduser() if args.out else None

    if args.format == "json":
        text = json.dumps(reels, indent=2, default=str, ensure_ascii=False)
    else:
        # CSV
        if not reels:
            text = ""
        else:
            buf = io.StringIO()
            cols = [
                "shortcode", "source", "account", "client_id", "is_own",
                "views", "likes", "comments", "engagement_rate",
                "language", "summary", "angle",
                "hook_type", "hook_text", "hook_score",
                "score_retention", "score_visual", "score_cta",
                "posted_at", "analyzed_at",
            ]
            w = csv.writer(buf)
            w.writerow(cols)
            for r in reels:
                w.writerow([r.get(c, "") for c in cols])
            text = buf.getvalue()

    if out_path:
        out_path.write_text(text, encoding="utf-8")
        print(f"[ci-export] Wrote {len(reels)} reels to {out_path}")
    else:
        print(text)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Client reports + data export")
    sub = parser.add_subparsers(dest="action", required=True)

    pr = sub.add_parser("report", help="Generate periodic report")
    pr.add_argument("--client", required=True)
    pr.add_argument("--period", choices=list(PERIOD_DAYS.keys()), default="weekly")
    pr.add_argument("--save", help="Save markdown to file")
    pr.add_argument("--output", choices=["pretty", "json"], default="pretty")
    pr.set_defaults(func=cmd_report)

    pe = sub.add_parser("export", help="Export reels as JSON or CSV")
    pe.add_argument("--client")
    pe.add_argument("--format", choices=["json", "csv"], default="csv")
    pe.add_argument("--limit", type=int, default=1000)
    pe.add_argument("--out", help="Output file path")
    pe.set_defaults(func=cmd_export)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
