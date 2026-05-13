"""Report Generator — Weekly/Monthly client reports."""

from __future__ import annotations

import logging
import time
from collections import Counter
from datetime import datetime, timezone

from db.local_db import get_local_db

logger = logging.getLogger(__name__)


def generate_report(
    client_slug: str,
    period_days: int = 7,
    include_script_suggestions: int = 3,
) -> dict:
    """Generate a weekly/monthly report for a client.

    Includes:
      - Eigene Performance over period
      - Competitor moves (new content)
      - Trend highlights
      - Top reel suggestions (script ideas based on viral patterns)
    """
    db = get_local_db()
    client = db.get_client_by_slug(client_slug)
    if not client:
        raise ValueError(f"Client not found: {client_slug}")

    cutoff = time.time() - (period_days * 86400)

    with db._conn() as c:
        own_rows = c.execute(
            "SELECT * FROM reels WHERE deleted_at IS NULL AND client_id = ? AND is_own = 1 AND analyzed_at > ?",
            (client_slug, cutoff),
        ).fetchall()
        comp_rows = c.execute(
            "SELECT * FROM reels WHERE deleted_at IS NULL AND client_id = ? AND is_own = 0 AND analyzed_at > ?",
            (client_slug, cutoff),
        ).fetchall()

    own = [db._reel_row_to_dict(r) for r in own_rows]
    comp = [db._reel_row_to_dict(r) for r in comp_rows]

    def stats(reels: list[dict]) -> dict:
        if not reels:
            return {"n": 0}
        scores = [r.get("hook_score") or 0 for r in reels]
        views = [r.get("views") or 0 for r in reels]
        return {
            "n": len(reels),
            "avg_hook_score": round(sum(scores) / len(scores), 1),
            "avg_views": round(sum(views) / len(views), 0),
            "max_views": max(views),
            "top_hook_types": [
                t for t, _ in Counter(r.get("hook_type") for r in reels).most_common(3)
            ],
        }

    own_s = stats(own)
    comp_s = stats(comp)

    # Best competitor reels of the period
    comp_top = sorted(comp, key=lambda r: r.get("hook_score") or 0, reverse=True)[:5]

    # Recently generated scripts for this client
    recent_scripts = db.list_scripts(client_id=client_slug, limit=5)

    return {
        "client": client,
        "period_days": period_days,
        "period_label": "weekly" if period_days == 7 else ("monthly" if period_days == 30 else f"{period_days}d"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "own_stats": own_s,
        "competitor_stats": comp_s,
        "top_competitor_reels": comp_top,
        "recent_scripts": recent_scripts,
    }


def render_report(data: dict) -> str:
    c = data["client"]
    p = data["period_label"]
    lines = []
    lines.append(f"# {p.capitalize()} Report: {c['name']}")
    lines.append(f"_Generated: {data['generated_at']}_")
    lines.append("")

    own = data["own_stats"]
    comp = data["competitor_stats"]

    lines.append(f"## Our Performance ({p})")
    if own["n"] == 0:
        lines.append("  No own reels analyzed in this period.")
    else:
        lines.append(f"  Reels analyzed:  {own['n']}")
        lines.append(f"  Avg Hook-Score:  {own['avg_hook_score']}/100")
        lines.append(f"  Avg Views:       {int(own['avg_views']):,}")
        lines.append(f"  Top Views:       {own['max_views']:,}")
        lines.append(f"  Top Hook-Types:  {', '.join(own.get('top_hook_types', []))}")
    lines.append("")

    lines.append(f"## Competitor Activity ({p})")
    if comp["n"] == 0:
        lines.append("  No competitor reels analyzed. Run /ci-batch on competitor accounts.")
    else:
        lines.append(f"  Competitor reels: {comp['n']}")
        lines.append(f"  Avg Hook-Score:  {comp['avg_hook_score']}/100")
        lines.append(f"  Top Hook-Types:  {', '.join(comp.get('top_hook_types', []))}")
    lines.append("")

    if data["top_competitor_reels"]:
        lines.append(f"## Top Competitor Reels (this {p})")
        for r in data["top_competitor_reels"]:
            score = r.get("hook_score") or 0
            ht = r.get("hook_text") or "(visual)"
            views = r.get("views") or 0
            lines.append(f"  - [{score:>3}/100] @{r['account']:<22} views: {views:,}")
            lines.append(f"           {ht!r}")
        lines.append("")

    if data["recent_scripts"]:
        lines.append(f"## Generated Scripts (drafts)")
        for s in data["recent_scripts"][:5]:
            lines.append(f"  - {s.get('thema', '?'):<40} [{s.get('status', '?')}] Score-Pred: {s.get('score_prediction', '?')}")
        lines.append("")

    # Action items
    lines.append("## Action Items")
    if comp["n"] > 0 and own["n"] > 0:
        if comp["avg_hook_score"] - own["avg_hook_score"] > 5:
            lines.append(f"  - Competitors out-hooking us by {comp['avg_hook_score'] - own['avg_hook_score']} pts. "
                         f"Run /ci-script to generate stronger hooks.")
    if own["n"] < 2 and data["period_days"] <= 7:
        lines.append("  - Posting frequency low this week. Algorithmus belohnt 3-5x/week.")
    if comp.get("top_hook_types") and own.get("top_hook_types"):
        missing = set(comp["top_hook_types"]) - set(own["top_hook_types"])
        if missing:
            lines.append(f"  - Untested hook-types vs competitors: {', '.join(missing)}. Run A/B with /ci-script-batch.")

    return "\n".join(lines)
