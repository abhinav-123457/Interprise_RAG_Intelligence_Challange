"""
cli.py — interactive terminal client.

Pick a user, ask questions in a loop with conversation memory, and see the
grounded answer, confidence, cited sources, routing, injection flag, and the
sources RBAC hid. Switch users with `:user <name>` to demo access differences.

Commands:  :user <name>  :users  :reset  :help  :quit / :exit
Usage:     python cli.py            (starts as 'carol')
           python cli.py --user dave
"""
import argparse

import rbac
from rag_pipeline import answer_query


def print_users():
    print("\nAvailable users:")
    for uname in rbac.list_users():
        print(f"  - {uname:8} {rbac.describe_access(uname)}")
    print()


def render(resp):
    print("\n" + "=" * 70)
    if resp.get("injection_flagged"):
        print("[!] Prompt-injection attempt detected and logged.")
    grounded = any(c.get("used") for c in resp["citations"])
    print(f"ANSWER ({resp['confidence']} confidence, "
          f"{'grounded' if grounded else 'ungrounded'}):\n")
    print(resp["answer"])
    routed = ", ".join(resp["routed_department"]) or "general (no single dept)"
    print(f"\nRouted to: {routed}")

    if resp["citations"]:
        print("\nSources:")
        for c in resp["citations"]:
            score = f"{c['score']:.2f}" if c.get("score") is not None else "-"
            used = "*" if c.get("used") else " "
            print(f"  {used}[{c['tag']}] {c['title']} "
                  f"({c['department']}/{c['sensitivity']}, {c['source_type']}) "
                  f"score={score}")

    if resp["sources_blocked"]:
        print(f"\n{resp['sources_blocked']} source(s) hidden by your access level:")
        for b in resp["blocked_detail"]:
            print(f"  - {b['title']} ({b['department']}/{b['sensitivity']})")
    print("=" * 70)


def main():
    ap = argparse.ArgumentParser(description="Enterprise RAG assistant (CLI)")
    ap.add_argument("--user", default="carol", help="username to query as")
    args = ap.parse_args()

    user = args.user
    try:
        rbac.get_user(user)
    except KeyError as e:
        print(e)
        print_users()
        return

    print("Nimbus Industries - Enterprise RAG Assistant")
    print("Type a question, or :help for commands.")
    print(f"\nYou are: {rbac.describe_access(user)}")

    history = []  # conversation memory: [{"role", "content"}, ...]

    while True:
        try:
            q = input(f"\n[{user}] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            break
        if not q:
            continue
        if q in (":quit", ":exit"):
            print("bye")
            break
        if q == ":help":
            print(__doc__)
            continue
        if q == ":users":
            print_users()
            continue
        if q == ":reset":
            history = []
            print("conversation memory cleared")
            continue
        if q.startswith(":user"):
            parts = q.split()
            if len(parts) != 2:
                print("usage: :user <name>")
                continue
            try:
                rbac.get_user(parts[1])
            except KeyError as e:
                print(e)
                continue
            user = parts[1]
            history = []  # reset memory on identity switch (security boundary)
            print(f"switched to: {rbac.describe_access(user)}")
            continue

        try:
            resp = answer_query(user, q, history=history)
            render(resp)
            history.append({"role": "user", "content": q})
            history.append({"role": "assistant", "content": resp["answer"]})
        except Exception as e:
            print(f"error: {e}")


if __name__ == "__main__":
    main()