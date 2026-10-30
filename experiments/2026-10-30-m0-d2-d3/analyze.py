"""Analyses planned in PROTOCOL.md §4. Reads a finished run, its same-session regression and the
A2 run's recorded trials; writes analysis.json next to this file. No execution, no API call.

Break-even per-execution cost against a conventional baseline b (D-026):
  t* = L / (E_b - E_m)
L and E_m are a Muse condition's median model seconds and median E1, both recorded (M4 in the
pilot, replayed in the same-session regression; A2 in its own run). E_b is the baseline's median
E1 with censored trials at budget + 1, so a censored median gives an upper bound on t*.
"Fastest" ranks method-seconds to a verified violation, with censored trials at the method-seconds
cap + 1 (the same convention as E1): time spent before censoring is not time to a bug.

Usage: analyze.py runs/m0-<ts> results/<ts>
"""

import collections
import json
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
A2_TRIALS = REPO / "experiments/2026-10-28-a2-no-source/results/20261028-172308/trials.json"


def wilson(k, n, z=1.96):
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)]


def lines(path):
    with open(path) as f:
        for line in f:
            yield json.loads(line)


def describe(ts, budget, success_at, cap_s):
    ts = sorted(ts, key=lambda t: t["seed"])
    e1 = [t["e1_executions"] if t["status"] == "verified" else None for t in ts]
    censored = [e if e is not None else budget + 1 for e in e1]
    return {"e1": e1, "statuses": [t["status"] for t in ts],
            "median_e1_censored_at_budget_plus_1": statistics.median(censored),
            "success_at": {str(b): {"k": sum(e is not None and e <= b for e in e1), "n": len(ts),
                                    "wilson95": wilson(sum(e is not None and e <= b for e in e1), len(ts))}
                           for b in success_at},
            "method_s": [t["method_s"] for t in ts],
            "median_method_s": round(statistics.median(t["method_s"] for t in ts), 3),
            "median_method_s_to_verified_censored_at_cap_plus_1": round(statistics.median(
                t["method_s"] if t["status"] == "verified" else cap_s + 1 for t in ts), 3),
            "median_model_s": round(statistics.median(t["model_s"] for t in ts), 2),
            "median_s_per_execution": round(statistics.median(
                (t["method_s"] - t["model_s"]) / t["executions"] for t in ts if t["executions"]), 5)}


def stress_stats(run, trial_keys):
    """Per M0 trial: stress runs, hits, and hits whose exploration found no controlled violation."""
    out = {k: {"stress": 0, "hits": 0, "unreproduced_hits": 0, "exploration_executions": 0,
               "inconclusive_stress": 0} for k in trial_keys}
    open_hit = {}
    for ev in lines(run / "executions.jsonl"):
        k = ev["trial"]
        if k not in out:
            continue
        if ev["event"] == "stress":
            if open_hit.pop(k, False):
                out[k]["unreproduced_hits"] += 1
            out[k]["stress"] += 1
            out[k]["inconclusive_stress"] += ev["record"]["verdict"] == "INCONCLUSIVE"
            if ev["record"]["verdict"] == "VIOLATION":
                out[k]["hits"] += 1
                open_hit[k] = True
        elif ev["event"] == "execution":
            out[k]["exploration_executions"] += 1
            if ev["record"]["verdict"] == "VIOLATION":
                open_hit[k] = False
    for k, still_open in open_hit.items():  # a trial that ended right after an unreproduced hit
        out[k]["unreproduced_hits"] += still_open
    return out


def main():
    run, results = Path(sys.argv[1]), Path(sys.argv[2])
    cfg = json.loads((HERE / "config.json").read_text())
    budget, success_at = cfg["budget"]["executions"], cfg["report_success_at"]
    cap_s = cfg["budget"]["method_seconds"]
    m0 = json.loads((results / "trials.json").read_text())
    same = json.loads((results / "same_session_regression/trials.json").read_text())
    a2 = json.loads(A2_TRIALS.read_text())

    report = {"status": "exploratory, development-only; Muse numbers are recorded, not new",
              "run": str(run), "results": str(results), "targets": {}}
    for target in sorted({t["target"] for t in m0}):
        rows = {"M0": describe([t for t in m0 if t["target"] == target], budget, success_at, cap_s)}
        for method in ("M1", "M3+", "M4"):
            rows[method] = describe([t for t in same if t["target"] == target and t["method"] == method],
                                    budget, success_at, cap_s) | {"source": "same-session regression"}
        rows["A2"] = describe([t for t in a2 if t["target"] == target], budget, success_at, cap_s) \
            | {"source": "A2 run, 2026-10-28 (different session)"}
        keys = [f"{target}/M0/{s}" for s in cfg["seeds"]]
        per = stress_stats(run, keys)
        rows["M0"]["stress"] = {
            "per_trial": [per[k] for k in keys],
            "hit_rate": round(sum(p["hits"] for p in per.values()) / max(1, sum(p["stress"] for p in per.values())), 4)}

        conventional = ("M0", "M1", "M3+")
        medians = {m: rows[m]["median_e1_censored_at_budget_plus_1"] for m in conventional}
        seconds = {m: rows[m]["median_method_s_to_verified_censored_at_cap_plus_1"] for m in conventional}
        best_e1 = min(medians.values())
        best_s = min(seconds.values())
        break_even = {}
        for muse in ("M4", "A2"):
            latency, e_m = rows[muse]["median_model_s"], rows[muse]["median_e1_censored_at_budget_plus_1"]
            break_even[muse] = {}
            for b in conventional:
                e_b = medians[b]
                if e_b <= e_m:
                    break_even[muse][b] = {"e_b": e_b, "e_m": e_m, "seconds": None,
                                           "note": "the baseline needs no more executions: no break-even"}
                    continue
                break_even[muse][b] = {
                    "e_b": e_b, "e_m": e_m, "seconds": round(latency / (e_b - e_m), 4),
                    "bound": "upper bound (baseline median censored)" if e_b > budget else "point",
                    "measured_s_per_execution": rows[b]["median_s_per_execution"]}
        report["targets"][target] = {
            "methods": rows, "break_even_per_execution": break_even,
            "strongest_conventional_by_median_e1": [m for m in conventional if medians[m] == best_e1],
            "strongest_conventional_by_median_method_s": [m for m in conventional if seconds[m] == best_s],
        }

    d2, d3 = report["targets"]["d2-loyalty-points"]["methods"], report["targets"]["d3-inventory"]["methods"]
    report["predictions"] = {
        "P1 D2: all 5 M0 trials verified": all(s == "verified" for s in d2["M0"]["statuses"]),
        "P2 D2: M0 median E1 in 2-15": 2 <= d2["M0"]["median_e1_censored_at_budget_plus_1"] <= 15,
        "P3 D3: M0 censored in all 5": all(s.startswith("censored") for s in d3["M0"]["statuses"]),
        "P4, P5": "see check_validity.py V7, V8, V9",
    }
    (HERE / "analysis.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
