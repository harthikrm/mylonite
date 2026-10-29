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


def item_quantity_conserved(clause, ops, pre, post):
    """Observations map each owner to {item: quantity}. For every (owner, item): the quantity
    after the round equals the quantity before plus ``amount_arg`` over ok calls of ``op`` on
    that pair, plus the amounts of any subset of info calls. If a ``reset_op`` call on the owner
    may have taken effect, the quantity may instead be the sum of any subset of the round's calls
    on that pair: each one is ordered either after the last reset or before it and wiped.
    Real-time order is not used, so every serial outcome is allowed (some violations are missed)."""
    failures = []
    for owner in sorted(set(pre) | set(post)):
        before, after = pre.get(owner) or {}, post.get(owner) or {}
        calls = [o for o in ops if o["args"].get(clause["owner_arg"]) == owner]
        resets = [o for o in calls if o["op"] == clause["reset_op"] and o["status"] != "fail"]
        adds = [o for o in calls if o["op"] == clause["op"]]
        for item in sorted(set(before) | set(after) | {o["args"][clause["item_arg"]] for o in adds}):
            mine = [o for o in adds if o["args"][clause["item_arg"]] == item]
            ok = [o["args"][clause["amount_arg"]] for o in mine if o["status"] == "ok"]
            maybe = [o["args"][clause["amount_arg"]] for o in mine if o["status"] == "info"]
            allowed = set()
            if not any(o["status"] == "ok" for o in resets):
                allowed |= {before.get(item, 0) + sum(ok) + s for s in _subset_sums(maybe)}
            if resets:
                allowed |= _subset_sums(ok + maybe)
            if after.get(item, 0) not in allowed:
                failures.append({"key": f"{owner}/{item}", "before": before.get(item, 0),
                                 "observed": after.get(item, 0), "allowed": sorted(allowed)})
    return failures


def non_negative(clause, ops, pre, post):
    """Every observed value is >= 0 after the round. A state invariant: no history needed."""
    return [{"key": key, "observed": value} for key, value in sorted(post.items())
            if value is not None and value < 0]


INVARIANTS = {"counter_conserved": counter_conserved, "non_negative": non_negative,
              "item_quantity_conserved": item_quantity_conserved}


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
