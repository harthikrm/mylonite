"""Search methods and the trial runner (EVALUATION_PLAN.md §2–§3). Host side; standard library.

``Trial`` is the only place where executions are counted, budgets enforced and violations
verified. The methods differ only in how they choose workloads and schedules. They share the
catalog, domains and size limits (space.py), the contract (checked by the executor's oracle on
every execution), the per-experiment schedule cap, and the verification procedure.

- M0  stress: M1's workload draw run in real time without schedule control; a hit is then
      reproduced under the scheduler, since an uncontrolled run has no schedule to replay.
- M1  random workload (space.random_workload) under a random schedule, one execution each.
- M3+ greybox setup search plus conflict-directed exhaustive exploration of pairs.
- M3+arg  M3+, except that the argument variants of the pairs it explored come first among its
      deferred pairs (D-024).
- M4  Muse proposes experiments; each runs hint-first, then depth-first up to the cap; the model
      sees results of its own experiments only (planner.feedback_entry).
"""

import collections
import itertools
import json
import random
import time

from . import audit, planner, space
from .resp import WRITES
from .scheduler import next_prefix


class BudgetExhausted(Exception):
    pass


class TrialError(Exception):
    pass


class Found(Exception):
    def __init__(self, record, verification, executions):
        super().__init__("verified violation")
        self.record, self.verification, self.executions = record, verification, executions


class Trial:
    def __init__(self, session, target, budget, verify_cfg, prices, log):
        self.session, self.target, self.budget = session, target, budget
        self.verify_cfg, self.prices, self.log = verify_cfg, prices, log
        self.executions = 0
        self.exec_s = self.overhead_s = self.model_s = self.verification_s = 0.0
        self.model_usd = 0.0
        self.tokens = collections.Counter()
        self.model_calls = 0
        self.replayed_latency_s = 0.0  # replayed answers return at once; their recorded latency counts
        self.unverified = []
        self.stats = collections.Counter()
        self.started = time.monotonic()

    # --- accounting ------------------------------------------------------------------------
    def method_seconds(self):
        """Wall-clock charged to the method: everything except harness overhead (process and
        container round trips) and verification, which are reported separately."""
        return (time.monotonic() - self.started - self.overhead_s - self.verification_s
                + self.replayed_latency_s)

    def check_budget(self):
        if self.executions >= self.budget["executions"]:
            raise BudgetExhausted("executions")
        if self.method_seconds() >= self.budget["method_seconds"]:
            raise BudgetExhausted("time")

    def _request(self, request):
        out, rtt = self.session.request(request)
        self.exec_s += out["ms"] / 1000
        self.overhead_s += max(rtt - out["ms"] / 1000, 0.0)
        return out

    def charge_model(self, meta):
        self.model_calls += 1
        self.model_s += meta["latency_s"]
        if meta.get("replayed"):
            self.replayed_latency_s += meta["latency_s"]
        usage = meta.get("usage") or {}
        prompt, completion = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
        reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0) or 0
        self.tokens.update(prompt=prompt, cached=cached, completion=completion, reasoning=reasoning)
        cost = ((prompt - cached) * self.prices["input"] + cached * self.prices["cached"]
                + completion * self.prices["output"]) / 1e6
        self.model_usd += cost
        return cost

    # --- the only ways a method can touch the target ------------------------------------------
    def execute(self, workload, policy):
        self.check_budget()
        record = self._request({"op": "execute", "variant": "buggy", "workload": workload,
                                "policy": policy})
        self.executions += 1
        self.stats[record["verdict"]] += 1
        self.log({"event": "execution", "n": self.executions, "policy": policy, "record": record})
        if record["verdict"] == "VIOLATION":
            self._on_violation(record)
        return record

    def stress(self, workload):
        """One uncontrolled execution (M0). Its verdict is never verified directly: there is
        no decision list to replay."""
        self.check_budget()
        record = self._request({"op": "stress", "variant": "buggy", "workload": workload})
        self.executions += 1
        self.stats["stress"] += 1
        self.stats[f"stress_{record['verdict']}"] += 1
        self.log({"event": "stress", "n": self.executions, "record": record})
        return record

    def profile(self, setup, call):
        self.check_budget()
        out = self._request({"op": "profile", "variant": "buggy", "setup": setup, "call": call})
        self.executions += 1
        self.stats["profile"] += 1
        self.log({"event": "profile", "n": self.executions, "setup": setup, "call": call,
                  "result": out})
        if out["verdict"] == "VIOLATION":
            raise TrialError("a serial run violated the contract: the target spec is wrong")
        return out

    def explore(self, workload, cap, first_policy=None):
        """Optional guided first schedule, then depth-first; at most ``cap`` schedules."""
        records, prefix = [], []
        if first_policy is not None:
            records.append(self.execute(workload, first_policy))
        while len(records) < cap:
            record = self.execute(workload, {"kind": "prefix", "prefix": prefix})
            records.append(record)
            prefix = next_prefix(record["steps"])
            if prefix is None:
                return records, True
        return records, False

    def _on_violation(self, record):
        started = time.monotonic()
        verification = verify(self.session, self.target, record, self.verify_cfg)
        self.verification_s += time.monotonic() - started
        self.log({"event": "verification", "n": self.executions, "result": verification})
        if verification["verified"]:
            raise Found(record, verification, self.executions)
        self.unverified.append({"n": self.executions, "verification": verification})

    def summary(self):
        return {"executions": self.executions, "method_s": round(self.method_seconds(), 3),
                "exec_s": round(self.exec_s, 3), "overhead_s": round(self.overhead_s, 3),
                "verification_s": round(self.verification_s, 3),
                "model_s": round(self.model_s, 3), "model_calls": self.model_calls,
                "tokens": dict(self.tokens), "model_usd": round(self.model_usd, 6),
                "compute_usd": round(self.exec_s * self.prices["compute_per_second"], 6),
                "counters": dict(self.stats), "unverified_violations": self.unverified}


