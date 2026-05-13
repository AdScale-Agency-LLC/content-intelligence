"""/ci-status — Plugin dashboard: clients, reels, jobs, recent activity."""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import json

from config import get_settings


def gather_status(preflight_only: bool = False) -> dict:
    s = get_settings()
    out: dict = {
        "user": s.ci_user,
        "config_ready": s.has_gemini() and s.has_apify(),
        "tiktok_configured": bool(s.apify_tiktok_actor),
        "supabase_sync": s.has_supabase(),
    }

    if preflight_only:
        return out

    # Local DB stats
    try:
        from db.local_db import get_local_db
        db = get_local_db()
        out["stats"] = db.stats()

        clients = db.list_clients()
        out["clients"] = [
            {
                "name": c["name"],
                "slug": c["slug"],
                "branche": c.get("branche"),
                "ig_handle": c.get("ig_handle"),
                "reel_count": c.get("reel_count", 0),
            }
            for c in clients[:10]
        ]
        out["recent_reels"] = []
        recent = db.list_reels(limit=5)
        for r in recent:
            out["recent_reels"].append(
                {
                    "shortcode": r["shortcode"],
                    "account": r["account"],
                    "client": r.get("client_id"),
                    "hook_score": r.get("hook_score"),
                    "angle": r.get("angle"),
                }
            )
    except Exception as e:
        out["db_error"] = str(e)[:300]

    return out


def render_human(s: dict) -> str:
    lines = []
    lines.append("Content Intelligence Plugin — Status")
    lines.append(f"  User: {s['user']}")
    lines.append("")

    lines.append("Configuration:")
    lines.append(f"  Gemini + Apify:  {'READY' if s['config_ready'] else 'NOT CONFIGURED — run /ci-setup'}")
    lines.append(f"  TikTok actor:    {'CONFIGURED' if s['tiktok_configured'] else 'NOT CONFIGURED'}")
    lines.append(f"  Supabase sync:   {'CONFIGURED' if s['supabase_sync'] else 'not configured (optional, local-only)'}")
    lines.append("")

    if s.get("stats"):
        st = s["stats"]
        lines.append("Database (local SQLite):")
        lines.append(f"  Reels total:       {st.get('reels_total', 0)}")
        lines.append(f"  Reels last 7 days: {st.get('reels_7d', 0)}")
        lines.append(f"  Clients total:     {st.get('clients_total', 0)}")
        lines.append(f"  Scripts:           {st.get('scripts_total', 0)}")
        lines.append(f"  Tracked accounts:  {st.get('tracked_total', 0)}")
        lines.append(f"  Jobs queued:       {st.get('jobs_queued', 0)}")
        lines.append(f"  Jobs failed:       {st.get('jobs_failed', 0)}")
        lines.append(f"  DB size:           {st.get('db_size_mb', 0)} MB")
        lines.append("")

    if s.get("clients"):
        lines.append(f"Clients (top {len(s['clients'])} by recent activity):")
        for c in s["clients"]:
            branche = c.get("branche") or "-"
            handle = c.get("ig_handle") or "-"
            lines.append(f"  - {c['name']:<28} [{branche:<14}] {handle:<20} reels: {c['reel_count']}")
        lines.append("")

    if s.get("recent_reels"):
        lines.append("Recent reels:")
        for r in s["recent_reels"]:
            client = r.get("client") or "_unassigned"
            score = r.get("hook_score") or 0
            lines.append(f"  - @{r['account']:<20} {r['shortcode']:<14} {client:<20} hook:{score}/100 [{r.get('angle','?')}]")
        lines.append("")

    if s.get("db_error"):
        lines.append(f"DB ERROR: {s['db_error']}")

    if not s.get("clients"):
        lines.append("No clients yet. Start with: /ci-client-add <name>")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Content Intelligence Status")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Silent preflight (for SessionStart hook). Exit 0 if configured, 1 otherwise.",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    args = parser.parse_args()

    s = gather_status(preflight_only=args.preflight)

    if args.preflight:
        return 0 if s["config_ready"] else 1

    if args.json:
        print(json.dumps(s, indent=2, default=str))
        return 0

    print(render_human(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
