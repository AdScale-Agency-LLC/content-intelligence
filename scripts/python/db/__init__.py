"""Local DB layer (SQLite — primary store)."""

from db.local_db import LocalDB, get_local_db, make_slug
from db.vector_search import SearchResult, search

__all__ = ["LocalDB", "get_local_db", "make_slug", "SearchResult", "search"]
