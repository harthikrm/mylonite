"""Held-out evaluation runner, v1.0 minimum scope (docs/HELDOUT_PROTOCOL.md C5; docs/FREEZE.md
§6; class A tooling, docs/AMENDMENTS.md AM-001).

  run_heldout.py <sealed root> --approved-cap <usd>
  run_heldout.py <toy root> --smoke                        plumbing check: stub model, seeds 1-2

Before any trial it refuses unless:
- it runs from this path;
- the tree is clean;
- ``freeze/manifest.py check`` passes;
- the unit tests pass;
- the sealed root is outside the repository, and ``heldout.verify_all`` finds nothing:
  - C2 still binds the bases, and C4 binds every file under heldout/;
  - the C4 record is for the round named at C2, with the committed beacon response;
  - the record follows the C4 rules;
  - each mutant is exactly mutate(base, chosen site);
- ``--approved-cap`` equals the config's cap, which is the owner's approval of model spend.

Then every trial runs in the config's order: the mutants, then the bases as negative controls,
seeds 1-20, and the methods in their listed order.
- **Crash rule:** an errored trial is re-run once with the same seed, and both attempts are kept.
- **Cost cap (strict):** a model call is refused if spend so far plus the reserve would exceed the
  cap. A model trial is not started unless spend plus 5 reserves fits, so a trial is never cut
  midway. Model trials that cannot start are recorded as ``not_run``.
- **Stop rules** (FREEZE.md §6):
  - a contamination refusal, or an A2 payload refusal;
  - a soundness problem, including on the corrected variant during verification;
  - any VIOLATION on a base, whether in a control trial or in a witness's corrected-variant
    check;
  - 3 errored trials in a row, or a crash-rule re-run that fails with the same exception type;
  - a harness failure outside a trial (for example, the sandbox cannot start).

  After a stop, every remaining trial is recorded as ``not_run`` with the reason.
- **Records** are appended to ``trials.jsonl`` as each trial ends. The manifest is written even
  if the run fails.
- **Screen output** is progress counts and spend only. Raw logs, which contain held-out source,
  stay in <sealed root>/private/logs/. ``trials.json`` and ``manifest.json`` go to
  experiments/heldout-v1/results/<ts>/.
- Each model answer's reported model must be ``muse-spark-1.3``; any other is counted and
  reported.
"""

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "experiments/2026-10-28-a2-no-source"))

from mylonite import methods, planner  # noqa: E402
from mylonite.sandbox import Sandbox  # noqa: E402
import a2_audit  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pilot = _load("run_pilot", REPO / "experiments/2026-10-29-pilot/run_pilot.py")
heldout = _load("heldout", HERE / "heldout.py")

EXPECTED_PATH = REPO / "experiments/heldout-v1/run_heldout.py"
EXPECTED_MODEL = "muse-spark-1.3"
MAX_CALLS = 5  # rounds per Muse trial, one call each


class StopRun(Exception):
    pass


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)


class CappedModel:
    """The A2 runner's strict cap, and for A2 also its payload check (no source, directly or
    indirectly), with the sealed root as the source of both variants. It also counts answers
    whose reported model is not the expected one."""

    def __init__(self, inner, cap, reserve, targets, root):
        self.inner, self.cap, self.reserve, self.targets, self.root = inner, cap, reserve, targets, root
        self.trial, self.condition, self.model_strings = None, None, {}

    @property
    def spent(self):
        return getattr(self.inner, "spent", 0.0)

    def can_start_trial(self):
        return self.spent + MAX_CALLS * self.reserve <= self.cap

    def __call__(self, body, round_no):
        self.inner.trial = self.trial
        if self.spent + self.reserve > self.cap:
            raise RuntimeError(f"strict cost cap: ${self.spent:.4f} spent + ${self.reserve} > ${self.cap}")
        if self.condition == "A2":
            problems, _ = a2_audit.check(body, self.targets[self.trial.split("/")[0]], self.root)
            if problems:
                raise RuntimeError(f"A2 payload check refused the request: {problems[:5]}")
        plan, meta = self.inner(body, round_no)
        model = meta.get("model")
        self.model_strings[model] = self.model_strings.get(model, 0) + 1
        return plan, meta