# --- verification (EVALUATION_PLAN.md §2 and §8; not charged to any method) -------------------

def verify(session, target, record, cfg):
    """Replay the witness ``cfg['replays']`` times on the original variant, then explore the same
    workload on the corrected variant: exhaustively if it fits under the cap, otherwise the cap's
    depth-first schedules plus ``cfg['corrected_bounded_random']`` random ones (reported as
    bounded).

    An INCONCLUSIVE execution is a harness problem, not evidence either way: with
    ``cfg['inconclusive_reruns']`` (default 0) it is run again, at most that many times. A run
    that completes with the wrong verdict or trace is never re-run. Rejected runs are listed."""
    workload, decisions = record["workload"], record["decisions"]
    reruns, rejected = collections.Counter(), []

    def run(variant, policy):
        for attempt in range(cfg.get("inconclusive_reruns", 0) + 1):
            out = session.request({"op": "execute", "variant": variant, "workload": workload,
                                   "policy": policy})[0]
            if out["verdict"] == "INCONCLUSIVE" and len(rejected) < 5:
                rejected.append({"variant": variant} | {k: out[k] for k in (
                    "decisions", "soundness_problems", "harness_error", "ms")})
            if out["verdict"] != "INCONCLUSIVE" or attempt == cfg.get("inconclusive_reruns", 0):
                return out
            reruns[variant] += 1

    replays = [run("buggy", {"kind": "replay", "decisions": decisions})
               for _ in range(cfg["replays"])]
    replay_ok = all(r["verdict"] == "VIOLATION" and r["trace_hash"] == record["trace_hash"]
                    for r in replays)
    corrected = {"mode": None, "schedules": 0, "verdicts": collections.Counter(),
                 "soundness_problems": 0}
    if "fixed" in target["variants"]:
        def run_corrected(policy):
            out = run("fixed", policy)
            corrected["schedules"] += 1
            corrected["verdicts"][out["verdict"]] += 1
            corrected["soundness_problems"] += len(out["soundness_problems"])
            return out
        prefix, exhausted = [], False
        while corrected["schedules"] < cfg["corrected_exhaustive_cap"]:
            prefix = next_prefix(run_corrected({"kind": "prefix", "prefix": prefix})["steps"])
            if prefix is None:
                exhausted = True
                break
        if not exhausted:
            for i in range(cfg["corrected_bounded_random"]):
                run_corrected({"kind": "random", "seed": f"verify:{record['trace_hash']}:{i}"})
        corrected["mode"] = "exhaustive" if exhausted else "bounded"
    corrected_ok = (corrected["mode"] is not None and corrected["soundness_problems"] == 0
                    and corrected["verdicts"]["PASS"] == corrected["schedules"])
    corrected["verdicts"] = dict(corrected["verdicts"])
    result = {"replays": len(replays),
              "replay_violations": sum(r["verdict"] == "VIOLATION" for r in replays),
              "replay_hash_matches": sum(r["trace_hash"] == record["trace_hash"] for r in replays),
              "corrected": corrected, "verified": bool(replay_ok and corrected_ok)}
    if reruns or rejected:  # absent when nothing was rejected, as in every pilot verification
        result["inconclusive_reruns"], result["rejected"] = dict(reruns), rejected
    return result


