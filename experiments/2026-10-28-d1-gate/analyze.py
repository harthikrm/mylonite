"""Revised break-even estimates for D1 (README.md §6). Reads the committed gate summary and the
pilot's and A2's committed trial records; writes analysis.json. No execution, no API call.

Muse has never run on D1. Its time and cost here are ESTIMATES from D3 measurements, under the
most favourable assumption that its first execution finds the bug (E1 = 1). The baselines'
E1 values are single feasibility trials at seed 0, not results.

Break-even per-execution cost t* (Muse ties the baseline):
  wall-clock  L + E_m t = E_b t      ->  t* = L / (E_b - E_m)
  dollars     C + E_m t r = E_b t r  ->  t* = C / (r (E_b - E_m)),  r = compute $ per second
"""

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PILOT = REPO / "experiments/2026-10-29-pilot/results/20261028-165020"
A2 = REPO / "experiments/2026-10-28-a2-no-source/results/20261028-172308"
RATE = 1.11e-05  # $ per execution-second, as in the pilot config
# D1 request: ~7 KB of scaffold, catalog and contract plus the 28-32 KB C# view; 3.9 bytes per
# token as measured on D3 -> 9-11k prompt tokens. Completion as the pilot's D3 median.
D1_PROMPT_TOKENS, D3_COMPLETION = 10_000, 3_425
D1_CALL_USD = round((D1_PROMPT_TOKENS * 1.25 + D3_COMPLETION * 4.25) / 1e6, 4)


def d3(path, method):
    trials = [t for t in json.loads((path / "trials.json").read_text())
              if t["method"] == method and t["target"].startswith("d3")]
    return {"model_s_median": round(statistics.median(t["model_s"] for t in trials), 2),
            "model_usd_median": round(statistics.median(t["model_usd"] for t in trials), 4),
            "e1": [t["e1_executions"] for t in trials]}


def break_even(e_b, latency_s, usd, e_m=1):
    if e_b <= e_m:
        return {"seconds": None, "dollars": None, "note": "baseline needs no more executions: never"}
    return {"seconds": round(latency_s / (e_b - e_m), 3), "dollars": round(usd / (RATE * (e_b - e_m)), 1)}


def main():
    gate = json.loads(Path(sys.argv[1]).read_text())
    costs = gate["costs"]
    measured = {
        "M1 executions (random workload and schedule)": costs["M1 draws: random workload, random schedule (buggy)"]["exec_ms"]["median"],
        "M3+ profile executions": costs["M3+ profile: one call after a random setup (buggy)"]["exec_ms"]["median"],
        "scenario A, depth-first": costs["A_same_item, depth-first schedules (buggy)"]["exec_ms"]["median"],
        "floor: reset and observe only": costs["floor: reset + observe, empty workload"]["exec_ms"]["median"],
    }
    muse = {"M4 (with source), D3 pilot": d3(PILOT, "M4"), "A2 (no source), D3": d3(A2, "A2")}
    scenarios = {  # (latency per trial, dollars per trial) for Muse on D1, E1 = 1
        "M4-like: one call, D3 latency, D1-sized prompt": (muse["M4 (with source), D3 pilot"]["model_s_median"], D1_CALL_USD),
        "A2-like: two calls, D3 latency": (muse["A2 (no source), D3"]["model_s_median"], 2 * D1_CALL_USD),
    }
    baselines = {m: {"e1": b["e1_executions"], "method_s": b["method_s"], "verified": b["verified"]}
                 for m, b in gate["baselines"].items()}
    table = {s: {m: break_even(b["e1"], lat, usd) for m, b in baselines.items()}
             for s, (lat, usd) in scenarios.items()}
    t = measured["M1 executions (random workload and schedule)"] / 1000
    report = {
        "status": "estimates; Muse has not run on D1; baseline E1 from one seed-0 trial each",
        "d1_measured_exec_ms_median": measured,
        "d1_baselines_seed0": baselines,
        "muse_on_d3": muse,
        "d1_call_usd_estimate": D1_CALL_USD,
        "break_even_per_execution": table,
        "shortfall_factor_vs_measured": {s: {m: round(v["seconds"] / t) for m, v in row.items() if v["seconds"]}
                                         for s, row in table.items()},
        "for_reference_d3_break_even_s": {"M4 vs M3+": 0.060, "A2 vs M3+": 0.215},
    }
    (HERE / "analysis.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
