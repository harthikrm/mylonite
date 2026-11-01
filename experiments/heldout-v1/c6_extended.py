"""C6 ground truth (docs/HELDOUT_PROTOCOL.md C6; class A tooling, docs/AMENDMENTS.md AM-001).
Runs only after the C5 results commit.

  c6_extended.py <sealed root> <C5 results dir>
  c6_extended.py <toy root> <smoke results dir> --toy     plumbing check, no verification

A mutant is **shown buggy** if any method, M4 included, produced a verified violation on it in
C5. For each other mutant, an extended search runs, and anything it verifies also makes the
mutant shown buggy:
  1. M1 and M3+ at 10× the execution budget and 10× the method-seconds cap, seed 1 each;
  2. exploration, from every setup on M3+'s frontier of the mutant, of each catalog operation
     that runs the mutated code, with each of its argument combinations, paired with itself and
     with every catalog call. Each pair is explored depth-first up to 5,000 schedules: exhaustive
     for any pair with fewer.
     - "Runs the mutated code" means the operation is the function the C4 record names, or
       calls it directly or through other module functions.
     - If no operation does, every catalog operation is used.
It refuses unless ``heldout.verify_all`` finds nothing.
Verification is the frozen one. Mutants not shown buggy are excluded from the E₁ comparison for
every method alike, which is the only exclusion rule. Writes <results dir>/c6.json.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))

import importlib.util  # noqa: E402

from mylonite import methods, space  # noqa: E402
from mylonite.sandbox import Sandbox  # noqa: E402

_spec = importlib.util.spec_from_file_location("heldout", HERE / "heldout.py")
heldout = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(heldout)
SCHEDULE_CAP = 5000


def shown_in_c5(trials, mutants):
    return {m: any(t["target"] == m and t["status"] == "verified" for t in trials) for m in mutants}


def operations_reaching(source, function, operations):
    """The catalog operations whose module function is ``function`` or reaches it through calls
    to other module functions; every operation if none does."""
    import ast
    tree = ast.parse(source)
    defined = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    calls = {name: {c.func.id for c in ast.walk(fn) if isinstance(c, ast.Call)
                    and isinstance(c.func, ast.Name) and c.func.id in defined}
             for name, fn in defined.items()}

    def reaches(name, seen=()):
        return name == function or any(reaches(c, seen + (name,)) for c in calls.get(name, ())
                                       if c not in seen)
    found = sorted(op for op in operations if op in defined and reaches(op))
    return found or sorted(operations)


def pairs_to_explore(target, operations, setups):
    """(setup, a, b) for every frontier setup, every call a of the given operations, and every
    catalog call b."""
    calls = space.op_calls(target)
    mine = [c for c in calls if c["op"] in operations]
    return [(setup, a, b) for setup in setups for a in mine for b in calls]


def extended(session, target, operations, cfg, log):
    """The extended search on one mutant. Returns how it was shown buggy, or None."""
    big = dict(cfg, budget={**cfg["budget"], "executions": 10 * cfg["budget"]["executions"],
                            "method_seconds": 10 * cfg["budget"]["method_seconds"]})
    for method in ("M1", "M3+"):
        result = methods.run_trial(method, session, target, 1, big, log)
        if result["status"] == "verified":
            return {"by": f"extended {method}", "e1": result["e1_executions"],
                    "witness": result["witness"]}
    unbounded = {"executions": 10 ** 9, "method_seconds": 10 ** 9}
    trial = methods.Trial(session, target, unbounded, cfg["verification"], cfg["prices"], log)
    setups = heldout.frontier(session, target, "buggy")
    try:
        for setup, a, b in pairs_to_explore(target, operations, setups):
            trial.explore({"setup": setup, "concurrent": [a, b]}, SCHEDULE_CAP)
    except methods.Found as found:
        return {"by": "extended exhaustive pairs", "executions": found.executions,
                "witness": {k: found.record[k] for k in ("workload", "decisions", "trace_hash")}}
    return None


def main():
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    root, results = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
    if "--toy" not in sys.argv:
        problems = heldout.verify_all(root)
        if problems:
            sys.exit("refusing: the sealed root does not verify:\n  " + "\n  ".join(problems))
    cfg = json.loads((HERE / "config.json").read_text())
    trials = json.loads((results / "trials.json").read_text())
    manifest = json.loads((results / "manifest.json").read_text())
    record = json.loads((root / "private" / "c4_record.json").read_text())["record"]
    out = {"shown_in_c5": shown_in_c5(trials, manifest["mutants"]), "extended": {}}
    raw = (root / "private" / "logs" / "c6.jsonl").open("w")
    try:
        for mutant, shown in out["shown_in_c5"].items():
            if shown:
                continue
            base = mutant[:-2]
            target = heldout.load_target(root, mutant)
            operations = operations_reaching(
                (root / "heldout" / mutant / "service.py").read_text(),
                record[base]["chosen"]["function"], target["operations"])
            out.setdefault("operations_explored", {})[mutant] = operations
            box = Sandbox(f"mylonite-c6-{mutant}", REPO, target_root=root / "heldout")
            box.up()
            try:
                with box.session(target, **cfg["executor"]) as session:
                    out["extended"][mutant] = extended(
                        session, target, operations, cfg,
                        lambda e, m=mutant: raw.write(methods.json_line({"mutant": m, **e}) + "\n"))
            finally:
                box.down()
    finally:
        raw.close()
    out["shown_buggy"] = sorted(m for m, s in out["shown_in_c5"].items()
                                if s or out["extended"].get(m))
    out["excluded"] = sorted(set(manifest["mutants"]) - set(out["shown_buggy"]))
    (results / "c6.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({"shown_buggy": out["shown_buggy"], "excluded": out["excluded"]}))


if __name__ == "__main__":
    main()
