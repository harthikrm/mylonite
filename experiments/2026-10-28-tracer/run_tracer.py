"""Tracer bullet (gate T0): fixture D2 end to end through the sandbox.

Runs on the host with the standard library only. Phases:
  baseline  build image, start sandbox, egress probe, pass-through check, exhaustive and random
            search on the buggy variant, 20x replay, exhaustive search on the corrected variant
  muse      one planner call (needs MODEL_API_KEY), validate, run its experiments, then verify
  verify    no model call: rerun each Muse hit, replay its witness 20x, and explore the same
            workload exhaustively on the corrected variant
Curated results go to results.json next to this file; full raw output to runs/ (git-ignored).
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from mylonite import planner  # noqa: E402
from mylonite.sandbox import Sandbox  # noqa: E402

HERE = Path(__file__).resolve().parent
TARGET = json.loads((REPO / "fixtures/dev/d2_counter/target.json").read_text())
RACE = {"setup": [], "concurrent": [{"op": "award", "args": {"member": "m1", "points": 1}},
                                    {"op": "award", "args": {"member": "m1", "points": 1}}]}
CONTROL_WORKLOADS = [
    RACE,
    {"setup": [], "concurrent": [{"op": "award", "args": {"member": "m1", "points": 1}},
                                 {"op": "award", "args": {"member": "m1", "points": 2}}]},
    {"setup": [{"op": "award", "args": {"member": "m2", "points": 2}}],
     "concurrent": [{"op": "award", "args": {"member": "m2", "points": 1}},
                    {"op": "balance", "args": {"member": "m2"}}]},
]
RANDOM_SEEDS = range(1, 21)
PRICES = {"input": 1.25, "cached": 0.15, "output": 4.25}  # USD per 1M tokens, Spark Standard


def request(variant, jobs):
    return {"target": TARGET, "variant": variant, "delta_q_ms": 300, "round_timeout_s": 10,
            "jobs": jobs}


def save_raw(run_dir, name, data):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / f"{name}.json").write_text(json.dumps(data, indent=1))


def first_violation(job):
    return next((r for r in job["records"] if r["verdict"] == "VIOLATION"), None)


def baseline(box, run_dir):
    buggy = box.run_executor(request("buggy", [
        {"id": "passthrough", "kind": "passthrough_check", "workload": RACE, "repeat": 50},
        {"id": "exhaustive", "kind": "exhaustive", "workload": RACE, "max_schedules": 100},
        *[{"id": f"random-{s}", "kind": "random_search", "seed": s, "n_concurrent": 2,
           "max_schedules": 300} for s in RANDOM_SEEDS],
    ]))
    save_raw(run_dir, "baseline_buggy", buggy)
    jobs = {j["id"]: j for j in buggy["jobs"]}
    witness = first_violation(jobs["exhaustive"])

    replay = box.run_executor(request("buggy", [
        {"id": "replay", "kind": "replay", "workload": RACE, "decisions": witness["decisions"],
         "repeat": 20}]))
    save_raw(run_dir, "replay", replay)

    fixed = box.run_executor(request("fixed", [
        {"id": f"fixed-{i}", "kind": "exhaustive", "workload": w, "max_schedules": 200}
        for i, w in enumerate(CONTROL_WORKLOADS)]))
    save_raw(run_dir, "fixed", fixed)

    random_hits = [jobs[f"random-{s}"]["summary"]["first_violation_at"] for s in RANDOM_SEEDS]
    records = [r for j in buggy["jobs"] if "records" in j for r in j["records"]]
    ex = jobs["exhaustive"]["summary"]
    rp = replay["jobs"][0]["summary"]
    return {
        "egress_probe": buggy["egress_probe"],
        "sandbox_policy": box.inspect_policy(),
        "passthrough_check": jobs["passthrough"]["summary"],
        "systematic_exhaustive": {
            "workload": RACE, "schedules": ex["executions"], "exhausted": ex["exhausted"],
            "violating_schedules": ex["verdicts"]["VIOLATION"],
            "first_violation_at": ex["first_violation_at"],
            "forced_decisions": ex["forced_decisions"],
            "soundness_problems": ex["soundness_problems"]},
        "witness": {k: witness[k] for k in ("decisions", "trace", "pre", "post", "ops",
                                            "violations", "trace_hash")},
        "replay_20": {"violations": rp["verdicts"]["VIOLATION"], "runs": rp["executions"],
                      "distinct_trace_hashes": rp["distinct_trace_hashes"],
                      "matches_witness": all(r["trace_hash"] == witness["trace_hash"]
                                             for r in replay["jobs"][0]["records"])},
        "random_search": {
            "trials": len(random_hits), "budget": 300,
            "found": sum(h is not None for h in random_hits),
            "executions_to_first_violation": random_hits,
            "median": statistics.median(h for h in random_hits if h is not None)},
        "corrected_variant": [
            {"workload": w, "schedules": j["summary"]["executions"],
             "exhausted": j["summary"]["exhausted"], "verdicts": j["summary"]["verdicts"]}
            for w, j in zip(CONTROL_WORKLOADS, fixed["jobs"])],
        "ms_per_execution_mean": round(statistics.mean(r["ms"] for r in records), 2),
    }


def muse(box, run_dir, commands):
    key = planner.load_api_key(REPO)
    if key is None:
        return {"status": "skipped: MODEL_API_KEY not set in the environment or .env"}
    schema = planner.plan_schema(TARGET, commands)
    messages = planner.build_messages(TARGET, REPO)
    plan, meta = planner.call_muse(key, messages, schema)
    save_raw(run_dir, "muse_call", {"plan": plan, **meta})
    experiments, problems = planner.validate(plan, TARGET, commands)
    jobs = [{"id": f"muse-{i}", "kind": "hint_then_exhaustive", "workload": e["workload"],
             "hint": e["hint"], "max_schedules": 100, "stop_on_violation": True}
            for i, e in enumerate(experiments)]
    executed = box.run_executor(request("buggy", jobs)) if jobs else {"jobs": []}
    save_raw(run_dir, "muse_runs", executed)
    usage = meta["usage"] or {}
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
    prompt, completion = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    cost = ((prompt - cached) * PRICES["input"] + cached * PRICES["cached"]
            + completion * PRICES["output"]) / 1e6
    executions_before = 0
    first_hit = None
    for job in executed["jobs"]:
        hit = job["summary"]["first_violation_at"]
        if hit is not None and first_hit is None:
            first_hit = executions_before + hit
        executions_before += job["summary"]["executions"]
    return {
        "status": "ran", "model": meta["model"], "prompt_version": planner.PROMPT_VERSION,
        "latency_s": meta["latency_s"], "usage": usage, "cost_usd": round(cost, 5),
        "hypotheses": plan["hypotheses"], "valid_experiments": len(experiments),
        "rejected_experiments": problems,
        "experiments": [{"workload": e["workload"], "hint": e["hint"], "summary": j["summary"],
                         "witness_trace_hash": (first_violation(j) or {}).get("trace_hash")}
                        for e, j in zip(experiments, executed["jobs"])],
        "executions_to_first_violation": first_hit,
    }


def verify(box, run_dir, experiments):
    """No model call. A Muse hit counts as verified only if its guided schedule reproduces it,
    the witness replays 20/20 with one trace hash, and the corrected variant passes the same
    workload under exhaustive exploration (EVALUATION_PLAN.md)."""
    found = [e for e in experiments if e["summary"]["first_violation_at"] is not None]
    if not found:
        return []
    rerun = box.run_executor(request("buggy", [
        {"id": f"rerun-{i}", "kind": "hint_then_exhaustive", "workload": e["workload"],
         "hint": e["hint"], "max_schedules": 100, "stop_on_violation": True}
        for i, e in enumerate(found)]))
    witnesses = [first_violation(j) for j in rerun["jobs"]]
    replay_jobs = [{"id": f"replay-{i}", "kind": "replay", "workload": e["workload"],
                    "decisions": w["decisions"], "repeat": 20}
                   for i, (e, w) in enumerate(zip(found, witnesses)) if w is not None]
    replay = box.run_executor(request("buggy", replay_jobs)) if replay_jobs else {"jobs": []}
    replays = {j["id"]: j for j in replay["jobs"]}
    fixed = box.run_executor(request("fixed", [
        {"id": f"fixed-{i}", "kind": "exhaustive", "workload": e["workload"],
         "max_schedules": 5000} for i, e in enumerate(found)]))
    save_raw(run_dir, "muse_verify", {"rerun": rerun, "replay": replay, "fixed": fixed})

    out = []
    for i, (e, w, fx) in enumerate(zip(found, witnesses, fixed["jobs"])):
        rp = replays.get(f"replay-{i}")
        replay_ok = (rp is not None and rp["summary"]["verdicts"]["VIOLATION"] == 20
                     and rp["summary"]["distinct_trace_hashes"] == 1
                     and all(r["trace_hash"] == w["trace_hash"] for r in rp["records"]))
        fs = fx["summary"]
        fixed_ok = (fs["exhausted"] is True and fs["verdicts"]["PASS"] == fs["executions"]
                    and fs["soundness_problems"] == 0)
        out.append({
            "workload": e["workload"],
            "rerun_first_violation_at": rerun["jobs"][i]["summary"]["first_violation_at"],
            "witness": None if w is None else {k: w[k] for k in ("decisions", "trace_hash", "pre",
                                                                  "post", "violations")},
            "matches_original_hash": (None if e.get("witness_trace_hash") is None or w is None
                                      else w["trace_hash"] == e["witness_trace_hash"]),
            "replay_20": None if rp is None else {
                "violations": rp["summary"]["verdicts"]["VIOLATION"],
                "distinct_trace_hashes": rp["summary"]["distinct_trace_hashes"]},
            "corrected_variant": {"schedules": fs["executions"], "exhausted": fs["exhausted"],
                                  "verdicts": fs["verdicts"],
                                  "soundness_problems": fs["soundness_problems"]},
            "verified": bool(w is not None and replay_ok and fixed_ok),
        })
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["baseline", "muse", "verify"])
    parser.add_argument("--no-build", action="store_true")
    args = parser.parse_args()

    out_path = HERE / "results.json"
    results = json.loads(out_path.read_text()) if out_path.exists() else {}
    run_dir = REPO / "runs" / f"tracer-{time.strftime('%Y%m%d-%H%M%S')}"
    box = Sandbox("mylonite-d2", REPO)
    if not args.no_build:
        box.build_executor_image()
    box.up()
    try:
        if args.only in (None, "baseline"):
            results["baseline"] = baseline(box, run_dir)
        if args.only in (None, "muse"):
            commands = sorted({e["cmd"] for e in results["baseline"]["witness"]["trace"]
                               if e["event"] == "exec"})
            results["muse"] = muse(box, run_dir, commands)
        if args.only in (None, "muse", "verify") and results.get("muse", {}).get("status") == "ran":
            results["muse_verification"] = verify(box, run_dir, results["muse"]["experiments"])
    finally:
        box.down()
    results["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    out_path.write_text(json.dumps(results, indent=1))
    print(json.dumps({k: v for k, v in results.items() if k != "baseline"} |
                     {"baseline_keys": sorted(results.get("baseline", {}))}, indent=1)[:4000])


if __name__ == "__main__":
    main()
