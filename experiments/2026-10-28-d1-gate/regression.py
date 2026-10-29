"""Regression check for the D1 harness changes on D2 and D3 (no API calls).

Re-runs all 30 pilot trials (experiments/2026-10-29-pilot/config.json) with the current code,
answering Muse's calls from the pilot's recorded responses, and compares every event of every
trial with the pilot's raw log: each execution's decisions, verdict and trace hash; each profile
result; each verification result. The recorded-model class refuses any request that differs
from the recorded one, so the planner input is checked too. Also reports the change in
per-execution time (TCP_NODELAY on the proxy's sockets).

Writes only to runs/d1gate-regression-<ts>/ (git-ignored) and prints a JSON report; the pilot
directory is read, never written.

Usage: regression.py runs/pilot-<ts>
"""

import importlib.util
import json
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from mylonite import methods  # noqa: E402
from mylonite.sandbox import Sandbox  # noqa: E402

PILOT = REPO / "experiments/2026-10-29-pilot"
RESULTS = PILOT / "results/20261028-165020"
_spec = importlib.util.spec_from_file_location("run_pilot", PILOT / "run_pilot.py")
pilot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pilot)


def fingerprint(event):
    kind = event["event"]
    if kind == "execution":
        r = event["record"]
        return [kind, event["n"], r["decisions"], r["verdict"], r["trace_hash"]]
    if kind == "profile":
        return [kind, event["n"], {k: v for k, v in event["result"].items() if k != "ms"}]
    if kind == "verification":
        return [kind, event["n"], event["result"]]
    return [kind, event["round"]]


def by_trial(path):
    out = {}
    for line in Path(path).read_text().splitlines():
        event = json.loads(line)
        out.setdefault(event["trial"], []).append(event)
    return out


def exec_ms(events):
    return [e["record"]["ms"] for e in events if e["event"] == "execution"]


def main():
    pilot_run = Path(sys.argv[1])
    cfg = json.loads((PILOT / "config.json").read_text())
    targets = [json.loads((REPO / p).read_text()) for p in cfg["targets"]]
    run_dir = REPO / "runs" / f"d1gate-regression-{time.strftime('%Y%m%d-%H%M%S')}"
    run_dir.mkdir(parents=True)
    calls = (run_dir / "model_calls.jsonl").open("w")
    model = pilot.RecordedModel(RESULTS / "model_calls.jsonl",
                                lambda entry: calls.write(methods.json_line(entry) + "\n"))
    events = {}
    trials = []
    box = Sandbox("mylonite-d1reg", REPO)
    try:
        for target in targets:
            box.up()
            with box.session(target, **cfg["executor"]) as session:
                for seed in cfg["seeds"]:
                    for method in cfg["methods"]:
                        key = f"{target['target']}/{method}/{seed}"
                        model.trial = key
                        events[key] = []
                        result = methods.run_trial(method, session, target, seed, cfg,
                                                   lambda e, key=key: events[key].append({"trial": key, **e}),
                                                   model=model, repo_root=REPO)
                        trials.append(result)
                        print(key, result["status"], result["e1_executions"], flush=True)
    finally:
        box.down()
        calls.close()
    with (run_dir / "executions.jsonl").open("w") as out:
        for evs in events.values():
            for e in evs:
                out.write(methods.json_line(e) + "\n")
    (run_dir / "trials.json").write_text(json.dumps(trials, indent=1, default=str))

    recorded = by_trial(pilot_run / "executions.jsonl")
    pilot_trials = {f"{t['target']}/{t['method']}/{t['seed']}": t
                    for t in json.loads((RESULTS / "trials.json").read_text())}
    fields = ("status", "e1_executions", "executions", "verification", "witness")
    report = {"run_dir": str(run_dir.relative_to(REPO)), "trials": len(trials), "identical_trials": 0,
              "identical_event_streams": 0, "events_compared": 0, "differences": [],
              "exec_ms_median": {}}
    for t in trials:
        key = f"{t['target']}/{t['method']}/{t['seed']}"
        same_trial = all(json.dumps(t[f], sort_keys=True, default=str)
                         == json.dumps(pilot_trials[key][f], sort_keys=True, default=str) for f in fields)
        a = [fingerprint(e) for e in recorded[key]]
        b = [fingerprint(e) for e in events[key]]
        report["identical_trials"] += same_trial
        report["identical_event_streams"] += a == b
        report["events_compared"] += len(a)
        if not (same_trial and a == b):
            first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
            report["differences"].append({"trial": key, "trial_fields_equal": same_trial,
                                          "events": [len(a), len(b)], "first_difference_at": first})
    for target in targets:
        name = target["target"]
        before = [ms for k, evs in recorded.items() if k.startswith(name) for ms in exec_ms(evs)]
        after = [ms for k, evs in events.items() if k.startswith(name) for ms in exec_ms(evs)]
        report["exec_ms_median"][name] = {"pilot": round(statistics.median(before), 2),
                                          "now": round(statistics.median(after), 2),
                                          "executions": [len(before), len(after)]}
    (run_dir / "report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
