"""
app.py — Streamlit web UI for the Enterprise RAG assistant (Hugging Face ready).

Modern, formal enterprise styling. Sidebar role selector (RBAC), chat with
conversation memory, per-answer confidence + grounded badges, injection flag,
cited sources, RBAC blocked-sources notice, and a live audit-trail panel.

Run:  streamlit run app.py
"""
import streamlit as st

from config import INDEX_DIR

st.set_page_config(page_title="Nimbus Enterprise RAG",
                   page_icon="🔒", layout="wide")


@st.cache_resource(show_spinner="First boot: building dataset + search index...")
def _bootstrap():
    """On a fresh deploy the data/index don't exist yet. Build once (seeded,
    so deterministic)."""
    if not (INDEX_DIR / "faiss.index").exists():
        try:
            import generate_dataset as gen
        except ImportError:
            import dataset_generator as gen
        import ingest
        gen.main()
        ingest.main()
    return True


_bootstrap()

import rbac
import audit
from rag_pipeline import answer_query


# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------
st.markdown("""
<style>
#MainMenu, footer {visibility: hidden;}
.block-container {padding-top: 1.4rem; max-width: 1080px;}
html, body, [class*="css"] {
    font-family: 'Inter','Segoe UI',-apple-system,sans-serif;
}
.hero {
    background: linear-gradient(135deg,#4f46e5 0%,#0ea5e9 100%);
    padding: 22px 28px; border-radius: 16px; color: #fff; margin-bottom: 20px;
    box-shadow: 0 6px 20px rgba(79,70,229,.25);
}
.hero h1 {margin:0; font-size:1.55rem; font-weight:700; letter-spacing:-.3px;}
.hero p {margin:6px 0 0; opacity:.92; font-size:.93rem;}
.pill {display:inline-block; padding:3px 12px; border-radius:999px;
    font-size:.74rem; font-weight:600; margin:0 6px 4px 0; color:#fff;}
.idcard {background:#f8fafc; border:1px solid #e2e8f0; border-radius:14px;
    padding:14px 16px; margin-bottom:10px;}
.idcard .nm {font-weight:700; font-size:1rem; color:#0f172a;}
.idcard .rl {color:#475569; font-size:.85rem; margin-top:2px;}
.kv {font-size:.82rem; color:#334155; margin-top:6px;}
.src {background:#f8fafc; border:1px solid #e8edf3; border-left:3px solid #4f46e5;
    border-radius:10px; padding:10px 13px; margin-bottom:9px;}
.src .t {font-weight:600; color:#0f172a; font-size:.9rem;}
.src .m {color:#64748b; font-size:.78rem; margin-top:2px;}
.src .s {color:#475569; font-size:.82rem; margin-top:6px; line-height:1.4;}
.tag {background:#eef2ff; color:#4338ca; padding:1px 7px; border-radius:6px;
    font-size:.72rem; font-weight:600;}
.tag.r {background:#fef2f2; color:#b91c1c;}
.muted {color:#94a3b8; font-size:.8rem;}
</style>
""", unsafe_allow_html=True)

BADGE = {"High": "#16a34a", "Medium": "#d97706", "Low": "#dc2626"}


def pill(text, color):
    return f"<span class='pill' style='background:{color}'>{text}</span>"


# ---------------------------------------------------------------------------
# Sidebar — identity / RBAC
# ---------------------------------------------------------------------------
st.sidebar.markdown("### 🔒 Nimbus Enterprise RAG")
st.sidebar.caption("Secure, RBAC-enforced intelligence assistant")

users = rbac.list_users()
username = st.sidebar.selectbox(
    "Signed in as",
    options=list(users),
    format_func=lambda u: f"{users[u]['name']} · {users[u]['role']}",
)
policy = rbac.user_policy(username)
depts = "All departments" if policy["departments"] == "*" else ", ".join(policy["departments"])
initials = "".join(p[0] for p in users[username]["name"].split()[:2]).upper()
st.sidebar.markdown(
    f"<div class='idcard'>"
    f"<div class='nm'>{users[username]['name']}</div>"
    f"<div class='rl'>{users[username]['role']}</div>"
    f"<div class='kv'>🏢 <b>Access:</b> {depts}</div>"
    f"<div class='kv'>🛡️ <b>Clearance:</b> <span class='tag'>{policy['max_sensitivity']}</span></div>"
    f"</div>", unsafe_allow_html=True)

