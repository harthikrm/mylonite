"""Stress (M0) on D2 and D3 (PROTOCOL.md). Host side, standard library only. No model calls.

Every trial runs through ``methods.run_trial`` against one persistent executor per target, with
the pilot's budgets, verification and executor settings (config.json). Afterwards, the pilot's 30
trials are re-run in the same session by the D1 gate's regression script (recorded model answers,
no API call), as the timing reference. Writes:
  runs/m0-<ts>/      raw: every stress run, execution and verification (git-ignored)
  results/<ts>/      curated: manifest, trials, summary, the regression's report and trials
Modes:
  --smoke            harness check, not data: seed 0 only, a 200-execution budget, no regression
"""

import argparse
import hashlib
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))

from mylonite import methods  # noqa: E402
from mylonite.sandbox import Sandbox  # noqa: E402

_spec = importlib.util.spec_from_file_location("run_pilot", REPO / "experiments/2026-10-29-pilot/run_pilot.py")
run_pilot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_pilot)
REGRESSION = REPO / "experiments/2026-10-28-d1-gate/regression.py"


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True,
                          text=True).stdout.strip()


def manifest(cfg, box):
    files = [p for d in ("src", "fixtures", "docker", "tests") for p in (REPO / d).rglob("*")
             if p.is_file() and "__pycache__" not in p.parts]
    files += list(HERE.glob("*.py")) + [HERE / "config.json"]
    return {"git_commit": git("rev-parse", "HEAD"),
            "git_dirty": git("status", "--porcelain").splitlines(),
            "files_sha256": {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in sorted(files)},
            "host_python": platform.python_version(), "images": box.image_ids(),
            "config": cfg, "argv": sys.argv[1:], "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    cfg = json.loads((HERE / "config.json").read_text())
    if not args.smoke and git("status", "--porcelain"):
        sys.exit("refusing a non-smoke run on a dirty tree: commit first, so the manifest's "
                 "commit identifies exactly what ran")
    seeds = [0] if args.smoke else cfg["seeds"]
    if args.smoke:
        cfg["budget"]["executions"] = 200
    targets = [json.loads((REPO / p).read_text()) for p in cfg["targets"]]

    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = REPO / "runs" / f"m0-{'smoke-' if args.smoke else ''}{stamp}"
    run_dir.mkdir(parents=True)
    box = Sandbox("mylonite-m0", REPO)
    meta = manifest(cfg, box)  # before any trial: code, config and images as run
    trials, ready = [], {}
    events_file = (run_dir / "executions.jsonl").open("w")
    trials_file = (run_dir / "trials.jsonl").open("w")
    try:
        for target in targets:
            box.up()
            with box.session(target, **cfg["executor"]) as session:
                ready[target["target"]] = session.ready
                for seed in seeds:
                    for method in cfg["methods"]:
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
    finally:
        box.down()
        events_file.close()
        trials_file.close()

    meta["executor"] = ready
    meta["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    summary = run_pilot.summarize(trials, cfg["budget"]["executions"], cfg["report_success_at"])
    for name, data in (("manifest", meta), ("trials", trials), ("summary", summary)):
        (run_dir / f"{name}.json").write_text(json.dumps(data, indent=1, default=str))
    print(json.dumps(summary, indent=1))
    if args.smoke:
        print(run_dir)
        return
    out = HERE / "results" / stamp
    out.mkdir(parents=True)
    for name in ("manifest.json", "trials.json", "trials.jsonl", "summary.json"):
        (out / name).write_bytes((run_dir / name).read_bytes())
    done = subprocess.run([sys.executable, str(REGRESSION), str(REPO / cfg["pilot_raw_run"])],
                          capture_output=True, text=True)
    report = json.loads(done.stdout[done.stdout.index("{\n"):])
    reg = out / "same_session_regression"
    reg.mkdir()
    shutil.copy(REPO / report["run_dir"] / "report.json", reg / "report.json")
    shutil.copy(REPO / report["run_dir"] / "trials.json", reg / "trials.json")
    (reg / "commit.txt").write_text(git("rev-parse", "HEAD") + ("\n" if not git("status", "--porcelain") else " dirty\n"))
    print(json.dumps({k: report[k] for k in ("trials", "identical_trials", "identical_event_streams",
                                             "events_compared", "differences")}, indent=1))
    print(run_dir)


if __name__ == "__main__":
    main()
