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


class PlannerSchemaTest(unittest.TestCase):
    """The generated schema must satisfy Meta's documented strict-mode rules."""

    def setUp(self):
        import json
        from mylonite import planner
        self.planner = planner
        root = Path(__file__).resolve().parents[1]
        self.target = json.loads((root / "fixtures/dev/d2_counter/target.json").read_text())
        self.schema = planner.plan_schema(self.target, ["GET", "SET"])

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
        valid, problems = self.planner.validate(plan, self.target, ["GET", "SET"])
        self.assertEqual(len(valid), 1)
        self.assertEqual(problems[0]["experiment"], 1)


class ExploreTest(unittest.TestCase):
    """Stopping early on a violation must never be reported as an exhausted search space."""

    def test_guided_hit_is_not_exhausted(self):
        import types
        from unittest import mock
        sys.modules.setdefault("redis", types.ModuleType("redis"))  # the executor imports it
        from mylonite import executor
        hit = {"verdict": oracle.VIOLATION, "steps": [(0, 1)]}
        with mock.patch.object(executor, "execute_once", return_value=hit):
            records, exhausted = executor.explore(None, {}, 100, True, first_policy=object())
        self.assertEqual(len(records), 1)
        self.assertFalse(exhausted)


class SoundnessTest(unittest.TestCase):
    def test_flags_exec_without_arrival(self):
        events = [{"seq": 1, "event": "exec", "conn": 3, "op": 0}]
        self.assertTrue(soundness_problems(events))
        events = [{"seq": 1, "event": "arrive", "conn": 3}, {"seq": 2, "event": "exec", "conn": 3}]
        self.assertFalse(soundness_problems(events))


if __name__ == "__main__":
    unittest.main()
