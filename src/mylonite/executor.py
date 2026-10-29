"""Executor: runs experiments inside the sandbox network (ARCHITECTURE.md §9).

Reads one request as JSON on stdin and writes one JSON result to stdout. It starts the proxy on
127.0.0.1, drives each concurrent round through the controller, observes state through the
service's own read operation, and checks the target's contract.
"""

import hashlib
import importlib
import json
import random
import socket
import sys
import threading
import time

import redis

from . import oracle
from .proxy import Controller, Proxy
from .scheduler import (Divergence, HintPolicy, PrefixPolicy, RandomPolicy, ReplayPolicy,
                        next_prefix, soundness_problems, trace_hash)

PROXY = ("127.0.0.1", 6380)
# Raised when the proxy, the store or (for an out-of-process service) the transport to the
# service fails, not the service itself: the execution is inconclusive.
HARNESS_FAILURES = (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError,
                    ConnectionError, TimeoutError)


_shared = {}


def shared_controller(store, delta_q, target):
    """One proxy per executor process, shared by every variant's context. In-process services
    reach it on loopback; a service in its own container (the target spec lists it under
    ``services``) reaches it over the internal network. A multiplexed store client puts every
    operation on one connection (ARCHITECTURE.md §5.4)."""
    if "ctl" not in _shared:
        _shared["ctl"] = Controller(delta_q=delta_q,
                                    shared_connections=target.get("store_client") == "multiplexed")
        listen = ("0.0.0.0", PROXY[1]) if target.get("services") else PROXY
        Proxy(listen, store, _shared["ctl"]).start()
    return _shared["ctl"]


class Context:
    def __init__(self, request):
        self.target = request["target"]
        module = importlib.import_module(self.target["variants"][request["variant"]])
        service = self.target.get("services", {}).get(request["variant"])
        self.module = module.bind(service) if service else module
        self.store = tuple(request["store"])
        self.round_timeout = request.get("round_timeout_s", 10)
        self.ctl = shared_controller(self.store, request.get("delta_q_ms", 300) / 1000, self.target)


def reset(ctx):
    admin = redis.Redis(host=ctx.store[0], port=ctx.store[1])
    try:
        admin.flushall()
    finally:
        admin.close()


def observe(ctx, client):
    spec = ctx.target["observe"]
    read = getattr(ctx.module, spec["op"])
    return {value: read(client, **{spec["arg"]: value})
            for value in ctx.target["domains"][spec["for_each"]]}


def state_digest(ctx):
    """Digest of the whole store, read directly (not through the proxy). Greybox signal for M3+."""
    admin = redis.Redis(host=ctx.store[0], port=ctx.store[1])
    try:
        items = []
        for key in sorted(admin.scan_iter(count=1000)):
            kind = admin.type(key)
            kind = kind.decode() if isinstance(kind, bytes) else kind
            if kind == "string":
                value = admin.get(key)
            elif kind == "hash":
                value = sorted(admin.hgetall(key).items())
            elif kind == "set":
                value = sorted(admin.smembers(key))
            elif kind == "list":
                value = admin.lrange(key, 0, -1)
            elif kind == "zset":
                value = admin.zrange(key, 0, -1, withscores=True)
            else:
                value = None
            items.append([key, kind, value])
        return hashlib.sha256(repr(items).encode()).hexdigest()[:16]
    finally:
        admin.close()


