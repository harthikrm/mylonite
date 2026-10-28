"""Fixture validation for D3 (no search method is run). Host side, standard library only.

Checks that the fixture is what its design says, using a witness constructed by its author:
  1. the proxy in pass-through changes nothing;
  2. serial runs never violate the contract, on either variant (the contract is serially valid);
  3. the author's witness violates, replays 20/20, and is one of k violating schedules of that
     workload under exhaustive exploration;
  4. each setup step is necessary: without it, every schedule of the same concurrent calls passes;
  5. the corrected variant passes exhaustive exploration of the witness workload and of harder
     variants of it.
Also writes a prediction for random search (M1) from an abstract model of the service, before any
method runs on D3. Results: results.json next to this file.
"""

import collections
import itertools
import json
import random
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from mylonite import space  # noqa: E402
from mylonite.sandbox import Sandbox  # noqa: E402
from mylonite.scheduler import next_prefix  # noqa: E402

HERE = Path(__file__).resolve().parent
TARGET = json.loads((REPO / "fixtures/dev/d3_inventory/target.json").read_text())


def call(op, sku="s1", qty=None):
    return {"op": op, "args": {"sku": sku} if qty is None else {"sku": sku, "qty": qty}}


READY = [call("create"), call("restock", qty=1), call("publish")]
WITNESS = {"setup": READY, "concurrent": [call("purchase", qty=1), call("purchase", qty=1)]}
HINT = [{"op_index": k, "command": c} for c in ("HGET", "GET", "DECRBY") for k in (0, 1)]


def execute(session, variant, workload, policy):
    return session.request({"op": "execute", "variant": variant, "workload": workload,
                            "policy": policy})[0]


def exhaustive(session, variant, workload, cap=20000):
    verdicts, prefix, n = collections.Counter(), [], 0
    first = None
    while n < cap:
        record = execute(session, variant, workload, {"kind": "prefix", "prefix": prefix})
        n += 1
        verdicts[record["verdict"]] += 1
        if record["verdict"] == "VIOLATION" and first is None:
            first = n
        prefix = next_prefix(record["steps"])
        if prefix is None:
            return {"schedules": n, "exhausted": True, "verdicts": dict(verdicts),
                    "first_violation_at": first}
    return {"schedules": n, "exhausted": False, "verdicts": dict(verdicts),
            "first_violation_at": first}


def abstract_setup(setup, state=None):
    """Serial semantics of the service, for the prediction only."""
    state = {k: dict(v) for k, v in (state or {}).items()}
    for c in setup:
        sku, op = c["args"]["sku"], c["op"]
        s = state.get(sku)
        if op == "create" and s is None:
            state[sku] = {"status": "draft", "stock": 0}
        elif s is None:
            continue
        elif op == "restock" and s["status"] != "retired":
            s["stock"] += c["args"]["qty"]
        elif op == "publish" and s["status"] == "draft" and s["stock"] > 0:
            s["status"] = "live"
        elif op == "unpublish" and s["status"] == "live":
            s["status"] = "draft"
        elif op == "retire" and s["status"] != "live":
            s["status"] = "retired"
        elif op == "purchase" and s["status"] == "live" and s["stock"] >= c["args"]["qty"]:
            s["stock"] -= c["args"]["qty"]
    return state


def prediction(results):
    p_exact = exact_violable_probability()
    rng = random.Random("d3-prediction")
    n = 200_000
    hits = sum(violable(space.random_workload(TARGET, rng)) for _ in range(n))
    p_schedule = results["witness"]["random_schedules_500"].get("VIOLATION", 0) / 500
    p = p_exact * p_schedule
    return {
        "method": "exact probability, under M1's draw, that the setup leaves a product live with "
                  "stock q and two concurrent purchases each fit q but together exceed it "
                  "(abstract serial model; concurrent calls that change the state are ignored), "
                  "times the witness's violating fraction under random schedules",
        "p_violable_workload_exact": p_exact,
        "monte_carlo_check": {"samples": n, "hits": hits, "p": hits / n},
        "p_violating_schedule": p_schedule, "p_per_execution": p,
        "expected_executions": (1 / p) if p else None,
        "p_found_within_300": 1 - (1 - p) ** 300 if p else 0.0,
        "caveat": "approximate: ignores enabling or disabling calls inside the concurrent round and "
                  "uses the two-purchase witness's schedule fraction for every workload"}


def violable(workload, state=None):
    """True if the setup leaves some product live with stock q and the concurrent calls include
    two purchases of it that each fit q but together exceed it. Ignores concurrent calls that
    change the state themselves, so it slightly underestimates."""
    state = abstract_setup(workload["setup"]) if state is None else state
    for sku, s in state.items():
        if s["status"] != "live":
            continue
        qtys = [c["args"]["qty"] for c in workload["concurrent"]
                if c["op"] == "purchase" and c["args"]["sku"] == sku and c["args"]["qty"] <= s["stock"]]
        if any(a + b > s["stock"] for i, a in enumerate(qtys) for b in qtys[i + 1:]):
            return True
    return False


def call_distribution():
    """M1's per-call draw (space.random_workload): operation uniform, then each argument uniform."""
    ops = sorted(TARGET["operations"])
    dist = []
    for op in ops:
        args = TARGET["operations"][op]["args"]
        names = sorted(args)
        combos = list(itertools.product(*(TARGET["domains"][args[n]["domain"]] for n in names)))
        dist += [({"op": op, "args": dict(zip(names, v))}, 1 / len(ops) / len(combos))
                 for v in combos]
    return dist


