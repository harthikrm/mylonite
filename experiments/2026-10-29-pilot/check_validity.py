"""Check a finished pilot run against READINESS.md §8.B and §8.C. Host side, standard library only.

Written after the 2026-10-28 run, to the criteria fixed before it. Reads the raw run directory
(runs/pilot-<ts>/), not the runner's own summary, so each criterion is checked against what
actually executed:
  B1  every recorded model request is clean under an independent re-run of audit.findings
  B2  no error status; INCONCLUSIVE <= 1% of executions per method; 0 soundness problems
  B3  every corrected-variant schedule passed, in every verification of the run
  B4  every verified trial: replay 20/20 with one hash, corrected mode recorded
  B5  D2: M1 and M3+ verified in 5/5
  B6  spend <= cap; every trial recorded; clean manifest at the expected commit
Also cross-checks execution accounting (logged executions and profiles against each trial's
count) and the method-seconds cap.

Usage: check_validity.py runs/pilot-<ts> [--commit SHA]
"""

import argparse
import collections
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from mylonite import audit  # noqa: E402


def lines(path):
    with open(path) as f:
        for line in f:
            yield json.loads(line)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("--commit")
    args = parser.parse_args()
    run = Path(args.run_dir)
    manifest = json.loads((run / "manifest.json").read_text())
    cfg = manifest["config"]
    trials = json.loads((run / "trials.json").read_text())
    targets = {t["target"]: t for t in
               (json.loads((REPO / p).read_text()) for p in cfg["targets"])}

    per_method = collections.defaultdict(collections.Counter)
    per_trial_n = collections.defaultdict(int)
    soundness, corrected_bad, requests = [], [], []
    for ev in lines(run / "executions.jsonl"):
        key, kind = ev["trial"], ev["event"]
        target, method, _ = key.split("/")
        if kind in ("execution", "profile"):
            rec = ev["record"] if kind == "execution" else ev["result"]
            per_method[(target, method)]["executions"] += 1
            per_trial_n[key] = max(per_trial_n[key], ev["n"])
            if rec.get("verdict") == "INCONCLUSIVE" or rec.get("harness_error"):
                per_method[(target, method)]["inconclusive"] += 1
            soundness += [(key, ev["n"], p) for p in rec.get("soundness_problems", [])]
        elif kind == "verification":
            corr = ev["result"]["corrected"]
            if corr["soundness_problems"] or set(corr["verdicts"]) - {"PASS"}:
                corrected_bad.append((key, corr))
        elif kind == "model_call":
            requests.append((key, ev["request"]))
    recorded_calls = list(lines(run / "model_calls.jsonl"))

    checks = []

    def check(name, ok, detail):
        checks.append({"criterion": name, "pass": bool(ok), "detail": detail})

    dirty = [(key, f) for key, body in requests
             for f in audit.findings(body, targets[key.split("/")[0]], REPO)]
    check("B1 audit re-run on every model request", not dirty and len(requests) == len(recorded_calls),
          {"requests": len(requests), "recorded_calls": len(recorded_calls), "findings": dirty})

    errors = [t for t in trials if t["status"].startswith("error")]
    rates = {f"{t}/{m}": {"executions": c["executions"], "inconclusive": c["inconclusive"]}
             for (t, m), c in sorted(per_method.items())}
    worst = max((c["inconclusive"] / c["executions"] for c in per_method.values()), default=0)
    check("B2 no error status", not errors, [f"{t['target']}/{t['method']}/{t['seed']}: {t['status']}"
                                            for t in errors])
    check("B2 INCONCLUSIVE <= 1% per method", worst <= 0.01, rates)
    check("B2 0 soundness problems", not soundness, soundness[:20])

    check("B3 corrected variant: every schedule PASS", not corrected_bad, corrected_bad[:20])

    verified = [t for t in trials if t["status"] == "verified"]
    weak = [f"{t['target']}/{t['method']}/{t['seed']}" for t in verified
            if not (t["verification"]["verified"]
                    and t["verification"]["replay_violations"] == cfg["verification"]["replays"]
                    and t["verification"]["replay_hash_matches"] == cfg["verification"]["replays"]
                    and t["verification"]["corrected"]["mode"])]
    modes = collections.Counter(t["verification"]["corrected"]["mode"] for t in verified)
    check("B4 every hit verified, mode recorded", not weak,
          {"verified_trials": len(verified), "corrected_modes": dict(modes), "weak": weak})

    d2 = {m: sum(t["status"] == "verified" for t in trials
                 if t["target"].startswith("d2") and t["method"] == m) for m in ("M1", "M3+")}
    check("B5 D2 sanity: M1 and M3+ verified 5/5", all(v == len(cfg["seeds"]) for v in d2.values()), d2)

    spend = round(sum(t["model_usd"] for t in trials), 6)
    expected = len(cfg["targets"]) * len(cfg["methods"]) * len(cfg["seeds"])
    commit_ok = args.commit is None or manifest["git_commit"] == args.commit
    check("B6 spend <= cap, all trials recorded, clean manifest",
          spend <= cfg["model_cost_cap_usd"] and len(trials) == expected
          and not manifest["git_dirty"] and commit_ok,
          {"model_usd": spend, "cap": cfg["model_cost_cap_usd"], "trials": len(trials),
           "expected": expected, "git_commit": manifest["git_commit"],
           "git_dirty": manifest["git_dirty"]})

    mismatched = {f"{t['target']}/{t['method']}/{t['seed']}": (t["executions"],
                                                                per_trial_n[f"{t['target']}/{t['method']}/{t['seed']}"])
                  for t in trials
                  if t["executions"] != per_trial_n[f"{t['target']}/{t['method']}/{t['seed']}"]}
    over = [f"{t['target']}/{t['method']}/{t['seed']}" for t in trials
            if t["executions"] > cfg["budget"]["executions"]
            or t["method_s"] > cfg["budget"]["method_seconds"]]
    check("accounting: logged executions match each trial's count", not mismatched, mismatched)
    check("accounting: no trial over B_exec or the method-seconds cap", not over, over)

    print(json.dumps(checks, indent=1, default=str))
    print("ALL PASS" if all(c["pass"] for c in checks) else "SOME CHECKS FAILED")
    sys.exit(0 if all(c["pass"] for c in checks) else 1)


if __name__ == "__main__":
    main()
