"""/ci-track — Track an account for periodic re-scraping.

NOTE: Phase 5 — sets up tracking metadata in the DB. The actual
background scrape-loop is run separately (n8n cron or manual `/ci-track-run`).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import json
import asyncio

from config import get_settings
from db.local_db import get_local_db, make_slug


def cmd_add(args: argparse.Namespace) -> int:
    db = get_local_db()
    s = get_settings()

    slug = make_slug(args.client)
    c = db.get_client_by_slug(slug) or db.get_client_by_name(args.client)
    if not c:
        print(f"[ci-track] Client not found: '{args.client}'. Create with /ci-client-add", file=sys.stderr)
        return 1

    tid = db.add_tracked_account(
        client_id=c["slug"],
        handle=args.handle,
        source=args.source,
        is_own=args.is_own,
        interval_hours=args.interval,
        created_by=s.ci_user,
    )

    if args.output == "json":
        print(json.dumps({"tracked_id": tid, "client": c["name"], "handle": args.handle}, indent=2))
    else:
        print(f"[ci-track] Tracking @{args.handle.lstrip('@')} ({args.source}) for client '{c['name']}'")
        print(f"  Interval: every {args.interval}h")
        print(f"  ID: {tid}")
        print()
        print("Background scraping not yet automated — use /ci-track run to do a manual batch now.")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    db = get_local_db()
    client_slug = None
    if args.client:
        c = db.get_client_by_slug(make_slug(args.client)) or db.get_client_by_name(args.client)
        if c:
            client_slug = c["slug"]
    tracked = db.list_tracked_accounts(client_id=client_slug)
    if args.output == "json":
        print(json.dumps(tracked, indent=2, default=str))
        return 0
    if not tracked:
        print("[ci-track] No tracked accounts.")
        return 0
    print(f"Tracked accounts ({len(tracked)}):")
    for t in tracked:
        last = t.get("last_scraped") or "never"
        kind = "own" if t.get("is_own") else "competitor"
        print(f"  @{t['handle']:<22} [{t['source']}/{kind}]  client={t['client_id']}  every {t['interval_hours']}h  last_scraped={last}")
    return 0


async def cmd_run(args: argparse.Namespace) -> int:
    """Manually trigger a scrape-run for all due tracked accounts."""
    db = get_local_db()
    s = get_settings()
    if not (s.has_gemini() and s.has_apify()):
        print("[ci-track] Missing keys. Run /ci-setup", file=sys.stderr)
        return 3

    tracked = db.list_tracked_accounts()
    if args.client:
        c = db.get_client_by_slug(make_slug(args.client)) or db.get_client_by_name(args.client)
        if c:
            tracked = [t for t in tracked if t["client_id"] == c["slug"]]

    now = time.time()
    due = []
    for t in tracked:
        if not t.get("active"):
            continue
        last = t.get("last_scraped") or 0
        interval_s = t.get("interval_hours", 24) * 3600
        if (now - last) >= interval_s or args.force:
            due.append(t)

    if not due:
        print(f"[ci-track] No tracked accounts due (total tracked: {len(tracked)})")
        return 0

    print(f"[ci-track] Running scrape for {len(due)} due accounts...", file=sys.stderr)

    from clients.apify import ApifyClient
    from pipeline.orchestrator import build_pipeline
    apify = ApifyClient()
    pipeline = build_pipeline()

    for t in due:
        handle = t["handle"]
        client_slug = t["client_id"]
        is_own = bool(t.get("is_own"))
        print(f"[ci-track] >>> @{handle} (client={client_slug})", file=sys.stderr)
        try:
            reels = await apify.scrape_account_top(handle, limit=args.last)
            # Skip already-analyzed
            new_reels = []
            for r in reels:
                if not db.get_reel(r.shortcode):
                    new_reels.append(r)
            print(f"  found {len(reels)} reels, {len(new_reels)} new", file=sys.stderr)

            ok = 0
            for r in new_reels:
                url = f"https://www.instagram.com/reel/{r.shortcode}/"
                try:
                    await pipeline.process_url(url, client_id=client_slug, is_own=is_own)
                    ok += 1
                except Exception as e:
                    print(f"  fail {r.shortcode}: {str(e)[:120]}", file=sys.stderr)
            print(f"  analyzed {ok}/{len(new_reels)}", file=sys.stderr)

            # Update last_scraped
            with db._conn() as c:
                c.execute(
                    "UPDATE tracked_accounts SET last_scraped = ?, reel_count = reel_count + ? WHERE id = ?",
                    (time.time(), ok, t["id"]),
                )
        except Exception as e:
            print(f"  account scrape failed: {str(e)[:200]}", file=sys.stderr)
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    db = get_local_db()
    with db._conn() as c:
        cur = c.execute(
            "DELETE FROM tracked_accounts WHERE handle = ?",
            (args.handle.lstrip("@"),),
        )
        n = cur.rowcount
    print(f"[ci-track] Removed {n} tracked entry/entries for @{args.handle.lstrip('@')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Track accounts for periodic scraping")
    sub = parser.add_subparsers(dest="action", required=True)

    pa = sub.add_parser("add", help="Track an account")
    pa.add_argument("handle", help="@username")
    pa.add_argument("--client", required=True)
    pa.add_argument("--source", choices=["ig", "tiktok"], default="ig")
    pa.add_argument("--is-own", action="store_true")
    pa.add_argument("--interval", type=int, default=24, help="Hours between scrapes (default 24)")
    pa.add_argument("--output", choices=["pretty", "json"], default="pretty")
    pa.set_defaults(func=cmd_add)

    pl = sub.add_parser("list", help="List tracked accounts")
    pl.add_argument("--client")
    pl.add_argument("--output", choices=["pretty", "json"], default="pretty")
    pl.set_defaults(func=cmd_list)

    pr = sub.add_parser("run", help="Manually run due trackers now")
    pr.add_argument("--client", help="Limit to one client")
    pr.add_argument("--force", action="store_true", help="Run even if not due")
    pr.add_argument("--last", type=int, default=10, help="Scrape last N reels per account")
    pr.set_defaults(_async=True, func=cmd_run)

    pd = sub.add_parser("remove", help="Stop tracking")
    pd.add_argument("handle")
    pd.set_defaults(func=cmd_remove)

    args = parser.parse_args()
    if getattr(args, "_async", False):
        return asyncio.run(args.func(args))
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
