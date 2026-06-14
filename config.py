"""
Central configuration for the Enterprise RAG system.
Single source of truth for paths, model names, departments and sensitivity.
"""
import os
from pathlib import Path

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DOCS_DIR = DATA_DIR / "documents"        # PDFs / text reports
STRUCT_DIR = DATA_DIR / "structured"     # CSV + SQL dumps
LOGS_DIR = DATA_DIR / "logs"             # JSON logs & audit trails
ACCESS_DIR = DATA_DIR / "access"         # RBAC policies + user-role mappings
INDEX_DIR = DATA_DIR / "index"           # persisted FAISS + BM25 + chunk store

for _d in (DATA_DIR, DOCS_DIR, STRUCT_DIR, LOGS_DIR, ACCESS_DIR, INDEX_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --- Models ---
EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# --- Enterprise domain ---
DEPARTMENTS = ["Finance", "HR", "Engineering", "Legal", "Operations", "Sales"]

# Sensitivity ordered least -> most sensitive.
SENSITIVITY_LEVELS = ["public", "internal", "confidential", "restricted"]


def sensitivity_rank(level: str) -> int:
    """Integer rank of a sensitivity level (higher = more secret)."""
    return SENSITIVITY_LEVELS.index(level)


# --- Retrieval / chunking ---
CHUNK_SIZE = 700          # characters per chunk (approx)
CHUNK_OVERLAP = 120       # overlap between consecutive chunks
TOP_K = 6                 # final chunks passed to the LLM
RRF_K = 60                # reciprocal-rank-fusion constant
# Cross-encoder re-ranker: re-scores fused candidates for precision.
# Set USE_RERANKER=0 in the environment to disable (pure hybrid fallback).
USE_RERANKER = os.getenv("USE_RERANKER", "1") == "1"
RERANK_MODEL = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
RERANK_POOL = 20          # how many fused candidates to re-rank
# ---------------------------------------------------------------------------
# Production guardrails
# ---------------------------------------------------------------------------
MAX_QUERY_LEN = int(os.getenv("MAX_QUERY_LEN", "1000"))        # input length cap
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", "15"))       # queries per window
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))  # seconds
ENABLE_DLP = os.getenv("ENABLE_DLP", "1") == "1"              # PII redaction
ENABLE_MODERATION = os.getenv("ENABLE_MODERATION", "1") == "1"  # output safety