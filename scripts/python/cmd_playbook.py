"""/ci-playbook — Generate and persist a content playbook for a client."""

from __future__ import annotations

import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import json

from config import get_settings
from db.local_db import get_local_db, make_slug


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate + persist a client content playbook")
    parser.add_argument("--client", required=True)
    parser.add_argument("--valid-days", type=int, default=30, help="Playbook valid for N days")
    parser.add_argument("--output", choices=["pretty", "json"], default="pretty")
    parser.add_argument("--dry-run", action="store_true", help="Don't save")
    args = parser.parse_args()

    db = get_local_db()
    s = get_settings()
    slug = make_slug(args.client)
    client = db.get_client_by_slug(slug) or db.get_client_by_name(args.client)
    if not client:
        print(f"[ci-playbook] Client not found: '{args.client}'", file=sys.stderr)
        return 1

    from generators.playbook_gen import generate_playbook, render_playbook
    data = generate_playbook(client["slug"])

    md = render_playbook(data)

    if not args.dry_run:
        valid_until = time.time() + (args.valid_days * 86400)
        pid = db.upsert_playbook(
            client_id=client["slug"],
            top_hooks=data["top_hooks_own"] + data["top_hooks_comp"][:5],
            top_angles=data["top_angles_own"] + data["top_angles_comp"][:3],
            posting_freq=data["posting_freq"],
            benchmark=data["benchmark"],
            empfehlungen=data["empfehlungen"],
            valid_until=valid_until,
            created_by=s.ci_user,
        )
    else:
        pid = "(not saved)"

    if args.output == "json":
        out = {
            "playbook_id": pid,
            "client": client["name"],
            "data": data,
            "markdown": md,
        }
        print(json.dumps(out, indent=2, default=str, ensure_ascii=False))
    else:
        print(md)
        print()
        print(f"---")
        print(f"Playbook ID: {pid}  (valid {args.valid_days}d)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
