"""Analyses planned in PROTOCOL.md §7. Reads a finished run's trials and raw log; writes
analysis.json next to this file. No execution, no API call.

Break-even per-execution cost (D-026), with E_m = 1, the most favourable case for Muse:
  wall-clock  t* = L / (E_b - E_m)          dollars  t* = C / (r (E_b - E_m))
L and C are the gate's two Muse scenarios (../2026-10-28-d1-gate/analysis.json). They are
ESTIMATES from D3 measurements: Muse has not run on D1. E_b is each method's measured median E1.

Usage: analyze.py runs/d1base-<ts> results/<ts>
"""

import collections
import json
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE.parent / "2026-10-28-d1-gate"


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)]


def lines(path):
    with open(path) as f:
        for line in f:
            yield json.loads(line)


def main():
    run, results = Path(sys.argv[1]), Path(sys.argv[2])
    trials = json.loads((results / "trials.json").read_text())
    cfg = json.loads((HERE / "config.json").read_text())
    budget, rate = cfg["budget"]["executions"], cfg["prices"]["compute_per_second"]
    gate = json.loads((GATE / "analysis.json").read_text())
    scenarios = {
        "M4-like: one call, D3 latency, D1-sized prompt":
            (gate["muse_on_d3"]["M4 (with source), D3 pilot"]["model_s_median"], gate["d1_call_usd_estimate"]),
        "A2-like: two calls, D3 latency":
            (gate["muse_on_d3"]["A2 (no source), D3"]["model_s_median"], 2 * gate["d1_call_usd_estimate"]),
    }

    stress = collections.defaultdict(lambda: {"stress": 0, "hits": 0, "inconclusive": 0, "exec_ms": []})
    exec_ms = collections.defaultdict(list)
    for ev in lines(run / "executions.jsonl"):
        method = ev["trial"].split("/")[1]
        if ev["event"] == "stress":
            s = stress[ev["trial"]]
            s["stress"] += 1
            s["hits"] += ev["record"]["verdict"] == "VIOLATION"
            s["inconclusive"] += ev["record"]["verdict"] == "INCONCLUSIVE"
            s["exec_ms"].append(ev["record"]["ms"])
            exec_ms[method].append(ev["record"]["ms"])
        elif ev["event"] == "execution":
            exec_ms[method].append(ev["record"]["ms"])
        elif ev["event"] == "profile":
            exec_ms[method].append(ev["result"]["ms"])

    methods = {}
    for method in cfg["methods"]:
        ts = sorted((t for t in trials if t["method"] == method), key=lambda t: t["seed"])
        e1 = [t["e1_executions"] if t["status"] == "verified" else None for t in ts]
        censored = [e if e is not None else budget + 1 for e in e1]
        per_exec = [t["method_s"] / t["executions"] for t in ts if t["executions"]]
        row = {
            "seeds": [t["seed"] for t in ts], "statuses": [t["status"] for t in ts], "e1": e1,
            "median_e1_censored_at_budget_plus_1": statistics.median(censored),
            "min_e1": min(censored), "max_e1": max(censored),
            "success_at": {str(b): {"k": sum(e is not None and e <= b for e in e1), "n": len(ts),
                                    "wilson95": wilson(sum(e is not None and e <= b for e in e1), len(ts))}
                           for b in cfg["report_success_at"]},
            "method_s": [t["method_s"] for t in ts],
            "median_method_s": round(statistics.median(t["method_s"] for t in ts), 3),
            "median_method_s_per_execution": round(statistics.median(per_exec), 5),
            "median_execution_ms": round(statistics.median(exec_ms[method]), 2),
            "compute_usd": [t["compute_usd"] for t in ts],
            "verification_s": [t["verification_s"] for t in ts],
        }
        if method == "M0":
            keys = [f"{t['target']}/M0/{t['seed']}" for t in ts]
            per = [{k: stress[key][k] for k in ("stress", "hits", "inconclusive")} for key in keys]
            row["stress"] = {
                "per_trial": per,
                "hit_rate": round(sum(p["hits"] for p in per) / max(1, sum(p["stress"] for p in per)), 4),
                "reproduced_under_scheduler": [t["counters"].get("m0_reproductions", 0) for t in ts],
                "exploration_executions": [t["executions"] - p["stress"] for t, p in zip(ts, per)],
                "median_stress_ms": round(statistics.median(ms for key in keys for ms in stress[key]["exec_ms"]), 2),
            }
        methods[method] = row

    break_even = {}
    for name, (latency, usd) in scenarios.items():
        break_even[name] = {}
        for method, row in methods.items():
            e_b = row["median_e1_censored_at_budget_plus_1"]
            seconds = latency / (e_b - 1) if e_b > 1 else None
            dollars = usd / (rate * (e_b - 1)) if e_b > 1 else None
            measured = row["median_method_s_per_execution"]
            break_even[name][method] = {
                "e_b": e_b, "seconds": seconds and round(seconds, 3), "dollars": dollars and round(dollars, 1),
                "measured_s_per_execution": measured,
                "shortfall_factor": seconds and round(seconds / measured, 1)}

    medians = {m: r["median_e1_censored_at_budget_plus_1"] for m, r in methods.items()}
    secs = {m: r["median_method_s"] for m, r in methods.items()}
    predictions = {
        "P1 all 15 verified within 1,000": all(s == "verified" for r in methods.values() for s in r["statuses"]),
        "P2 medians in range": {"M3+": 23 <= medians["M3+"] <= 80, "M1": 10 <= medians["M1"] <= 100,
                                "M0": 10 <= medians["M0"] <= 150},
        "P3 M3+ lowest median E1": medians["M3+"] == min(medians.values()) and
                                   sorted(medians.values()).count(medians["M3+"]) == 1,
        "P3 M3+ and M1 method-seconds within 2x": max(secs["M3+"], secs["M1"]) <= 2 * min(secs["M3+"], secs["M1"]),
        "P4 every trial under 2 method-seconds": all(s < 2 for r in methods.values() for s in r["method_s"]),
        "P6 every median E1 above 10": all(m > 10 for m in medians.values()),
        "P7 every break-even above 0.1 s": all(v["seconds"] is None or v["seconds"] > 0.1
                                               for row in break_even.values() for v in row.values()),
        "P5": "see check_validity.py V7",
    }
    report = {"status": "exploratory, development-only; break-evens are estimates (Muse has not run on D1)",
              "run": str(run), "results": str(results), "methods": methods,
              "break_even_per_execution": break_even, "muse_scenarios": {k: {"latency_s": v[0], "usd": v[1]}
                                                                         for k, v in scenarios.items()},
              "predictions": predictions}
    (HERE / "analysis.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