def execute_once(ctx, workload, policy, digests=False):
    started = time.perf_counter()
    svc, ctl = ctx.module, ctx.ctl
    reset(ctx)
    setup_client = svc.connect(*PROXY)
    setup_outcomes, setup_failure = [], None
    try:
        for call in workload["setup"]:
            try:  # a setup call the service rejects is part of the workload, not a harness error
                getattr(svc, call["op"])(setup_client, **call["args"])
                setup_outcomes.append("ok")
            except HARNESS_FAILURES as exc:
                setup_failure = f"setup: {type(exc).__name__}: {exc}"
                break
            except Exception as exc:
                setup_outcomes.append(type(exc).__name__)
        pre = observe(ctx, setup_client)
    finally:
        setup_client.close()
    state_before = state_digest(ctx) if digests else None

    calls = workload["concurrent"]
    raw = [None] * len(calls)

    def run_op(k):
        value, error, harness = None, None, False
        try:
            client = svc.connect(*PROXY)
            try:
                value = getattr(svc, calls[k]["op"])(client, **calls[k]["args"])
            finally:
                client.close()
        except HARNESS_FAILURES as exc:
            error, harness = type(exc).__name__, True
        except Exception as exc:  # the service's failure is data for the oracle
            error = type(exc).__name__
        raw[k] = {"op": calls[k]["op"], "args": calls[k]["args"], "value": value, "error": error,
                  "harness_failure": harness}
        ctl.op_done(k)

    decisions, steps, threads = [], [], []
    forced, harness_error = 0, setup_failure
    deadline = time.monotonic() + ctx.round_timeout
    ctl.begin_round(len(calls))
    try:
        while not ctl.all_done():
            if ctl.wait_quiescent():
                forced += 1
            if ctl.all_done():
                break
            choices = ctl.choices()
            if not choices:
                if time.monotonic() > deadline:
                    harness_error = "round timeout"
                    break
                continue
            label = policy.choose(len(decisions), choices, ctl.held_commands())
            steps.append((choices.index(label), len(choices)))
            decisions.append(label)
            kind, op = label.split(":")
            if kind == "admit":
                ctl.admit(int(op))
                thread = threading.Thread(target=run_op, args=(int(op),), daemon=True)
                threads.append(thread)
                thread.start()
            else:
                ctl.permit(int(op))
    except Divergence as exc:
        harness_error = f"divergence: {exc}"
    finally:
        ctl.end_round()
    for thread in threads:
        thread.join(timeout=5)
    events = list(ctl.events)

    observer = svc.connect(*PROXY)
    try:
        post = observe(ctx, observer)
    finally:
        observer.close()

    problems = soundness_problems(events)
    if ctl.shared_connections and forced:
        problems.append(f"{forced} forced decision(s) on a shared connection: attribution is not guaranteed")
    if harness_error is None and any(r and r["harness_failure"] for r in raw):
        harness_error = "proxy or store failure during the round"
    ops = [dict(r, status=oracle.classify(r, ctx.target["contract"])) for r in raw if r]
    if harness_error or problems or len(ops) != len(calls):
        verdict, details = oracle.INCONCLUSIVE, []
    else:
        verdict, details = oracle.check(ctx.target["contract"], ops, pre, post)
    record = {
        "workload": workload,
        "setup_outcomes": setup_outcomes,
        "decisions": decisions,
        "steps": steps,
        "verdict": verdict,
        "violations": details,
        "ops": ops,
        "pre": pre,
        "post": post,
        "forced_decisions": forced,
        "soundness_problems": problems,
        "harness_error": harness_error,
        "trace": [e for e in events if e["event"] in ("admit", "exec")],
        "trace_hash": trace_hash(decisions, events),
    }
    if hasattr(policy, "stats"):
        record["policy_stats"] = policy.stats()
    if digests:
        record["state_before"], record["state_after"] = state_before, state_digest(ctx)
    record["ms"] = round((time.perf_counter() - started) * 1000, 2)
    return record


def profile(ctx, setup, call):
    """Run ``call`` alone after ``setup`` and report the store commands it issued, in order.
    One search execution. Used by the systematic baseline (M3+) to find conflicting pairs."""
    record = execute_once(ctx, {"setup": setup, "concurrent": [call]}, PrefixPolicy([]),
                          digests=True)
    op = record["ops"][0] if record["ops"] else {"error": "missing"}
    return {"commands": [[e["cmd"], e["key"]] for e in record["trace"] if e["event"] == "exec"],
            "outcome": op.get("error") or "ok", "setup_outcomes": record["setup_outcomes"],
            "state_before": record["state_before"], "state_after": record["state_after"],
            "verdict": record["verdict"], "harness_error": record["harness_error"],
            "ms": record["ms"]}


def make_policy(spec):
    kind = spec["kind"]
    if kind == "prefix":
        return PrefixPolicy(spec["prefix"])
    if kind == "random":
        return RandomPolicy(spec["seed"])
    if kind == "hint":
        return HintPolicy(spec["hint"])
    if kind == "replay":
        return ReplayPolicy(spec["decisions"])
    raise ValueError(f"unknown policy {kind!r}")


def explore(ctx, workload, max_schedules, stop_on_violation, first_policy=None):
    """Optionally run one guided schedule, then depth-first over every decision sequence."""
    records, prefix = [], []
    if first_policy is not None:
        records.append(execute_once(ctx, workload, first_policy))
        if stop_on_violation and records[-1]["verdict"] == oracle.VIOLATION:
            return records, False
    while len(records) < max_schedules:
        records.append(execute_once(ctx, workload, PrefixPolicy(prefix)))
        if stop_on_violation and records[-1]["verdict"] == oracle.VIOLATION:
            return records, False
        prefix = next_prefix(records[-1]["steps"])
        if prefix is None:
            return records, True
    return records, False


def random_workload(target, rng, n_concurrent):
    calls = []
    for _ in range(n_concurrent):
        op = rng.choice(sorted(target["operations"]))
        args = {name: rng.choice(target["domains"][spec["domain"]])
                for name, spec in target["operations"][op]["args"].items()}
        calls.append({"op": op, "args": args})
    return {"setup": [], "concurrent": calls}