def exact_violable_probability():
    """P(violable(workload)) under M1's draw, computed exactly: dynamic programming over the
    abstract setup state, then enumeration of the concurrent calls over a reduced alphabet."""
    dist = call_distribution()
    freeze = lambda st: tuple(sorted((k, v["status"], v["stock"]) for k, v in st.items()))
    thaw = lambda fs: {k: {"status": s_, "stock": q} for k, s_, q in fs}
    layer, by_state = {freeze({}): 1.0}, collections.Counter()
    for length in range(space.MAX_SETUP + 1):
        for fs, pr in layer.items():
            by_state[fs] += pr / (space.MAX_SETUP + 1)
        nxt = collections.Counter()
        for fs, pr in layer.items():
            for c, pc in dist:
                nxt[freeze(abstract_setup([c], thaw(fs)))] += pr * pc
        layer = nxt
    purchases = [(c, pc) for c, pc in dist if c["op"] == "purchase"]
    other = 1 - sum(pc for _, pc in purchases)
    alphabet = purchases + [(None, other)]
    total = 0.0
    sizes = range(space.MIN_CONCURRENT, space.MAX_CONCURRENT + 1)
    for fs, pr in by_state.items():
        state = thaw(fs)
        if not any(v["status"] == "live" for v in state.values()):
            continue
        cond = 0.0
        for n in sizes:
            for seq in itertools.product(alphabet, repeat=n):
                calls = [c for c, _ in seq if c is not None]
                if calls and violable({"setup": [], "concurrent": calls}, state):
                    weight = 1.0
                    for _, pc in seq:
                        weight *= pc
                    cond += weight / len(sizes)
        total += pr * cond
    return total


def main():
    if "--prediction-only" in sys.argv:
        results = json.loads((HERE / "results.json").read_text())
        results["prediction_m1"] = prediction(results)
        (HERE / "results.json").write_text(json.dumps(results, indent=1))
        print(json.dumps(results["prediction_m1"], indent=1))
        return
    results = {"target": TARGET["target"], "run": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
               "witness": {"author_constructed": True, "workload": WITNESS, "hint": HINT}}
    box = Sandbox("mylonite-d3", REPO)
    box.up()
    try:
        one_shot = box.run_executor({"target": TARGET, "variant": "buggy", "delta_q_ms": 300,
                                     "round_timeout_s": 10, "jobs": [
                                         {"id": "pt", "kind": "passthrough_check",
                                          "workload": WITNESS, "repeat": 50}]})
        results["egress_probe"] = one_shot["egress_probe"]
        results["passthrough_check"] = one_shot["jobs"][0]["summary"]
        with box.session(TARGET) as session:
            rng = random.Random("d3-serial")
            serial = {"buggy": collections.Counter(), "fixed": collections.Counter()}
            for _ in range(150):
                workload = space.random_workload(TARGET, rng)
                for variant in serial:  # PrefixPolicy([]) runs the calls one after another
                    serial[variant][execute(session, variant, workload,
                                            {"kind": "prefix", "prefix": []})["verdict"]] += 1
            results["serial_runs"] = {v: dict(c) for v, c in serial.items()}

            hinted = execute(session, "buggy", WITNESS, {"kind": "hint", "hint": HINT})
            replays = [execute(session, "buggy", WITNESS,
                               {"kind": "replay", "decisions": hinted["decisions"]})
                       for _ in range(20)]
            results["witness"].update({
                "verdict": hinted["verdict"], "decisions": hinted["decisions"],
                "pre": hinted["pre"], "post": hinted["post"], "violations": hinted["violations"],
                "policy_stats": hinted.get("policy_stats"),
                "replay_20": {"violations": sum(r["verdict"] == "VIOLATION" for r in replays),
                              "distinct_trace_hashes": len({r["trace_hash"] for r in replays}),
                              "matches": all(r["trace_hash"] == hinted["trace_hash"]
                                             for r in replays)},
                "exhaustive_buggy": exhaustive(session, "buggy", WITNESS)})
            rand = collections.Counter(
                execute(session, "buggy", WITNESS, {"kind": "random", "seed": f"d3:{i}"})["verdict"]
                for i in range(500))
            results["witness"]["random_schedules_500"] = dict(rand)

            results["setup_necessity"] = {}
            for k in range(len(READY)):
                w = {"setup": READY[:k], "concurrent": WITNESS["concurrent"]}
                results["setup_necessity"][f"first_{k}_of_3_setup_calls"] = exhaustive(
                    session, "buggy", w)

            harder = [WITNESS,
                      {"setup": [call("create"), call("restock", qty=3), call("publish")],
                       "concurrent": [call("purchase", qty=2), call("purchase", qty=2)]},
                      {"setup": [call("create"), call("restock", qty=2), call("publish")],
                       "concurrent": [call("purchase", qty=1)] * 3}]
            results["corrected_variant"] = [{"workload": w, **exhaustive(session, "fixed", w)}
                                            for w in harder]
    finally:
        box.down()

    results["prediction_m1"] = prediction(results)
    (HERE / "results.json").write_text(json.dumps(results, indent=1))
    print(json.dumps({k: v for k, v in results.items() if k != "witness"}, indent=1)[:3000])
    w = results["witness"]
    print("witness:", w["verdict"], w["pre"], "->", w["post"], w["replay_20"],
          w["exhaustive_buggy"], w["random_schedules_500"])


if __name__ == "__main__":
    main()
