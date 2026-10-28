"""A2's payload: source code cannot reach the model, and nothing else differs from the pilot's M4.

Run: python3 -m unittest discover -s experiments/2026-10-28-a2-no-source -p 'test_*.py'
1. Equivalence: the A2 request is the pilot's recorded source-visible request with its source
   block replaced by the no-source marker, byte for byte, for D2 and D3.
2. Noninterference: replacing or rewriting the source files, including with the corrected
   variant or with text full of answer words, leaves the A2 request byte-for-byte unchanged,
   while the same change does change the source-visible request (so the test is not vacuous).
3. Detection: each a2_audit check fires on a planted positive; the real requests are clean, with
   and without feedback.
4. Cost cap: StrictCap refuses a call when spend plus the reserve would exceed the cap.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(HERE))

from mylonite import audit, planner  # noqa: E402

import a2_audit  # noqa: E402
import run_a2  # noqa: E402

TARGETS = {"d2-loyalty-points": "d2_counter", "d3-inventory": "d3_inventory"}


def load(name):
    return json.loads((REPO / f"fixtures/dev/{TARGETS[name]}/target.json").read_text())


def body(target, repo, feedback=(), include_source=False):
    return planner.build_request(target, repo, feedback, include_source, "medium")


def sample_feedback(target):
    calls = planner.space.op_calls(target)
    record = {"verdict": "PASS", "decisions": ["admit:0", "admit:1", "exec:0", "exec:1"],
              "steps": [[0, 2], [0, 1], [0, 2], [0, 1]], "setup_outcomes": ["ok"],
              "trace": [{"seq": 1, "event": "exec", "op": 0, "conn": 1, "cmd": "GET",
                         "key": "aa" * 8, "args": "bb" * 8, "reply": "cc" * 8}],
              "trace_hash": "ff" * 32, "pre": {"k": 0}, "post": {"k": 1},
              "ops": [{"op": calls[0]["op"], "error": None}, {"op": calls[0]["op"], "error": None}]}
    experiment = {"workload": {"setup": [calls[0]], "concurrent": [calls[0], calls[0]]}}
    return [{"round": 1, "results": [planner.feedback_entry(experiment, [record], False)],
             "rejected": []}]


class EquivalenceTest(unittest.TestCase):
    def test_a2_is_the_pilot_request_minus_its_source(self):
        recorded = {}
        for line in a2_audit.PILOT_CALLS.read_text().splitlines():
            entry = json.loads(line)
            recorded.setdefault(entry["trial"].split("/")[0], entry["request"])
        for name in TARGETS:
            target = load(name)
            a2 = a2_audit.canonical(body(target, REPO))
            self.assertEqual(a2, a2_audit.canonical(a2_audit.without_source(recorded[name])), name)
            self.assertEqual(a2, a2_audit.canonical(
                a2_audit.without_source(body(target, REPO, include_source=True))), name)


REWRITES = ("corrected variant shown", "answer words", "unrelated code",
            "corrected variant rewritten")


def rewrite(label, target, root):
    """Apply one rewrite to a throwaway copy under ``root``, never to the real tree."""
    shown = root / target["model_view"]["files"]["service.py"]
    fixed = root / (target["variants"]["fixed"].replace(".", "/") + ".py")
    if label == "corrected variant shown":
        shown.write_text(fixed.read_text())
    elif label == "answer words":
        shown.write_text(shown.read_text() + "\n\ndef racy_check_then_act_lost_update_here():\n"
                         "    return 'buggy'\n")
    elif label == "unrelated code":
        shown.write_text("def f(x):\n    return x + 1\n")
    else:
        fixed.write_text("def g():\n    pass\n")


class NoninterferenceTest(unittest.TestCase):
    def test_source_cannot_change_the_a2_request(self):
        for name, rel in TARGETS.items():
            target = load(name)
            for label in REWRITES:
                with self.subTest(target=name, rewrite=label):
                    root = Path(tempfile.mkdtemp())
                    try:
                        shutil.copytree(REPO / "fixtures/dev" / rel, root / "fixtures/dev" / rel)
                        before_a2 = a2_audit.canonical(body(target, root))
                        before_m4 = a2_audit.canonical(body(target, root, include_source=True))
                        rewrite(label, target, root)
                        self.assertEqual(before_a2, a2_audit.canonical(body(target, root)))
                        if label != "corrected variant rewritten":  # not shown even to M4
                            self.assertNotEqual(before_m4, a2_audit.canonical(
                                body(target, root, include_source=True)))
                    finally:
                        shutil.rmtree(root)


class DetectionTest(unittest.TestCase):
    def test_real_requests_are_clean(self):
        for name in TARGETS:
            target = load(name)
            for feedback in ((), sample_feedback(target)):
                b = body(target, REPO, feedback)
                self.assertEqual(audit.findings(b, target, REPO), [], name)
                self.assertEqual(a2_audit.check(b, target, REPO)[0], [], name)

    def plant(self, b, text):
        user = next(m for m in b["messages"] if m["role"] == "user")
        user["content"] = user["content"].replace("Contract:", text + "\nContract:", 1)
        return b

    def test_every_check_fires(self):
        d3 = load("d3-inventory")
        source = a2_audit.source_texts(d3, REPO)[0]
        line = next(line.strip() for line in source.splitlines() if "decrby" in line)
        cases = [
            (body(d3, REPO, include_source=True), "source block"),
            (self.plant(body(d3, REPO), line), "source line"),
            (self.plant(body(d3, REPO), "hint: see _status"), "unexplained source identifier"),
        ]
        no_marker = body(d3, REPO)
        user = next(m for m in no_marker["messages"] if m["role"] == "user")
        user["content"] = user["content"].replace(planner.NO_SOURCE, "")
        cases.append((no_marker, "no-source marker missing"))
        for planted, expected in cases:
            with self.subTest(expected=expected):
                problems, _ = a2_audit.check(planted, d3, REPO)
                self.assertIn(expected, {p["check"] for p in problems})


class StrictCapTest(unittest.TestCase):
    class Inner:
        def __init__(self, spent):
            self.spent, self.trial, self.calls = spent, None, 0

        def __call__(self, body, round_no):
            self.calls += 1
            return None, {}

    def test_refuses_only_when_the_reserve_would_cross_the_cap(self):
        d2 = load("d2-loyalty-points")
        request = body(d2, REPO)
        for spent, allowed in ((0.0, True), (4.74, True), (4.76, False), (5.0, False)):
            with self.subTest(spent=spent):
                inner = self.Inner(spent)
                model = run_a2.StrictCap(inner, 5.0, 0.25, {"d2-loyalty-points": d2})
                model.trial = "d2-loyalty-points/A2/1"
                if allowed:
                    model(request, 1)
                    self.assertEqual(inner.calls, 1)
                else:
                    with self.assertRaises(RuntimeError):
                        model(request, 1)
                    self.assertEqual(inner.calls, 0)

    def test_refuses_a_request_with_source(self):
        d3 = load("d3-inventory")
        inner = self.Inner(0.0)
        model = run_a2.StrictCap(inner, 5.0, 0.25, {"d3-inventory": d3})
        model.trial = "d3-inventory/A2/1"
        with self.assertRaises(RuntimeError):
            model(body(d3, REPO, include_source=True), 1)
        self.assertEqual(inner.calls, 0)


if __name__ == "__main__":
    unittest.main()
