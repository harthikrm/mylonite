"""Tests for the frozen analysis (src/mylonite/analysis.py): every statistic against an
independent computation or a hand-computed value, and the decision rules on small cases,
including the counterexamples an independent review found in the first draft."""

import itertools
import json
import math
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mylonite import analysis  # noqa: E402

B = 1000
INF = math.inf


def brute_force_p(x, y):
    """Two-sided permutation p-value from the Mann–Whitney U count, by enumerating every split
    of the pooled values. Independent of analysis.midranks."""
    pooled, n, m = list(x) + list(y), len(x), len(y)

    def u(xs, ys):
        return sum((a < b) + 0.5 * (a == b) for a in xs for b in ys)
    center = n * m / 2
    observed = abs(u(x, y) - center)
    hits = total = 0
    for split in itertools.combinations(range(len(pooled)), n):
        chosen = set(split)
        xs = [pooled[i] for i in split]
        ys = [pooled[i] for i in range(len(pooled)) if i not in chosen]
        hits += abs(u(xs, ys) - center) >= observed - 1e-9
        total += 1
    return hits / total


def trial(target, method, seed, status="verified", e1=None, method_s=1.0, exec_s=0.01,
          model_usd=0.0, compute_usd=0.0, executions=None, **extra):
    return {"target": target, "method": method, "seed": seed, "status": status,
            "e1_executions": e1 if status == "verified" else None, "method_s": method_s,
            "exec_s": exec_s, "model_usd": model_usd, "compute_usd": compute_usd,
            "executions": executions if executions is not None else (e1 or B), **extra}


class StatisticsTest(unittest.TestCase):
    def test_midranks_share_ties(self):
        self.assertEqual(analysis.midranks([5, 1, 5, INF, INF]), [2.5, 1, 2.5, 4.5, 4.5])

    def test_exact_test_equals_enumeration_with_ties_and_failures(self):
        rng = random.Random(7)
        for _ in range(40):
            n, m = rng.randint(1, 6), rng.randint(1, 6)
            draw = lambda: rng.choice([1, 2, 2, 3, 5, INF, INF])  # noqa: E731
            x, y = [draw() for _ in range(n)], [draw() for _ in range(m)]
            self.assertAlmostEqual(analysis.mann_whitney(x, y), brute_force_p(x, y), places=12)

    def test_complete_separation_of_five_and_five(self):
        # the most extreme split in either direction: 2 of C(10, 5) = 252
        self.assertAlmostEqual(analysis.mann_whitney([1] * 5, [211, 246, 211, 211, 775]), 2 / 252)

    def test_all_tied_is_not_evidence(self):
        self.assertEqual(analysis.mann_whitney([INF] * 4, [INF] * 6), 1.0)
        self.assertEqual(analysis.a12([INF] * 4, [INF] * 6), 0.5)

    def test_a12_lower_is_better_and_ties_count_half(self):
        self.assertEqual(analysis.a12([1, 1], [2, 2]), 1.0)
        self.assertEqual(analysis.a12([3], [2]), 0.0)
        self.assertEqual(analysis.a12([1, 2], [2]), 0.75)

    def test_holm(self):
        for got, want in zip(analysis.holm([0.01, 0.04, 0.03]), [0.03, 0.06, 0.06]):
            self.assertAlmostEqual(got, want)
        self.assertEqual(analysis.holm([0.6, 0.9]), [1.0, 1.0])

    def test_wilson_matches_the_reported_development_intervals(self):
        for (k, n), (lo, hi) in {(5, 5): (0.57, 1.00), (3, 5): (0.23, 0.88),
                                 (0, 5): (0.00, 0.43)}.items():
            got = analysis.wilson(k, n)
            self.assertEqual((round(got[0], 2), round(got[1], 2)), (lo, hi))

    def test_median_is_kaplan_meier_with_one_censoring_point(self):
        self.assertEqual(analysis.median([4, 1, 3, 2]), 2)  # never the average 2.5
        self.assertEqual(analysis.median([1, B + 1, B + 1, B + 1]), B + 1)  # not reached
        self.assertEqual(analysis.median([1, 2, B + 1, B + 1]), 2)  # exactly half failed
        self.assertEqual(analysis.median([0.5, INF]), 0.5)

    def test_bootstrap_is_reproducible(self):
        values = [1, 2, 3, 5, 8, 13, 21, B + 1]
        self.assertEqual(analysis.bootstrap_median_ci(values, "x"),
                         analysis.bootstrap_median_ci(values, "x"))


