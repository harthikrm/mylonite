"""PROTOCOL.md §6.3: M3+'s argument-blindness on D3, and an estimate for a proposed variant, M3+arg.

No executions and no model calls. ``methods.run_m3plus`` itself, unchanged, is driven by a
RecordedTrial that answers from the pilot's records instead of the executor:
- ``profile(setup, call)`` returns the profile the pilot recorded for that setup and call;
- ``explore(workload, cap)`` charges the schedules the pilot recorded for that workload, and stops
  at the recorded violating schedule.

Step 1, fidelity. Each seed is replayed against its own log with the original ``pair_priority``.
Every profile call and every exploration must match the log in order (setup, call, workload, the
execution number where it starts), and E1 must equal the pilot's. Otherwise nothing else is
reported.

Step 2, estimate, for two argument-aware variants under new method IDs (post-pilot development;
M3+ itself is unchanged):
- M3+arg (proposed), ``run_m3plus_arg``: run_m3plus with one change. Pairs M3+ defers only because
  they differ in argument values from a representative it explored (same command signature) are
  explored first once the frontier is exhausted, before the other deferred pairs. Until then the
  order is M3+'s exactly, so on any run where M3+ hits before its frontier is exhausted the two
  are identical. With the change switched off, the copy must reproduce the pilot's logs exactly
  (step 1 runs it too).
- M3+arg-immediate (alternative), ``pair_priority_arg``: the argument variants are explored right
  after the representatives, at the same state.
Costs come from the union of all five seeds' records. A pair no seed explored has no recorded
cost:
- purchase ∥ purchase at a published state with stock S is decided by D3's design (it violates
  iff both quantities are <= S and their sum exceeds S), at the depth-first index observed for
  that pair shape, or else at the cap;
- any other unexplored pair is a PASS costing between the smallest count recorded for the same
  operation pair and the cap: the estimate is a range.
The design predicate is checked against every recorded exploration before it is used.

Usage: m3arg_estimate.py [--extract runs/pilot-<ts>/executions.jsonl]
  --extract rebuilds m3_d3_record.json from the raw pilot log (git-ignored); without it the
  committed extract is used.
"""

import argparse
import collections
import itertools
import json
import random
import sys
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))

from mylonite import methods, space  # noqa: E402

RECORD = HERE / "m3_d3_record.json"
TARGET = REPO / "fixtures/dev/d3_inventory/target.json"
PILOT_E1 = {"1": 211, "2": 246, "3": 211, "4": 211, "5": 775}
M3PLUS_PRIORITY = methods.pair_priority  # the original, kept before any patching


def key(*parts):
    return json.dumps(parts, sort_keys=True)


def extract(log_path):
    """Per seed: profiles and exploration groups in log order. A group is one ``explore`` call:
    it starts at an execution whose depth-first prefix is empty."""
    seeds = {}
    for line in open(log_path):
        ev = json.loads(line)
        target, method, seed = ev["trial"].split("/")
        if target != "d3-inventory" or method != "M3+":
            continue
        s = seeds.setdefault(seed, {"profiles": [], "groups": []})
        if ev["event"] == "profile":
            r = ev["result"]
            s["profiles"].append({"n": ev["n"], "setup": ev["setup"], "call": ev["call"],
                                  "result": {k: r[k] for k in ("commands", "outcome",
                                                               "state_before", "state_after")}})
        elif ev["event"] == "execution":
            rec = ev["record"]
            if ev["policy"].get("prefix") == []:
                s["groups"].append({"n": ev["n"], "pre": rec["pre"], "schedules": 0,
                                    "violated_at": None,
                                    "concurrent": [{"op": o["op"], "args": o["args"]}
                                                   for o in rec["ops"]]})
            g = s["groups"][-1]
            g["schedules"] += 1
            if rec["verdict"] == "VIOLATION" and g["violated_at"] is None:
                g["violated_at"] = g["schedules"]
    RECORD.write_text(json.dumps(seeds, indent=1, sort_keys=True) + "\n")


class Hit(Exception):
    def __init__(self, executions):
        super().__init__(executions)
        self.executions = executions


class RecordedTrial:
    """The slice of methods.Trial that run_m3plus uses, answered from records."""

    def __init__(self, budget, profile_of, explore_of):
        self.budget, self.profile_of, self.explore_of = budget, profile_of, explore_of
        self.executions, self.stats = 0, collections.Counter()

    def _charge(self):
        if self.executions >= self.budget:
            raise methods.BudgetExhausted("executions")
        self.executions += 1

    def profile(self, setup, call):
        self._charge()
        return self.profile_of(setup, call, self.executions)

    def explore(self, workload, cap):
        start = self.executions + 1
        schedules, violated_at = self.explore_of(workload, start)
        for i in range(1, min(schedules, cap) + 1):
            self._charge()
            if violated_at == i:
                raise Hit(self.executions)
        return [], schedules <= cap


