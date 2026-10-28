"""The search space every method shares (EVALUATION_PLAN.md §3, fairness rule 7).

Muse, random search and the systematic baseline all build workloads from the same catalog, the
same value domains and the same size limits, and every workload passes the same validator before
it runs. Standard library only: used on the host and inside the executor.
"""

import itertools

MAX_SETUP, MIN_CONCURRENT, MAX_CONCURRENT = 6, 2, 4


def op_calls(target):
    """Every catalog call: each operation with each combination of its argument domains."""
    calls = []
    for op in sorted(target["operations"]):
        args = target["operations"][op]["args"]
        names = sorted(args)
        for values in itertools.product(*(target["domains"][args[n]["domain"]] for n in names)):
            calls.append({"op": op, "args": dict(zip(names, values))})
    return calls


def call_problems(target, call):
    spec = target["operations"].get(call.get("op"))
    if spec is None:
        return [f"unknown op {call.get('op')!r}"]
    problems = []
    for name, arg in spec["args"].items():
        value = call.get("args", {}).get(name)
        if value not in target["domains"][arg["domain"]]:
            problems.append(f"{call['op']}.{name}={value!r} outside domain")
    extra = [n for n, v in call.get("args", {}).items() if v is not None and n not in spec["args"]]
    if extra:
        problems.append(f"{call['op']} has extra args {extra}")
    return problems


def normalize_call(target, call):
    """Keep only the operation's own arguments (the planner schema nulls the others)."""
    spec = target["operations"][call["op"]]
    return {"op": call["op"], "args": {n: call["args"][n] for n in sorted(spec["args"])}}


def workload_problems(target, workload):
    problems = []
    if len(workload["setup"]) > MAX_SETUP:
        problems.append("setup size")
    if not MIN_CONCURRENT <= len(workload["concurrent"]) <= MAX_CONCURRENT:
        problems.append("concurrent size")
    for call in workload["setup"] + workload["concurrent"]:
        problems += call_problems(target, call)
    return problems


def random_workload(target, rng):
    """M1's draw: setup length uniform in 0..MAX_SETUP, concurrent size uniform in the allowed
    range, each call an operation chosen uniformly with each argument chosen uniformly."""
    def call():
        op = rng.choice(sorted(target["operations"]))
        args = target["operations"][op]["args"]
        return {"op": op, "args": {n: rng.choice(target["domains"][args[n]["domain"]])
                                   for n in sorted(args)}}
    return {"setup": [call() for _ in range(rng.randint(0, MAX_SETUP))],
            "concurrent": [call() for _ in range(rng.randint(MIN_CONCURRENT, MAX_CONCURRENT))]}
