"""Check a finished D1 baseline run against PROTOCOL.md §6. Host side, standard library only.

Written before the run, with the protocol. Reads the raw run directory (runs/d1base-<ts>/) for
every execution and verification, not the runner's own summary, and the pre-run reports copied
into the results directory (results/<ts>/pre_run/).

Usage: check_validity.py runs/d1base-<ts> results/<ts> --commit SHA
"""

import argparse
import collections
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))

from mylonite import space  # noqa: E402

GATE = REPO / "experiments/2026-10-28-d1-gate"
UNCHANGED_SINCE = "20f1666"
UNCHANGED = ["experiments/2026-10-29-pilot", "experiments/2026-10-28-a2-no-source",
             "experiments/2026-10-28-d1-gate/results", "experiments/2026-10-28-d1-gate/build.json",
             "targets/d1-otel-cart/Dockerfile", "targets/d1-otel-cart/build.py"]


def lines(path):
    with open(path) as f:
        for line in f:
            yield json.loads(line)


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("results_dir")
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    run, results = Path(args.run_dir), Path(args.results_dir)
    manifest = json.loads((run / "manifest.json").read_text())
    trials = json.loads((run / "trials.json").read_text())
    cfg = json.loads((HERE / "config.json").read_text())
    target = json.loads((REPO / cfg["target"]).read_text())
    commit = git("rev-parse", args.commit).stdout.decode().strip()
    checks = []

    def check(name, ok, detail):
        checks.append({"criterion": name, "pass": bool(ok), "detail": detail})

    # V1: provenance
    committed_cfg = git("show", f"{commit}:experiments/2026-10-29-d1-baselines/config.json").stdout
    build = json.loads((GATE / "build.json").read_text())
    gate_run = json.loads((GATE / "results/20261028-193603.json").read_text())
    images = manifest["bringup"]["images"]
    services = manifest["bringup"]["service_images"]
    check("V1 provenance",
          manifest["git_commit"] == commit and not manifest["git_dirty"]
          and json.loads(committed_cfg) == manifest["config"] == cfg
          and images["executor"] == gate_run["isolation"]["images"]["executor"]
          and all(services[v] == build["variants"][v]["image_id"] for v in ("buggy", "fixed")),
          {"manifest_commit": manifest["git_commit"], "dirty": manifest["git_dirty"],
           "config_sha256": hashlib.sha256(committed_cfg).hexdigest(), "images": images,
           "service_images": services})

    # V2: trial set
    keys = collections.Counter((t["method"], t["seed"]) for t in trials)
    expected = {(m, s) for m in cfg["methods"] for s in cfg["seeds"]}
    errors = [t["status"] for t in trials if t["status"].startswith("error")]
    check("V2 trials", set(keys) == expected and all(v == 1 for v in keys.values()) and not errors,
          {"trials": len(trials), "errors": errors})

    # V3: verified witnesses
    bad = []
    for t in trials:
        if t["status"] != "verified":
            continue
        v = t["verification"]
        c = v["corrected"]
        if not (v["replays"] == v["replay_violations"] == v["replay_hash_matches"] == 20
                and c["mode"] == "exhaustive" and c["verdicts"].get("PASS") == c["schedules"]
                and c["soundness_problems"] == 0):
            bad.append(f"{t['method']}/{t['seed']}")
    check("V3 verification", not bad, {"failing": bad})

    # raw log
    search = collections.defaultdict(list)          # trial -> search execution records
    verifications = collections.defaultdict(list)   # trial -> (n, result)
    invalid = []
    for ev in lines(run / "executions.jsonl"):
        if ev["event"] in ("execution", "stress"):
            search[ev["trial"]].append(ev)
            problems = space.workload_problems(target, ev["record"]["workload"])
            if problems:
                invalid.append({"trial": ev["trial"], "n": ev["n"], "problems": problems})
        elif ev["event"] == "verification":
            verifications[ev["trial"]].append((ev["n"], ev["result"]))
    check("V4 workloads in D1's space", not invalid, {"invalid": invalid[:10], "count": len(invalid)})

    over = [f"{t['method']}/{t['seed']}" for t in trials if t["executions"] > cfg["budget"]["executions"]]
    early = [f"{t['method']}/{t['seed']}" for t in trials
             if t["status"] == "censored:executions" and t["executions"] != cfg["budget"]["executions"]]
    check("V5 budgets", not over and not early, {"over_budget": over, "censored_early": early})

    mismatch = []
    for t in trials:
        key = f"{t['target']}/{t['method']}/{t['seed']}"
        verified = [n for n, r in verifications[key] if r["verified"]]
        if t["status"] == "verified":
            ok = verified[:1] == [t["e1_executions"]]
        else:
            ok = not verified
        profiles = t["counters"].get("profile", 0)
        if len(search[key]) + profiles != t["executions"]:
            ok = False
        if not ok:
            mismatch.append({"trial": key, "e1": t["e1_executions"], "verified_at": verified,
                             "logged": len(search[key]) + profiles, "executions": t["executions"]})
    check("V6 E1 from the raw log", not mismatch, {"mismatches": mismatch})

    fixed_violations = [{"trial": k, "n": n} for k, vs in verifications.items() for n, r in vs
                        if r["corrected"]["verdicts"].get("VIOLATION")]
    check("V7 no violation on the corrected build", not fixed_violations, {"found": fixed_violations})

    rates, reruns = {}, []
    for method in cfg["methods"]:
        records = [ev["record"] for k, evs in search.items() if k.split("/")[1] == method for ev in evs]
        inconclusive = sum(r["verdict"] == "INCONCLUSIVE" for r in records)
        rates[method] = {"search_executions": len(records), "inconclusive": inconclusive}
    for k, vs in verifications.items():
        for n, r in vs:
            if "inconclusive_reruns" in r:
                reruns.append({"trial": k, "n": n, "reruns": r["inconclusive_reruns"],
                               "causes": [x["soundness_problems"] or x["harness_error"] for x in r["rejected"]]})
    check("V8 harness health",
          all(r["inconclusive"] <= 0.01 * r["search_executions"] for r in rates.values()),
          {"by_method": rates, "verification_reruns": reruns})

    pre = {p.name: json.loads(p.read_text()) for p in sorted((results / "pre_run").glob("*.json"))}
    sec = [r for n, r in pre.items() if n.startswith("d1sec-")]
    stall = [r for n, r in pre.items() if n.startswith("d1stall-")]

    def stall_ok(r):
        rows = r["builds"].values()
        return (r["commit"] == commit and r.get("dirty") is False
                and all(row["pairs"]["verdicts"].get("INCONCLUSIVE", 0) == 0
                        and row["pairs"]["unstable_schedules"] == 0
                        and row["random"]["verdicts"].get("INCONCLUSIVE", 0) <= 0.001 * row["random"]["executions"]
                        and row["random"]["executions"] >= 4000 and row["pairs"]["executions"] >= 1200
                        for row in rows))
    check("V9 pre-run checks",
          len(sec) == 1 and sec[0]["all_pass"] and sec[0]["commit"] == commit and sec[0].get("dirty") is False
          and len(stall) == 1 and stall_ok(stall[0]),
          {"files": sorted(pre)})

    diff = git("diff", "--quiet", UNCHANGED_SINCE, commit, "--", *UNCHANGED).returncode
    worktree = git("diff", "--quiet", "HEAD", "--", *UNCHANGED).returncode
    check("V10 earlier experiments unchanged", diff == 0 and worktree == 0,
          {"since": UNCHANGED_SINCE, "paths": UNCHANGED})

    print(json.dumps(checks, indent=1, default=str))
    print("ALL PASS" if all(c["pass"] for c in checks) else "SOME CHECKS FAILED")


if __name__ == "__main__":
    main()
