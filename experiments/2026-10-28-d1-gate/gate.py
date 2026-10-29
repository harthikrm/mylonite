"""D1 feasibility gate (README.md in this directory). No model calls.

Every stage runs through the executor path all methods share (reset, setup, scheduled round,
observation, oracle), on the real cart built from source, in the sandbox.

  (always)    isolation: container flags as Docker applied them; egress probe; cart startup
  serial      EVALUATION_PLAN.md §8.4: serial requests give the contract-expected cart; the same
              serial workload twice from fresh resets gives the same result (no hidden state)
  gate_k      ROADMAP gate K: depth-first exploration of fixed workloads on both builds; the
              first violation replayed 20 times; the corrected build must have none
  costs       per-execution time for the workloads each method actually runs
  baselines   one M1 and one M3+ trial at seed 0 (outside the planned seeds 1-5): feasibility only
  natural     no proxy: the cart talks to Valkey directly and two AddItem calls race in real time

Writes raw records to runs/d1gate-<ts>/ (git-ignored) and the summary to results/<ts>.json.

Usage: gate.py [stage ...]   (default: all stages)
"""

import json
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import d1  # noqa: E402
from d1 import REPO  # noqa: E402
from mylonite import methods, space  # noqa: E402
from mylonite.sandbox import EXECUTOR_D1_IMAGE, LOCKED_DOWN, limits  # noqa: E402
from mylonite.scheduler import next_prefix  # noqa: E402

STAGES = ("serial", "gate_k", "costs", "baselines", "natural")
P1, P2 = "OLJCESPC7Z", "66VCHSJNUP"


def add(user, product, quantity):
    return {"op": "AddItem", "args": {"user_id": user, "product_id": product, "quantity": quantity}}


WORKLOADS = {  # fixed in advance, before any exploration of the corrected build
    "A_same_item": {"setup": [], "concurrent": [add("u1", P1, 1), add("u1", P1, 1)]},
    "A_two_items": {"setup": [], "concurrent": [add("u1", P1, 1), add("u1", P2, 2)]},
    "A_three_adds": {"setup": [], "concurrent": [add("u1", P1, 1), add("u1", P1, 2), add("u1", P2, 3)]},
    "B_add_vs_empty": {"setup": [add("u1", P1, 1)],
                       "concurrent": [add("u1", P1, 1), {"op": "EmptyCart", "args": {"user_id": "u1"}}]},
    "ctl_two_users": {"setup": [], "concurrent": [add("u1", P1, 1), add("u2", P1, 1)]},
}
GATE_CFG = {
    "budget": {"executions": 1000, "method_seconds": 900, "schedules_per_experiment": 50},
    "verification": {"replays": 20, "corrected_exhaustive_cap": 5000, "corrected_bounded_random": 2000},
    "prices": {"input": 1.25, "cached": 0.15, "output": 4.25, "compute_per_second": 1.11e-05},
}


class Raw:
    def __init__(self, run_dir):
        self.file = (run_dir / "records.jsonl").open("w")

    def __call__(self, stage, **fields):
        self.file.write(methods.json_line({"stage": stage, **fields}) + "\n")
        self.file.flush()


def execute(session, variant, workload, policy):
    out, rtt = session.request({"op": "execute", "variant": variant, "workload": workload,
                                "policy": policy})
    return out, rtt


def stats(values):
    values = sorted(values)
    if not values:
        return None
    return {"n": len(values), "median": round(statistics.median(values), 3),
            "p90": round(values[int(0.9 * (len(values) - 1))], 3),
            "mean": round(statistics.fmean(values), 3), "max": round(values[-1], 3)}


def problems_of(record):
    return {"soundness": record["soundness_problems"], "harness_error": record["harness_error"],
            "forced": record["forced_decisions"]}


# --- stages -------------------------------------------------------------------------------------

