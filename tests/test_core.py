"""Unit tests for the parts that need no store: framing, oracle, enumeration, policies."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mylonite import oracle, resp  # noqa: E402
from mylonite.scheduler import (Divergence, HintPolicy, PrefixPolicy, ReplayPolicy,  # noqa: E402
                                next_prefix, soundness_problems)


class FramingTest(unittest.TestCase):
    def test_command_round_trip(self):
        frame = b"*3\r\n$3\r\nSET\r\n$9\r\npoints:m1\r\n$1\r\n5\r\n"
        self.assertEqual(resp.frame_end(frame + b"*1\r\n$4\r\nPING\r\n"), len(frame))
        self.assertEqual(resp.command_parts(frame), [b"SET", b"points:m1", b"5"])

    def test_reply_types(self):
        for reply in (b"+OK\r\n", b"-ERR x\r\n", b":42\r\n", b"$-1\r\n", b"$2\r\nhi\r\n",
                      b"*-1\r\n", b"*2\r\n:1\r\n*1\r\n$1\r\nx\r\n"):
            self.assertEqual(resp.frame_end(reply), len(reply))

    def test_incomplete_and_binary_payload(self):
        with self.assertRaises(resp.Incomplete):
            resp.frame_end(b"$5\r\nab")
        payload = b"a\r\nb"
        frame = b"$4\r\n" + payload + b"\r\n"
        self.assertEqual(resp.frame_end(frame), len(frame))

    def test_resp3_types(self):
        for reply in (b"_\r\n", b",3.14\r\n", b"#t\r\n", b"(123\r\n", b"=8\r\ntxt:abcd\r\n",
                      b"%1\r\n+server\r\n+valkey\r\n", b"~2\r\n:1\r\n:2\r\n",
                      b"|1\r\n+ttl\r\n:3\r\n$1\r\nx\r\n"):
            self.assertEqual(resp.frame_end(reply), len(reply))
        self.assertTrue(resp.is_push(b">2\r\n+invalidate\r\n*1\r\n+k\r\n"))
        with self.assertRaises(resp.ProtocolError):
            resp.frame_end(b"?1\r\n")


CONTRACT = {"invariants": [{"id": "no_lost_award", "kind": "counter_conserved", "op": "award",
                            "key_arg": "member", "amount_arg": "points"}],
            "status_semantics": {"award": {"no_effect": ["Rejected"]}}}


def award(member, points, status="ok"):
    return {"op": "award", "args": {"member": member, "points": points}, "status": status}


class OracleTest(unittest.TestCase):
    def test_lost_award_is_violation(self):
        verdict, details = oracle.check(CONTRACT, [award("m1", 1), award("m1", 1)],
                                        {"m1": 0, "m2": 0}, {"m1": 1, "m2": 0})
        self.assertEqual(verdict, oracle.VIOLATION)
        self.assertEqual(details[0]["failures"][0]["allowed_deltas"], [2])

    def test_info_may_or_may_not_apply(self):
        ops = [award("m1", 1), award("m1", 2, status="info")]
        for final in (1, 3):
            self.assertEqual(oracle.check(CONTRACT, ops, {"m1": 0}, {"m1": final})[0], oracle.PASS)
        self.assertEqual(oracle.check(CONTRACT, ops, {"m1": 0}, {"m1": 2})[0], oracle.VIOLATION)

    def test_errors_are_info_unless_declared(self):
        self.assertEqual(oracle.classify({"op": "award", "error": "TimeoutError"}, CONTRACT), "info")
        self.assertEqual(oracle.classify({"op": "award", "error": "Rejected"}, CONTRACT), "fail")
        self.assertEqual(oracle.classify({"op": "award", "error": None}, CONTRACT), "ok")


class EnumerationTest(unittest.TestCase):
    def test_depth_first_covers_every_interleaving(self):
        # Two operations, each: admit then two commands. Simulate the controller's choices.
        def run(policy):
            state = {0: ["admit", "c1", "c2"], 1: ["admit", "c1", "c2"]}
            steps, labels = [], []
            while any(state.values()):
                choices = [f"{'admit' if s[0] == 'admit' else 'exec'}:{k}"
                           for k, s in sorted(state.items()) if s]
                choices.sort(key=lambda c: (not c.startswith("admit"), c))
                label = policy.choose(len(labels), choices, {})
                steps.append((choices.index(label), len(choices)))
                labels.append(label)
                state[int(label.split(":")[1])].pop(0)
            return steps, tuple(labels)

        seen, prefix = set(), []
        while prefix is not None:
            steps, labels = run(PrefixPolicy(prefix))
            seen.add(labels)
            prefix = next_prefix(steps)
        self.assertEqual(len(seen), 20)  # C(6, 3) interleavings of two 3-step sequences

    def test_replay_divergence_is_loud(self):
        with self.assertRaises(Divergence):
            ReplayPolicy(["exec:1"]).choose(0, ["admit:0"], {})

    def test_hint_admits_then_follows(self):
        hint = HintPolicy([{"op_index": 1, "command": "GET"}])
        self.assertEqual(hint.choose(0, ["admit:0", "admit:1"], {}), "admit:1")
        self.assertEqual(hint.choose(1, ["admit:0", "exec:1"], {1: "GET"}), "exec:1")
        self.assertEqual(hint.followed, 1)

    def test_hint_runs_earlier_commands_of_the_same_operation(self):
        hint = HintPolicy([{"op_index": 0, "command": "GET"}])
        self.assertEqual(hint.choose(0, ["admit:0", "admit:1"], {}), "admit:0")
        self.assertEqual(hint.choose(1, ["admit:1", "exec:0"], {0: "HGET"}), "exec:0")
        self.assertEqual(hint.choose(2, ["admit:1", "exec:0"], {0: "GET"}), "exec:0")
        self.assertEqual(hint.stats(), {"hint_followed": 1, "hint_skipped": 0, "hint_advanced": 1})


class PlannerSchemaTest(unittest.TestCase):
    """The generated schema must satisfy Meta's documented strict-mode rules."""

    def setUp(self):
        import json
        from mylonite import planner
        self.planner = planner
        root = Path(__file__).resolve().parents[1]
        self.target = json.loads((root / "fixtures/dev/d2_counter/target.json").read_text())
        self.schema = planner.plan_schema(self.target)

    def walk(self, node, depth=0):
        self.assertLessEqual(depth, 10)
        for banned in ("allOf", "oneOf", "$ref"):
            self.assertNotIn(banned, node)
        if node.get("type") == "object":
            self.assertIs(node.get("additionalProperties"), False)
            self.assertEqual(sorted(node["required"]), sorted(node["properties"]))
            for child in node["properties"].values():
                self.walk(child, depth + 1)
        if node.get("type") == "array":
            self.walk(node["items"], depth + 1)
        for option in node.get("anyOf", []):
            self.walk(option, depth + 1)

    def test_strict_rules(self):
        self.assertEqual(self.schema["type"], "object")
        for banned in ("anyOf", "enum", "not"):
            self.assertNotIn(banned, self.schema)
        self.walk(self.schema)

    def test_validator_keeps_domain_values_only(self):
        call = lambda member, points: {"op": "award", "args": {"member": member, "points": points}}
        plan = {"experiments": [
            {"hypothesis_id": "H1", "setup": [], "concurrent": [call("m1", 1), call("m1", 1)],
             "schedule_hint": [{"op_index": 0, "command": "GET"}], "expected_effect": ""},
            {"hypothesis_id": "H2", "setup": [], "concurrent": [call("m9", 1), call("m1", 1)],
             "schedule_hint": [], "expected_effect": ""}]}
        valid, problems = self.planner.validate(plan, self.target)
        self.assertEqual(len(valid), 1)
        self.assertEqual(problems[0]["experiment"], 1)


