"""Answer contamination in the complete model-visible context (EVALUATION_PLAN.md rules 4–7).

The request body is everything the model sees. These tests check it four ways:
1. Noninterference: changing anything outside the declared view (corrected variant, locations,
   names, provenance, stray result files, comments and docstrings, schedules in feedback) leaves
   the body byte-for-byte unchanged. Building the body reads only the declared files.
2. Sensitivity: changing something inside the view does change the body, so (1) is not vacuous.
3. Detection: every audit detector fires on a planted positive, and the real bodies are clean.
4. Gate: a contaminated request is refused before any model call is made.
"""

import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mylonite import audit, methods, planner  # noqa: E402

TARGETS = {"d2": "d2_counter", "d3": "d3_inventory"}


def load(name):
    return json.loads((ROOT / f"fixtures/dev/{TARGETS[name]}/target.json").read_text())


def body_bytes(target, repo, feedback=(), include_source=True):
    return json.dumps(planner.build_request(target, repo, feedback, include_source),
                      sort_keys=True)


def sample_records(target):
    """Records shaped like the executor's, for a two-call workload."""
    call = planner.space.op_calls(target)[0]
    trace = [{"seq": 1, "event": "admit", "op": 0}, {"seq": 2, "event": "admit", "op": 1},
             {"seq": 3, "event": "exec", "op": 0, "conn": 1, "cmd": "GET", "key": "aa" * 8,
              "args": "bb" * 8, "reply": "cc" * 8},
             {"seq": 4, "event": "exec", "op": 1, "conn": 2, "cmd": "SET", "key": "aa" * 8,
              "args": "dd" * 8, "reply": "ee" * 8}]
    record = {"verdict": "PASS", "decisions": ["admit:0", "admit:1", "exec:0", "exec:1"],
              "steps": [[0, 2], [0, 1], [0, 2], [0, 1]], "trace": trace,
              "trace_hash": "ff" * 32, "setup_outcomes": ["ok"],
              "ops": [{"op": call["op"], "error": None}, {"op": call["op"], "error": None}],
              "pre": {"k": 0}, "post": {"k": 1}}
    experiment = {"workload": {"setup": [call], "concurrent": [call, call]}}
    return experiment, [record, dict(record, decisions=["admit:1", "admit:0", "exec:1", "exec:0"])]


class Copy:
    """A throwaway repository holding one target's files, so perturbations stay off the real
    tree."""

    def __init__(self, name):
        self.dir = Path(tempfile.mkdtemp())
        rel = f"fixtures/dev/{TARGETS[name]}"
        shutil.copytree(ROOT / rel, self.dir / rel)
        self.rel = rel
        self.target = load(name)

    def path(self, rel):
        return self.dir / rel

    def body(self, target=None, **kw):
        return body_bytes(target or self.target, self.dir, **kw)

    def close(self):
        shutil.rmtree(self.dir)


