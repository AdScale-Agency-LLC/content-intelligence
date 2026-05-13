"""/ci-batch — Analyze multiple reels from an account or URL list.

Use cases:
  /ci-batch @account --last 20 --client "X" [--is-own]
  /ci-batch --urls url1,url2,url3 --client "X"
"""

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
    logging.basicConfig(level=level, format="[%(asctime)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")


def resolve_or_create_client(client_arg: str) -> str:
    """Resolve or auto-create client. Returns slug."""
    db = get_local_db()
    s = get_settings()
    slug = make_slug(client_arg)
    c = db.get_client_by_slug(slug) or db.get_client_by_name(client_arg)
    if c:
        return c["slug"]
    new = db.upsert_client(name=client_arg, slug=slug, created_by=s.ci_user)
    print(f"[ci-batch] Auto-created client: '{new['name']}'", file=sys.stderr)
    return new["slug"]


def build_client_context(slug: str | None) -> str | None:
    if not slug:
        return None
    db = get_local_db()
    c = db.get_client_by_slug(slug)
    if not c:
        return None
    parts = [f"Klient: {c['name']}"]
    if c.get("branche"):
        parts.append(f"Branche: {c['branche']}")
    if c.get("zielgruppe"):
        parts.append(f"Zielgruppe: {c['zielgruppe']}")
    return ". ".join(parts)


async def analyze_one(pipeline, url: str, client_id: str | None, is_own: bool, client_context: str | None) -> tuple[str, dict]:
    """Run pipeline for one URL. Returns (status, info_dict)."""
    try:
        result = await pipeline.process_url(
            url, client_id=client_id, is_own=is_own, client_context=client_context
        )
        return "ok", {
            "url": url,
            "shortcode": result.shortcode,
            "account": result.account,
            "hook_score": result.analysis.hook.strength_score,
            "angle": result.analysis.angle.value,
            "hook_type": result.analysis.hook.type.value,
        }
    except Exception as e:
        return "fail", {"url": url, "error": str(e)[:200]}