if st.sidebar.button("🧹 Clear conversation", use_container_width=True):
    st.session_state["history"] = []

# Reset chat history when the user switches identity (security boundary).
if st.session_state.get("_user") != username:
    st.session_state["_user"] = username
    st.session_state["history"] = []

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown(
    "<div class='hero'><h1>Enterprise RAG Intelligence Assistant</h1>"
    "<p>Cross-source retrieval across PDFs, databases, and logs — with strict "
    "role-based access control, grounded citations, and full auditability.</p></div>",
    unsafe_allow_html=True)

# Replay prior turns.
for turn in st.session_state.get("history", []):
    with st.chat_message(turn["role"], avatar="🧑‍💼" if turn["role"] == "user" else "🤖"):
        st.markdown(turn["content"])

query = st.chat_input("Ask a question about the enterprise…")
if query:
    with st.chat_message("user", avatar="🧑‍💼"):
        st.markdown(query)

    history = list(st.session_state.get("history", []))

    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Retrieving authorized sources and generating…"):
            resp = answer_query(username, query, history=history)

        grounded = any(c.get("used") for c in resp["citations"])
        routed = ", ".join(resp["routed_department"]) or "general"

        badges = pill(f"Confidence: {resp['confidence']}",
                      BADGE.get(resp["confidence"], "#64748b"))
        badges += pill("Grounded ✓" if grounded else "Ungrounded",
                       "#16a34a" if grounded else "#dc2626")
        badges += pill(f"Routed: {routed}", "#475569")
        if resp.get("pii_redacted"):
            badges += pill(f"PII redacted: {resp['pii_redacted']}", "#0ea5e9")
        if resp.get("injection_flagged"):
            badges += pill("⚠ Injection blocked", "#dc2626")
        if resp.get("moderation_flagged"):
            badges += pill("⚠ Moderated", "#dc2626")
        st.markdown(badges, unsafe_allow_html=True)

        st.markdown(resp["answer"])

        if resp["citations"]:
            with st.expander(f"📚 Sources used ({resp['sources_used']})", expanded=True):
                for c in resp["citations"]:
                    score = f"{c['score']:.2f}" if c.get("score") is not None else "-"
                    used = "✅" if c.get("used") else "▫️"
                    st.markdown(
                        f"<div class='src'><div class='t'>{used} [{c['tag']}] {c['title']}</div>"
                        f"<div class='m'>{c['department']} · {c['sensitivity']} · "
                        f"{c['source_type']} · relevance {score}</div>"
                        f"<div class='s'>{c['snippet']}…</div></div>",
                        unsafe_allow_html=True)

        if resp["sources_blocked"]:
            with st.expander(f"🚫 {resp['sources_blocked']} source(s) hidden by your access level"):
                for b in resp["blocked_detail"]:
                    st.markdown(
                        f"- {b['title']} &nbsp;<span class='tag r'>"
                        f"{b['department']}/{b['sensitivity']}</span>",
                        unsafe_allow_html=True)

    st.session_state["history"].append({"role": "user", "content": query})
    st.session_state["history"].append({"role": "assistant", "content": resp["answer"]})

# ---------------------------------------------------------------------------
# Sidebar — audit trail
# ---------------------------------------------------------------------------
with st.sidebar.expander("📜 Audit trail (recent)"):
    records = audit.read_audit(limit=15)
    if not records:
        st.caption("No queries logged yet.")
    for r in reversed(records):
        flags = []
        if r.get("refused"):
            flags.append("refused")
        if r.get("injection_flagged"):
            flags.append("⚠injection")
        if r.get("pii_redacted"):
            flags.append(f"PII×{r['pii_redacted']}")
        tag = f" · {' '.join(flags)}" if flags else ""
        st.markdown(
            f"<span class='muted'>`{r['timestamp'][11:19]}` <b>{r['user']}</b> "
            f"(↑{len(r['sources_served'])}/⊘{len(r['sources_blocked'])}){tag}<br>"
            f"{r['query'][:58]}</span>", unsafe_allow_html=True)