def signature(a, b):
    return tuple(map(tuple, a[1])), tuple(map(tuple, b[1]))


def run_m3plus_arg(trial, target, seed, cfg, promote_variants=True):
    """Proposed M3+arg. methods.run_m3plus line for line, except that deferred pairs sharing a
    signature with an explored representative are explored first after the frontier."""
    rng = random.Random(f"M3+:{seed}")
    calls = space.op_calls(target)
    observe_op = target["observe"]["op"]
    behaviors, states = set(), set()
    frontier, variants, deferred = collections.deque([[]]), [], []
    while frontier:
        setup = frontier.popleft()
        order = calls[:]
        rng.shuffle(order)
        profiles = []
        for call in order:
            p = trial.profile(setup, call)
            profiles.append((call, p["commands"]))
            states.add(p["state_before"])
            behavior = (call["op"], tuple(c for c, _ in p["commands"]), p["outcome"])
            if (behavior not in behaviors and p["state_after"] not in states
                    and len(setup) < space.MAX_SETUP):
                states.add(p["state_after"])
                frontier.append(setup + [call])
            behaviors.add(behavior)
        pairs = [(a, b) for a, b in itertools.combinations_with_replacement(profiles, 2)
                 if methods.unserializable_pair(a[1], b[1])]
        rng.shuffle(pairs)
        observed_keys = {key for call, commands in profiles if call["op"] == observe_op
                         for _, key in commands}
        now, later = M3PLUS_PRIORITY(pairs, observed_keys)
        explored = {signature(a, b) for a, b in now}
        for a, b in later:
            promoted = promote_variants and signature(a, b) in explored
            (variants if promoted else deferred).append((setup, a, b))
        for (a, _), (b, _) in now:
            trial.explore({"setup": setup, "concurrent": [a, b]}, cfg["schedules_per_experiment"])
    for setup, (a, _), (b, _) in variants + deferred:
        trial.explore({"setup": setup, "concurrent": [a, b]}, cfg["schedules_per_experiment"])


def original(trial, target, seed, cfg):
    with mock.patch.object(methods, "pair_priority", M3PLUS_PRIORITY):
        methods.run_m3plus(trial, target, seed, cfg)


def copy_unpromoted(trial, target, seed, cfg):
    run_m3plus_arg(trial, target, seed, cfg, promote_variants=False)


def immediate(trial, target, seed, cfg):
    with mock.patch.object(methods, "pair_priority", pair_priority_arg):
        methods.run_m3plus(trial, target, seed, cfg)


def run(seed, profile_of, explore_of, search=original):
    target = json.loads(TARGET.read_text())
    trial = RecordedTrial(1000, profile_of, explore_of)
    try:
        search(trial, target, int(seed), {"schedules_per_experiment": 50})
    except Hit as hit:
        return hit.executions
    except methods.BudgetExhausted:
        return None
    return None


def fidelity(record):
    """Replay each seed against its own log, with methods.run_m3plus and with the M3+arg copy
    with its change switched off; any divergence is an AssertionError."""
    out = {}
    for name, search in (("methods.run_m3plus", original), ("run_m3plus_arg, change off", copy_unpromoted)):
        for seed, log in sorted(record.items()):
            profiles, groups = iter(log["profiles"]), iter(log["groups"])

            def profile_of(setup, call, n, profiles=profiles, seed=seed):
                p = next(profiles)
                assert (p["setup"], p["call"], p["n"]) == (setup, call, n), (seed, n, p["n"])
                return p["result"]

            def explore_of(workload, start, groups=groups, seed=seed):
                g = next(groups)
                assert (g["concurrent"], g["n"]) == (workload["concurrent"], start), (seed, start)
                return g["schedules"], g["violated_at"]

            e1 = run(seed, profile_of, explore_of, search)
            assert e1 == PILOT_E1[seed], (name, seed, e1, PILOT_E1[seed])
            out.setdefault(name, {})[seed] = e1
    return out


def state(setup):
    """Stock and published flag of D3 after a setup of successful calls (M3+ only extends the
    frontier with calls that changed the store)."""
    stock, live = collections.Counter(), {}
    for c in setup:
        sku = c["args"]["sku"]
        if c["op"] == "restock":
            stock[sku] += c["args"]["qty"]
        elif c["op"] == "purchase":
            stock[sku] -= c["args"]["qty"]
        elif c["op"] == "publish":
            live[sku] = True
        elif c["op"] in ("unpublish", "retire"):
            live[sku] = False
    return stock, live


def design_violates(setup, a, b):
    """D3's design (DESIGN.md): only two purchases that each fit and together exceed the stock of
    a published product can drive it negative."""
    if a["op"] != "purchase" or b["op"] != "purchase" or a["args"]["sku"] != b["args"]["sku"]:
        return False
    stock, live = state(setup)
    sku, s = a["args"]["sku"], stock[a["args"]["sku"]]
    qa, qb = a["args"]["qty"], b["args"]["qty"]
    return bool(live.get(sku)) and qa <= s and qb <= s and qa + qb > s


