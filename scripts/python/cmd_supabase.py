"""/ci-supabase — Optional Supabase sync admin commands.

Sub-commands:
  test           — verify connection
  migrate        — apply migration-001-init.sql
  status         — show table counts
  push           — sync local SQLite → Supabase (Phase 6+)
"""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import asyncio
import json

from config import get_settings


def get_migration_sql() -> str:
    sql_path = Path(__file__).resolve().parent / "db" / "migration-001-init.sql"
    return sql_path.read_text(encoding="utf-8")


async def cmd_test(args: argparse.Namespace) -> int:
    s = get_settings()
    if not s.has_supabase():
        print("[ci-supabase] SUPABASE_URL/SUPABASE_DB_URL missing in .env", file=sys.stderr)
        return 1

    try:
        from clients.supabase import SupabaseDB
        db = SupabaseDB()
        await db.connect()
        ok = await db.ping()
        await db.close()
        print(f"[ci-supabase] Connection: {'OK' if ok else 'FAILED'}")
        return 0 if ok else 1
    except Exception as e:
        print(f"[ci-supabase] FAIL: {str(e)[:400]}", file=sys.stderr)
        return 1


async def cmd_migrate(args: argparse.Namespace) -> int:
    s = get_settings()
    if not s.has_supabase():
        print("[ci-supabase] SUPABASE_DB_URL missing", file=sys.stderr)
        return 1

    try:
        from clients.supabase import SupabaseDB
        db = SupabaseDB()
        await db.connect()
        sql = get_migration_sql()
        async with db.acquire() as conn:
            await conn.execute(sql)
        await db.close()
        print("[ci-supabase] Migration applied successfully")
        return 0
    except Exception as e:
        print(f"[ci-supabase] Migration FAILED: {str(e)[:600]}", file=sys.stderr)
        return 1


async def cmd_status(args: argparse.Namespace) -> int:
    import re
    s = get_settings()
    if not s.has_supabase():
        print("[ci-supabase] Not configured")
        return 1

    # Whitelist of known plugin tables — prevents SQL injection via unexpected
    # table names in information_schema (defense-in-depth, low actual risk).
    _IDENT_RX = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

    try:
        from clients.supabase import SupabaseDB
        db = SupabaseDB()
        await db.connect()
        async with db.acquire() as conn:
            tables = await conn.fetch(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            )
            counts = {}
            for r in tables:
                tn = r["table_name"]
                if tn.startswith("pg_") or tn.startswith("schema_"):
                    continue
                if not _IDENT_RX.match(tn):
                    counts[tn] = "(invalid name)"
                    continue
                try:
                    # Safe: tn matched strict ident regex
                    c = await conn.fetchval(f'SELECT COUNT(*) FROM "{tn}"')
                    counts[tn] = c
                except Exception:
                    counts[tn] = "?"
        await db.close()
        if args.output == "json":
            print(json.dumps(counts, indent=2))
        else:
            print("Supabase tables:")
            for t, n in counts.items():
                print(f"  {t:<22} {n}")
        return 0
    except Exception as e:
        print(f"[ci-supabase] status FAILED: {str(e)[:400]}", file=sys.stderr)
        return 1


async def cmd_print_migration(args: argparse.Namespace) -> int:
    print(get_migration_sql())
    return 0


async def amain() -> int:
    parser = argparse.ArgumentParser(description="Supabase admin")
    sub = parser.add_subparsers(dest="action", required=True)

    pt = sub.add_parser("test")
    pt.set_defaults(func=cmd_test)

    pm = sub.add_parser("migrate")
    pm.set_defaults(func=cmd_migrate)

    ps = sub.add_parser("status")
    ps.add_argument("--output", choices=["pretty", "json"], default="pretty")
    ps.set_defaults(func=cmd_status)

    pp = sub.add_parser("print-migration")
    pp.set_defaults(func=cmd_print_migration)

    args = parser.parse_args()
    return await args.func(args)


def main() -> int:
    return asyncio.run(amain())


if __name__ == "__main__":
    sys.exit(main())
