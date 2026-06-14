"""
audit.py — Enterprise audit trail (append-only JSONL).

Logs every query: who asked, what, where it routed, sources served vs blocked
by RBAC, confidence, and whether it was refused. Satisfies the "audit trails"
requirement and gives the system enterprise accountability. No network.
"""
import json
from datetime import datetime, timezone

import rbac
from config import DATA_DIR
from generator import REFUSAL

AUDIT_DIR = DATA_DIR / "audit"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_PATH = AUDIT_DIR / "query_audit.jsonl"


def log_query(resp):
    """Append one audit record built from a rag_pipeline response dict."""
    try:
        role = rbac.get_user(resp["user"]).get("role")
    except Exception:
        role = None

    refused = (resp.get("sources_used", 0) == 0) or \
        (resp.get("answer", "").strip() == REFUSAL)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user": resp.get("user"),
        "role": role,
        "query": resp.get("query"),
        "routed_department": resp.get("routed_department"),
        "confidence": resp.get("confidence"),
        "refused": refused,
        "injection_flagged": resp.get("injection_flagged", False),
        "sources_served": [
            {"title": c["title"], "department": c["department"],
             "sensitivity": c["sensitivity"]}
            for c in resp.get("citations", [])
        ],
        "sources_blocked": resp.get("blocked_detail", []),
    }
    with open(AUDIT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return record


def read_audit(limit=None):
    """Return audit records (most recent last). For the UI / inspection."""
    if not AUDIT_PATH.exists():
        return []
    with open(AUDIT_PATH, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    return records[-limit:] if limit else records


if __name__ == "__main__":
    records = read_audit()
    print(f"{len(records)} audit records in {AUDIT_PATH}")
    refusals = sum(1 for r in records if r["refused"])
    print(f"  refusals (blocked/insufficient): {refusals}")
    for r in records[-10:]:
        print(f"  {r['timestamp']} | {r['user']:6} ({r['role']}) | "
              f"served={len(r['sources_served'])} blocked={len(r['sources_blocked'])} "
              f"| refused={r['refused']} | {r['query'][:50]}")