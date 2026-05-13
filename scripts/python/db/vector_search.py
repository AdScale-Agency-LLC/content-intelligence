"""Brute-force vector search over SQLite-stored embeddings.

Pure numpy implementation — fast enough for <10k reels (<200ms typical).
At 50k+ reels: still works, just slower (~500-800ms). At that scale,
migrate to Supabase pgvector via the optional sync layer.

Algorithm:
  1. Load all candidate (id, shortcode, meta, embedding) tuples from SQLite
  2. Compute cosine similarity in one numpy matmul
  3. argpartition for top-K (faster than sort for K << N)
  4. Apply min_score filter + return results
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import numpy as np

from db.local_db import get_local_db

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SearchResult:
    shortcode: str
    similarity: float
    account: str
    hook_text: str | None
    summary: str
    views: int | None
    posted_at: str | None
    client_id: str | None
    hook_type: str | None
    hook_score: int | None
    angle: str | None


def _l2_normalize(mat: np.ndarray) -> np.ndarray:
    """Row-normalize a 2D matrix. Zero-rows stay zero."""
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


def search(
    query_embedding: list[float],
    column: Literal["hook_emb", "transcript_emb", "summary_emb"] = "summary_emb",
    top_k: int = 10,
    min_score: float | None = None,
    client_id: str | None = None,
    filter_hook_type: str | None = None,
    filter_angle: str | None = None,
    filter_min_hook_score: int | None = None,
    filter_min_views: int | None = None,
) -> list[SearchResult]:
    """Cosine-similarity search across reels with embedding in `column`."""
    db = get_local_db()
    q = np.array(query_embedding, dtype=np.float32)
    q_norm = np.linalg.norm(q)
    if q_norm == 0:
        return []
    q = q / q_norm

    ids: list[str] = []
    metas: list[dict] = []
    vecs: list[np.ndarray] = []

    for _rid, shortcode, emb, meta in db.iter_reels_with_embedding(column=column, client_id=client_id):
        # Apply post-filters early to save matmul work
        if filter_hook_type and meta.get("hook_type") != filter_hook_type:
            continue
        if filter_angle and meta.get("angle") != filter_angle:
            continue
        if filter_min_hook_score is not None and (meta.get("hook_score") or 0) < filter_min_hook_score:
            continue
        if filter_min_views is not None and (meta.get("views") or 0) < filter_min_views:
            continue

        ids.append(shortcode)
        metas.append(meta)
        vecs.append(np.array(emb, dtype=np.float32))

    if not vecs:
        return []

    mat = np.vstack(vecs)
    mat_n = _l2_normalize(mat)
    sims = mat_n @ q  # shape: (N,)

    if min_score is not None:
        mask = sims >= min_score
        if not mask.any():
            return []
        sims = sims[mask]
        ids = [i for i, m in zip(ids, mask, strict=False) if m]
        metas = [m for m, k in zip(metas, mask, strict=False) if k]

    n = len(sims)
    k = min(top_k, n)

    if k < n:
        idx = np.argpartition(-sims, k - 1)[:k]
        idx = idx[np.argsort(-sims[idx])]
    else:
        idx = np.argsort(-sims)

    results = []
    for i in idx:
        m = metas[i]
        results.append(
            SearchResult(
                shortcode=m["shortcode"],
                similarity=float(sims[i]),
                account=m["account"],
                hook_text=m.get("hook_text"),
                summary=m.get("summary", ""),
                views=m.get("views"),
                posted_at=m.get("posted_at"),
                client_id=m.get("client_id"),
                hook_type=m.get("hook_type"),
                hook_score=m.get("hook_score"),
                angle=m.get("angle"),
            )
        )
    return results