def stage_serial(session, target, raw):
    serial = {"setup": [add("u1", P1, 1), add("u1", P1, 2), add("u1", P1, 3), add("u1", P2, 2)],
              "concurrent": []}
    expected = {"u1": {P1: 6, P2: 2}, "u2": {}}
    out = {}
    for variant in ("buggy", "fixed"):
        runs = [execute(session, variant, serial, {"kind": "prefix", "prefix": []})[0] for _ in range(2)]
        emptied = execute(session, variant, {"setup": serial["setup"] + [{"op": "EmptyCart", "args": {"user_id": "u1"}}],
                                             "concurrent": []}, {"kind": "prefix", "prefix": []})[0]
        for r in runs + [emptied]:
            raw("serial", variant=variant, record=r)
        out[variant] = {"observed": runs[0]["pre"], "expected": expected,
                        "matches_contract": runs[0]["pre"] == expected,
                        "same_twice_from_reset": runs[0]["pre"] == runs[1]["pre"],
                        "after_empty": emptied["pre"], "empty_ok": emptied["pre"] == {"u1": {}, "u2": {}},
                        "setup_outcomes": runs[0]["setup_outcomes"]}
    return out


def explore(session, variant, workload, raw, cap=5000):
    records, prefix = [], []
    while len(records) < cap:
        record = execute(session, variant, workload, {"kind": "prefix", "prefix": prefix})[0]
        records.append(record)
        raw("gate_k", variant=variant, record=record)
        prefix = next_prefix(record["steps"])
        if prefix is None:
            break
    verdicts = {v: sum(r["verdict"] == v for r in records) for v in ("PASS", "VIOLATION", "INCONCLUSIVE")}
    first = next((r for r in records if r["verdict"] == "VIOLATION"), None)
    return records, {"schedules": len(records), "exhausted": prefix is None, "verdicts": verdicts,
                     "forced_decisions": sum(r["forced_decisions"] for r in records),
                     "soundness_problems": sum(len(r["soundness_problems"]) for r in records),
                     "harness_errors": sum(r["harness_error"] is not None for r in records),
                     "distinct_traces": len({r["trace_hash"] for r in records}),
                     "first_violation_at": records.index(first) + 1 if first else None,
                     "first_violation": None if first is None else {
                         k: first[k] for k in ("decisions", "pre", "post", "violations", "trace_hash")}
                     | {"store_order": [[e["op"], e["cmd"]] for e in first["trace"] if e["event"] == "exec"]}}


def stage_gate_k(session, target, raw):
    out = {}
    for name, workload in WORKLOADS.items():
        row = {}
        for variant in ("buggy", "fixed"):
            records, summary = explore(session, variant, workload, raw)
            first = next((r for r in records if r["verdict"] == "VIOLATION"), None)
            if first is not None:
                replays = [execute(session, variant, workload,
                                   {"kind": "replay", "decisions": first["decisions"]})[0] for _ in range(20)]
                for r in replays:
                    raw("gate_k_replay", variant=variant, workload=name, record=r)
                summary["replay"] = {"runs": 20,
                                     "violations": sum(r["verdict"] == "VIOLATION" for r in replays),
                                     "hash_matches": sum(r["trace_hash"] == first["trace_hash"] for r in replays)}
            row[variant] = summary
        out[name] = row
    return out


def stage_costs(session, target, raw, n=300):
    out = {}
    rng = random.Random("d1-costs")

    def measure(label, make):
        ms, rtt_extra, verdicts, problems = [], [], {}, 0
        for i in range(n):
            variant, workload, policy = make(i)
            record, rtt = execute(session, variant, workload, policy)
            raw("costs", label=label, record=record)
            ms.append(record["ms"])
            rtt_extra.append(max(rtt * 1000 - record["ms"], 0.0))
            verdicts[record["verdict"]] = verdicts.get(record["verdict"], 0) + 1
            problems += bool(record["soundness_problems"] or record["harness_error"])
        out[label] = {"exec_ms": stats(ms), "harness_roundtrip_ms": stats(rtt_extra),
                      "verdicts": verdicts, "executions_with_problems": problems}

    empty = {"setup": [], "concurrent": []}
    measure("floor: reset + observe, empty workload", lambda i: ("buggy", empty, {"kind": "prefix", "prefix": []}))
    a = WORKLOADS["A_same_item"]
    schedules, prefix = [], []
    while prefix is not None:  # the 8 schedules of A_same_item, cycled
        record = execute(session, "buggy", a, {"kind": "prefix", "prefix": prefix})[0]
        schedules.append(prefix)
        prefix = next_prefix(record["steps"])
    measure("A_same_item, depth-first schedules (buggy)",
            lambda i: ("buggy", a, {"kind": "prefix", "prefix": schedules[i % len(schedules)]}))
    measure("A_same_item, depth-first schedules (fixed)",
            lambda i: ("fixed", a, {"kind": "prefix", "prefix": schedules[i % len(schedules)]}))
    measure("M1 draws: random workload, random schedule (buggy)",
            lambda i: ("buggy", space.random_workload(target, rng), {"kind": "random", "seed": f"costs:{i}"}))
    calls = space.op_calls(target)
    ms = []
    for i in range(n):
        setup = space.random_workload(target, rng)["setup"]
        result, _ = session.request({"op": "profile", "variant": "buggy", "setup": setup, "call": rng.choice(calls)})
        raw("costs", label="profile", result=result)
        ms.append(result["ms"])
    out["M3+ profile: one call after a random setup (buggy)"] = {"exec_ms": stats(ms)}
    return out