class ExploreTest(unittest.TestCase):
    """Stopping early on a violation must never be reported as an exhausted search space."""

    def test_guided_hit_is_not_exhausted(self):
        import types
        from unittest import mock
        if "redis" not in sys.modules:  # the executor imports it; the host has no redis package
            stub = types.ModuleType("redis")
            stub.exceptions = types.SimpleNamespace(ConnectionError=type("CE", (Exception,), {}),
                                                    TimeoutError=type("TE", (Exception,), {}))
            sys.modules["redis"] = stub
        from mylonite import executor
        hit = {"verdict": oracle.VIOLATION, "steps": [(0, 1)]}
        with mock.patch.object(executor, "execute_once", return_value=hit):
            records, exhausted = executor.explore(None, {}, 100, True, first_policy=object())
        self.assertEqual(len(records), 1)
        self.assertFalse(exhausted)


class ValidatorRobustnessTest(unittest.TestCase):
    def test_malformed_plan_is_dropped_not_crashed(self):
        from mylonite import planner
        target = load_target("d2_counter")
        valid, problems = planner.validate({"experiments": [{"concurrent": []}]}, target)
        self.assertEqual(valid, [])
        self.assertEqual(planner.issue_codes(problems[0]["issues"]), ["malformed_experiment"])

    def test_shared_argument_names_get_the_union_of_domains(self):
        from mylonite import planner
        target = {"operations": {"a": {"args": {"n": {"domain": "x"}}},
                                 "b": {"args": {"n": {"domain": "y"}}}},
                  "domains": {"x": [1, 2], "y": [2, 3]}}
        args = planner.plan_schema(target)["properties"]["experiments"]["items"]["properties"]
        enum = args["setup"]["items"]["properties"]["args"]["properties"]["n"]["anyOf"][0]["enum"]
        self.assertEqual(enum, [1, 2, 3])


