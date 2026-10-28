"""Contract oracle (ARCHITECTURE.md §6). Invariant kinds are code; contracts only select them.

Operations come back as ``ok``, ``fail`` or ``info``. A non-OK outcome is ``info`` (it may or
may not have taken effect) unless the contract declares that status ``no_effect``.
"""

from itertools import combinations

PASS, VIOLATION, INCONCLUSIVE = "PASS", "VIOLATION", "INCONCLUSIVE"


def _subset_sums(amounts):
    sums = set()
    for r in range(len(amounts) + 1):
        for combo in combinations(amounts, r):
            sums.add(sum(combo))
    return sums


def counter_conserved(clause, ops, pre, post):
    """final(key) == initial(key) + sum of ``amount_arg`` over ok calls of ``op`` on that key,
    plus the amounts of any subset of info calls."""
    failures = []
    for key in sorted(set(pre) | set(post)):
        calls = [o for o in ops if o["op"] == clause["op"] and o["args"][clause["key_arg"]] == key]
        ok = sum(o["args"][clause["amount_arg"]] for o in calls if o["status"] == "ok")
        maybe = [o["args"][clause["amount_arg"]] for o in calls if o["status"] == "info"]
        delta = post.get(key, 0) - pre.get(key, 0)
        allowed = {ok + s for s in _subset_sums(maybe)}
        if delta not in allowed:
            failures.append({"key": key, "observed_delta": delta, "allowed_deltas": sorted(allowed)})
    return failures


INVARIANTS = {"counter_conserved": counter_conserved}


def classify(op_result, contract):
    """Map a raw outcome to ok / fail / info per the contract's status semantics."""
    if op_result["error"] is None:
        return "ok"
    no_effect = contract.get("status_semantics", {}).get(op_result["op"], {}).get("no_effect", [])
    return "fail" if op_result["error"] in no_effect else "info"


def check(contract, ops, pre, post):
    """Return (verdict, details). ``ops`` must already carry ``status``."""
    details = []
    for clause in contract["invariants"]:
        failures = INVARIANTS[clause["kind"]](clause, ops, pre, post)
        if failures:
            details.append({"clause": clause["id"], "failures": failures})
    return (VIOLATION if details else PASS), details