class TrialRulesTest(unittest.TestCase):
    def test_outcomes(self):
        self.assertEqual(analysis.outcome(trial("T", "M1", 1, e1=3), "e1"), ("found", 3))
        self.assertEqual(analysis.outcome(trial("T", "M1", 1, status="censored:executions"), "e1"),
                         ("censored", B))
        self.assertEqual(analysis.outcome(trial("T", "M1", 1, status="censored:time",
                                                executions=400), "e1"), ("failed", None))
        with self.assertRaises(ValueError):
            analysis.outcome(trial("T", "M1", 1, status="mystery"), "e1")
        self.assertEqual(analysis.outcome(trial("T", "M3+", 1, status="search_plan_exhausted"),
                                          "seconds"), ("failed", None))
        self.assertEqual(analysis.outcome(trial("T", "M4", 1, status="error:X"), "e1"),
                         ("failed", None))
        self.assertIsNone(analysis.outcome(trial("T", "M1", 1, status="error:X"), "e1"))
        self.assertIsNone(analysis.outcome(trial("T", "M1", 1, status="not_run"), "e1"))
        t = trial("T", "M4", 1, e1=3, method_s=12.0, model_usd=0.02, compute_usd=0.001)
        self.assertEqual([analysis.value(t, m, B) for m in analysis.METRICS], [3, 12.0, 0.021])

    def test_review_counterexample_seconds_are_compared_on_a_common_scale(self):
        """A baseline censored at 7 s against Muse succeeding at 300 s is not evidence for Muse."""
        muse = [("found", 300.0)] * 20
        base = [("censored", 7.0)] * 20
        sx, sy, tau = analysis.comparable(muse, base)
        self.assertEqual((tau, analysis.mann_whitney(sx, sy), analysis.a12(sx, sy)), (7.0, 1.0, 0.5))
        sx, _, _ = analysis.comparable([("found", 5.0)], base)  # cheaper than τ still counts
        self.assertEqual(sx, [5.0])
        sx, sy, tau = analysis.comparable([("found", 3)], [("failed", None)])  # nothing censored
        self.assertEqual((sx, sy, tau), ([3], [INF], INF))

    def test_review_counterexample_time_censored_muse_does_not_truncate_e1(self):
        """Muse: 10 found at 5, 9 plan-exhausted, 1 stopped by the time budget at 20 executions.
        Every baseline trial: found at 100. Not "better": half of Muse's trials failed."""
        trials = ([trial("T", "M4", s, e1=5) for s in range(1, 11)]
                  + [trial("T", "M4", s, status="search_plan_exhausted") for s in range(11, 20)]
                  + [trial("T", "M4", 20, status="censored:time", executions=20)])
        for b in analysis.CONVENTIONAL:
            trials += [trial("T", b, s, e1=100) for s in range(1, 21)]
        cells = {("T", "e1"): analysis.compare(trials, "T", "e1")}
        self.assertEqual(cells[("T", "e1")]["M3+"]["truncated_at"], INF)
        self.assertEqual(cells[("T", "e1")]["M3+"]["a12"], 0.5)
        self.assertEqual(analysis.verdicts(cells)["conventional|T|e1"]["verdict"],
                         "no significant difference")

    def test_crash_rule(self):
        error, success = trial("T", "M1", 1, status="error:X"), trial("T", "M1", 1, e1=9)
        self.assertEqual(analysis.attempts([error, success]), [success])  # a baseline repeats
        muse_error, muse_success = trial("T", "M4", 1, status="error:X"), trial("T", "M4", 1, e1=1)
        self.assertEqual(analysis.attempts([muse_error, muse_success]), [muse_error])  # no re-roll
        with self.assertRaises(ValueError):  # a re-run without an error
            analysis.attempts([trial("T", "M4", 1, status="search_plan_exhausted"), muse_success])
        with self.assertRaises(ValueError):
            analysis.attempts([error, error, success])

    def test_completeness(self):
        trials = [trial("T", "M1", 1, e1=4), trial("T", "M1", 2, status="not_run")]
        analysis.require_complete(trials, ["T"], ["M1"], [1, 2])
        with self.assertRaises(ValueError):
            analysis.require_complete(trials, ["T"], ["M1", "M4"], [1, 2])

    def test_error_flags_never_exclude(self):
        def run(errors):
            return [trial("T", "M4", s, status="error:X" if s <= errors else "verified", e1=4)
                    for s in range(1, 21)]
        self.assertEqual(analysis.error_flags(run(3), "T"), ["M4: errors"])  # 3 of 20: over 10%
        noisy = [trial("T", "M1", 1, e1=100, counters={"INCONCLUSIVE": 2})]
        self.assertEqual(analysis.error_flags(noisy, "T"), ["M1: inconclusive"])  # 2%
        self.assertEqual(analysis.error_flags(run(2), "T"), [])
        values, left_out = analysis.outcomes_of(run(3), "T", "M4", "e1")
        self.assertEqual((len(values), left_out), (20, 0))  # still in, as failures

    def test_false_positives_count_every_violation_on_a_base(self):
        unverified = [{"n": 5, "verification": {"replays": 20, "replay_violations": 20}}]
        trials = [trial("BASE", "M1", 1, status="censored:executions", counters={"VIOLATION": 1},
                        unverified_violations=unverified),
                  trial("BASE", "M0", 1, status="censored:executions",
                        counters={"stress": 50, "stress_VIOLATION": 3}),
                  trial("BASE", "M3+", 1, status="error:TrialError: a serial run violated the "
                        "contract: the target spec is wrong"),
                  trial("MUT", "M0", 1, e1=4, verification={
                      "replays": 20, "replay_violations": 20,
                      "corrected": {"verdicts": {"PASS": 5, "VIOLATION": 1}}})]
        self.assertEqual(analysis.false_positives(trials, {"BASE"}),
                         {"scheduled": 1, "stress": 3, "profile": 1, "corrected_variant": 1,
                          "replaying_on_controls": 1, "control_trials": 3, "total": 6})