class M3PlusOrderTest(unittest.TestCase):
    """Contract-relevant pairs first; everything else later, never dropped."""

    class FakeTrial:
        PROFILES = {"w": [["GET", "o"], ["SET", "o"]], "x": [["GET", "u"], ["SET", "u"]],
                    "r": [["GET", "o"]]}

        def __init__(self):
            import collections
            self.explored, self.stats = [], collections.Counter()

        def profile(self, setup, call):
            return {"commands": self.PROFILES[call["op"]], "outcome": "ok",
                    "state_before": "s0", "state_after": "s0"}

        def explore(self, workload, cap, first_policy=None):
            self.explored.append(tuple(c["op"] for c in workload["concurrent"]))
            return [], True

    def test_observed_key_pairs_come_first(self):
        from mylonite import methods
        target = {"operations": {op: {"args": {}} for op in "wxr"}, "domains": {},
                  "observe": {"op": "r", "arg": None, "for_each": None}}
        trial = self.FakeTrial()
        methods.run_m3plus(trial, target, 1, {"schedules_per_experiment": 5})
        self.assertEqual(trial.explored, [("w", "w"), ("x", "x")])
        self.assertEqual(trial.stats["m3_pairs_deferred"], 1)


class SoundnessTest(unittest.TestCase):
    def test_flags_unscheduled_commands(self):
        events = [{"seq": 1, "event": "ungated", "conn": 3, "cmd": "RENAME"}]
        self.assertEqual(soundness_problems(events), ["unscheduled RENAME on conn 3"])

    def test_flags_exec_without_arrival(self):
        events = [{"seq": 1, "event": "exec", "conn": 3, "op": 0}]
        self.assertTrue(soundness_problems(events))
        events = [{"seq": 1, "event": "arrive", "conn": 3}, {"seq": 2, "event": "exec", "conn": 3}]
        self.assertFalse(soundness_problems(events))


def load_target(name):
    import json
    return json.loads((Path(__file__).resolve().parents[1] / f"fixtures/dev/{name}/target.json")
                      .read_text())


class SpaceTest(unittest.TestCase):
    def test_d3_catalog_and_limits(self):
        import random
        from mylonite import space
        target = load_target("d3_inventory")
        self.assertEqual(len(target["operations"]), 8)
        self.assertEqual(len(space.op_calls(target)), 24)
        rng = random.Random(1)
        for _ in range(200):
            workload = space.random_workload(target, rng)
            self.assertEqual(space.workload_problems(target, workload), [])
        too_big = {"setup": [], "concurrent": [{"op": "stock", "args": {"sku": "s1"}}] * 5}
        self.assertIn("concurrent size", space.workload_problems(target, too_big))


class NonNegativeTest(unittest.TestCase):
    def test_state_invariant(self):
        contract = {"invariants": [{"id": "c", "kind": "non_negative"}]}
        self.assertEqual(oracle.check(contract, [], {"s1": 1}, {"s1": 0, "s2": 3})[0], oracle.PASS)
        verdict, details = oracle.check(contract, [], {"s1": 1}, {"s1": -1, "s2": 0})
        self.assertEqual(verdict, oracle.VIOLATION)
        self.assertEqual(details[0]["failures"], [{"key": "s1", "observed": -1}])


class ScriptKeyTest(unittest.TestCase):
    def test_eval_key_is_first_declared_key(self):
        parts = [b"EVAL", b"return 1", b"2", b"stock:s1", b"sold:s1", b"3"]
        self.assertEqual(resp.command_key(parts), b"stock:s1")
        self.assertEqual(resp.command_key([b"GET", b"k"]), b"k")