class NoninterferenceTest(unittest.TestCase):
    def setUp(self):
        self.copies = {n: Copy(n) for n in TARGETS}

    def tearDown(self):
        for c in self.copies.values():
            c.close()

    def perturbations(self, c):
        """(description, mutate) pairs; each mutate(copy) returns the target to build from."""
        def relocate(c):
            src = c.target["model_view"]["files"]["service.py"]
            dest = "CANARY_fixture_buggy/heldout/service_buggy_v2.py"
            c.path(dest).parent.mkdir(parents=True)
            shutil.copy(c.path(src), c.path(dest))
            c.path(src).unlink()
            t = copy.deepcopy(c.target)
            t["model_view"]["files"]["service.py"] = dest
            return t

        def replace_corrected(c):
            c.path(f"{c.rel}/service_fixed.py").write_text("CANARY_FIX = 'use INCRBY / EVAL'\n")
            return c.target

        def rename_everything(c):
            t = copy.deepcopy(c.target)
            t["target"] = "CANARY-target-id"
            t["variants"] = {"buggy": "CANARY.buggy.module", "fixed": "CANARY.fixed.module"}
            t["contract"]["source"] = "CANARY provenance: the bug is in award"
            t["contract"]["approved_by"] = "CANARY approver"
            return t

        def stray_artifacts(c):
            for rel, text in (("experiments/x/results.json",
                               json.dumps({"decisions": ["admit:0", "exec:1"], "trace_hash": "ab" * 32,
                                           "verdict": "VIOLATION"})),
                              ("runs/tracer/muse_runs.json", '{"witness": "CANARY"}'),
                              (f"{c.rel}/README.md", "CANARY: the bug is a check-then-act race")):
                c.path(rel).parent.mkdir(parents=True, exist_ok=True)
                c.path(rel).write_text(text)
            return c.target

        def comments_and_docstrings(c):
            src = c.path(c.target["model_view"]["files"]["service.py"])
            lines = src.read_text().splitlines()
            out = ["# CANARY: BUG HERE, the read and the write are not atomic"]
            for line in lines:
                out.append(line)
                if line.startswith("def "):
                    out.append('    """CANARY docstring: this is the buggy variant."""')
                    out.append("    # CANARY comment: lost update / oversell")
            src.write_text("\n".join(out) + "\n")
            return c.target

        return [("source relocated under a revealing path", relocate),
                ("corrected variant replaced", replace_corrected),
                ("target id, variant modules and provenance renamed", rename_everything),
                ("result files, raw runs and a README added", stray_artifacts),
                ("comments and docstrings added to the shown source", comments_and_docstrings)]

    def test_outside_the_view_cannot_change_the_request(self):
        for name in TARGETS:
            baseline = self.copies[name].body()
            self.assertEqual(baseline, body_bytes(load(name), ROOT), "copy differs from repo")
            for description, mutate in self.perturbations(self.copies[name]):
                with self.subTest(target=name, perturbation=description):
                    c = Copy(name)
                    try:
                        target = mutate(c)
                        self.assertEqual(c.body(target), baseline)
                    finally:
                        c.close()

    def test_only_declared_files_are_read(self):
        import builtins
        import io
        for name in TARGETS:
            c, opened = self.copies[name], []
            real_open = io.open

            def spy(file, *args, **kwargs):  # every Path read and plain open() ends here
                if isinstance(file, (str, Path)):
                    opened.append(Path(file).resolve())
                return real_open(file, *args, **kwargs)

            with mock.patch.object(io, "open", spy), mock.patch.object(builtins, "open", spy):
                planner.build_request(c.target, c.dir)
            declared = {(c.dir / p).resolve() for p in c.target["model_view"]["files"].values()}
            self.assertEqual(set(opened), declared)
            self.assertTrue(opened, "the spy saw no reads at all")

    def test_feedback_carries_no_schedules_or_digests(self):
        for name in TARGETS:
            target = load(name)
            experiment, records = sample_records(target)
            base = planner.feedback_entry(experiment, records, False)
            scrambled = copy.deepcopy(records)
            for r in scrambled:
                r["decisions"], r["steps"], r["trace_hash"] = ["exec:9"], [[9, 9]], "00" * 32
                for e in r["trace"]:
                    e.update(key="99" * 8, args="98" * 8, reply="97" * 8, seq=e["seq"] + 100)
            self.assertEqual(planner.feedback_entry(experiment, scrambled, False), base)
            body = planner.build_request(target, ROOT, [{"round": 1, "results": [base]}])
            self.assertEqual(audit.findings(body, target, ROOT), [])


class SensitivityTest(unittest.TestCase):
    """Changes inside the view must reach the request, or the tests above prove nothing."""

    def test_inside_the_view_changes_the_request(self):
        for name in TARGETS:
            c = Copy(name)
            try:
                baseline = c.body()
                src = c.path(c.target["model_view"]["files"]["service.py"])
                src.write_text(src.read_text().replace("int(", "float(", 1))
                self.assertNotEqual(c.body(), baseline, "source semantics")
                src.write_text(src.read_text().replace("float(", "int(", 1))
                self.assertEqual(c.body(), baseline)
                t = copy.deepcopy(c.target)
                first = sorted(t["domains"])[0]
                t["domains"][first] = t["domains"][first][:-1]
                self.assertNotEqual(c.body(t), baseline, "domain")
                t = copy.deepcopy(c.target)
                t["contract"]["statement"] += " Also."
                self.assertNotEqual(c.body(t), baseline, "contract")
                self.assertNotEqual(c.body(include_source=False), baseline, "A2 drops source")
            finally:
                c.close()


class DetectorTest(unittest.TestCase):
    def test_real_requests_are_clean(self):
        for name in TARGETS:
            target = load(name)
            for include_source in (True, False):
                body = planner.build_request(target, ROOT, include_source=include_source)
                self.assertEqual(audit.findings(body, target, ROOT), [], name)

    def plant(self, target, text):
        body = planner.build_request(target, ROOT)
        body["messages"][1]["content"] += "\n" + text
        return {f["detector"] for f in audit.findings(body, target, ROOT)}

    def test_every_detector_fires(self):
        d2, d3 = load("d2"), load("d3")
        cases = [
            (d2, "try admit:0 then exec:1", "decision label"),
            (d2, "seen before as 3e6f3a2b3394aa01", "digest"),
            (d2, "verdict VIOLATION", "verdict word"),
            (d2, '{"trace_hash": 1}', "result key"),
            (d2, "see fixtures/dev/", "harness path"),
            (d3, "this is D3", "fixture id"),
            (d3, "the buggy path", "label word"),
            (d3, "def isRacyPath(): pass", "label word"),
            (d2, "consider incrby", "fix-only identifier"),
            (d2, "return int(r.incrby(f'points:{member}', points))", "fix-only line"),
            (d3, "maybe _purchase", "fix-only identifier"),
            (d2, "target d2-loyalty-points", "target identity"),
        ]
        for target, text, detector in cases:
            with self.subTest(detector=detector, text=text):
                self.assertIn(detector, self.plant(target, text))

    def test_label_in_a_string_literal_is_caught(self):
        c = Copy("d3")
        try:
            src = c.path(c.target["model_view"]["files"]["service.py"])
            src.write_text(src.read_text() + '\nNOTE = "seeded bug below"\n')
            body = planner.build_request(c.target, c.dir)
            found = {f["match"] for f in audit.findings(body, c.target, c.dir)}
            self.assertTrue({"seeded", "bug"} <= found)
        finally:
            c.close()


