"""Author-side safety check of the held-out bases before C2 (PROTOCOL.md in this directory).

  base_safety.py <sealed root> [--minutes-per-base N]

Not one of the frozen C2 checks. It looks for a contract violation on the **unmutated** bases
under concurrency, so that a base does not become a false positive in C5, where one VIOLATION on
a base stops the run. No mutant exists when it runs, and it never runs on one.

For each base, in the sandbox, with the frozen executor and oracle:
1. pairs: from the empty setup and every setup on the base's M3+ frontier
   (``heldout.frontier``), every unordered pair of catalog calls that share a value of a key
   argument (an argument whose domain is the observation's), neither of them the observation's
   read, explored depth-first until exhausted or 2,000 schedules;
2. groups: 1,000 workloads of 3 or 4 such calls on one key value, after a setup drawn from the
   same list, each under 5 random schedules;
3. stress: 1,000 workloads of M1's draw (``space.random_workload``), each run once without the
   scheduler.
Stages run in that order until the time limit, and whatever was not reached is reported.
Screen and results file: counts only. Any record that is not a clean PASS goes, with its
workload and decisions, to <sealed root>/private/base_safety/.
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))

import importlib.util  # noqa: E402

from mylonite import space  # noqa: E402
from mylonite.sandbox import Sandbox  # noqa: E402
from mylonite.scheduler import next_prefix  # noqa: E402

_spec = importlib.util.spec_from_file_location("heldout", REPO / "experiments/heldout-v1/heldout.py")
heldout = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(heldout)

PAIR_CAP, GROUPS, GROUP_SCHEDULES, STRESS = 2000, 1000, 5, 1000


def key_values(target, call):
    domain = target["observe"]["for_each"]
    args = target["operations"][call["op"]]["args"]
    return {call["args"][name] for name, spec in args.items() if spec["domain"] == domain}


def writers(target):
    read = target["observe"]["op"]
    return [c for c in space.op_calls(target) if c["op"] != read]


def pairs(target):
    calls = writers(target)
    return [(a, b) for i, a in enumerate(calls) for b in calls[i:]
            if key_values(target, a) & key_values(target, b)]


def group(target, setups, rng):
    calls = writers(target)
    value = rng.choice(target["domains"][target["observe"]["for_each"]])
    mine = [c for c in calls if value in key_values(target, c)]
    return {"setup": rng.choice(setups), "concurrent": [rng.choice(mine)
                                                        for _ in range(rng.randint(3, 4))]}


class Tally:
    def __init__(self, base, private):
        self.base, self.private = base, private
        self.counts = {"executions": 0, "PASS": 0, "VIOLATION": 0, "INCONCLUSIVE": 0,
                       "soundness_problems": 0, "harness_errors": 0, "forced_decisions": 0}
        self.flagged = []

    def add(self, stage, record):
        c = self.counts
        c["executions"] += 1
        c[record["verdict"]] = c.get(record["verdict"], 0) + 1
        c["soundness_problems"] += bool(record.get("soundness_problems"))
        c["harness_errors"] += bool(record.get("harness_error"))
        c["forced_decisions"] += record.get("forced_decisions", 0)
        if record["verdict"] != "PASS" or record.get("soundness_problems") or record.get("harness_error"):
            self.flagged.append({"stage": stage, **{k: record.get(k) for k in (
                "workload", "decisions", "verdict", "violations", "ops", "pre", "post",
                "soundness_problems", "harness_error")}})


def check(root, base, deadline):
    target = heldout.load_target(root, base)
    target["variants"] = {"base": f"heldout.{base}.service"}
    rng = random.Random(f"base-safety:{base}")
    tally = Tally(base, Path(root) / "private" / "base_safety")
    out = {"stages": {}}
    box = Sandbox(f"mylonite-safety-{base}", REPO, target_root=Path(root) / "heldout")
    box.up()
    try:
        with box.session(target) as session:
            def execute(workload, policy):
                return session.request({"op": "execute", "variant": "base", "workload": workload,
                                        "policy": policy})[0]

            setups = [[]] + [s for s in heldout.frontier(session, target, "base") if s]
            out["setups"] = len(setups)
            todo = [(s, a, b) for s in setups for a, b in pairs(target)]
            done = exhausted = 0
            for setup, a, b in todo:
                if time.monotonic() > deadline:
                    break
                workload, prefix, n = {"setup": setup, "concurrent": [a, b]}, [], 0
                while n < PAIR_CAP:
                    record = execute(workload, {"kind": "prefix", "prefix": prefix})
                    tally.add("pairs", record)
                    n += 1
                    prefix = next_prefix(record["steps"])
                    if prefix is None:
                        exhausted += 1
                        break
                done += 1
            out["stages"]["pairs"] = {"planned": len(todo), "explored": done,
                                      "exhausted": exhausted, "capped": done - exhausted}
            done = 0
            for i in range(GROUPS):
                if time.monotonic() > deadline:
                    break
                workload = group(target, setups, rng)
                for k in range(GROUP_SCHEDULES):
                    tally.add("groups", execute(workload, {"kind": "random",
                                                           "seed": f"base-safety:{base}:{i}:{k}"}))
                done += 1
            out["stages"]["groups"] = {"planned": GROUPS, "run": done}
            done = 0
            for _ in range(STRESS):
                if time.monotonic() > deadline:
                    break
                workload = space.random_workload(target, rng)
                tally.add("stress", session.request({"op": "stress", "variant": "base",
                                                     "workload": workload})[0])
                done += 1
            out["stages"]["stress"] = {"planned": STRESS, "run": done}
    finally:
        box.down()
    out["counts"] = tally.counts
    out["flagged"] = len(tally.flagged)
    if tally.flagged:
        tally.private.mkdir(parents=True, exist_ok=True)
        (tally.private / f"{base}.json").write_text(json.dumps(tally.flagged, indent=1))
    out["passes"] = tally.counts["VIOLATION"] == 0 and tally.counts["soundness_problems"] == 0
    out["complete"] = (out["stages"]["pairs"]["explored"] == out["stages"]["pairs"]["planned"]
                       and out["stages"]["groups"]["run"] == GROUPS
                       and out["stages"]["stress"]["run"] == STRESS)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("--minutes-per-base", type=float, default=60)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if REPO in root.parents or root == REPO:
        sys.exit("refusing: the sealed root must be outside the repository")
    started = time.time()
    results = {}
    for base in heldout.BASES:
        t0 = time.monotonic()
        results[base] = check(root, base, t0 + 60 * args.minutes_per_base)
        results[base]["seconds"] = round(time.monotonic() - t0, 1)
        print(json.dumps({base: results[base]}), flush=True)
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    name = time.strftime("%Y%m%d-%H%M%S", time.gmtime(started)) + ".json"
    (out / name).write_text(json.dumps({"started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                                     time.gmtime(started)),
                                        "limits": {"pair_cap": PAIR_CAP, "groups": GROUPS,
                                                   "group_schedules": GROUP_SCHEDULES,
                                                   "stress": STRESS,
                                                   "minutes_per_base": args.minutes_per_base},
                                        "results": results}, indent=1) + "\n")
    print(f"wrote {out / name}")
    sys.exit(0 if all(r["passes"] for r in results.values()) else 1)


if __name__ == "__main__":
    main()
