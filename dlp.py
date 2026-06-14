"""
dlp.py — Data Loss Prevention: redact PII before text reaches the LLM/screen.

Second privacy layer on top of RBAC: RBAC decides which documents a user sees;
DLP scrubs PII inside them (emails, phones, SSNs, cards, IPs). Pure regex.
"""
import re

PII_PATTERNS = {
    "EMAIL": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "PHONE": r"\b(?:\+?\d{1,2}[ -])?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b",
    "SSN": r"\b\d{3}-\d{2}-\d{4}\b",
    "CREDIT_CARD": r"\b(?:\d{4}[ -]){3}\d{4}\b",
    "IP_ADDRESS": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
}

_COMPILED = {label: re.compile(p) for label, p in PII_PATTERNS.items()}


def redact(text):
    """Return (redacted_text, count_of_redactions)."""
    count = 0
    for label, pat in _COMPILED.items():
        text, n = pat.subn(f"[{label}_REDACTED]", text)
        count += n
    return text, count


def redact_chunks(chunks):
    """Redact PII in each chunk's text. Returns (new_chunks, total_redactions)."""
    total, out = 0, []
    for c in chunks:
        c = dict(c)
        c["text"], n = redact(c["text"])
        total += n
        out.append(c)
    return out, total


if __name__ == "__main__":
    samples = [
        "Contact john.doe@nimbus.com or call 415-555-0142.",
        "Login from 192.168.10.55 by user mwilson.",
        "Card 4111 1111 1111 1111, SSN 123-45-6789.",
        "Band L5 base salary range $128,000 - $155,000.",
    ]
    for s in samples:
        red, n = redact(s)
        print(f"({n}) {red}")