def stop_reason(event, target, controls):
    """A stop rule this logged event triggers, or None."""
    record = event.get("record") or {}
    if event.get("event") in ("execution", "stress") and record.get("soundness_problems"):
        return f"soundness problem on {target}"
    if target in controls and event.get("event") in ("execution", "stress") \
            and record.get("verdict") == "VIOLATION":
        return f"VIOLATION on base {target}"
    if event.get("event") == "verification":
        corrected = event["result"].get("corrected") or {}
        if corrected.get("verdicts", {}).get("VIOLATION"):
            return f"VIOLATION on the corrected variant (a base) while verifying on {target}"
        if corrected.get("soundness_problems"):
            return f"soundness problem on the corrected variant while verifying on {target}"
    return None


def error_type(status):
    """'error:ModelAPIError: HTTP 500 …' → 'ModelAPIError'."""
    return status.split(":", 2)[1].strip() if status.startswith("error:") else None


def not_run(target, method, seed, reason):
    return {"target": target, "method": method, "seed": seed, "status": "not_run",
            "reason": reason, "e1_executions": None, "executions": 0, "method_s": 0.0,
            "exec_s": 0.0, "model_usd": 0.0, "compute_usd": 0.0, "counters": {}}


def plan_of(cfg, mutants, controls, seeds):
    return ([(t, s, m) for t in mutants for s in seeds for m in cfg["methods"]["buggy"]]
            + [(t, s, m) for t in controls for s in seeds for m in cfg["methods"]["negative_controls"]])


