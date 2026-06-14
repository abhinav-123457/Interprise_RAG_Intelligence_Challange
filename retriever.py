"""
retriever.py — Step 4: hybrid retrieval + cross-encoder re-ranking + RBAC.

Per query:
  1. route(query)   -> guess relevant department(s) from keywords (soft boost).
  2. dense (FAISS)  -> semantic similarity.
  3. sparse (BM25)  -> keyword relevance.
  4. fuse (RRF)     -> Reciprocal Rank Fusion + routing boost selects candidates.
  5. re-rank        -> a cross-encoder re-scores query+chunk pairs for precision
                       (falls back to fused order if the model can't load).
  6. RBAC filter    -> rbac.filter_chunks keeps only chunks the user may see.

Returns allowed chunks (scored), the chunks blocked by access control, and the
routed department(s). Index + models are loaded once and cached.
"""
import json
import pickle
import re

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

import rbac
from config import (
    INDEX_DIR, EMBED_MODEL, TOP_K, RRF_K,
    USE_RERANKER, RERANK_MODEL, RERANK_POOL,
)


_STATE = {"index": None, "chunks": None, "bm25": None, "model": None,
          "reranker": None, "reranker_tried": False}


def _load_state():
    if _STATE["index"] is not None:
        return _STATE
    missing = [p for p in ("faiss.index", "chunks.json", "bm25.pkl")
               if not (INDEX_DIR / p).exists()]
    if missing:
        raise SystemExit(f"Index files missing ({missing}). Run `python ingest.py` first.")
    _STATE["index"] = faiss.read_index(str(INDEX_DIR / "faiss.index"))
    _STATE["chunks"] = json.loads((INDEX_DIR / "chunks.json").read_text())
    with open(INDEX_DIR / "bm25.pkl", "rb") as f:
        _STATE["bm25"] = pickle.load(f)
    _STATE["model"] = SentenceTransformer(EMBED_MODEL)
    return _STATE


def _load_reranker():
    """Lazily load the cross-encoder. Returns None if disabled/unavailable."""
    if _STATE["reranker_tried"]:
        return _STATE["reranker"]
    _STATE["reranker_tried"] = True
    if not USE_RERANKER:
        return None
    try:
        from sentence_transformers import CrossEncoder
        _STATE["reranker"] = CrossEncoder(RERANK_MODEL)
    except Exception as e:  # graceful fallback to hybrid order
        print(f"[retriever] re-ranker unavailable ({e}); using hybrid order.")
        _STATE["reranker"] = None
    return _STATE["reranker"]


# Keyword hints that nudge a query toward a department (soft signal only).
ROUTING_HINTS = {
    "Finance": ["revenue", "budget", "invoice", "transaction", "expense",
                "cash", "financial", "cost", "vendor", "payment"],
    "HR": ["salary", "compensation", "employee", "payroll", "leave",
           "hiring", "headcount", "band", "hr", "staff", "working hours",
           "hours", "handbook", "vacation", "holiday", "conduct", "onboarding"],
    "Engineering": ["architecture", "incident", "system", "deploy", "bug",
                    "helios", "service", "latency", "security", "api"],
    "Legal": ["compliance", "gdpr", "audit", "contract", "policy", "legal",
              "breach", "regulatory", "consent", "data protection"],
    "Operations": ["uptime", "device", "fleet", "alert", "runbook", "on-call",
                   "sla", "monitoring", "outage", "operational"],
    "Sales": ["customer", "account", "deal", "discount", "arr", "renewal",
              "pipeline", "quota", "sales", "playbook"],
}


def route(query):
    """Return department(s) the query most likely concerns (may be empty)."""
    q = query.lower()
    scores = {d: sum(1 for kw in kws if kw in q) for d, kws in ROUTING_HINTS.items()}
    best = max(scores.values())
    if best == 0:
        return []
    return [d for d, s in scores.items() if s == best]


def _tokenize(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def _rrf(rank):
    """Reciprocal Rank Fusion contribution for a 0-based rank."""
    return 1.0 / (RRF_K + rank)


def _rerank(query, candidates):
    """Re-score candidates with the cross-encoder (precise). Falls back to the
    incoming order + scores if the re-ranker is unavailable."""
    model = _load_reranker()
    if model is None or not candidates:
        return candidates
    scores = np.array(model.predict([[query, c["text"]] for c in candidates]),
                      dtype=float)
    lo, hi = scores.min(), scores.max()
    norm = (scores - lo) / (hi - lo) if hi > lo else np.ones_like(scores)
    out = []
    for i in np.argsort(scores)[::-1]:
        c = dict(candidates[i])
        c["score"] = round(float(norm[i]), 4)  # cross-encoder relevance 0..1
        out.append(c)
    return out


def hybrid_search(query, pool=RERANK_POOL):
    """Return chunks ranked by fused dense+sparse score, then re-ranked."""
    state = _load_state()
    chunks = state["chunks"]
    pool = min(pool, len(chunks))

    qvec = state["model"].encode(
        [query], convert_to_numpy=True, normalize_embeddings=True
    ).astype("float32")
    _, dense_idx = state["index"].search(qvec, pool)
    dense_idx = dense_idx[0]

    bm_scores = state["bm25"].get_scores(_tokenize(query))
    sparse_idx = np.argsort(bm_scores)[::-1][:pool]

    fused = {}
    for rank, i in enumerate(dense_idx):
        fused[int(i)] = fused.get(int(i), 0.0) + _rrf(rank)
    for rank, i in enumerate(sparse_idx):
        fused[int(i)] = fused.get(int(i), 0.0) + _rrf(rank)

    routed = set(route(query))
    if routed:
        for i in list(fused):
            if chunks[i]["department"] in routed:
                fused[i] += 0.5 * _rrf(0)  # small nudge, never decisive

    ranked = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
    if not ranked:
        return []

    # Build candidates with normalized RRF scores (used if re-ranker is off).
    top = ranked[0][1]
    candidates = []
    for i, sc in ranked:
        c = dict(chunks[i])
        c["score"] = round(sc / top, 4)
        candidates.append(c)

    # Cross-encoder re-rank for precision (overrides scores when available).
    return _rerank(query, candidates)


def retrieve_for_user(username, query, top_k=TOP_K):
    """Retrieve, then enforce access control.

    Returns: (allowed[:top_k], denied_metadata, routed_departments)
    """
    ranked = hybrid_search(query)
    allowed_all, denied = rbac.filter_chunks(username, ranked)
    return allowed_all[:top_k], denied, route(query)


if __name__ == "__main__":
    import sys
    user = sys.argv[1] if len(sys.argv) > 1 else "carol"
    q = sys.argv[2] if len(sys.argv) > 2 else "What are the L5 salary bands?"
    print(rbac.describe_access(user))
    print(f"\nQuery: {q}")
    allowed, denied, routed = retrieve_for_user(user, q)
    print(f"Routed to: {routed or 'no specific department'}")
    print(f"\nAllowed sources ({len(allowed)}):")
    for c in allowed:
        print(f"  [{c['score']:.2f}] {c['title']} ({c['department']}/{c['sensitivity']})")
    if denied:
        print(f"\nBlocked by RBAC ({len(denied)}):")
        for d in denied:
            print(f"  - {d['title']} ({d['department']}/{d['sensitivity']})")