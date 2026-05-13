"""Playbook Generator — Per-client content strategy distillation.

Takes a client's analyzed reels + competitor reels, computes:
  - Top hook types (with avg scores)
  - Top angles
  - Optimal posting frequency (from posted_at timeline)
  - Benchmark scores (avg hook/retention/cta vs. competitors)
  - Concrete recommendations
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from typing import Any

from db.local_db import get_local_db

logger = logging.getLogger(__name__)


def generate_playbook(client_slug: str) -> dict:
    """Generate a fresh playbook for a client. Returns dict ready for DB insert + render."""
    db = get_local_db()
    client = db.get_client_by_slug(client_slug)
    if not client:
        raise ValueError(f"Client not found: {client_slug}")

    own = db.list_reels(client_id=client_slug, is_own=True, limit=200)
    comp = db.list_reels(client_id=client_slug, is_own=False, limit=200)

    # Top hooks (by score) — group by type, avg score
    def hook_stats(reels: list[dict]) -> list[dict]:
        by_type: dict[str, list[int]] = {}
        for r in reels:
            ht = r.get("hook_type")
            sc = r.get("hook_score") or 0
            if ht:
                by_type.setdefault(ht, []).append(sc)
        out = []
        for ht, scores in by_type.items():
            out.append({
                "hook_type": ht,
                "avg_score": round(sum(scores) / len(scores), 1),
                "count": len(scores),
                "max_score": max(scores),
            })
        out.sort(key=lambda x: (x["avg_score"], x["count"]), reverse=True)
        return out

    top_hooks_own = hook_stats(own)
    top_hooks_comp = hook_stats(comp)

    # Top angles
    def angle_stats(reels: list[dict]) -> list[dict]:
        by_type: dict[str, list[int]] = {}
        for r in reels:
            a = r.get("angle")
            sc = r.get("hook_score") or 0
            if a:
                by_type.setdefault(a, []).append(sc)
        return sorted(
            [
                {"angle": a, "avg_score": round(sum(s) / len(s), 1), "count": len(s)}
                for a, s in by_type.items()
            ],
            key=lambda x: (x["avg_score"], x["count"]),
            reverse=True,
        )

    top_angles_own = angle_stats(own)
    top_angles_comp = angle_stats(comp)

    # Posting frequency (analyze posted_at gaps for own reels)
    posting_freq = "unknown"
    if len(own) >= 3:
        from datetime import datetime
        timestamps = []
        for r in own:
            pa = r.get("posted_at")
            if pa:
                try:
                    if isinstance(pa, str):
                        # try ISO
                        ts = datetime.fromisoformat(pa.replace("Z", "+00:00")).timestamp()
                    else:
                        ts = float(pa)
                    timestamps.append(ts)
                except (ValueError, TypeError):
                    continue
        if len(timestamps) >= 2:
            timestamps.sort()
            gaps = [(timestamps[i + 1] - timestamps[i]) / 86400 for i in range(len(timestamps) - 1)]
            avg_gap_days = sum(gaps) / len(gaps)
            if avg_gap_days < 1.5:
                posting_freq = "daily"
            elif avg_gap_days < 3.5:
                posting_freq = "2-3x per week"
            elif avg_gap_days < 8:
                posting_freq = "weekly"
            else:
                posting_freq = "sporadic (every 1-2 weeks+)"

    # Benchmark
    def avg(arr: list[int]) -> float:
        arr = [a for a in arr if a is not None]
        return round(sum(arr) / len(arr), 1) if arr else 0.0

    benchmark = {
        "own": {
            "n_reels": len(own),
            "avg_hook": avg([r.get("hook_score") for r in own]),
            "avg_retention": avg([r.get("score_retention") for r in own]),
            "avg_cta": avg([r.get("score_cta") for r in own]),
            "avg_visual": avg([r.get("score_visual") for r in own]),
        },
        "competitors": {
            "n_reels": len(comp),
            "avg_hook": avg([r.get("hook_score") for r in comp]),
            "avg_retention": avg([r.get("score_retention") for r in comp]),
            "avg_cta": avg([r.get("score_cta") for r in comp]),
            "avg_visual": avg([r.get("score_visual") for r in comp]),
        },
    }

    # Recommendations — gap analysis
    empfehlungen: list[str] = []
    own_b = benchmark["own"]
    comp_b = benchmark["competitors"]
    if comp_b["n_reels"] > 0 and own_b["n_reels"] > 0:
        if own_b["avg_hook"] < comp_b["avg_hook"] - 5:
            empfehlungen.append(
                f"Hook-Staerke schwach: {own_b['avg_hook']}/100 vs. Competitors {comp_b['avg_hook']}/100. "
                f"Top-Competitor-Hook-Types nutzen: {[h['hook_type'] for h in top_hooks_comp[:2]]}"
            )
        if own_b["avg_cta"] < comp_b["avg_cta"] - 5:
            empfehlungen.append(
                f"CTA-Klarheit schwach: {own_b['avg_cta']}/100 vs. Competitors {comp_b['avg_cta']}/100. "
                "Konkrete CTAs einbauen (z.B. 'Kommentier X', 'Link in Bio fuer Y')"
            )
        if own_b["avg_visual"] < comp_b["avg_visual"] - 5:
            empfehlungen.append(
                f"Visual-Quality schwach: {own_b['avg_visual']}/100 vs. Competitors {comp_b['avg_visual']}/100. "
                "Production-Setup verbessern (Lighting, Stabilizer, Audio)."
            )

    # Underutilized hook types
    own_types = {h["hook_type"] for h in top_hooks_own}
    comp_types = {h["hook_type"] for h in top_hooks_comp[:3]}
    missing = comp_types - own_types
    if missing:
        empfehlungen.append(
            f"Hook-Types die Competitors nutzen aber wir nicht: {', '.join(missing)}. "
            "Testen mit 2-3 Reels."
        )

    if posting_freq in ("weekly", "sporadic (every 1-2 weeks+)"):
        empfehlungen.append(
            f"Posting-Frequenz {posting_freq} ist niedrig. Algorithmus belohnt 3-5x/Woche. "
            "Content-Batch-Production planen."
        )

    if not empfehlungen:
        empfehlungen.append("Performance ist on-par mit Competitors. Continue testing variations.")

    return {
        "client": client,
        "top_hooks_own": top_hooks_own,
        "top_hooks_comp": top_hooks_comp,
        "top_angles_own": top_angles_own,
        "top_angles_comp": top_angles_comp,
        "posting_freq": posting_freq,
        "benchmark": benchmark,
        "empfehlungen": empfehlungen,
    }


def render_playbook(data: dict) -> str:
    """Render playbook as Markdown."""
    c = data["client"]
    b = data["benchmark"]
    lines = []
    lines.append(f"# Content-Playbook: {c['name']}")
    if c.get("branche"):
        lines.append(f"Branche: {c['branche']}")
    if c.get("zielgruppe"):
        lines.append(f"Zielgruppe: {c['zielgruppe']}")
    lines.append("")

    lines.append("## Datenbasis")
    lines.append(f"  Eigene Reels:       {b['own']['n_reels']}")
    lines.append(f"  Competitor Reels:   {b['competitors']['n_reels']}")
    lines.append("")

    lines.append("## Performance Benchmark")
    lines.append(f"  {'Metric':<22} {'Uns':>10} {'Competitors':>14} {'Gap':>10}")
    lines.append(f"  {'-' * 22} {'-' * 10} {'-' * 14} {'-' * 10}")
    for key, label in [("avg_hook", "Hook-Score"), ("avg_retention", "Retention"), ("avg_cta", "CTA"), ("avg_visual", "Visual-Quality")]:
        own_v = b["own"].get(key, 0)
        comp_v = b["competitors"].get(key, 0)
        gap = round(own_v - comp_v, 1)
        gap_str = f"{'+' if gap >= 0 else ''}{gap}"
        lines.append(f"  {label:<22} {own_v:>10} {comp_v:>14} {gap_str:>10}")
    lines.append("")

    if data["top_hooks_own"]:
        lines.append("## Unsere Top Hook-Types")
        for h in data["top_hooks_own"][:5]:
            lines.append(f"  - {h['hook_type']:<22} avg {h['avg_score']}/100  ({h['count']} reels)")
        lines.append("")

    if data["top_hooks_comp"]:
        lines.append("## Competitor Top Hook-Types")
        for h in data["top_hooks_comp"][:5]:
            lines.append(f"  - {h['hook_type']:<22} avg {h['avg_score']}/100  ({h['count']} reels)")
        lines.append("")

    if data["top_angles_own"]:
        lines.append("## Unsere Top Angles")
        for a in data["top_angles_own"][:3]:
            lines.append(f"  - {a['angle']:<22} avg {a['avg_score']}/100  ({a['count']} reels)")
        lines.append("")

    lines.append(f"## Posting-Frequenz")
    lines.append(f"  Aktuell: {data['posting_freq']}")
    lines.append("")

    lines.append("## Empfehlungen")
    for i, emp in enumerate(data["empfehlungen"], 1):
        lines.append(f"{i}. {emp}")

    return "\n".join(lines)