def preflight(args, cfg, root):
    """Refusals before anything runs. Returns the C4 commitment (None in a smoke run)."""
    if Path(__file__).resolve() != EXPECTED_PATH:
        sys.exit(f"refusing: run from {EXPECTED_PATH}, not {Path(__file__).resolve()}")
    if REPO in root.parents or root == REPO:
        sys.exit("refusing: the sealed root must be outside the repository")
    if args.smoke:
        return None
    if git("status", "--porcelain").stdout.strip():
        sys.exit("refusing: dirty tree")
    check = subprocess.run([sys.executable, str(REPO / "freeze/manifest.py"), "check"],
                           capture_output=True, text=True)
    if check.returncode:
        sys.exit(f"refusing: freeze check failed\n{check.stderr}")
    tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                           capture_output=True, text=True, cwd=REPO)
    if tests.returncode:
        sys.exit(f"refusing: unit tests fail\n{tests.stderr[-2000:]}")
    problems = heldout.verify_all(root)
    if problems:
        sys.exit("refusing: the sealed root does not verify:\n  " + "\n  ".join(problems))
    commitment = heldout.committed("c4_commitment.json")
    if args.approved_cap != cfg["model_cost_cap_usd"]:
        sys.exit(f"refusing: --approved-cap must equal the config's cap (${cfg['model_cost_cap_usd']})")
    return commitment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("--approved-cap", type=float)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    cfg = json.loads((HERE / "config.json").read_text())
    root = Path(args.root).resolve()
    commitment = preflight(args, cfg, root)
    names = commitment["names"] if commitment else sorted(
        p.name for p in (root / "heldout").iterdir() if (p / "target.json").exists())
    mutants = [n for n in names if n.endswith("_m")]
    controls = [n for n in names if not n.endswith("_m")]
    seeds = [1, 2] if args.smoke else cfg["seeds"]
    targets = {}
    for name in mutants + controls:
        target = heldout.load_target(root, name)
        if name in controls:
            target["variants"] = {"buggy": f"heldout.{name}.service"}  # a base has no corrected variant
        targets[name] = target

    stamp = time.strftime("%Y%m%d-%H%M%S")
    logs = root / "private" / "logs" / stamp
    logs.mkdir(parents=True)
    events = (logs / "executions.jsonl").open("w")
    calls = (logs / "model_calls.jsonl").open("w")

    def sink(entry):
        calls.write(json.dumps(entry, default=str) + "\n")
        calls.flush()

    if args.smoke:
        inner = pilot.StubModel(targets, sink)
        reserve = 0.0
    else:
        key = planner.load_api_key(REPO)
        if key is None:
            sys.exit("MODEL_API_KEY is not set (environment or .env)")
        inner = pilot.LiveModel(key, cfg, sink)
        reserve = cfg["per_call_reserve_usd"]
    model = CappedModel(inner, cfg["model_cost_cap_usd"], reserve, targets, root)

    plan = plan_of(cfg, mutants, controls, seeds)
    meta = {"commit": git("rev-parse", "HEAD").stdout.strip(),
            "dirty": bool(git("status", "--porcelain").stdout.strip()), "smoke": args.smoke,
            "freeze_check": subprocess.run([sys.executable, str(REPO / "freeze/manifest.py"), "check"],
                                           capture_output=True, text=True).stdout.strip(),
            "config_sha256": hashlib.sha256((HERE / "config.json").read_bytes()).hexdigest(),
            "c4_commitment": commitment, "mutants": mutants, "controls": controls,
            "prompt_fingerprint": planner.prompt_fingerprint(), "planned_trials": len(plan),
            "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    out = (REPO / "runs" / f"heldout-smoke-{stamp}") if args.smoke else (HERE / "results" / stamp)
    out.mkdir(parents=True)
    stream = (out / "trials.jsonl").open("w")
    trials, stopped, consecutive_errors, done = [], None, 0, 0

    def keep(record):
        trials.append(record)
        stream.write(json.dumps(record, default=str) + "\n")
        stream.flush()
    try:
        for name in mutants + controls:
            mine = [(s, m) for t, s, m in plan if t == name]
            if stopped:
                for s, m in mine:
                    keep(not_run(name, m, s, f"stopped: {stopped}"))
                continue
            box = Sandbox(f"mylonite-heldout-{name}", REPO, target_root=root / "heldout")
            try:
                box.up()
                meta.setdefault("images", box.image_ids())
                with box.session(targets[name], **cfg["executor"]) as session:
                    for seed, method in mine:
                        if stopped:
                            keep(not_run(name, method, seed, f"stopped: {stopped}"))
                            continue
                        is_model = method in ("M4", "A2")
                        if is_model and not model.can_start_trial():
                            keep(not_run(name, method, seed, "model cost cap"))
                            continue
                        trial_cfg = {**cfg, "M4": cfg[method]} if is_model else cfg
                        key = f"{name}/{method}/{seed}"
                        model.trial, model.condition = key, method
                        for attempt in (1, 2):
                            def log(event, key=key, attempt=attempt):
                                events.write(methods.json_line({"trial": key, "attempt": attempt,
                                                                **event}) + "\n")
                                reason = stop_reason(event, name, controls)
                                if reason:
                                    raise StopRun(reason)
                            result = methods.run_trial("M4" if is_model else method, session,
                                                       targets[name], seed, trial_cfg, log,
                                                       model=model, repo_root=root)
                            result.update(method=method, attempt=attempt)
                            keep(result)
                            status = result["status"]
                            if status.startswith("error:StopRun"):
                                stopped = status.split(":", 2)[-1].strip()
                            elif "ContaminationError" in status:
                                stopped = "contamination refusal"
                            elif "A2 payload check refused" in status:
                                stopped = "A2 payload refusal"
                            elif name in controls and "serial run violated" in status:
                                stopped = f"VIOLATION in a serial profile on base {name}"
                            if stopped or not status.startswith("error"):
                                break
                            if attempt == 2 and error_type(status) == error_type(trials[-2]["status"]):
                                stopped = "a crash-rule re-run failed with the same exception type"
                            if attempt == 1 and is_model and not model.can_start_trial():
                                break  # no re-run that the cap could cut; the error stands
                        errored = trials[-1]["status"].startswith("error")
                        consecutive_errors = consecutive_errors + 1 if errored else 0
                        if consecutive_errors >= 3 and not stopped:
                            stopped = "3 errored trials in a row"
                        done += 1
                        if done % 10 == 0:
                            print(f"[{done}/{len(plan)}] trials; model ${model.spent:.2f}", flush=True)
            except Exception as exc:  # outside any trial: the sandbox or the session failed
                stopped = stopped or f"harness failure on {name}: {type(exc).__name__}: {str(exc)[:300]}"
                recorded = {(t["seed"], t["method"]) for t in trials if t["target"] == name}
                for s_, m_ in mine:
                    if (s_, m_) not in recorded:
                        keep(not_run(name, m_, s_, f"stopped: {stopped}"))
            finally:
                box.down()
    finally:
        events.close()
        calls.close()
        stream.close()
        meta.update(finished=time.strftime("%Y-%m-%dT%H:%M:%S%z"), stopped=stopped,
                    model_spent_usd=round(model.spent, 4), model_strings=model.model_strings,
                    unexpected_model_answers=sum(v for k, v in model.model_strings.items()
                                                 if k not in (EXPECTED_MODEL, "stub")),
                    records=len(trials))
        (out / "trials.json").write_text(json.dumps(trials, indent=1, default=str))
        (out / "manifest.json").write_text(json.dumps(meta, indent=1, default=str))
    print(f"done: {len(trials)} records; stopped: {stopped or 'no'}; results in {out}")


if __name__ == "__main__":
    main()