def pair_priority_arg(pairs, observed_keys):
    """M3+arg-immediate: M3+'s representatives first, then their argument variants at the same
    state, then the rest deferred as before."""
    now, later = M3PLUS_PRIORITY(pairs, observed_keys)
    explored = {signature(a, b) for a, b in now}
    variants = [(a, b) for a, b in later if signature(a, b) in explored]
    return now + variants, [p for p in later if p not in variants]


def estimate(record):
    profiles, costs = {}, {}
    for seed, log in record.items():
        for p in log["profiles"]:
            k = key(p["setup"], p["call"])
            assert profiles.setdefault(k, p["result"]) == p["result"], "profiles differ across seeds"
    # attach setups to groups by replaying each seed's original order
    for seed, log in sorted(record.items()):
        groups = iter(log["groups"])

        def profile_of(setup, call, n):
            return profiles[key(setup, call)]

        def explore_of(workload, start, groups=groups, seed=seed):
            g = next(groups)
            k = key(workload["setup"], *workload["concurrent"])
            assert costs.setdefault(k, (g["schedules"], g["violated_at"])) == (
                g["schedules"], g["violated_at"]), "recorded outcomes differ across seeds"
            return g["schedules"], g["violated_at"]

        run(seed, profile_of, explore_of)
    checked = 0
    shape_index = {}
    for k, (n, violated_at) in costs.items():
        setup, a, b = json.loads(k)
        assert design_violates(setup, a, b) == (violated_at is not None), ("design predicate", k)
        checked += 1
        if a["op"] == b["op"] == "purchase" and violated_at is not None:
            shape_index.setdefault(violated_at, 0)
            shape_index[violated_at] += 1
    min_by_ops = {}
    for k, (n, violated_at) in costs.items():
        _, a, b = json.loads(k)
        if violated_at is None:
            ops = tuple(sorted((a["op"], b["op"])))
            min_by_ops[ops] = min(n, min_by_ops.get(ops, n))
    violation_index = max(shape_index) if shape_index else 50
    results = {}
    for name, search in (("M3+arg (proposed)", run_m3plus_arg),
                         ("M3+arg-immediate (alternative)", immediate)):
        for bound in ("low", "high"):
            unknown = collections.Counter()
            for seed in sorted(record):
                def profile_of(setup, call, n):
                    return profiles[key(setup, call)]

                def explore_of(workload, start, bound=bound, unknown=unknown):
                    setup, (a, b) = workload["setup"], workload["concurrent"]
                    k = key(setup, a, b)
                    if k in costs:
                        return costs[k]
                    unknown[key(setup, a, b)] += 1
                    if a["op"] == b["op"] == "purchase":
                        hit = design_violates(setup, a, b)
                        return (violation_index, violation_index) if hit else (50, None)
                    low = min_by_ops.get(tuple(sorted((a["op"], b["op"]))), 1)
                    return (low if bound == "low" else 50), None

                try:
                    e1 = run(seed, profile_of, explore_of, search)
                except KeyError:
                    e1 = "not estimable: reaches a state the pilot never profiled"
                results.setdefault(name, {}).setdefault(seed, {})[bound] = e1
            results[name].setdefault("_pairs_without_recorded_cost", {})[bound] = len(unknown)
    return {"recorded_explorations_checked_against_design": checked,
            "purchase_violation_index_observed": shape_index,
            "m3arg_e1_estimate": results}


def blind_spot_probability():
    """P(the one prioritized purchase pair at the published state cannot violate), from
    pair_priority and D3's domains: the first successful restock in a seed's shuffled order sets
    the stock S (novelty ignores arguments), uniformly over qty; all purchases with qty <= S
    share one signature, and the representative is uniform over their unordered pairs."""
    from fractions import Fraction
    qtys = json.loads(TARGET.read_text())["domains"]["qty"]
    total = Fraction(0)
    per_s = {}
    for s in qtys:
        fits = [q for q in qtys if q <= s]
        pairs = [(x, y) for i, x in enumerate(fits) for y in fits[i:]]
        blind = Fraction(sum(x + y <= s for x, y in pairs), len(pairs))
        per_s[s] = str(blind)
        total += blind / len(qtys)
    return {"per_stock": per_s, "overall": str(total), "overall_float": round(float(total), 4)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--extract")
    args = parser.parse_args()
    if args.extract:
        extract(args.extract)
    record = json.loads(RECORD.read_text())
    report = {"fidelity_e1": fidelity(record), "blind_spot_probability": blind_spot_probability(),
              **estimate(record)}
    (HERE / "m3arg_estimate.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    print(json.dumps(report, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
