"""Check a finished A2 run against PROTOCOL.md §5. Host side, standard library only.

Written before the run, with the protocol. Reads the raw run directory (runs/a2-<ts>/), not the
runner's own summary:
  V1  every recorded request: no source (a2_audit.check) and clean under audit.findings; the
      recorded calls and the logged calls agree
  V2  no error status; INCONCLUSIVE <= 1% of executions; 0 soundness problems
  V3  every corrected-variant schedule passed, in every verification of the run
  V4  every verified trial: replay 20/20 with one hash, corrected mode recorded
  V5  comparable with the pilot: src/, fixtures/, docker/, tests/ hash as in the pilot run; the
      pilot's directory is unchanged since its results commit; every condition in config.json
      equals the pilot's except include_source and the cost cap
  V6  spend <= cap; every trial recorded; clean manifest at the expected commit
Also cross-checks execution accounting and the method-seconds cap.

Usage: check_validity.py runs/a2-<ts> [--commit SHA]
"""

import argparse
import collections
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))

from mylonite import audit  # noqa: E402

import a2_audit  # noqa: E402

SAME_AS_PILOT = ("targets", "seeds", "budget", "verification", "executor", "prices",
                 "report_success_at")


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

    executions, inconclusive = 0, 0
    per_trial_n = collections.defaultdict(int)
    soundness, corrected_bad, requests = [], [], []
    for ev in lines(run / "executions.jsonl"):
        key, kind = ev["trial"], ev["event"]
        if kind in ("execution", "profile"):
            rec = ev["record"] if kind == "execution" else ev["result"]
            executions += 1
            per_trial_n[key] = max(per_trial_n[key], ev["n"])
            inconclusive += rec.get("verdict") == "INCONCLUSIVE" or bool(rec.get("harness_error"))
            soundness += [(key, ev["n"], p) for p in rec.get("soundness_problems", [])]
        elif kind == "verification":
            corr = ev["result"]["corrected"]
            if corr["soundness_problems"] or set(corr["verdicts"]) - {"PASS"}:
                corrected_bad.append((key, corr))
        elif kind == "model_call":
            requests.append((key, ev["round"], ev["request"]))
    recorded = [c for c in lines(run / "model_calls.jsonl") if "request" in c]

    checks = []

    def check(name, ok, detail):
        checks.append({"criterion": name, "pass": bool(ok), "detail": detail})

    found = []
    for key, round_no, body in requests:
        target = targets[key.split("/")[0]]
        found += [(key, round_no, f) for f in audit.findings(body, target, REPO)]
        found += [(key, round_no, p) for p in a2_audit.check(body, target, REPO)[0]]
    logged = {(k, r, a2_audit.canonical(b)) for k, r, b in requests}
    sent = {(c["trial"], c["round"], a2_audit.canonical(c["request"])) for c in recorded}
    check("V1 no source in any request; audit clean; recorded = logged calls",
          not found and logged == sent,
          {"requests": len(requests), "recorded_calls": len(recorded), "problems": found[:20]})

    errors = [f"{t['target']}/{t['method']}/{t['seed']}: {t['status']}" for t in trials
              if t["status"].startswith("error")]
    check("V2 no error status", not errors, errors)
    check("V2 INCONCLUSIVE <= 1%", executions and inconclusive / executions <= 0.01,
          {"executions": executions, "inconclusive": inconclusive})
    check("V2 0 soundness problems", not soundness, soundness[:20])

    check("V3 corrected variant: every schedule PASS", not corrected_bad, corrected_bad[:20])

    verified = [t for t in trials if t["status"] == "verified"]
    replays = cfg["verification"]["replays"]
    weak = [f"{t['target']}/{t['seed']}" for t in verified
            if not (t["verification"]["verified"] and t["verification"]["replay_violations"] == replays
                    and t["verification"]["replay_hash_matches"] == replays
                    and t["verification"]["corrected"]["mode"])]
    modes = collections.Counter(t["verification"]["corrected"]["mode"] for t in verified)
    check("V4 every hit verified, mode recorded", not weak,
          {"verified_trials": len(verified), "corrected_modes": dict(modes), "weak": weak})

    reference = cfg["pilot_reference"]
    pilot_cfg = json.loads((REPO / reference["config"]).read_text())
    pilot_dir = str(Path(reference["config"]).parent)
    pilot_changed = subprocess.run(["git", "-C", str(REPO), "diff", "--quiet", reference["results_commit"],
                                    "--", pilot_dir]).returncode != 0
    pilot_untracked = subprocess.run(["git", "-C", str(REPO), "ls-files", "--others",
                                      "--exclude-standard", "--", pilot_dir],
                                     capture_output=True, text=True).stdout.split()
    conditions = {k: cfg[k] == pilot_cfg[k] for k in SAME_AS_PILOT}
    conditions["method config"] = ({k: v for k, v in cfg["A2"].items() if k != "include_source"}
                                   == {k: v for k, v in pilot_cfg["M4"].items() if k != "include_source"}
                                   and cfg["A2"]["include_source"] is False
                                   and pilot_cfg["M4"]["include_source"] is True)
    check("V5 comparable with the pilot",
          not manifest["differs_from_pilot_run"] and not pilot_changed and not pilot_untracked
          and all(conditions.values()),
          {"files_differing_from_pilot_run": manifest["differs_from_pilot_run"],
           "pilot_dir_changed_since_results_commit": pilot_changed,
           "pilot_dir_untracked": pilot_untracked, "conditions_equal": conditions})

    spend = round(sum(t["model_usd"] for t in trials), 6)
    expected = len(cfg["targets"]) * len(cfg["seeds"])
    commit_ok = args.commit is None or manifest["git_commit"] == args.commit
    check("V6 spend <= cap, all trials recorded, clean manifest",
          spend <= cfg["model_cost_cap_usd"] and len(trials) == expected
          and not manifest["git_dirty"] and commit_ok,
          {"model_usd": spend, "cap": cfg["model_cost_cap_usd"], "trials": len(trials),
           "expected": expected, "git_commit": manifest["git_commit"],
           "git_dirty": manifest["git_dirty"]})

    keys = {f"{t['target']}/{t['method']}/{t['seed']}": t for t in trials}
    mismatched = {k: (t["executions"], per_trial_n[k]) for k, t in keys.items()
                  if t["executions"] != per_trial_n[k]}
    over = [k for k, t in keys.items() if t["executions"] > cfg["budget"]["executions"]
            or t["method_s"] > cfg["budget"]["method_seconds"]]
    check("accounting: logged executions match each trial's count", not mismatched, mismatched)
    check("accounting: no trial over B_exec or the method-seconds cap", not over, over)

    print(json.dumps(checks, indent=1, default=str))
    print("ALL PASS" if all(c["pass"] for c in checks) else "SOME CHECKS FAILED")
    sys.exit(0 if all(c["pass"] for c in checks) else 1)


if __name__ == "__main__":
    main()
