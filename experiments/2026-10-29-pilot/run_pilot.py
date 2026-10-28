"""Pilot value checkpoint (EVALUATION_PLAN.md §9). Host side, standard library only.

Every trial of every method runs through ``methods.run_trial`` against one persistent executor
per target, with the budgets, seeds and caps in config.json. Writes:
  runs/pilot-<ts>/      raw: every execution, profile, verification and model call (git-ignored)
  results/<ts>/         curated: manifest, trial summaries, model I/O (committed after a run)
Modes:
  --smoke               harness check, not pilot data: small budget, one seed, stub model, raw only
  --replay-model FILE   re-run M4 from recorded model answers (model_calls.jsonl); no API call
"""

import argparse
import hashlib
import json
import platform
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from mylonite import methods, planner, space  # noqa: E402
from mylonite.sandbox import Sandbox  # noqa: E402

HERE = Path(__file__).resolve().parent


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True,
                          text=True).stdout.strip()


def manifest(cfg, box, ready, args):
    files = [p for d in ("src", "fixtures", "docker", "tests") for p in (REPO / d).rglob("*")
             if p.is_file() and "__pycache__" not in p.parts]
    files += [HERE / "config.json", Path(__file__)]
    return {"git_commit": git("rev-parse", "HEAD"),
            "git_dirty": git("status", "--porcelain").splitlines(),
            "files_sha256": {str(p.relative_to(REPO)): sha256(p) for p in sorted(files)},
            "host_python": platform.python_version(), "images": box.image_ids(),
            "executor": ready, "prompt_version": planner.PROMPT_VERSION,
            "prompt_fingerprint": planner.prompt_fingerprint(), "model": planner.MODEL,
            "config": cfg, "argv": sys.argv[1:],
            "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}


class LiveModel:
    """Pre-registered retry rule: up to 3 attempts on transport errors, HTTP 429 and 5xx, waiting
    5 s then 15 s. Time spent on failed attempts and waits counts as model latency."""

    WAITS = (5, 15)

    def __init__(self, key, cfg, sink):
        self.key, self.cap, self.prices, self.sink = key, cfg["model_cost_cap_usd"], cfg["prices"], sink
        self.spent, self.trial = 0.0, None

    def __call__(self, body, round_no):
        if self.spent >= self.cap:
            raise RuntimeError(f"model cost cap ${self.cap} reached")
        started, failures = time.monotonic(), []
        for attempt in range(len(self.WAITS) + 1):
            try:
                plan, meta = planner.call_muse(self.key, body)
                break
            except planner.ModelAPIError as exc:
                failures.append(str(exc)[:300])
                self.sink({"trial": self.trial, "round": round_no, "failed_attempt": attempt + 1,
                           "error": failures[-1]})
                if not exc.retryable or attempt == len(self.WAITS):
                    raise
                time.sleep(self.WAITS[attempt])
        meta["latency_s"] = round(time.monotonic() - started, 2)
        meta["failed_attempts"] = failures
        usage = meta.get("usage") or {}
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
        self.spent += ((usage.get("prompt_tokens", 0) - cached) * self.prices["input"]
                       + cached * self.prices["cached"]
                       + usage.get("completion_tokens", 0) * self.prices["output"]) / 1e6
        self.sink({"trial": self.trial, "round": round_no, "request": body, **meta})
        return plan, meta


class RecordedModel:
    """Answers from a previous run's model_calls.jsonl. Refuses if the request differs, since the
    recorded answer would then not belong to this request."""

    def __init__(self, path, sink):
        self.calls = {}
        for line in Path(path).read_text().splitlines():
            entry = json.loads(line)
            self.calls[(entry["trial"], entry["round"])] = entry
        self.sink, self.trial = sink, None

    def __call__(self, body, round_no):
        entry = self.calls.get((self.trial, round_no))
        if entry is None:
            raise RuntimeError(f"no recorded answer for {self.trial} round {round_no}")
        if json.dumps(entry["request"], sort_keys=True) != json.dumps(body, sort_keys=True):
            raise RuntimeError(f"request for {self.trial} round {round_no} differs from the record")
        meta = {**{k: entry[k] for k in ("latency_s", "usage", "model", "response")},
                "replayed": True}
        self.sink({**entry, "replayed": True})
        try:
            return json.loads(entry["response"]["choices"][0]["message"]["content"]), meta
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            meta["parse_error"] = f"{type(exc).__name__}: {exc}"
            return None, meta


class StubModel:
    """Smoke tests only: one random valid experiment per round, no API."""

    def __init__(self, target_by_name, sink):
        self.targets, self.sink, self.trial = target_by_name, sink, None

    def __call__(self, body, round_no):
        target = self.targets[self.trial.split("/")[0]]
        workload = space.random_workload(target, random.Random(f"{self.trial}:{round_no}"))
        plan = {"hypotheses": [], "experiments": [{
            "hypothesis_id": "stub", "expected_effect": "", "schedule_hint": [],
            "setup": workload["setup"], "concurrent": workload["concurrent"]}]}
        response = {"model": "stub", "usage": {},
                    "choices": [{"message": {"content": json.dumps(plan)}}]}  # the API's shape
        meta = {"latency_s": 0.0, "usage": {}, "model": "stub", "response": response}
        self.sink({"trial": self.trial, "round": round_no, "request": body, **meta})
        return plan, meta


def summarize(trials, budget, success_at):
    """Per target and method. Censored trials count as budget + 1 in the median (§7), and
    Success@b is read off E1, so no statistic quietly drops a failed trial."""
    out = {}
    for t in trials:
        out.setdefault(t["target"], {}).setdefault(t["method"], []).append(t)
    table = {}
    for target, by_method in out.items():
        for method, ts in by_method.items():
            e1 = [t["e1_executions"] if t["status"] == "verified" else None for t in ts]
            table.setdefault(target, {})[method] = {
                "trials": len(ts), "verified": sum(e is not None for e in e1),
                "statuses": sorted({t["status"] for t in ts}),
                "e1_executions": e1,
                "median_e1_censored_at_budget_plus_1": statistics.median(
                    e if e is not None else budget + 1 for e in e1),
                "success_at": {str(b): sum(e is not None and e <= b for e in e1)
                               for b in success_at},
                "method_s": [t["method_s"] for t in ts],
                "model_usd_total": round(sum(t["model_usd"] for t in ts), 5)}
    return table


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--targets", nargs="*", help="subset by target id (smoke only)")
    parser.add_argument("--methods", nargs="*")
    parser.add_argument("--budget", type=int, help="execution budget override (smoke only)")
    parser.add_argument("--replay-model")
    args = parser.parse_args()

    cfg = json.loads((HERE / "config.json").read_text())
    if (args.targets or args.budget) and not args.smoke:
        parser.error("--targets and --budget are for --smoke runs; the pilot uses config.json")
    if not args.smoke and git("status", "--porcelain"):
        sys.exit("refusing a non-smoke run on a dirty tree: commit first, so the manifest's "
                 "commit identifies exactly what ran")
    targets = [json.loads((REPO / p).read_text()) for p in cfg["targets"]]
    if args.targets:
        targets = [t for t in targets if t["target"] in args.targets]
    method_names = args.methods or cfg["methods"]
    seeds = cfg["seeds"]
    if args.smoke:
        seeds = seeds[:1]
        cfg["budget"]["executions"] = args.budget or 40
        cfg["model_cost_cap_usd"] = 0.0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = REPO / "runs" / f"pilot-{'smoke-' if args.smoke else ''}{stamp}"
    run_dir.mkdir(parents=True)
    calls_file = (run_dir / "model_calls.jsonl").open("w")

    def record_call(entry):
        calls_file.write(methods.json_line(entry) + "\n")
        calls_file.flush()

    if args.replay_model:
        model = RecordedModel(args.replay_model, record_call)
    elif args.smoke:
        model = StubModel({t["target"]: t for t in targets}, record_call)
    elif "M4" in method_names:
        key = planner.load_api_key(REPO)
        if key is None:
            sys.exit("MODEL_API_KEY is not set (environment or .env)")
        model = LiveModel(key, cfg, record_call)
    else:
        model = None

    box = Sandbox("mylonite-pilot", REPO)
    meta = manifest(cfg, box, {}, args)  # before any trial: code, config and images as run
    trials, ready_info = [], {}
    events_file = (run_dir / "executions.jsonl").open("w")
    trials_file = (run_dir / "trials.jsonl").open("w")  # appended as trials finish
    try:
        for target in targets:
            box.up()
            with box.session(target, **cfg["executor"]) as session:
                ready_info[target["target"]] = session.ready
                for seed in seeds:
                    for method in method_names:
                        key = f"{target['target']}/{method}/{seed}"
                        if model is not None:
                            model.trial = key

                        def log(event, key=key):
                            events_file.write(methods.json_line({"trial": key, **event}) + "\n")

                        result = methods.run_trial(method, session, target, seed, cfg, log,
                                                   model=model, repo_root=REPO)
                        trials.append(result)
                        trials_file.write(methods.json_line(result) + "\n")
                        trials_file.flush()
                        print(f"{key}: {result['status']} e1={result['e1_executions']} "
                              f"executions={result['executions']} method_s={result['method_s']} "
                              f"model_usd={result['model_usd']}", flush=True)
    finally:
        box.down()
        events_file.close()
        trials_file.close()
        calls_file.close()

    meta["executor"] = ready_info
    meta["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    summary = summarize(trials, cfg["budget"]["executions"], cfg["report_success_at"])
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
