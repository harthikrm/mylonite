"""Tests for M3+arg (D-024): its order on a small fake, and, without any execution, against the
pilot's recorded D3 data through the A2 experiment's emulator (m3arg_estimate.py)."""

import collections
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mylonite import methods  # noqa: E402

A2 = ROOT / "experiments/2026-10-28-a2-no-source"


class FakeTrial:
    """``w`` and ``x`` are read-modify-writes whatever their argument; only ``o`` is observed.
    ``s`` changes the store once, so there are two states: [] and [s]."""
    COMMANDS = {"w": [["GET", "o"], ["SET", "o"]], "x": [["GET", "u"], ["SET", "u"]],
                "r": [["GET", "o"]], "s": [["SET", "z"]]}

    def __init__(self):
        self.explored, self.stats = [], collections.Counter()

    def profile(self, setup, call):
        state = f"s{len(setup)}"
        after = f"s{len(setup) + 1}" if call["op"] == "s" else state
        return {"commands": self.COMMANDS[call["op"]], "outcome": "ok",
                "state_before": state, "state_after": after}

    def explore(self, workload, cap, first_policy=None):
        self.explored.append((len(workload["setup"]),
                              tuple((c["op"], c["args"].get("n")) for c in workload["concurrent"])))
        return [], True


TARGET = {"operations": {"w": {"args": {"n": {"domain": "n"}}}, "x": {"args": {}},
                         "r": {"args": {}}, "s": {"args": {}}},
          "domains": {"n": [1, 2]}, "observe": {"op": "r", "arg": None, "for_each": None}}


def run(search, seed):
    trial = FakeTrial()
    search(trial, TARGET, seed, {"schedules_per_experiment": 5})
    return trial


class M3ArgOrderTest(unittest.TestCase):
    def test_variants_come_first_among_the_deferred(self):
        for seed in range(1, 6):
            plus, arg = run(methods.run_m3plus, seed), run(methods.run_m3plus_arg, seed)
            # the same pairs, none dropped or added
            self.assertEqual(sorted(plus.explored), sorted(arg.explored))
            # until the frontier is exhausted, M3+ exactly: one w pair per state
            self.assertEqual(arg.explored[:2], plus.explored[:2])
            self.assertEqual([ops[0][0] for _, ops in arg.explored[:2]], ["w", "w"])
            # then the other w pairs (other values of n), state by state, then x pairs
            rest = arg.explored[2:]
            self.assertEqual([(depth, ops[0][0]) for depth, ops in rest],
                             [(0, "w"), (0, "w"), (1, "w"), (1, "w"), (0, "x"), (1, "x")])
            self.assertEqual(arg.stats["m3arg_variants_promoted"], 4)
            self.assertNotIn("m3arg_variants_promoted", plus.stats)
            self.assertEqual({k: v for k, v in arg.stats.items() if k.startswith("m3_")},
                             dict(plus.stats))

    def test_registered_under_its_own_id(self):
        self.assertIs(methods.METHODS["M3+arg"], methods.run_m3plus_arg)
        self.assertIs(methods.METHODS["M3+"], methods.run_m3plus)


def load_emulator():
    spec = importlib.util.spec_from_file_location("m3arg_estimate", A2 / "m3arg_estimate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class M3ArgAgainstPilotRecordTest(unittest.TestCase):
    """No execution: the emulator answers profiles and explorations from the pilot's D3 log."""

    @classmethod
    def setUpClass(cls):
        cls.emulator = load_emulator()
        cls.record = json.loads((A2 / "m3_d3_record.json").read_text())
        cls.accepted = json.loads((A2 / "m3arg_estimate.json").read_text())

    def test_m3plus_still_reproduces_the_pilot_logs(self):
        """Every profile and exploration in the pilot's order, and E1 211, 246, 211, 211, 775."""
        out = self.emulator.fidelity(self.record)
        self.assertEqual(out["methods.run_m3plus"], self.emulator.PILOT_E1)

    def test_m3plus_arg_matches_the_accepted_estimate(self):
        """methods.run_m3plus_arg in place of the emulator's prototype gives D-024's estimate,
        211, 246, 211, 211, 555, with every pair it reaches recorded."""
        with mock.patch.object(self.emulator, "run_m3plus_arg", methods.run_m3plus_arg):
            got = self.emulator.estimate(self.record)["m3arg_e1_estimate"]["M3+arg (proposed)"]
        expected = self.accepted["m3arg_e1_estimate"]["M3+arg (proposed)"]
        self.assertEqual(got, expected)
        self.assertEqual({s: got[s]["low"] for s in "12345"},
                         {"1": 211, "2": 246, "3": 211, "4": 211, "5": 555})
        self.assertEqual(got["_pairs_without_recorded_cost"], {"low": 0, "high": 0})


if __name__ == "__main__":
    unittest.main()