class TargetIndependenceTest(unittest.TestCase):
    """The instructions are the same for every target and name nothing target-specific."""

    @staticmethod
    def skeleton(schema):
        s = copy.deepcopy(schema)
        exp = s["properties"]["experiments"]["items"]["properties"]
        for part in ("setup", "concurrent"):
            exp[part]["items"]["properties"]["op"] = "*"
            exp[part]["items"]["properties"]["args"] = "*"
        s["properties"]["hypotheses"]["items"]["properties"]["operations"] = "*"
        return s

    def test_same_instructions_and_schema_skeleton(self):
        bodies = {n: planner.build_request(load(n), ROOT) for n in TARGETS}
        self.assertEqual(bodies["d2"]["messages"][0], bodies["d3"]["messages"][0])
        schemas = [self.skeleton(b["response_format"]["json_schema"]["schema"])
                   for b in bodies.values()]
        self.assertEqual(schemas[0], schemas[1])

    def test_instructions_name_no_target_vocabulary(self):
        fixed_text = planner.SYSTEM + planner.USER_TEMPLATE
        for name in TARGETS:
            target = load(name)
            vocab = set(target["operations"]) | {str(v) for d in target["domains"].values()
                                                 for v in d}
            vocab |= {w for w in audit.words(target["contract"]["statement"]) if len(w) > 4}
            hits = sorted(w for w in vocab if w.lower() in audit.words(fixed_text))
            self.assertEqual(hits, [], name)


class ModelTextTest(unittest.TestCase):
    """Text the model wrote must not be echoed back, or the audit would end the trial."""

    def test_rejected_experiment_feedback_uses_codes(self):
        target, bodies = load("d2"), []
        bad = {"hypotheses": [], "experiments": [{
            "hypothesis_id": "H1 buggy incrby", "expected_effect": "fixed by incrby",
            "setup": [], "concurrent": [{"op": "award", "args": {"member": "m1", "points": 1}}] * 2,
            "schedule_hint": [{"op_index": 7, "command": "INCRBY"}]}]}

        def model(body, round_no):
            bodies.append(body)
            return bad, {"latency_s": 0, "usage": {}}

        trial = methods.Trial(None, target, {"executions": 10, "method_seconds": 60}, {},
                              {"input": 0, "cached": 0, "output": 0, "compute_per_second": 0},
                              lambda e: None)
        cfg = {"max_rounds": 2, "include_source": True, "reasoning_effort": "medium",
               "schedules_per_experiment": 5}
        methods.run_m4(trial, target, 1, cfg, model, ROOT)
        self.assertEqual(len(bodies), 2)
        self.assertIn('"bad_hint_step"', bodies[1]["messages"][1]["content"])
        self.assertEqual(audit.findings(bodies[1], target, ROOT), [])


class GateTest(unittest.TestCase):
    def test_contaminated_request_never_reaches_the_model(self):
        c = Copy("d3")
        try:
            src = c.path(c.target["model_view"]["files"]["service.py"])
            src.write_text(src.read_text() + '\nHINT = "fixture: race in purchase"\n')
            calls = []

            def model(body, round_no):
                calls.append(body)
                return {"hypotheses": [], "experiments": []}, {"latency_s": 0, "usage": {}}

            trial = methods.Trial(None, c.target, {"executions": 10, "method_seconds": 60},
                                  {}, {"input": 0, "cached": 0, "output": 0,
                                       "compute_per_second": 0}, lambda e: None)
            cfg = {"max_rounds": 2, "include_source": True, "reasoning_effort": "medium",
                   "schedules_per_experiment": 5}
            with self.assertRaises(audit.ContaminationError):
                methods.run_m4(trial, c.target, 1, cfg, model, c.dir)
            self.assertEqual(calls, [])
        finally:
            c.close()


if __name__ == "__main__":
    unittest.main()
