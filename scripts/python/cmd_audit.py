"""/ci-audit — Content audit for a single client."""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import json

from db.local_db import get_local_db, make_slug


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a client's content vs. competitors")
    parser.add_argument("--client", required=True)
    parser.add_argument("--output", choices=["pretty", "json"], default="pretty")
    args = parser.parse_args()

    db = get_local_db()
    slug = make_slug(args.client)
    client = db.get_client_by_slug(slug) or db.get_client_by_name(args.client)
    if not client:
        print(f"[ci-audit] Client not found: '{args.client}'", file=sys.stderr)
        return 1

    from generators.playbook_gen import generate_playbook, render_playbook
    data = generate_playbook(client["slug"])

    if args.output == "json":
        print(json.dumps(data, indent=2, default=str, ensure_ascii=False))
        return 0

    print(render_playbook(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