async def amain() -> int:
    parser = argparse.ArgumentParser(description="Batch-analyze multiple reels")
    parser.add_argument("source", nargs="?", help="@username (IG account) or empty if using --urls")
    parser.add_argument("--urls", help="Comma-separated list of reel URLs")
    parser.add_argument("--last", type=int, default=20, help="When @account: analyze last N reels (default 20)")
    parser.add_argument("--client", help="Client name (auto-create if new)")
    parser.add_argument("--is-own", action="store_true", help="Mark all as own content")
    parser.add_argument("--concurrency", type=int, default=3, help="Parallel analyses (default 3, max 5)")
    parser.add_argument("--output", choices=["pretty", "json"], default="pretty")
    parser.add_argument("--log-level", default="WARNING")
    parser.add_argument("--skip-existing", action="store_true", default=True, help="Skip reels already in DB")
    args = parser.parse_args()

    setup_logging(args.log_level)

    s = get_settings()
    if not (s.has_gemini() and s.has_apify()):
        print("[ci-batch] Missing required keys (Gemini + Apify). "
              "Run /ci-setup --interactive to configure.", file=sys.stderr)
        return 3

    db = get_local_db()
    client_slug = resolve_or_create_client(args.client) if args.client else None
    client_context = build_client_context(client_slug)

    # Build URL list
    urls: list[str] = []
    if args.urls:
        urls = [u.strip() for u in args.urls.split(",") if u.strip()]
    elif args.source:
        # Source is @username → scrape account top N
        from clients.apify import ApifyClient
        handle = args.source.lstrip("@")
        print(f"[ci-batch] Scraping @{handle} (last {args.last} reels)...", file=sys.stderr)
        apify = ApifyClient()
        reels = await apify.scrape_account_top(handle, limit=args.last)
        print(f"[ci-batch] Found {len(reels)} reels from @{handle}", file=sys.stderr)
        # Construct IG URLs
        urls = [f"https://www.instagram.com/reel/{r.shortcode}/" for r in reels]
    else:
        print("[ci-batch] Need either @username or --urls", file=sys.stderr)
        return 1

    if not urls:
        print("[ci-batch] No URLs to process", file=sys.stderr)
        return 1

    # Skip already-analyzed (idempotent) — batched lookup, 1 query instead of N
    from pipeline.scraper import extract_shortcode
    if args.skip_existing:
        # Build (url, shortcode) pairs; preserve order, skip un-parseable URLs
        url_pairs: list[tuple[str, str]] = []
        for url in urls:
            try:
                url_pairs.append((url, extract_shortcode(url)))
            except Exception:
                # Invalid URL — let downstream pipeline raise a clean error
                url_pairs.append((url, ""))

        shortcodes = [sc for _, sc in url_pairs if sc]
        existing_map: dict[str, dict] = {}
        if shortcodes:
            placeholders = ",".join("?" * len(shortcodes))
            with db._conn() as c:
                rows = c.execute(
                    f"SELECT shortcode, client_id FROM reels "
                    f"WHERE deleted_at IS NULL AND shortcode IN ({placeholders})",
                    shortcodes,
                ).fetchall()
                existing_map = {r["shortcode"]: dict(r) for r in rows}

                # Batched UPDATE for any existing-but-unlinked reels
                if client_slug:
                    relink = [
                        sc for sc in shortcodes
                        if sc in existing_map and not existing_map[sc].get("client_id")
                    ]
                    if relink:
                        c.executemany(
                            "UPDATE reels SET client_id = ?, is_own = ? WHERE shortcode = ?",
                            [(client_slug, 1 if args.is_own else 0, sc) for sc in relink],
                        )

        to_process = [url for url, sc in url_pairs if not (sc and sc in existing_map)]
        skipped = len(urls) - len(to_process)
        urls = to_process
        if skipped:
            print(f"[ci-batch] Skipped {skipped} reels already in DB", file=sys.stderr)

    if not urls:
        print("[ci-batch] All reels already analyzed", file=sys.stderr)
        return 0

    print(f"[ci-batch] Processing {len(urls)} reels with concurrency={min(args.concurrency, 5)}", file=sys.stderr)

    # Build pipeline once
    from pipeline.orchestrator import build_pipeline
    pipeline = build_pipeline()

    # Parallel with bounded concurrency
    sem = asyncio.Semaphore(min(args.concurrency, 5))
    async def bounded(url: str):
        async with sem:
            print(f"[ci-batch] >>> {url}", file=sys.stderr)
            return await analyze_one(pipeline, url, client_slug, args.is_own, client_context)

    start = time.time()
    # return_exceptions=True ensures one crashing task doesn't cancel the rest
    raw_results = await asyncio.gather(*[bounded(u) for u in urls], return_exceptions=True)
    results = []
    for r in raw_results:
        if isinstance(r, BaseException):
            results.append(("fail", {"url": "?", "error": f"unhandled: {str(r)[:200]}"}))
        else:
            results.append(r)
    elapsed = time.time() - start

    ok = [r for r in results if r[0] == "ok"]
    failed = [r for r in results if r[0] == "fail"]

    db.log_invocation(
        "ci-batch",
        args={"source": args.source, "count": len(urls), "client": args.client},
        status="ok" if not failed else "partial",
        duration_ms=int(elapsed * 1000),
    )

    if args.output == "json":
        out = {
            "total": len(urls),
            "ok": len(ok),
            "failed": len(failed),
            "elapsed_s": round(elapsed, 1),
            "results": [r[1] for r in results],
        }
        print(json.dumps(out, indent=2, default=str))
    else:
        print()
        print(f"[ci-batch] Completed in {elapsed:.1f}s — {len(ok)} ok, {len(failed)} failed")
        print()
        if ok:
            print("Successful analyses:")
            print(f"  {'Account':<20} {'Shortcode':<14} {'Hook':<22} {'Score':>5} {'Angle':<20}")
            print(f"  {'-' * 20} {'-' * 14} {'-' * 22} {'-' * 5} {'-' * 20}")
            for _, info in ok:
                print(
                    f"  @{info['account']:<19} {info['shortcode']:<14} "
                    f"{info.get('hook_type', '?'):<22} {info.get('hook_score', 0):>5} "
                    f"{info.get('angle', '?'):<20}"
                )
        if failed:
            print()
            print("Failed:")
            for _, info in failed:
                print(f"  - {info['url']}: {info['error']}")

    return 0 if not failed else (0 if ok else 1)


def main() -> int:
    return asyncio.run(amain())


if __name__ == "__main__":
    sys.exit(main())
