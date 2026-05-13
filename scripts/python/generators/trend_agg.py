"""Trend Aggregation — Statistical analysis over reels in DB.

Aggregates hook-type distribution, angle shifts, cut frequency trends,
emotion shifts, color trends, view distribution.
"""

from __future__ import annotations

import logging
import statistics
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from db.local_db import get_local_db

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TrendReport:
    period_days: int
    n_reels: int
    n_accounts: int
    branche: str | None = None
    client_id: str | None = None
    hook_distribution: dict[str, int] = field(default_factory=dict)
    angle_distribution: dict[str, int] = field(default_factory=dict)
    top_hooks_by_score: list[dict] = field(default_factory=list)
    top_themes: list[str] = field(default_factory=list)
    avg_cut_frequency: float = 0.0
    avg_hook_score: float = 0.0
    avg_retention: float = 0.0
    score_distribution: dict[str, int] = field(default_factory=dict)  # bins
    color_moods: dict[str, int] = field(default_factory=dict)


def aggregate(
    period_days: int = 30,
    branche: str | None = None,
    client_id: str | None = None,
) -> TrendReport:
    """Aggregate trends over reels matching filters."""
    db = get_local_db()
    cutoff = time.time() - (period_days * 24 * 3600)

    # Pull candidate reels — wide query, filter in Python for flexibility
    with db._conn() as c:
        sql = "SELECT * FROM reels WHERE deleted_at IS NULL AND analyzed_at > ?"
        params: list[Any] = [cutoff]
        if client_id:
            sql += " AND client_id = ?"
            params.append(client_id)
        rows = c.execute(sql, params).fetchall()

    reels = [db._reel_row_to_dict(r) for r in rows]

    # Branche-Filter (via clients table)
    if branche:
        client_slugs_in_branche = set()
        with db._conn() as c:
            for r in c.execute("SELECT slug FROM clients WHERE branche = ?", (branche,)):
                client_slugs_in_branche.add(r["slug"])
        reels = [r for r in reels if r.get("client_id") in client_slugs_in_branche]

    if not reels:
        return TrendReport(period_days=period_days, n_reels=0, n_accounts=0, branche=branche, client_id=client_id)

    n = len(reels)
    accounts = {r["account"] for r in reels}

    hook_dist = Counter(r.get("hook_type") for r in reels if r.get("hook_type"))
    angle_dist = Counter(r.get("angle") for r in reels if r.get("angle"))

    # Top hooks by score
    top_hooks = sorted(reels, key=lambda r: r.get("hook_score", 0), reverse=True)[:10]
    top_hooks_summary = [
        {
            "shortcode": r["shortcode"],
            "account": r["account"],
            "hook_type": r.get("hook_type"),
            "hook_text": r.get("hook_text") or f"(visual: {r.get('hook_visual', '?')[:60]})",
            "hook_score": r.get("hook_score"),
            "views": r.get("views"),
        }
        for r in top_hooks
    ]

    # Themes
    all_themes: list[str] = []
    for r in reels:
        for t in (r.get("content_themes") or []):
            all_themes.append(t)
    top_themes = [t for t, _ in Counter(all_themes).most_common(10)]

    # Aggregates
    cuts = [(r.get("visual_patterns") or {}).get("cut_frequency_per_10s", 0) for r in reels]
    cuts = [c for c in cuts if c is not None]
    avg_cuts = sum(cuts) / len(cuts) if cuts else 0.0

    scores = [r.get("hook_score") or 0 for r in reels]
    avg_score = sum(scores) / len(scores) if scores else 0.0

    retentions = [r.get("score_retention") or 0 for r in reels]
    avg_ret = sum(retentions) / len(retentions) if retentions else 0.0

    # Score bins
    bins = {"1-40": 0, "41-60": 0, "61-75": 0, "76-90": 0, "91-100": 0}
    for s in scores:
        if s <= 40:
            bins["1-40"] += 1
        elif s <= 60:
            bins["41-60"] += 1
        elif s <= 75:
            bins["61-75"] += 1
        elif s <= 90:
            bins["76-90"] += 1
        else:
            bins["91-100"] += 1

    # Color moods
    moods: Counter[str] = Counter()
    for r in reels:
        cp = r.get("color_palette") or {}
        m = cp.get("overall_mood")
        if m:
            moods[m] += 1

    return TrendReport(
        period_days=period_days,
        n_reels=n,
        n_accounts=len(accounts),
        branche=branche,
        client_id=client_id,
        hook_distribution=dict(hook_dist),
        angle_distribution=dict(angle_dist),
        top_hooks_by_score=top_hooks_summary,
        top_themes=top_themes,
        avg_cut_frequency=round(avg_cuts, 2),
        avg_hook_score=round(avg_score, 1),
        avg_retention=round(avg_ret, 1),
        score_distribution=bins,
        color_moods=dict(moods),
    )