class ModelViewTest(unittest.TestCase):
    def test_comments_and_docstrings_removed(self):
        from mylonite import planner
        text = '"""Module doc."""\n# comment\ndef f(x):\n    """Doc."""\n    return x  # trailing\n'
        self.assertEqual(planner.model_view_source(text), "def f(x):\n    return x\n")


class PairFilterTest(unittest.TestCase):
    """M3+ explores a pair only if some interleaving is not conflict-serializable."""

    def test_cases(self):
        from mylonite.methods import unserializable_pair as u
        get_set = [["GET", "k"], ["SET", "k"]]
        self.assertTrue(u(get_set, get_set))                         # lost update
        self.assertFalse(u([["SET", "k"]], [["SET", "k"]]))           # single commands
        self.assertFalse(u([["GET", "x"], ["SET", "y"]], [["SET", "x"]]))  # one conflict only
        self.assertFalse(u([["GET", "k"]], [["GET", "k"]]))           # reads never conflict
        purchase = [["HGET", "p"], ["GET", "s"], ["DECRBY", "s"], ["INCRBY", "n"]]
        self.assertTrue(u(purchase, purchase))                       # check-then-act
        restock, retire = [["HGET", "p"], ["INCRBY", "s"]], [["HGET", "p"], ["HSET", "p"]]
        self.assertFalse(u(restock, retire))


class FakeSession:
    """Stands in for the executor: buggy executions return the queued verdicts."""

    def __init__(self, verdicts, replay_hash="h"):
        self.verdicts, self.replay_hash = list(verdicts), replay_hash

    def request(self, req):
        policy = req.get("policy", {})
        base = {"ms": 1.0, "steps": [], "soundness_problems": [], "trace": [], "ops": [],
                "pre": {}, "post": {}, "setup_outcomes": [], "workload": req.get("workload"),
                "decisions": ["admit:0"], "violations": []}
        if req["variant"] == "fixed":
            return {**base, "verdict": "PASS", "trace_hash": "f"}, 0.002
        if policy.get("kind") == "replay":
            return {**base, "verdict": "VIOLATION", "trace_hash": self.replay_hash}, 0.002
        return {**base, "verdict": self.verdicts.pop(0), "trace_hash": "h"}, 0.002


class TrialAccountingTest(unittest.TestCase):
    CFG = {"replays": 20, "corrected_exhaustive_cap": 10, "corrected_bounded_random": 5}
    PRICES = {"input": 1.25, "cached": 0.15, "output": 4.25, "compute_per_second": 0.0}
    TARGET = {"target": "t", "variants": {"buggy": "b", "fixed": "f"}}

    def trial(self, session, executions=5):
        from mylonite.methods import Trial
        return Trial(session, self.TARGET, {"executions": executions, "method_seconds": 60},
                     self.CFG, self.PRICES, lambda event: None)

    def test_budget_is_enforced_per_execution(self):
        from mylonite.methods import BudgetExhausted
        trial = self.trial(FakeSession(["PASS"] * 10), executions=5)
        with self.assertRaises(BudgetExhausted):
            while True:
                trial.execute({"setup": [], "concurrent": []}, {"kind": "prefix", "prefix": []})
        self.assertEqual(trial.executions, 5)

    def test_first_verified_violation_is_counted(self):
        from mylonite.methods import Found
        trial = self.trial(FakeSession(["PASS", "PASS", "VIOLATION"]))
        with self.assertRaises(Found) as caught:
            for _ in range(3):
                trial.execute({"setup": [], "concurrent": []}, {"kind": "prefix", "prefix": []})
        self.assertEqual(caught.exception.executions, 3)
        self.assertEqual(caught.exception.verification["replay_violations"], 20)
        self.assertEqual(caught.exception.verification["corrected"]["mode"], "exhaustive")

    def test_unreliable_replay_is_not_verified(self):
        trial = self.trial(FakeSession(["VIOLATION", "PASS"], replay_hash="other"))
        trial.execute({"setup": [], "concurrent": []}, {"kind": "prefix", "prefix": []})
        trial.execute({"setup": [], "concurrent": []}, {"kind": "prefix", "prefix": []})
        self.assertEqual(len(trial.unverified), 1)
        self.assertEqual(trial.executions, 2)


if __name__ == "__main__":
    unittest.main()