class DecisionRulesTest(unittest.TestCase):
    @staticmethod
    def stat(p, a):
        return {"p": p, "a12": a}

    def test_better_than_a_group_needs_every_member(self):
        both = {"M3+": self.stat(0.001, 0.9), "M3+arg": self.stat(0.02, 0.8)}
        self.assertEqual(analysis.group_p(both, ("M3+", "M3+arg")), (0.02, 1.0))
        one = {"M3+": self.stat(0.001, 0.9), "M3+arg": self.stat(0.02, 0.4)}
        self.assertEqual(analysis.group_p(one, ("M3+", "M3+arg")), (1.0, 0.02))
        self.assertIsNone(analysis.group_p({"M3+": self.stat(0.001, 0.9)}, ("M3+", "M3+arg")))

    def test_holm_runs_across_tested_cells_only(self):
        win = {b: self.stat(0.02, 0.9) for b in analysis.CONVENTIONAL}
        lose = {b: self.stat(0.001, 0.1) for b in analysis.CONVENTIONAL}
        cells = {("T1", "e1"): win, ("T1", "seconds"): lose, ("T2", "e1"): {}}
        out = analysis.verdicts(cells)
        self.assertEqual(out["conventional|T1|e1"]["verdict"], "better")  # 0.02 × 1 after Holm
        self.assertEqual(out["conventional|T1|seconds"]["verdict"], "worse")
        self.assertEqual(out["conventional|T2|e1"]["verdict"], "not tested")  # not in Holm
        self.assertTrue(out["systematic|T1|e1"]["confirmatory"])
        self.assertFalse(out["M0|T1|e1"]["confirmatory"])
        cells[("T2", "e1")] = win
        cells[("T2", "seconds")] = {b: self.stat(0.5, 0.6) for b in analysis.CONVENTIONAL}
        out = analysis.verdicts(cells)  # better: 0.02, 0.02, 1, 1, so 0.06 for each
        self.assertEqual(out["conventional|T1|e1"]["verdict"], "no significant difference")


