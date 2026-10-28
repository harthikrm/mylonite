"""Ablation A2 (EVALUATION_PLAN.md §3): Muse without source, on the pilot's development targets.
Exploratory, development only; not an independent replication or a held-out result (PROTOCOL.md).

A2 is M4's code path (``methods.run_m4``) with ``include_source: false`` and nothing else changed:
the same catalog, domains, contract, limits, budgets, verification, executor and prices as the
pilot. The pilot runner's model classes (retry rule, recording, replay) and summary are imported
unchanged from experiments/2026-10-29-pilot/run_pilot.py. Two additions:
- every request must pass ``a2_audit.check`` (no source, directly or indirectly) before it is
  sent, besides ``audit.assert_clean`` inside run_m4;
- a strict cost cap: a call is refused when spend so far plus a per-call reserve would exceed the
  cap, so no single call can carry spend past it (the pilot's cap is checked only before a call).
Writes:
  runs/a2-<ts>/      raw: every execution, profile, verification and model call (git-ignored)
  results/<ts>/      curated: manifest, trial summaries, model I/O (committed after a run)
Modes: --smoke (stub model, budget 40, seed 1, raw only), --replay-model FILE (no API call).
"""

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))

from mylonite import methods, planner  # noqa: E402
from mylonite.sandbox import Sandbox  # noqa: E402

import a2_audit  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "run_pilot", REPO / "experiments/2026-10-29-pilot/run_pilot.py")
pilot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pilot)

COMPARED_TREES = ("src/", "fixtures/", "docker/", "tests/")


class StrictCap:
    """Wraps a model: refuses a call that could take spend past the cap, or whose request fails
    the A2 payload check. A refusal ends the trial in ``error``, which invalidates the run."""

    def __init__(self, inner, cap, reserve, targets):
        self.inner, self.cap, self.reserve, self.targets = inner, cap, reserve, targets
        self.trial = None

    def __call__(self, body, round_no):
        self.inner.trial = self.trial
        spent = getattr(self.inner, "spent", 0.0)
        if spent + self.reserve > self.cap:
            raise RuntimeError(f"strict cost cap: ${spent:.4f} spent + ${self.reserve} reserve "
                               f"> ${self.cap}")
        problems, _ = a2_audit.check(body, self.targets[self.trial.split("/")[0]], REPO)
        if problems:
            raise RuntimeError(f"A2 payload check refused the request: {problems[:5]}")
        return self.inner(body, round_no)


def against_pilot(meta, cfg):
    """Which compared files differ from the pilot run's manifest (added, removed or changed)."""
    reference = json.loads((REPO / cfg["pilot_reference"]["results"] / "manifest.json").read_text())
    old = {p: h for p, h in reference["files_sha256"].items() if p.startswith(COMPARED_TREES)}
    new = {p: h for p, h in meta["files_sha256"].items() if p.startswith(COMPARED_TREES)}
    return sorted(p for p in old.keys() | new.keys() if old.get(p) != new.get(p))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--budget", type=int, help="execution budget override (smoke only)")
    parser.add_argument("--replay-model")
    args = parser.parse_args()

    cfg = json.loads((HERE / "config.json").read_text())
    if cfg["A2"]["include_source"] is not False:
        sys.exit("config.json: A2 must have include_source false")
    if args.budget and not args.smoke:
        parser.error("--budget is for --smoke runs; A2 uses config.json")
    if not args.smoke and pilot.git("status", "--porcelain"):
        sys.exit("refusing a non-smoke run on a dirty tree: commit first, so the manifest's "
                 "commit identifies exactly what ran")
    targets = [json.loads((REPO / p).read_text()) for p in cfg["targets"]]
    by_name = {t["target"]: t for t in targets}
    seeds = cfg["seeds"]
    if args.smoke:
        seeds = seeds[:1]
        cfg["budget"]["executions"] = args.budget or 40

    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = REPO / "runs" / f"a2-{'smoke-' if args.smoke else ''}{stamp}"
    run_dir.mkdir(parents=True)
    calls_file = (run_dir / "model_calls.jsonl").open("w")

    def record_call(entry):
        calls_file.write(methods.json_line(entry) + "\n")
        calls_file.flush()

    reserve = 0.0
    if args.replay_model:
        inner = pilot.RecordedModel(args.replay_model, record_call)
    elif args.smoke:
        inner = pilot.StubModel(by_name, record_call)
    else:
        key = planner.load_api_key(REPO)
        if key is None:
            sys.exit("MODEL_API_KEY is not set (environment or .env)")
        inner = pilot.LiveModel(key, cfg, record_call)
        reserve = cfg["per_call_reserve_usd"]
    model = StrictCap(inner, cfg["model_cost_cap_usd"], reserve, by_name)
    trial_cfg = {**cfg, "M4": cfg["A2"]}  # A2 is run_m4 with this method config

    box = Sandbox("mylonite-a2", REPO)
    meta = pilot.manifest(cfg, box, {}, args)  # before any trial: code, config and images as run
    meta["a2_files_sha256"] = {str(p.relative_to(REPO)): pilot.sha256(p)
                               for p in sorted(HERE.glob("*")) if p.is_file()}
    meta["differs_from_pilot_run"] = against_pilot(meta, cfg)
    trials, ready_info = [], {}
    events_file = (run_dir / "executions.jsonl").open("w")
    trials_file = (run_dir / "trials.jsonl").open("w")  # appended as trials finish
    try:
        for target in targets:
            box.up()
            with box.session(target, **cfg["executor"]) as session:
                ready_info[target["target"]] = session.ready
                for seed in seeds:
                    key = f"{target['target']}/A2/{seed}"
                    model.trial = key

                    def log(event, key=key):
                        events_file.write(methods.json_line({"trial": key, **event}) + "\n")

                    result = methods.run_trial("M4", session, target, seed, trial_cfg, log,
                                               model=model, repo_root=REPO)
                    result["method"] = "A2"
                    result["implemented_as"] = "methods.run_m4 with include_source=false"
                    trials.append(result)
                    trials_file.write(methods.json_line(result) + "\n")
                    trials_file.flush()
                    print(f"{key}: {result['status']} e1={result['e1_executions']} "
                          f"executions={result['executions']} method_s={result['method_s']} "
                          f"model_calls={result['model_calls']} model_usd={result['model_usd']}",
                          flush=True)
    finally:
        box.down()
        events_file.close()
        trials_file.close()
        calls_file.close()

    meta["executor"] = ready_info
    meta["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    summary = pilot.summarize(trials, cfg["budget"]["executions"], cfg["report_success_at"])
    for name, data in (("manifest", meta), ("trials", trials), ("summary", summary)):
        (run_dir / f"{name}.json").write_text(json.dumps(data, indent=1, default=str))
    if not args.smoke:
        out = HERE / "results" / stamp
        out.mkdir(parents=True)
        for name in ("manifest.json", "trials.json", "trials.jsonl", "summary.json",
                     "model_calls.jsonl"):
            (out / name).write_bytes((run_dir / name).read_bytes())
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
