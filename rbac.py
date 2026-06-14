"""
rbac.py — Role-Based Access Control engine (the security core).

Given a user and retrieved chunks, decides which the user may see BEFORE they
reach the LLM. A chunk is visible only if BOTH hold:
  1. Department match: chunk.department in the user's allowed departments
     (or the policy grants "*" = all departments).
  2. Clearance: chunk.sensitivity rank <= the user's max clearance rank.
Returns allowed AND denied chunks so the system can stay explainable.
"""
import json

from config import ACCESS_DIR, sensitivity_rank


def _load(name):
    return json.loads((ACCESS_DIR / name).read_text())


USERS = _load("users.json")
POLICIES = _load("access_policies.json")


def list_users():
    """Return {username: {name, role, department}} for the UI / CLI."""
    return USERS


def get_user(username):
    user = USERS.get(username)
    if user is None:
        raise KeyError(f"Unknown user '{username}'. Known: {list(USERS)}")
    return user


def get_policy(role):
    policy = POLICIES.get(role)
    if policy is None:
        raise KeyError(f"Unknown role '{role}'. Known: {list(POLICIES)}")
    return policy


def user_policy(username):
    """Resolve a username straight to its access policy."""
    return get_policy(get_user(username)["role"])


def can_access(policy, chunk):
    """True if a user with `policy` may read `chunk`."""
    depts = policy["departments"]
    dept_ok = depts == "*" or chunk["department"] in depts
    clearance_ok = (
        sensitivity_rank(chunk["sensitivity"])
        <= sensitivity_rank(policy["max_sensitivity"])
    )
    return dept_ok and clearance_ok


def filter_chunks(username, chunks):
    """Split chunks into (allowed, denied) for the given user.

    `denied` carries metadata for an explainable notice without leaking text.
    """
    policy = user_policy(username)
    allowed, denied = [], []
    for c in chunks:
        if can_access(policy, c):
            allowed.append(c)
        else:
            denied.append({
                "doc_id": c["doc_id"],
                "title": c["title"],
                "department": c["department"],
                "sensitivity": c["sensitivity"],
            })
    return allowed, denied


def describe_access(username):
    """Human-readable summary of what a user can see (for UI/CLI headers)."""
    user = get_user(username)
    policy = user_policy(username)
    depts = "all departments" if policy["departments"] == "*" else \
        ", ".join(policy["departments"])
    return (
        f"{user['name']} | role={user['role']} | "
        f"can read: {depts} | clearance: {policy['max_sensitivity']}"
    )


if __name__ == "__main__":
    # Self-test: show every user's reach.
    for uname in USERS:
        print(describe_access(uname))