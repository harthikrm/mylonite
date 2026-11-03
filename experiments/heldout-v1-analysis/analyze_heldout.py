"""The held-out analysis: the frozen ``analysis.analyze`` (docs/FREEZE.md §4) on the C5 results,
combined as AM-002's class B remedy requires. Run after C6 (D-045).

  python3 experiments/heldout-v1-analysis/analyze_heldout.py

Written after held-out outcomes were observed, so it makes no rule of its own. Every comparison
rule is in src/mylonite/analysis.py, called as the held-out config names it:
``analyze(trials, config, shown_buggy_targets, control_targets)``. This script only chooses which
C5 records go in, by these rules, fixed before it was first run:
- **primary** (AMENDMENTS.md class B: the aborted run stays primary for every trial it
  completed): for each (target, method, seed), run 1's records if run 1 has any record for it
  other than ``not_run``; otherwise run 2's. A trial that errored in run 1 has a result there:
  FREEZE.md §4 rule 3 makes an errored Muse trial a failure, from its first attempt;
- **run2**: run 2 alone, the one complete run under a single version (post-observation);
- **a2_seed10_from_run2**: the primary, except beta_m A2 seed 10 from run 2. D-044 read that trial
  as not completed by run 1; this variant shows what that reading would change.
C6's shown-buggy set must be the same for both runs. Writes report_<variant>.json and inputs.json
next to this script, and prints a summary.
"""

import collections
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))

from mylonite import analysis  # noqa: E402

HELDOUT = REPO / "experiments/heldout-v1"
RUN1, RUN2 = HELDOUT / "results/20261101-231428", HELDOUT / "results/20261102-114636"


def load(run):
    rows = [json.loads(line) for line in (run / "trials.jsonl").read_text().splitlines()]
    if rows != json.loads((run / "trials.json").read_text()):
        sys.exit(f"refusing: {run.name}: trials.jsonl and trials.json differ")
    return rows


def by_key(rows):
    out = collections.defaultdict(list)
    for row in rows:
        out[(row["target"], row["method"], row["seed"])].append(row)
    return out


def combine(run1, run2, from_run2=()):
    """Run 1's records for each trial it completed, otherwise run 2's; ``from_run2`` overrides."""
    one, two = by_key(run1), by_key(run2)
    chosen, source = [], collections.Counter()
    for key in sorted(set(one) | set(two), key=str):
        completed = any(r["status"] != "not_run" for r in one.get(key, []))
        use = "run1" if completed and key not in from_run2 else "run2"
        rows = one[key] if use == "run1" else two.get(key, [])
        if not rows:
            sys.exit(f"refusing: {key} has no record in {use}")
        chosen += rows
        source[(key[0], use)] += 1
    return chosen, dict(sorted((f"{t}|{u}", n) for (t, u), n in source.items()))


def clean(obj):
    """JSON without NaN or Infinity: infinite costs are written as "inf"."""
    if isinstance(obj, float) and math.isinf(obj):
        return "inf" if obj > 0 else "-inf"
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    return obj


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_to_run(run1, run2):
    """Descriptive only: for each trial both runs completed, whether the runs agree."""
    one, two = by_key(analysis.attempts(run1)), by_key(analysis.attempts(run2))
    out = collections.defaultdict(lambda: {"both_completed": 0, "same_status": 0,
                                           "both_verified": 0, "same_e1_when_both_verified": 0})
    for key in sorted(set(one) & set(two), key=str):
        a, b = one[key][0], two[key][0]
        if "not_run" in (a["status"], b["status"]):
            continue
        row = out[f"{key[0]}|{key[1]}"]
        row["both_completed"] += 1
        row["same_status"] += a["status"] == b["status"]
        if a["status"] == b["status"] == "verified":
            row["both_verified"] += 1
            row["same_e1_when_both_verified"] += a["e1_executions"] == b["e1_executions"]
    return dict(out)


def main():
    cfg = json.loads((HELDOUT / "config.json").read_text())
    run1, run2 = load(RUN1), load(RUN2)
    c6 = [json.loads((run / "c6.json").read_text()) for run in (RUN1, RUN2)]
    if c6[0]["shown_buggy"] != c6[1]["shown_buggy"]:
        sys.exit(f"refusing: C6 differs between the runs: {c6[0]['shown_buggy']} {c6[1]['shown_buggy']}")
    shown = c6[0]["shown_buggy"]
    controls = json.loads((RUN2 / "manifest.json").read_text())["controls"]
    primary, primary_source = combine(run1, run2)
    variant, variant_source = combine(run1, run2, from_run2={("beta_m", "A2", 10)})
    variants = {"primary": (primary, primary_source), "run2": (run2, {"all|run2": len(run2)}),
                "a2_seed10_from_run2": (variant, variant_source)}
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True).stdout)
    inputs = {"commit": head, "dirty": dirty, "shown_buggy": shown, "excluded": c6[0]["excluded"],
              "controls": controls,
              "files": {str(p.relative_to(REPO)): sha256(p) for run in (RUN1, RUN2)
                        for p in sorted(run.iterdir()) if p.is_file()},
              "sources": {name: source for name, (_, source) in variants.items()},
              "run_to_run": run_to_run(run1, run2)}
    (HERE / "inputs.json").write_text(json.dumps(clean(inputs), indent=1) + "\n")
    for name, (trials, _) in variants.items():
        report = analysis.analyze(trials, cfg, shown, controls)
        (HERE / f"report_{name}.json").write_text(json.dumps(clean(report), indent=1) + "\n")
        print(f"== {name}: false positives {report['false_positives']}; flags {report['flags']}; "
              f"conventional trials cut {report['conventional_trials_cut']}")
        for muse, cells in report["verdicts"].items():
            for cell, v in cells.items():
                print(f"  {muse:9} {cell:40} {v['verdict']}")
    print(json.dumps({"commit": head, "dirty": dirty, "sources": inputs["sources"]}, indent=1))


if __name__ == "__main__":
    main()
