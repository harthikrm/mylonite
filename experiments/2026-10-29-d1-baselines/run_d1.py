"""D1 baseline experiment (PROTOCOL.md): M0, M1 and M3+ on the real cart. No model calls.

One bring-up (Valkey, the executor with the proxy, both cart builds, warm-up) serves every trial.
Each trial runs through ``methods.run_trial`` with config.json's seeds, budgets and verification,
so every execution resets the store and is checked by the same oracle. Writes:
  runs/d1base-<ts>/   raw: every execution, profile, stress run and verification (git-ignored)
  results/<ts>/       curated: manifest, trial summaries, summary (committed after a run)
Modes:
  --smoke             harness check, not data: seed 0 only (outside the planned seeds), raw only
"""

import argparse
import hashlib
import importlib.util
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-10-28-d1-gate"))

import d1  # noqa: E402
from d1 import REPO  # noqa: E402
from mylonite import methods, space  # noqa: E402

_spec = importlib.util.spec_from_file_location("run_pilot", REPO / "experiments/2026-10-29-pilot/run_pilot.py")
run_pilot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_pilot)


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True,
                          text=True).stdout.strip()


def manifest(cfg, args):
    files = [p for d in ("src", "docker", "tests", "targets/d1-otel-cart") for p in (REPO / d).rglob("*")
             if p.is_file() and "__pycache__" not in p.parts]
    files += [p for p in HERE.glob("*.py")] + [HERE / "config.json", HERE.parent / "2026-10-28-d1-gate/d1.py"]
    return {"git_commit": git("rev-parse", "HEAD"),
            "git_dirty": git("status", "--porcelain").splitlines(),
            "files_sha256": {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in sorted(files)},
            "build": json.loads((HERE.parent / "2026-10-28-d1-gate/build.json").read_text()),
            "host_python": platform.python_version(), "config": cfg, "argv": sys.argv[1:],
            "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--methods", nargs="*")
    args = parser.parse_args()

    cfg = json.loads((HERE / "config.json").read_text())
    if not args.smoke and (args.methods or git("status", "--porcelain")):
        sys.exit("refusing: a non-smoke run uses config.json as is, on a clean tree, so the "
                 "manifest's commit identifies exactly what ran")
    seeds = [0] if args.smoke else cfg["seeds"]
    method_names = args.methods or cfg["methods"]

    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = REPO / "runs" / f"d1base-{'smoke-' if args.smoke else ''}{stamp}"
    run_dir.mkdir(parents=True)
    meta = manifest(cfg, args)  # before any trial: code, config and build as run
    trials = []
    events_file = (run_dir / "executions.jsonl").open("w")
    trials_file = (run_dir / "trials.jsonl").open("w")  # appended as trials finish
    try:
        with d1.bringup(name="mylonite-d1base", **cfg["executor"]) as (box, session, target, info):
            meta["bringup"] = info
            assert space.max_concurrent(target) == cfg["concurrent_max"], "D1's space limit (D-029)"
            for seed in seeds:
                for method in method_names:
                    key = f"{target['target']}/{method}/{seed}"

                    def log(event, key=key):
                        events_file.write(methods.json_line({"trial": key, **event}) + "\n")

                    result = methods.run_trial(method, session, target, seed, cfg, log)
                    trials.append(result)
                    trials_file.write(methods.json_line(result) + "\n")
                    trials_file.flush()
                    print(f"{key}: {result['status']} e1={result['e1_executions']} "
                          f"executions={result['executions']} method_s={result['method_s']}",
                          flush=True)
            meta["cart_logs_tail"] = {v: d1.cart_logs(box, v, target, tail=15) for v in ("buggy", "fixed")}
    finally:
        events_file.close()
        trials_file.close()

    meta["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    summary = run_pilot.summarize(trials, cfg["budget"]["executions"], cfg["report_success_at"])
    for name, data in (("manifest", meta), ("trials", trials), ("summary", summary)):
        (run_dir / f"{name}.json").write_text(json.dumps(data, indent=1, default=str))
    if not args.smoke:
        out = HERE / "results" / stamp
        out.mkdir(parents=True)
        for name in ("manifest.json", "trials.json", "trials.jsonl", "summary.json"):
            (out / name).write_bytes((run_dir / name).read_bytes())
    print(json.dumps(summary, indent=1))
    print(run_dir)


if __name__ == "__main__":
    main()