class BreakEvenTest(unittest.TestCase):
    def rows(self, method, n, **kw):
        return [trial("T", method, s, **kw) for s in range(1, n + 1)]

    def test_hand_computed_crossing(self):
        trials = (self.rows("M4", 5, e1=1, method_s=12.61, exec_s=0.01, model_usd=0.027)
                  + self.rows("M0", 5, e1=7, method_s=0.05, exec_s=0.05))
        r = analysis.break_even(trials, "T", "M4", "M0", 1.11e-5, "seconds")
        self.assertEqual(r["status"], "breaks_even")
        self.assertAlmostEqual(r["c"], 2.1)
        d = analysis.break_even(trials, "T", "M4", "M0", 1.11e-5, "dollars")
        self.assertAlmostEqual(d["c"], 0.027 / 1.11e-5 / 6)

    def test_review_counterexample_failed_muse_trials_count(self):
        """Muse succeeds in 2 of 5: its median cost is infinite, so it never breaks even."""
        trials = (self.rows("M4", 2, e1=1, method_s=12.61, exec_s=0.01)
                  + [trial("T", "M4", s, status="search_plan_exhausted") for s in (3, 4, 5)]
                  + self.rows("M0", 5, e1=7, method_s=0.05, exec_s=0.05))
        self.assertEqual(analysis.break_even(trials, "T", "M4", "M0", 1.11e-5)["status"], "never")

    def test_censored_baseline_enters_at_its_lower_bound(self):
        trials = (self.rows("M4", 5, e1=1, method_s=12.61, exec_s=0.01)
                  + self.rows("M1", 5, status="censored:executions", method_s=7.0, exec_s=7.0))
        r = analysis.break_even(trials, "T", "M4", "M1", 1.11e-5)
        self.assertAlmostEqual(r["c"], 12.6 / 1000)  # 1·c + 12.6 = 1001·c

    def test_always_and_least_favorable(self):
        trials = (self.rows("M4", 3, e1=1, method_s=0.01, exec_s=0.01)
                  + self.rows("M0", 3, e1=7, method_s=0.6, exec_s=0.1))
        always = analysis.break_even(trials, "T", "M4", "M0", 1.11e-5)
        self.assertEqual(always["status"], "always")
        late, early = {"status": "breaks_even", "c": 2.0}, {"status": "breaks_even", "c": 0.5}
        never = {"status": "never"}
        self.assertIs(analysis.least_favorable([always, early, late]), late)
        self.assertIs(analysis.least_favorable([late, never]), never)

    def test_exact_on_random_lines(self):
        """Muse is cheaper at every probe above c, and not cheaper just below a positive c."""
        rng = random.Random(3)
        for _ in range(60):
            trials = [trial("T", "M4", s, e1=rng.randint(1, 30), method_s=rng.uniform(5, 40),
                            exec_s=0.0) for s in range(1, 8)]
            trials += [trial("T", "M0", s, e1=rng.randint(1, 60), method_s=rng.uniform(0, 3),
                             exec_s=0.0) for s in range(1, 8)]
            r = analysis.break_even(trials, "T", "M4", "M0", 1.11e-5)
            m = analysis.cost_lines(trials, "T", "M4", "seconds", 1.11e-5)
            b = analysis.cost_lines(trials, "T", "M0", "seconds", 1.11e-5)
            if r["status"] != "breaks_even":
                continue
            for c in [r["c"] + 10 ** k for k in range(-6, 3)]:
                self.assertLess(analysis.median_at(m, c), analysis.median_at(b, c))
            if r["c"] > 0:
                self.assertGreaterEqual(analysis.median_at(m, r["c"] * (1 - 1e-6)),
                                        analysis.median_at(b, r["c"] * (1 - 1e-6)))

    def test_scenario_crossing(self):
        self.assertEqual(analysis.crossing(1, 12.6, 7, 0.0), ("breaks_even", 2.1))
        self.assertEqual(analysis.crossing(7, 12.6, 7, 0.0), ("never", None))
        self.assertEqual(analysis.crossing(9, 12.6, 7, 0.0), ("never", None))
        self.assertEqual(analysis.crossing(1, 0.0, 7, 1.0), ("always", 0.0))


class DevelopmentRecordTest(unittest.TestCase):
    """The frozen code on a real trial file, against hand-computed values. Development data, so
    nothing here is a result."""

    @classmethod
    def setUpClass(cls):
        cls.trials = json.loads((ROOT / "experiments/2026-10-29-pilot/results/20261028-165020/"
                                 "trials.json").read_text())
        cls.cfg = json.loads((ROOT / "experiments/2026-10-29-pilot/config.json").read_text())

    def test_pilot_d3_executions(self):
        out = analysis.compare(self.trials, "d3-inventory", "e1")
        self.assertAlmostEqual(out["M3+"]["p"], 2 / 252)  # 1 ×5 against 211, 246, 211, 211, 775
        self.assertEqual(out["M3+"]["a12"], 1.0)
        self.assertEqual(out["M1"]["a12"], 1.0)  # M1 censored ×5 at 1,000; M4 found at 1

    def test_review_counterexample_pilot_d3_cost(self):
        """M1 was censored after about 7 s and $0.00007; M4 found the bug at about 12.6 s and
        $0.016. On a common scale that is no evidence either way, not "M4 better"."""
        for metric in ("seconds", "dollars"):
            out = analysis.compare(self.trials, "d3-inventory", metric)
            self.assertEqual((out["M1"]["p"], out["M1"]["a12"]), (1.0, 0.5), metric)

    def test_pilot_report_runs(self):
        report = analysis.analyze(self.trials, self.cfg, ["d3-inventory"], muse_conditions=("M4",))
        methods = report["targets"]["d3-inventory"]["methods"]
        self.assertEqual((methods["M3+"]["median_e1"], methods["M1"]["median_e1"]), (211, B + 1))


if __name__ == "__main__":
    unittest.main()