# --- M0 -----------------------------------------------------------------------------------------

def run_m0(trial, target, seed, cfg):
    """Stress, as a practitioner with this harness would run it: M1's workload draw, one
    uncontrolled execution each. On a hit, explore that workload depth-first under the
    scheduler, up to the per-workload cap; the first controlled violation goes through the
    shared verification. Every execution of both kinds counts. (EVALUATION_PLAN.md §3 planned to
    replay the command order the proxy saw. On a multiplexed client that order cannot be
    attributed to operations, so the hit is reproduced instead, D-031.)"""
    rng = random.Random(f"M0:{seed}")
    while True:
        workload = space.random_workload(target, rng)
        if trial.stress(workload)["verdict"] == "VIOLATION":
            trial.stats["m0_reproductions"] += 1
            trial.explore(workload, cfg["schedules_per_experiment"])


# --- M1 -----------------------------------------------------------------------------------------

def run_m1(trial, target, seed, cfg):
    rng = random.Random(f"M1:{seed}")
    for i in itertools.count():
        trial.execute(space.random_workload(target, rng), {"kind": "random", "seed": f"M1:{seed}:{i}"})


# --- M3+ ----------------------------------------------------------------------------------------

def conflict(a, b):
    """Two store commands ([name, key digest]) conflict if they touch one key and one writes."""
    return a[1] == b[1] and (a[0] in WRITES or b[0] in WRITES)


def unserializable_pair(pa, pb):
    """Can some interleaving of two command sequences have a cycle in its conflict graph?
    For two sequences that needs conflicting pairs (i, j) and (l, k) with a_i before b_j and b_k
    before a_l, which program order allows exactly when l > i or k < j. If not, every
    interleaving is conflict-equivalent to a serial order and is not worth exploring."""
    pairs = [(i, j) for i, ca in enumerate(pa) for j, cb in enumerate(pb) if conflict(ca, cb)]
    return any(l > i or k < j for i, j in pairs for l, k in pairs)


def pair_signature(a, b):
    """A pair's command signature: both profiles' commands and key digests, not argument values."""
    return tuple(map(tuple, a[1])), tuple(map(tuple, b[1]))


def pair_priority(pairs, observed_keys):
    """Split a state's candidate pairs into (now, later). Now: pairs with a conflict on a key the
    contract's observation reads, one per distinct command signature. Later: everything else,
    deferred rather than dropped. Uses only what M3+ measured itself."""
    now, later, signatures = [], [], set()
    for a, b in pairs:
        signature = pair_signature(a, b)
        relevant = any(conflict(x, y) and x[1] in observed_keys for x in a[1] for y in b[1])
        if relevant and signature not in signatures:
            signatures.add(signature)
            now.append((a, b))
        else:
            later.append((a, b))
    return now, later


def run_m3plus(trial, target, seed, cfg, promote_variants=False):
    """Breadth-first over setup states. At each state, profile every catalog call alone (one
    execution each). A call whose behavior (operation, command names, outcome) is new and which
    leads to a new store state extends the frontier. Then explore, depth-first up to the cap,
    the pairs of calls whose profiles at that state can interleave unserializably: first the
    contract-relevant ones (``pair_priority``), the rest after the frontier is exhausted.
    Seeds only shuffle the order of calls and pairs.

    ``promote_variants`` is M3+arg (D-024): of the deferred pairs, those deferred only because
    they share a command signature with a pair explored at the same state, that is, the same
    calls with other argument values, are explored first, in the order M3+ would have reached
    them. M3+arg uses M3+'s seed stream, so it is M3+ exactly until the frontier is exhausted."""
    rng = random.Random(f"M3+:{seed}")
    calls = space.op_calls(target)
    observe_op = target["observe"]["op"]
    behaviors, states = set(), set()
    frontier, variants, deferred = collections.deque([[]]), [], []
    while frontier:
        setup = frontier.popleft()
        order = calls[:]
        rng.shuffle(order)
        profiles = []
        for call in order:
            p = trial.profile(setup, call)
            profiles.append((call, p["commands"]))
            states.add(p["state_before"])
            behavior = (call["op"], tuple(c for c, _ in p["commands"]), p["outcome"])
            if (behavior not in behaviors and p["state_after"] not in states
                    and len(setup) < space.MAX_SETUP):
                states.add(p["state_after"])
                frontier.append(setup + [call])
            behaviors.add(behavior)
        pairs = [(a, b) for a, b in itertools.combinations_with_replacement(profiles, 2)
                 if unserializable_pair(a[1], b[1])]
        rng.shuffle(pairs)
        observed_keys = {key for call, commands in profiles if call["op"] == observe_op
                         for _, key in commands}
        now, later = pair_priority(pairs, observed_keys)
        trial.stats["m3_states"] += 1
        trial.stats["m3_pairs"] += len(pairs)
        trial.stats["m3_pairs_deferred"] += len(later)
        explored = {pair_signature(a, b) for a, b in now}
        for a, b in later:
            promoted = promote_variants and pair_signature(a, b) in explored
            (variants if promoted else deferred).append((setup, a, b))
        for (a, _), (b, _) in now:
            trial.explore({"setup": setup, "concurrent": [a, b]}, cfg["schedules_per_experiment"])
    if promote_variants:  # M3+'s counters stay exactly as in the pilot
        trial.stats["m3arg_variants_promoted"] += len(variants)
    for setup, (a, _), (b, _) in variants + deferred:
        trial.explore({"setup": setup, "concurrent": [a, b]}, cfg["schedules_per_experiment"])
    trial.stats["m3_plan_exhausted"] = 1


