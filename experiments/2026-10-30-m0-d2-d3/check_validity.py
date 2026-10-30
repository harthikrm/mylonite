"""Check a finished M0 run against PROTOCOL.md §3. Host side, standard library only.

Written before the run, with the protocol. Reads the raw run directory (runs/m0-<ts>/) for
every execution and verification, not the runner's summary, and the same-session regression
copied into the results directory.

Usage: check_validity.py runs/m0-<ts> results/<ts> --commit SHA
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

PILOT_MANIFEST = REPO / "experiments/2026-10-29-pilot/results/20261028-165020/manifest.json"
UNCHANGED_SINCE = "c301ecf"
UNCHANGED = ["experiments/2026-10-29-pilot", "experiments/2026-10-28-a2-no-source",
             "experiments/2026-10-28-d1-gate", "experiments/2026-10-29-d1-baselines", "fixtures"]
PILOT_COMMIT = "db1f84f"


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
    targets = {t["target"]: t for t in (json.loads((REPO / p).read_text()) for p in cfg["targets"])}
    commit = git("rev-parse", args.commit).stdout.decode().strip()
    checks = []

    def check(name, ok, detail):
        checks.append({"criterion": name, "pass": bool(ok), "detail": detail})

    committed_cfg = git("show", f"{commit}:experiments/2026-10-30-m0-d2-d3/config.json").stdout
    pilot_images = json.loads(PILOT_MANIFEST.read_text())["images"]
    check("V1 provenance",
          manifest["git_commit"] == commit and not manifest["git_dirty"]
          and json.loads(committed_cfg) == manifest["config"] == cfg
          and manifest["images"] == pilot_images,
          {"manifest_commit": manifest["git_commit"], "dirty": manifest["git_dirty"],
           "config_sha256": hashlib.sha256(committed_cfg).hexdigest(), "images": manifest["images"],
           "pilot_images": pilot_images})

    keys = collections.Counter((t["target"], t["method"], t["seed"]) for t in trials)
    expected = {(name, m, s) for name in targets for m in cfg["methods"] for s in cfg["seeds"]}
    errors = [t["status"] for t in trials if t["status"].startswith("error")]
    check("V2 trials", set(keys) == expected and all(v == 1 for v in keys.values()) and not errors,
          {"trials": len(trials), "errors": errors})

    bad = []
    for t in trials:
        if t["status"] != "verified":
            continue
        v, c = t["verification"], t["verification"]["corrected"]
        if not (v["replays"] == v["replay_violations"] == v["replay_hash_matches"] == 20
                and c["mode"] in ("exhaustive", "bounded")
                and c["verdicts"].get("PASS") == c["schedules"] and c["soundness_problems"] == 0):
            bad.append(f"{t['target']}/{t['seed']}")
    check("V3 verification", not bad,
          {"failing": bad, "modes": {f"{t['target']}/{t['seed']}": t["verification"]["corrected"]["mode"]
                                     for t in trials if t["verification"]}})

    search = collections.defaultdict(list)
    verifications = collections.defaultdict(list)
    invalid = []
    for ev in lines(run / "executions.jsonl"):
        target = targets[ev["trial"].split("/")[0]]
        if ev["event"] in ("execution", "stress"):
            search[ev["trial"]].append(ev)
            problems = space.workload_problems(target, ev["record"]["workload"])
            if problems:
                invalid.append({"trial": ev["trial"], "n": ev["n"], "problems": problems})
        elif ev["event"] == "verification":
            verifications[ev["trial"]].append((ev["n"], ev["result"]))
    check("V4 workloads in the space", not invalid, {"invalid": invalid[:10], "count": len(invalid)})

    budget = cfg["budget"]
    over = [f"{t['target']}/{t['seed']}" for t in trials if t["executions"] > budget["executions"]]
    early = [f"{t['target']}/{t['seed']}" for t in trials
             if (t["status"] == "censored:executions" and t["executions"] != budget["executions"])
             or (t["status"] == "censored:time" and t["method_s"] < budget["method_seconds"])]
    check("V5 budgets", not over and not early, {"over_budget": over, "censored_early": early})

    mismatch = []
    for t in trials:
        key = f"{t['target']}/{t['method']}/{t['seed']}"
        verified = [n for n, r in verifications[key] if r["verified"]]
        ok = verified[:1] == [t["e1_executions"]] if t["status"] == "verified" else not verified
        ok = ok and len(search[key]) + t["counters"].get("profile", 0) == t["executions"]
        if not ok:
            mismatch.append({"trial": key, "e1": t["e1_executions"], "verified_at": verified,
                             "logged": len(search[key]), "executions": t["executions"]})
    check("V6 E1 from the raw log", not mismatch, {"mismatches": mismatch})

    fixed_violations = [{"trial": k, "n": n} for k, vs in verifications.items() for n, r in vs
                        if r["corrected"]["verdicts"].get("VIOLATION")]
    check("V7 no violation on the corrected build", not fixed_violations, {"found": fixed_violations})

    rates = {}
    for name in targets:
        records = [ev["record"] for k, evs in search.items() if k.startswith(name + "/") for ev in evs]
        rates[name] = {"search_executions": len(records),
                       "inconclusive": sum(r["verdict"] == "INCONCLUSIVE" for r in records)}
    check("V8 harness health", all(r["inconclusive"] <= 0.01 * r["search_executions"] for r in rates.values()),
          {"by_target": rates})

    reg = results / "same_session_regression"
    report = json.loads((reg / "report.json").read_text())
    reg_commit = (reg / "commit.txt").read_text().split()
    check("V9 same-session regression",
          reg_commit == [commit] and report["trials"] == report["identical_trials"]
          == report["identical_event_streams"] == 30 and not report["differences"],
          {k: report[k] for k in ("trials", "identical_trials", "identical_event_streams",
                                  "events_compared", "differences")} | {"commit": reg_commit})

    since = git("diff", "--quiet", UNCHANGED_SINCE, commit, "--", *UNCHANGED).returncode
    worktree = git("diff", "--quiet", "HEAD", "--", *UNCHANGED).returncode
    fixtures = git("diff", "--quiet", PILOT_COMMIT, commit, "--", "fixtures").returncode
    check("V10 earlier experiments and fixtures unchanged", since == worktree == fixtures == 0,
          {"since": UNCHANGED_SINCE, "paths": UNCHANGED, "fixtures_since_pilot": PILOT_COMMIT})

    print(json.dumps(checks, indent=1, default=str))
    print("ALL PASS" if all(c["pass"] for c in checks) else "SOME CHECKS FAILED")


if __name__ == "__main__":
    main()
