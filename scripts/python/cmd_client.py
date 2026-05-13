"""/ci-client-add, /ci-client-list, /ci-client-update — Client management."""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import json

from config import get_settings
from db.local_db import get_local_db, make_slug


def cmd_add(args: argparse.Namespace) -> int:
    """Create a new client profile."""
    db = get_local_db()
    s = get_settings()

    name = args.name.strip()
    if not name:
        print("[ci-client-add] error: name is empty", file=sys.stderr)
        return 1

    slug = make_slug(name)

    # Check duplicate exact match
    existing = db.get_client_by_slug(slug)
    if existing and not args.force:
        print(f"[ci-client-add] Client already exists: '{existing['name']}' (slug={slug})")
        if args.json:
            print(json.dumps({"status": "exists", "client": existing}, default=str))
        return 0

    # Check fuzzy match (to catch typos)
    if not args.force:
        similar = db.find_similar_clients(name, threshold=0.6)
        # Filter out exact slug match (already handled)
        similar = [s for s in similar if s["slug"] != slug]
        if similar:
            print(f"[ci-client-add] Warning: similar clients found:")
            for s_match in similar:
                print(f"  - {s_match['name']:<30} (similarity: {s_match['_similarity']:.2f})")
            if not args.yes:
                print()
                print("If you meant one of those, use that name instead.")
                print("To create anyway, re-run with --yes or --force.")
                if args.json:
                    print(json.dumps({"status": "similar", "similar": similar}, default=str))
                return 2

    competitors = args.competitor or []

    client = db.upsert_client(
        name=name,
        slug=slug,
        branche=args.branche,
        zielgruppe=args.zielgruppe,
        tonalitaet=args.tonalitaet,
        ig_handle=args.ig_handle.lstrip("@") if args.ig_handle else None,
        competitor_handles=[c.lstrip("@") for c in competitors],
        notes=args.notes,
        created_by=s.ci_user,
    )

    if args.json:
        print(json.dumps({"status": "created", "client": client}, default=str))
    else:
        print(f"[ci-client-add] Created client: {client['name']}")
        print(f"  Slug: {client['slug']}")
        if client.get("branche"):
            print(f"  Branche: {client['branche']}")
        if client.get("ig_handle"):
            print(f"  IG: @{client['ig_handle']}")
        if client.get("competitor_handles"):
            print(f"  Competitors: {', '.join('@' + h for h in client['competitor_handles'])}")
        print()
        print(f"Next: /ci-analyze <url> --client \"{client['name']}\"")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List all clients."""
    db = get_local_db()
    clients = db.list_clients()

    if args.json:
        print(json.dumps(clients, indent=2, default=str))
        return 0

    if not clients:
        print("No clients yet. Create one with: /ci-client-add <name>")
        return 0

    print(f"Clients ({len(clients)}):")
    print()
    print(f"  {'Name':<30} {'Branche':<18} {'IG-Handle':<22} {'Reels':>6}")
    print(f"  {'-' * 30} {'-' * 18} {'-' * 22} {'-' * 6}")
    for c in clients:
        branche = c.get("branche") or "-"
        handle = ("@" + c["ig_handle"]) if c.get("ig_handle") else "-"
        reel_count = c.get("reel_count", 0)
        print(f"  {c['name']:<30} {branche:<18} {handle:<22} {reel_count:>6}")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    """Update an existing client."""
    db = get_local_db()
    s = get_settings()

    # Find client by name or slug
    slug = make_slug(args.name)
    client = db.get_client_by_slug(slug)
    if not client:
        client = db.get_client_by_name(args.name)
    if not client:
        print(f"[ci-client-update] Client not found: '{args.name}'")
        # Suggest fuzzy matches
        similar = db.find_similar_clients(args.name, threshold=0.5)
        if similar:
            print("Did you mean:")
            for s_match in similar:
                print(f"  - {s_match['name']}")
        return 1

    competitors = args.competitor if args.competitor is not None else None
    if competitors:
        competitors = [c.lstrip("@") for c in competitors]

    updated = db.upsert_client(
        name=client["name"],  # keep original name (use slug as identity)
        slug=client["slug"],
        branche=args.branche,
        zielgruppe=args.zielgruppe,
        tonalitaet=args.tonalitaet,
        ig_handle=args.ig_handle.lstrip("@") if args.ig_handle else None,
        competitor_handles=competitors,
        notes=args.notes,
        created_by=s.ci_user,
    )

    if args.json:
        print(json.dumps({"status": "updated", "client": updated}, default=str))
    else:
        print(f"[ci-client-update] Updated: {updated['name']}")
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    """Delete a client (and cascade delete scripts/playbooks/tracked_accounts)."""
    db = get_local_db()
    slug = make_slug(args.name)
    client = db.get_client_by_slug(slug) or db.get_client_by_name(args.name)
    if not client:
        print(f"[ci-client-delete] Client not found: '{args.name}'")
        return 1
    if not args.yes:
        print(f"This will delete '{client['name']}' and all associated scripts/playbooks/tracked_accounts.")
        print("Re-run with --yes to confirm.")
        return 2
    ok = db.delete_client(client["slug"])
    print(f"[ci-client-delete] {'Deleted' if ok else 'Failed to delete'}: {client['name']}")
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Content Intelligence — Client Management")
    sub = parser.add_subparsers(dest="action", required=True)

    # add
    p_add = sub.add_parser("add", help="Add a new client")
    p_add.add_argument("name", help="Client name (e.g. 'CS Abbruch')")
    p_add.add_argument("--branche", help="Branche / industry")
    p_add.add_argument("--zielgruppe", help="Zielgruppe / target audience")
    p_add.add_argument("--tonalitaet", help="Tonalitaet (du/locker, Sie/formal, etc.)")
    p_add.add_argument("--ig-handle", help="Instagram handle (without @)")
    p_add.add_argument("--competitor", action="append", help="Competitor IG handle (can repeat)")
    p_add.add_argument("--notes", help="Free-form notes")
    p_add.add_argument("--yes", action="store_true", help="Skip fuzzy-duplicate warning")
    p_add.add_argument("--force", action="store_true", help="Force create even if duplicates exist")
    p_add.add_argument("--json", action="store_true")
    p_add.set_defaults(func=cmd_add)

    # list
    p_list = sub.add_parser("list", help="List all clients")
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=cmd_list)

    # update
    p_upd = sub.add_parser("update", help="Update an existing client")
    p_upd.add_argument("name", help="Client name or slug")
    p_upd.add_argument("--branche")
    p_upd.add_argument("--zielgruppe")
    p_upd.add_argument("--tonalitaet")
    p_upd.add_argument("--ig-handle")
    p_upd.add_argument("--competitor", action="append")
    p_upd.add_argument("--notes")
    p_upd.add_argument("--json", action="store_true")
    p_upd.set_defaults(func=cmd_update)

    # delete
    p_del = sub.add_parser("delete", help="Delete a client")
    p_del.add_argument("name")
    p_del.add_argument("--yes", action="store_true")
    p_del.set_defaults(func=cmd_delete)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