def stage_baselines(session, target, raw):
    out = {}
    for method in ("M1", "M3+"):
        result = methods.run_trial(method, session, target, 0, GATE_CFG,
                                   lambda e, m=method: raw("baselines", method=m, event=e))
        raw("baselines_trial", result=result)
        out[method] = {k: result[k] for k in ("status", "e1_executions", "executions", "method_s",
                                              "exec_s", "overhead_s", "verification_s", "counters")}
        out[method]["verified"] = bool(result["verification"] and result["verification"]["verified"])
        out[method]["verification"] = result["verification"]
        out[method]["witness"] = result["witness"] and {k: result["witness"][k] for k in ("workload", "decisions", "post")}
    return out


def stage_natural(box, target, raw, rounds=1000):
    """Two AddItem(u1, P1, 1) calls released together, with the cart connected to Valkey directly."""
    runtime = target["service_runtime"]
    out = {}
    for variant in ("buggy", "fixed"):
        name = f"direct-{variant}"
        env = dict(runtime["env"], VALKEY_ADDR=f"{box.store}:6379")
        container = box.start_service(name, target["services"][variant]["image"], env,
                                      runtime["memory"], runtime["user"])
        cmd = ["docker", "run", "--rm", "--network", box.network, *LOCKED_DOWN, *limits("512m"),
               "--user", "65534:65534", "--tmpfs", "/tmp:rw,size=16m,noexec",
               "-v", f"{REPO / 'src'}:/app/src:ro", "-v", f"{HERE / 'natural.py'}:/app/natural.py:ro",
               "--entrypoint", "python", EXECUTOR_D1_IMAGE, "/app/natural.py",
               f"{container}:7070", f"{box.store}:6379", str(rounds)]
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if done.returncode != 0:
            raise RuntimeError(f"natural {variant}: {done.stderr[-2000:]}")
        result = json.loads(done.stdout)
        raw("natural", variant=variant, result=result)
        out[variant] = result
    return out


def main():
    wanted = sys.argv[1:] or list(STAGES)
    assert set(wanted) <= set(STAGES), wanted
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = REPO / "runs" / f"d1gate-{stamp}"
    run_dir.mkdir(parents=True)
    raw = Raw(run_dir)
    report = {"stamp": stamp, "stages": wanted,
              "commit": subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True,
                                       text=True).stdout.strip(),
              "dirty": bool(subprocess.run(["git", "-C", str(REPO), "status", "--porcelain"],
                                           capture_output=True, text=True).stdout.strip()),
              "build": json.loads((HERE / "build.json").read_text())}
    started = time.monotonic()
    with d1.bringup() as (box, session, target, info):
        report["isolation"] = info
        for stage in wanted:
            t0 = time.monotonic()
            if stage == "serial":
                report[stage] = stage_serial(session, target, raw)
            elif stage == "gate_k":
                report[stage] = stage_gate_k(session, target, raw)
            elif stage == "costs":
                report[stage] = stage_costs(session, target, raw)
            elif stage == "baselines":
                report[stage] = stage_baselines(session, target, raw)
            elif stage == "natural":
                report[stage] = stage_natural(box, target, raw)
            report.setdefault("stage_seconds", {})[stage] = round(time.monotonic() - t0, 1)
            print(f"{stage} done in {report['stage_seconds'][stage]}s", flush=True)
        report["cart_logs_tail"] = {v: d1.cart_logs(box, v, target, tail=15) for v in ("buggy", "fixed")}
    report["wall_s"] = round(time.monotonic() - started, 1)
    out = HERE / "results" / f"{stamp}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=1, sort_keys=True, default=str) + "\n")
    print(out)


if __name__ == "__main__":
    main()
