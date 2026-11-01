"""D1 re-check at freeze v1.0 (PROTOCOL.md in this directory). No model calls, no method trials.

Re-establishes, with the frozen code, that the authentic defect reproduces and that the oracle
and the corrected build behave, and measures the costs every method shares on D1. It reuses the
D1 gate's stages unchanged (../2026-10-28-d1-gate/gate.py) and adds two:

  verification  the frozen verification (methods.verify, held-out settings) on the first
                violation of the gate's same-item workload, timed
  dependencies  per-call serial latency of AddItem, GetCart and EmptyCart, and what the cart's
                whole log says about the services it runs without (flagd, the collector, OpAMP)

Raw records go to runs/d1recheck-<ts>/ (git-ignored), the summary to results/<ts>.json.

Usage: recheck.py [--smoke]   (--smoke: any tree, fewer executions, nothing written to results/)
"""

import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
GATE = REPO / "experiments/2026-10-28-d1-gate"
sys.path.insert(0, str(GATE))

import d1  # noqa: E402
import gate  # noqa: E402
from mylonite import methods  # noqa: E402

HELDOUT = json.loads((REPO / "experiments/heldout-v1/config.json").read_text())
CALLS = {"AddItem": gate.add("u1", gate.P1, 1),
         "GetCart": {"op": "GetCart", "args": {"user_id": "u1"}},
         "EmptyCart": {"op": "EmptyCart", "args": {"user_id": "u1"}}}


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True).stdout.strip()


def stage_verification(session, target, raw):
    """The first violation of the same-item workload, through the frozen verification."""
    records, summary = gate.explore(session, "buggy", gate.WORKLOADS["A_same_item"], raw)
    first = next(r for r in records if r["verdict"] == "VIOLATION")
    started = time.monotonic()
    result = methods.verify(session, target, first, HELDOUT["verification"])
    seconds = time.monotonic() - started
    raw("verification", result=result)
    return {"workload": "A_same_item", "first_violation_at": summary["first_violation_at"],
            "verified": result["verified"], "replays": result["replays"],
            "replay_violations": result["replay_violations"],
            "replay_hash_matches": result["replay_hash_matches"],
            "corrected": result["corrected"], "inconclusive_reruns": result.get("inconclusive_reruns"),
            "seconds": round(seconds, 3)}


def stage_dependencies(box, session, target, raw, n):
    """Per-call serial latency: (median of 5 calls − median of none) / 5. Then the cart's log."""
    def run(setup):
        ms, outcomes = [], set()
        for _ in range(n):
            record, _ = gate.execute(session, "buggy", {"setup": setup, "concurrent": []},
                                     {"kind": "prefix", "prefix": []})
            raw("dependencies", record=record)
            ms.append(record["ms"])
            outcomes.update(record["setup_outcomes"])
        return statistics.median(ms), sorted(outcomes)

    floor, _ = run([])
    out = {"floor_ms": round(floor, 3), "per_call_ms": {}, "outcomes": {}}
    for name, call in CALLS.items():
        five, outcomes = run([call] * 5)
        out["per_call_ms"][name] = round((five - floor) / 5, 3)
        out["outcomes"][name] = outcomes
    lines = d1.cart_logs(box, "buggy", target, tail=1_000_000)  # the whole log, startup included
    keys = {"flagd": ("flagd", "Flagd", "FLAGD", "OpenFeature"), "otlp": ("OTLP", "otlp", "4317"),
            "opamp": ("OpAmp", "opamp", "OPAMP")}
    out["cart_log"] = {name: {"lines": sum(any(k in l for k in ks) for l in lines),
                              "first": next((l[:240] for l in lines if any(k in l for k in ks)), None)}
                       for name, ks in keys.items()}
    out["cart_log"]["lines_read"] = len(lines)
    out["cart_log"]["first_lines"] = [l[:240] for l in lines[:12]]
    return out


def main():
    smoke = "--smoke" in sys.argv[1:]
    dirty = git("status", "--porcelain")
    if dirty and not smoke:
        sys.exit("refusing a non-smoke run on a dirty tree: commit first")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = REPO / "runs" / f"d1recheck-{'smoke-' if smoke else ''}{stamp}"
    run_dir.mkdir(parents=True)
    raw = gate.Raw(run_dir)
    n = 30 if smoke else 300
    check = subprocess.run([sys.executable, str(REPO / "freeze/manifest.py"), "check"],
                           capture_output=True, text=True)
    if check.returncode and not smoke:
        sys.exit(f"freeze check failed:\n{check.stderr}")
    report = {"stamp": stamp, "smoke": smoke, "commit": git("rev-parse", "HEAD"),
              "freeze_check": (check.stdout + check.stderr).strip(),
              "dirty": bool(dirty), "freeze_tag": git("rev-parse", "freeze-v1.0^{commit}"),
              "freeze_tag_is_ancestor": subprocess.run(
                  ["git", "-C", str(REPO), "merge-base", "--is-ancestor", "freeze-v1.0", "HEAD"]
              ).returncode == 0,
              "build": json.loads((GATE / "build.json").read_text())}
    started = time.monotonic()
    with d1.bringup(name="mylonite-d1recheck") as (box, session, target, info):
        report["isolation"] = info
        for stage, call in (
                ("serial", lambda: gate.stage_serial(session, target, raw)),
                ("gate_k", lambda: gate.stage_gate_k(session, target, raw)),
                ("verification", lambda: stage_verification(session, target, raw)),
                ("dependencies", lambda: stage_dependencies(box, session, target, raw, n // 3)),
                ("costs", lambda: gate.stage_costs(session, target, raw, n=n)),
                ("natural", lambda: gate.stage_natural(box, target, raw, rounds=100 if smoke else 1000))):
            t0 = time.monotonic()
            report[stage] = call()
            report.setdefault("stage_seconds", {})[stage] = round(time.monotonic() - t0, 1)
            print(f"{stage}: {report['stage_seconds'][stage]} s", flush=True)
    report["total_seconds"] = round(time.monotonic() - started, 1)
    text = json.dumps(report, indent=1, default=str)
    (run_dir / "report.json").write_text(text)
    if not smoke:
        (HERE / "results").mkdir(exist_ok=True)
        (HERE / "results" / f"{stamp}.json").write_text(text)
    print(f"report: {run_dir / 'report.json'}")


if __name__ == "__main__":
    main()
