"""Stall check on the corrected cart, before the D1 baseline experiment (PROTOCOL.md §2).

On both builds:
  pairs   every depth-first schedule of the gate's 2-operation workloads, cycled; a schedule
          must give the same verdict and trace hash every time
  random  random workloads from D1's space (as M1 draws them) under random schedules
Counts inconclusive executions, forced decisions and soundness problems by kind, and keeps the
first few inconclusive records. No model calls.

Usage: stall.py <label> [pair executions per build] [random executions per build]
"""

import collections
import json
import random
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-10-28-d1-gate"))

import d1  # noqa: E402
from d1 import REPO  # noqa: E402
from gate import WORKLOADS  # noqa: E402
from mylonite import space  # noqa: E402
from mylonite.scheduler import next_prefix  # noqa: E402

PAIRS = ["A_same_item", "A_two_items", "B_add_vs_empty", "ctl_two_users"]


def kind(problem):
    return problem.split(" on conn")[0].split(" after")[0].lstrip("0123456789 ")


class Tally:
    def __init__(self):
        self.verdicts, self.problems = collections.Counter(), collections.Counter()
        self.slow = self.forced = self.unstable = 0
        self.ms, self.examples, self.seen = [], [], {}

    def add(self, out, key=None):
        self.verdicts[out["verdict"]] += 1
        self.ms.append(out["ms"])
        self.slow += out["ms"] > 100
        self.forced += out["forced_decisions"]
        for p in out["soundness_problems"]:
            self.problems[kind(p)] += 1
        if out["verdict"] == "INCONCLUSIVE" and len(self.examples) < 3:
            self.examples.append({k: out[k] for k in ("workload", "decisions", "soundness_problems",
                                                      "harness_error", "ms", "ops")}
                                 | {"trace": [[e["event"], e.get("op"), e.get("cmd")] for e in out["trace"]]})
        if key is not None and out["verdict"] != "INCONCLUSIVE":
            got = (out["verdict"], out["trace_hash"])
            self.unstable += self.seen.setdefault(key, got) != got

    def report(self, wall_s):
        ms = sorted(self.ms)
        return {"executions": len(ms), "verdicts": dict(self.verdicts), "over_100ms": self.slow,
                "forced_decisions": self.forced, "soundness_problems": dict(self.problems),
                "unstable_schedules": self.unstable, "median_ms": ms[len(ms) // 2],
                "p99_ms": ms[int(0.99 * (len(ms) - 1))], "wall_s": round(wall_s, 1),
                "inconclusive_examples": self.examples}


def main():
    label = sys.argv[1]
    n_pairs = int(sys.argv[2]) if len(sys.argv) > 2 else 1200
    n_random = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True,
                            text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain"],
                           capture_output=True, text=True).stdout.strip()
    report = {"label": label, "commit": commit, "dirty": bool(dirty), "builds": {}}
    with d1.bringup(name="mylonite-d1stall") as (box, session, target, info):
        report["services"] = info["services"]

        def run(variant, workload, policy):
            return session.request({"op": "execute", "variant": variant, "workload": workload,
                                    "policy": policy})[0]

        for variant in ("buggy", "fixed"):
            schedules = []
            for name in PAIRS:
                prefix = []
                while prefix is not None:
                    out = run(variant, WORKLOADS[name], {"kind": "prefix", "prefix": prefix})
                    schedules.append((name, prefix))
                    prefix = next_prefix(out["steps"])
            pairs, started = Tally(), time.monotonic()
            for i in range(n_pairs):
                name, prefix = schedules[i % len(schedules)]
                pairs.add(run(variant, WORKLOADS[name], {"kind": "prefix", "prefix": prefix}),
                          key=(name, tuple(prefix)))
            row = {"pairs": pairs.report(time.monotonic() - started) | {"schedules": len(schedules)}}
            rng, rand, started = random.Random(f"stall:{variant}"), Tally(), time.monotonic()
            for i in range(n_random):
                rand.add(run(variant, space.random_workload(target, rng),
                             {"kind": "random", "seed": f"stall:{variant}:{i}"}))
            if n_random:
                row["random"] = rand.report(time.monotonic() - started)
            report["builds"][variant] = row
            for part, r in row.items():
                print(variant, part, json.dumps({k: v for k, v in r.items() if k != "inconclusive_examples"}),
                      flush=True)
    out = REPO / "runs" / f"d1stall-{label}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(report, indent=1) + "\n")
    print(out)


if __name__ == "__main__":
    main()
