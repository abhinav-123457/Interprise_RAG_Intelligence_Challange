"""
rag_pipeline.py — Step 6: the orchestrator.

Flow: input validation + rate limit -> injection detection -> routing -> hybrid
retrieve + re-rank -> RBAC filter -> DLP redaction -> grounded generation (memory
+ citations) -> output moderation -> audit logging.
"""
import retriever
import rbac
import generator
import audit
import guard
import dlp
import moderation
import ratelimit
from config import MAX_QUERY_LEN, ENABLE_DLP, ENABLE_MODERATION


def _response(username, query, answer, **extra):
    """Build a response dict with sane defaults for the explainable fields."""
    base = {
        "user": username,
        "access": rbac.describe_access(username),
        "query": query,
        "routed_department": [],
        "answer": answer,
        "confidence": "Low",
        "citations": [],
        "sources_used": 0,
        "sources_blocked": 0,
        "blocked_detail": [],
        "injection_flagged": False,
        "injection_pattern": None,
        "pii_redacted": 0,
        "moderation_flagged": False,
        "rate_limited": False,
    }
    base.update(extra)
    return base


def answer_query(username, query, history=None):
    """Run the full secure RAG pipeline for one user question.

    `history` is an optional list of prior turns [{"role", "content"}, ...]
    enabling multi-turn follow-up questions.
    """
    access = rbac.describe_access(username)  # validates the user

    # 0a. Input validation: cap query length (avoid oversized prompts).
    if query and len(query) > MAX_QUERY_LEN:
        query = query[:MAX_QUERY_LEN]

    # 0b. Rate limit per user (skip all heavy work if exceeded).
    allowed_call, retry = ratelimit.check(username)
    if not allowed_call:
        resp = _response(
            username, query,
            f"Rate limit exceeded. Please try again in {retry}s.",
            rate_limited=True)
        audit.log_query(resp)
        return resp

    # 1. Prompt-injection detection (RBAC is the real defense; this flags + logs).
    injection_flagged, injection_pattern = guard.detect_injection(query)

    # 2. For follow-ups, give retrieval the prior question as light context.
    retrieval_query = query
    if history:
        last_user = next((t["content"] for t in reversed(history)
                          if t.get("role") == "user"), "")
        if last_user:
            retrieval_query = f"{last_user} {query}"

    # 3-4. Route + hybrid retrieve + RBAC filter.
    allowed, denied, routed = retriever.retrieve_for_user(username, retrieval_query)

    # 5. DLP: redact PII inside the authorized chunks before generation.
    pii_redacted = 0
    if ENABLE_DLP:
        allowed, pii_redacted = dlp.redact_chunks(allowed)

    # 6. Grounded generation (refuses safely if no authorized sources).
    result = generator.generate_answer(query, allowed, history=history)
    answer = result["answer"]

    # 7. Output moderation (toxicity / system-prompt leak).
    moderation_flagged = False
    if ENABLE_MODERATION:
        safe, _reason = moderation.moderate(answer)
        if not safe:
            answer = moderation.SAFE_MESSAGE
            moderation_flagged = True

    # 8. Assemble an explainable response (de-dup blocked list by document).
    seen, blocked_detail = set(), []
    for d in denied:
        if d["doc_id"] not in seen:
            seen.add(d["doc_id"])
            blocked_detail.append({
                "title": d["title"],
                "department": d["department"],
                "sensitivity": d["sensitivity"],
            })

    response = _response(
        username, query, answer,
        routed_department=routed,
        confidence=result["confidence"],
        citations=result["citations"],
        sources_used=len(allowed),
        sources_blocked=len(blocked_detail),
        blocked_detail=blocked_detail,
        injection_flagged=injection_flagged,
        injection_pattern=injection_pattern,
        pii_redacted=pii_redacted,
        moderation_flagged=moderation_flagged,
    )

    audit.log_query(response)
    return response


if __name__ == "__main__":
    import sys
    import json

    user = sys.argv[1] if len(sys.argv) > 1 else "carol"
    query = sys.argv[2] if len(sys.argv) > 2 else "What are the L5 salary bands?"
    resp = answer_query(user, query)
    print(json.dumps(resp, indent=2))