def detect_viral(
    period_days: int = 30,
    branche: str | None = None,
    client_id: str | None = None,
    viral_threshold: float = 2.0,  # views/followers >= 2x average
) -> list[dict]:
    """Detect viral outliers — reels with views/followers ratio > Nx the median."""
    db = get_local_db()
    cutoff = time.time() - (period_days * 24 * 3600)

    with db._conn() as c:
        sql = """
            SELECT * FROM reels
            WHERE deleted_at IS NULL AND analyzed_at > ?
              AND views IS NOT NULL AND account_followers IS NOT NULL
              AND account_followers > 0
        """
        params: list[Any] = [cutoff]
        if client_id:
            sql += " AND client_id = ?"
            params.append(client_id)
        rows = c.execute(sql, params).fetchall()

    reels = [db._reel_row_to_dict(r) for r in rows]

    if branche:
        with db._conn() as c:
            slugs_in_branche = {r["slug"] for r in c.execute("SELECT slug FROM clients WHERE branche = ?", (branche,))}
        reels = [r for r in reels if r.get("client_id") in slugs_in_branche]

    if not reels:
        return []

    # Compute view-to-follower ratios
    ratios = []
    for r in reels:
        if r.get("account_followers", 0) > 0:
            ratios.append(r["views"] / r["account_followers"])
    if not ratios:
        return []

    # Use statistics.median — correct for both even and odd N
    median = statistics.median(ratios)
    if median <= 0:
        # Degenerate case: nothing to compare against, every reel would be "viral"
        logger.warning("viral.median_zero", extra={"n_ratios": len(ratios)})
        return []
    threshold_ratio = median * viral_threshold

    virals = []
    for r in reels:
        if r.get("account_followers", 0) <= 0:
            continue
        ratio = r["views"] / r["account_followers"]
        if ratio >= threshold_ratio:
            virals.append(
                {
                    "shortcode": r["shortcode"],
                    "account": r["account"],
                    "views": r["views"],
                    "account_followers": r["account_followers"],
                    "ratio": round(ratio, 2),
                    "median_ratio": round(median, 2),
                    "factor_above_median": round(ratio / median, 1),
                    "hook_type": r.get("hook_type"),
                    "hook_text": r.get("hook_text"),
                    "hook_score": r.get("hook_score"),
                    "angle": r.get("angle"),
                    "hook_reasoning": r.get("hook_reasoning"),
                }
            )

    virals.sort(key=lambda x: x["ratio"], reverse=True)
    return virals


def render_trend_report(t: TrendReport) -> str:
    """Render a TrendReport as Markdown."""
    if t.n_reels == 0:
        return f"No reels found for period={t.period_days}d, branche={t.branche}, client={t.client_id}"

    lines = []
    scope = []
    if t.client_id:
        scope.append(f"Client: {t.client_id}")
    if t.branche:
        scope.append(f"Branche: {t.branche}")
    scope_str = " · ".join(scope) if scope else "All clients"
    lines.append(f"# Trend-Report ({scope_str})")
    lines.append("")
    lines.append(f"**Period:** {t.period_days} days  |  **Reels:** {t.n_reels}  |  **Accounts:** {t.n_accounts}")
    lines.append("")
    lines.append(f"**Avg Hook-Score:** {t.avg_hook_score}/100")
    lines.append(f"**Avg Cut-Frequency:** {t.avg_cut_frequency} / 10s")
    lines.append(f"**Avg Retention-Prediction:** {t.avg_retention}%")
    lines.append("")

    lines.append("## Hook-Type Distribution")
    total_h = sum(t.hook_distribution.values()) or 1
    for ht, cnt in sorted(t.hook_distribution.items(), key=lambda x: x[1], reverse=True):
        pct = round(cnt / total_h * 100, 1)
        lines.append(f"  {ht:<22} {cnt:>3}  ({pct}%)")
    lines.append("")

    lines.append("## Angle Distribution")
    total_a = sum(t.angle_distribution.values()) or 1
    for ang, cnt in sorted(t.angle_distribution.items(), key=lambda x: x[1], reverse=True):
        pct = round(cnt / total_a * 100, 1)
        lines.append(f"  {ang:<22} {cnt:>3}  ({pct}%)")
    lines.append("")

    lines.append("## Score Distribution")
    for bin_label, cnt in t.score_distribution.items():
        pct = round(cnt / t.n_reels * 100, 1)
        bar = "#" * int(pct / 2)
        lines.append(f"  {bin_label:<8} {cnt:>3}  {bar} ({pct}%)")
    lines.append("")

    lines.append("## Top 10 Hooks (by score)")
    for r in t.top_hooks_by_score:
        ht = r.get("hook_text") or ""
        ht_short = ht[:80] if ht else "(visual)"
        lines.append(f"  - [{r.get('hook_score', 0):>3}/100] @{r['account']:<20} {r.get('hook_type', '?'):<22} {ht_short!r}")
    lines.append("")

    if t.top_themes:
        lines.append(f"## Top Themes")
        lines.append(", ".join(t.top_themes))
        lines.append("")

    if t.color_moods:
        lines.append("## Color Moods")
        for mood, cnt in t.color_moods.items():
            lines.append(f"  {mood:<16} {cnt}")

    return "\n".join(lines)