def run_m3plus_arg(trial, target, seed, cfg):
    run_m3plus(trial, target, seed, cfg, promote_variants=True)


# --- M4 -----------------------------------------------------------------------------------------

def run_m4(trial, target, seed, cfg, model, repo_root):
    """``model(body, round)`` returns (plan or None, meta); live, recorded or stub."""
    feedback = []
    for round_no in range(1, cfg["max_rounds"] + 1):
        trial.check_budget()
        body = planner.build_request(target, repo_root, feedback, cfg["include_source"],
                                     cfg["reasoning_effort"])
        audit.assert_clean(body, target, repo_root)
        plan, meta = model(body, round_no)
        cost = trial.charge_model(meta)
        trial.log({"event": "model_call", "round": round_no, "request": body, "meta": meta,
                   "cost_usd": cost})
        if plan is None:
            trial.stats["plans_unparseable"] += 1
            feedback.append({"round": round_no, "plan_error": "answer did not match the schema",
                             "results": []})
            continue
        experiments, problems = planner.validate(plan, target)
        trial.stats["experiments_proposed"] += len(plan.get("experiments", []))
        trial.stats["experiments_valid"] += len(experiments)
        results = []
        for exp in experiments:
            records, exhausted = trial.explore(exp["workload"], cfg["schedules_per_experiment"],
                                               {"kind": "hint", "hint": exp["hint"]})
            stats = records[0].get("policy_stats", {})
            trial.stats["hint_followed"] += stats.get("hint_followed", 0)
            trial.stats["hint_skipped"] += stats.get("hint_skipped", 0)
            results.append(planner.feedback_entry(exp, records, exhausted))
        feedback.append({"round": round_no, "results": results,
                         "rejected": [{"experiment": p["experiment"],
                                       "issues": planner.issue_codes(p["issues"])}
                                      for p in problems]})
        trial.log({"event": "validation", "round": round_no, "problems": problems})
    trial.stats["m4_rounds_exhausted"] = 1


METHODS = {"M0": run_m0, "M1": run_m1, "M3+": run_m3plus, "M3+arg": run_m3plus_arg, "M4": run_m4}


def run_trial(method, session, target, seed, cfg, log, model=None, repo_root=None):
    trial = Trial(session, target, cfg["budget"], cfg["verification"], cfg["prices"], log)
    status, witness, verification, e1 = None, None, None, None
    method_cfg = {**cfg["budget"], **cfg.get(method, {})}
    try:
        if method == "M4":
            run_m4(trial, target, seed, method_cfg, model, repo_root)
        else:
            METHODS[method](trial, target, seed, method_cfg)
        status = "search_plan_exhausted"
    except Found as found:
        status, e1, verification = "verified", found.executions, found.verification
        witness = {k: found.record[k] for k in ("workload", "decisions", "trace_hash", "pre",
                                                "post", "violations", "setup_outcomes")}
    except BudgetExhausted as exc:
        status = f"censored:{exc}"
    except Exception as exc:  # any failure ends this trial only; it is reported, never dropped
        status = f"error:{type(exc).__name__}: {str(exc)[:500]}"
    return {"target": target["target"], "method": method, "seed": seed, "status": status,
            "e1_executions": e1, "witness": witness, "verification": verification,
            **trial.summary()}


def json_line(obj):
    return json.dumps(obj, sort_keys=True, default=str)
