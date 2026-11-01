"""D1 break-even with the frozen formula (analysis.crossing), from recorded data only.

Baselines: the D1 baseline experiment's 15 trials (KM medians and overheads, analysis.py rules).
Per-execution cost: this re-check's measured medians. Muse: scenarios taken from measured
development runs (the pilot's M4 and A2's calls on D3); Muse has never run on D1.

Usage: breakeven.py <recheck results json>
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))

from mylonite import analysis  # noqa: E402

BUDGET, PRICE = 1000, 1.11e-05


def main():
    recheck = json.loads(Path(sys.argv[1]).read_text())
    trials = json.loads((REPO / "experiments/2026-10-29-d1-baselines/results/20261029-125353/"
                         "trials.json").read_text())
    pilot = json.loads((REPO / "experiments/2026-10-29-pilot/results/20261028-165020/"
                        "trials.json").read_text())
    a2 = json.loads((REPO / "experiments/2026-10-28-a2-no-source/results/20261028-172308/"
                     "trials.json").read_text())

    def muse(rows, method):
        mine = [t for t in rows if t["target"] == "d3-inventory" and t["method"] == method]
        return {"model_s": analysis.median([t["model_s"] for t in mine]),
                "model_s_range": [min(t["model_s"] for t in mine), max(t["model_s"] for t in mine)],
                "model_usd": analysis.median([t["model_usd"] for t in mine]),
                "calls": analysis.median([t["model_calls"] for t in mine])}

    scenarios = {"M4-like (pilot M4 on D3: one call, with source)": muse(pilot, "M4"),
                 "A2-like (A2 on D3: no source)": muse(a2, "A2")}
    baselines = {}
    for method in ("M0", "M1", "M3+"):
        mine = [t for t in trials if t["method"] == method]
        baselines[method] = {
            "e1": analysis.median([analysis.value(t, "e1", BUDGET) for t in mine]),
            "overhead_s": analysis.median([t["method_s"] - t["exec_s"] for t in mine]),
            "method_s_median": analysis.median([t["method_s"] for t in mine])}
    costs = recheck["costs"]
    measured = {k: v["exec_ms"]["median"] / 1000 for k, v in costs.items() if v.get("exec_ms")}
    restart_s = max(s["start_to_ready_s"] for s in recheck["isolation"]["services"].values())
    out = {"status": "estimates: Muse has never run on D1", "baselines": baselines,
           "muse_scenarios": scenarios, "measured_seconds_per_execution": measured,
           "reset_by_restart_s": restart_s, "break_even": {}}
    for name, s in scenarios.items():
        for e_m in (1, 3):
            rows = {}
            for b, base in baselines.items():
                status, c = analysis.crossing(e_m, s["model_s"], base["e1"], base["overhead_s"])
                dstatus, d = analysis.crossing(e_m, s["model_usd"] / PRICE, base["e1"], 0.0)
                rows[b] = {"status": status, "seconds_per_execution": c,
                           "dollar_tie_compute_seconds_per_execution": d}
            worst = analysis.least_favorable(list(rows.values()))
            out["break_even"][f"{name}, E_m = {e_m}"] = {"each": rows, "least_favorable": worst}
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
