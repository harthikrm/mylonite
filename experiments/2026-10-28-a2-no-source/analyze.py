"""PROTOCOL.md §6.1–6.2: compare A2 with the pilot's M4, M1 and M3+, and look at what Muse's hits
depend on. Reads the raw runs (git-ignored) and writes analysis.json, which is committed.

Per trial of A2 and of the pilot's M4:
- round, experiment and schedule index of the hit (schedule 1 is the hint schedule);
- every proposed experiment: whether it was valid, whether D3's design says some schedule of its
  workload violates ("violable"), and the stock it ran against;
- hint adherence of each experiment's first schedule (followed / advanced / skipped);
- hypothesis kinds and whether code references were given.
Per method and target: verified, E1, Success@100/300/1000 with Wilson 95% intervals, median
method seconds, dollars, model calls and tokens.

Usage: analyze.py runs/a2-<ts> runs/pilot-<ts>
"""

import collections
import json
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import m3arg_estimate  # noqa: E402  (D3's design predicate and state reader)


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)]


def violable(target, workload, setup_outcomes):
    """By the fixtures' design: D2 loses an award when two awards to one member interleave; D3
    goes negative only when purchases of one published product each fit and together exceed
    its stock. Setup calls that failed had no effect (the contract's status semantics)."""
    conc = workload["concurrent"]
    setup = [c for c, outcome in zip(workload["setup"], setup_outcomes) if outcome == "ok"]
    if target.startswith("d2"):
        members = collections.Counter(c["args"]["member"] for c in conc if c["op"] == "award")
        return any(n >= 2 for n in members.values()), None
    stock, live = m3arg_estimate.state(setup)
    purchases = [c for c in conc if c["op"] == "purchase"]
    by_sku = collections.defaultdict(list)
    for c in purchases:
        by_sku[c["args"]["sku"]].append(c["args"]["qty"])
    # purchases that fit can all pass the check before any decrement; the others always fail
    fits = {sku: [q for q in qs if q <= stock[sku]] for sku, qs in by_sku.items()}
    hits = [sku for sku, qs in fits.items() if live.get(sku) and len(qs) >= 2 and sum(qs) > stock[sku]]
    return bool(hits), {sku: stock[sku] for sku in by_sku}