def run_job(ctx, job):
    kind = job["kind"]
    exhausted = None
    if kind == "exhaustive":
        records, exhausted = explore(ctx, job["workload"], job["max_schedules"],
                                     job.get("stop_on_violation", False))
    elif kind == "hint_then_exhaustive":
        hint = HintPolicy(job["hint"])
        records, exhausted = explore(ctx, job["workload"], job["max_schedules"],
                                     job.get("stop_on_violation", True), first_policy=hint)
    elif kind == "random_search":
        rng = random.Random(job["seed"])
        records = []
        for i in range(job["max_schedules"]):
            workload = random_workload(ctx.target, rng, job.get("n_concurrent", 2))
            records.append(execute_once(ctx, workload, RandomPolicy(f"{job['seed']}-{i}")))
            if job.get("stop_on_violation", True) and records[-1]["verdict"] == oracle.VIOLATION:
                break
    elif kind == "replay":
        records = [execute_once(ctx, job["workload"], ReplayPolicy(job["decisions"]))
                   for _ in range(job["repeat"])]
    elif kind == "passthrough_check":
        return {"id": job["id"], "kind": kind,
                "summary": passthrough_check(ctx, job["workload"], job["repeat"])}
    else:
        raise ValueError(f"unknown job kind {kind!r}")

    first = next((i + 1 for i, r in enumerate(records) if r["verdict"] == oracle.VIOLATION), None)
    summary = {
        "executions": len(records),
        "first_violation_at": first,
        "verdicts": {v: sum(r["verdict"] == v for r in records)
                     for v in (oracle.PASS, oracle.VIOLATION, oracle.INCONCLUSIVE)},
        "distinct_trace_hashes": len({r["trace_hash"] for r in records}),
        "forced_decisions": sum(r["forced_decisions"] for r in records),
        "soundness_problems": sum(len(r["soundness_problems"]) for r in records),
        "exhausted": exhausted,
        "ms_total": round(sum(r["ms"] for r in records), 2),
    }
    if kind == "hint_then_exhaustive":
        summary["hint_followed"], summary["hint_skipped"] = hint.followed, hint.skipped
    return {"id": job["id"], "kind": kind, "summary": summary, "records": records}


def passthrough_check(ctx, workload, repeat):
    """The proxy in pass-through must change nothing: run the workload's calls one at a time
    through the proxy and directly against the store, and compare every call's result or error
    and the final observations."""
    svc = ctx.module
    mismatches = 0
    for _ in range(repeat):
        observations = []
        for endpoint in (PROXY, ctx.store):
            reset(ctx)
            client = svc.connect(*endpoint)
            try:
                outcomes = []
                for call in workload["setup"] + workload["concurrent"]:
                    try:  # results and rejections must match too, not only the final state
                        outcomes.append(["ok", getattr(svc, call["op"])(client, **call["args"])])
                    except Exception as exc:
                        outcomes.append(["error", type(exc).__name__])
                observations.append([outcomes, observe(ctx, client)])
            finally:
                client.close()
        mismatches += observations[0] != observations[1]
    return {"runs": repeat, "mismatches": mismatches}


def egress_probe():
    findings = {}
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=2).close()
        findings["tcp_1.1.1.1:443"] = "REACHABLE"
    except OSError as exc:
        findings["tcp_1.1.1.1:443"] = f"blocked ({type(exc).__name__})"
    try:
        socket.getaddrinfo("pypi.org", 443)
        findings["dns_pypi.org"] = "RESOLVED"
    except OSError as exc:
        findings["dns_pypi.org"] = f"blocked ({type(exc).__name__})"
    return findings


def serve():
    """JSON-lines session (one request per line in, one response per line out), so a host-side
    trial runner can drive every method through one execution counter. First line: settings."""
    settings = json.loads(sys.stdin.readline())
    # started before "ready", so a service in its own container can connect to it at startup
    shared_controller(tuple(settings["store"]), settings.get("delta_q_ms", 300) / 1000,
                      settings["target"])
    contexts = {}
    print(json.dumps({"ready": True, "egress_probe": egress_probe(),
                      "python": sys.version.split()[0], "redis_py": redis.__version__}), flush=True)
    for line in sys.stdin:
        request = json.loads(line)
        try:
            variant = request["variant"]
            if variant not in contexts:
                contexts[variant] = Context({**settings, "variant": variant})
            ctx = contexts[variant]
            if request["op"] == "execute":
                out = execute_once(ctx, request["workload"], make_policy(request["policy"]))
            elif request["op"] == "profile":
                out = profile(ctx, request["setup"], request["call"])
            else:
                raise ValueError(f"unknown op {request['op']!r}")
        except Exception as exc:  # reported to the host, which stops the trial
            out = {"error": f"{type(exc).__name__}: {exc}"}
        print(json.dumps(out), flush=True)


def main():
    if "--serve" in sys.argv:
        return serve()
    request = json.load(sys.stdin)
    ctx = Context(request)
    result = {"egress_probe": egress_probe(), "variant": request["variant"],
              "jobs": [run_job(ctx, job) for job in request["jobs"]]}
    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