def trial_details(run_dir, method):
    events = collections.defaultdict(list)
    for line in open(Path(run_dir) / "executions.jsonl"):
        ev = json.loads(line)
        t, m, _ = ev["trial"].split("/")
        if m == method:
            events[ev["trial"]].append(ev)
    trials = {f"{t['target']}/{t['method']}/{t['seed']}": t
              for t in json.loads((Path(run_dir) / "trials.json").read_text()) if t["method"] == method}
    out = {}
    for key, evs in sorted(events.items()):
        target = key.split("/")[0]
        rounds, experiments, current, hit = [], [], None, None
        for ev in evs:
            if ev["event"] == "model_call":
                plan = json.loads(ev["meta"]["response"]["choices"][0]["message"]["content"])
                rounds.append({"round": ev["round"], "cost_usd": round(ev["cost_usd"], 6),
                               "latency_s": ev["meta"]["latency_s"],
                               "usage": ev["meta"]["usage"],
                               "hypotheses": [{"kind": h["kind"], "operations": h["operations"],
                                               "code_refs": len(h["code_refs"])}
                                              for h in plan["hypotheses"]],
                               "proposed": len(plan["experiments"])})
            elif ev["event"] == "validation":
                rounds[-1]["rejected"] = len(ev["problems"])
            elif ev["event"] == "execution":
                rec = ev["record"]
                if ev["policy"]["kind"] == "hint":
                    workload = {"setup": [], "concurrent": [{"op": o["op"], "args": o["args"]}
                                                            for o in rec["ops"]]}
                    current = {"round": len(rounds), "first_n": ev["n"], "schedules": 0,
                               "hint": ev["policy"]["hint"], "first_schedule": rec["verdict"],
                               "hint_stats": rec.get("policy_stats"),
                               "concurrent": workload["concurrent"],
                               "setup_outcomes": rec["setup_outcomes"], "verdicts": collections.Counter()}
                    experiments.append(current)
                current["schedules"] += 1
                current["verdicts"][rec["verdict"]] += 1
                if rec["verdict"] == "VIOLATION" and hit is None:
                    hit = {"n": ev["n"], "round": current["round"],
                           "experiment": len(experiments), "schedule_in_experiment": current["schedules"]}
        trial = trials[key]
        plans = [json.loads(ev["meta"]["response"]["choices"][0]["message"]["content"])
                 for ev in evs if ev["event"] == "model_call"]
        for exp in experiments:  # attach the proposed setup and hint, in order within its round
            plan = plans[exp["round"] - 1]
            unused = plan.setdefault("_unused", list(range(len(plan["experiments"]))))
            match = None
            for i in unused:
                proposed = plan["experiments"][i]
                strip = [{"op": c["op"], "args": {k: v for k, v in c["args"].items() if v is not None}}
                         for c in proposed["concurrent"]]
                if strip == exp["concurrent"] and len(proposed["setup"]) == len(exp["setup_outcomes"]):
                    match = i
                    break
            unused.remove(match)
            proposed = plan["experiments"][match]
            exp["setup"] = [{"op": c["op"], "args": {k: v for k, v in c["args"].items() if v is not None}}
                            for c in proposed["setup"]]
            exp["schedule_hint"] = [f"{h['command']}@{h['op_index']}" for h in proposed["schedule_hint"]]
            exp["violable_by_design"], exp["stock"] = violable(
                target, {"setup": exp["setup"], "concurrent": exp["concurrent"]}, exp["setup_outcomes"])
            exp["verdicts"] = dict(exp["verdicts"])
        out[key] = {"status": trial["status"], "e1": trial["e1_executions"], "hit": hit,
                    "rounds": rounds, "experiments": experiments,
                    "method_s": trial["method_s"], "model_usd": trial["model_usd"]}
    return out


def table(run_dir, methods_wanted, success_at=(100, 300, 1000), budget=1000):
    trials = json.loads((Path(run_dir) / "trials.json").read_text())
    out = {}
    for t in trials:
        if t["method"] in methods_wanted:
            out.setdefault(t["target"], {}).setdefault(t["method"], []).append(t)
    rows = {}
    for target, by in out.items():
        for method, ts in by.items():
            e1 = [t["e1_executions"] if t["status"] == "verified" else None for t in ts]
            n = len(ts)
            rows.setdefault(target, {})[method] = {
                "trials": n, "verified": sum(e is not None for e in e1),
                "verified_wilson95": wilson(sum(e is not None for e in e1), n),
                "e1": e1, "median_e1_censored": statistics.median(e if e is not None else budget + 1 for e in e1),
                "success_at": {str(b): [sum(e is not None and e <= b for e in e1),
                                        wilson(sum(e is not None and e <= b for e in e1), n)]
                               for b in success_at},
                "median_method_s": round(statistics.median(t["method_s"] for t in ts), 3),
                "method_s": [t["method_s"] for t in ts],
                "usd_per_trial_median": round(statistics.median(t["model_usd"] + t["compute_usd"] for t in ts), 6),
                "usd_total": round(sum(t["model_usd"] + t["compute_usd"] for t in ts), 6),
                "model_calls": [t["model_calls"] for t in ts],
                "tokens_total": {k: sum(t["tokens"].get(k, 0) for t in ts)
                                 for k in ("prompt", "cached", "completion", "reasoning")}}
    return rows


def main():
    a2_run, pilot_run = sys.argv[1], sys.argv[2]
    report = {"comparison": {"pilot (M1, M3+, M4 with source)": table(pilot_run, {"M1", "M3+", "M4"}),
                             "A2 (M4 without source)": table(a2_run, {"A2"})},
              "a2_trials": trial_details(a2_run, "A2"),
              "m4_trials": trial_details(pilot_run, "M4")}
    (HERE / "analysis.json").write_text(json.dumps(report, indent=1, sort_keys=True, default=str) + "\n")
    print(json.dumps(report["comparison"], indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
