"""Tests for the held-out construction tooling (experiments/heldout-v1/heldout.py) on toy code that
is not a held-out base: site finding, strata, each operator's rewrite, serial equivalence of the
mutants on an in-memory store, the C4 selection rules, and the salted commitments."""

import importlib.util
import json
import random
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
_spec = importlib.util.spec_from_file_location("heldout", ROOT / "experiments/heldout-v1/heldout.py")
heldout = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(heldout)

TOY = '''"""A toy ledger (test material only)."""

import redis

RELEASE = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0
end
"""


class Missing(Exception):
    pass


class Low(Exception):
    pass


def connect(host, port):
    return redis.Redis(host=host, port=port, decode_responses=True)


def _state(r, a):
    return r.hget(f"acct:{a}", "state")


def open_account(r, a):
    if not r.hsetnx(f"acct:{a}", "state", "open"):
        raise Missing(a)


def deposit(r, a, n):
    r.incrby(f"bal:{a}", n)


def credit(r, a, n):
    if _state(r, a) != "open":
        raise Missing(a)
    return int(r.incrby(f"bal:{a}", n))


def tally(r, a):
    count = r.hincrby(f"acct:{a}", "tally", 1)
    return count


def withdraw(r, a, n):
    if _state(r, a) != "open":
        raise Missing(a)
    with r.pipeline() as p:
        while True:
            try:
                p.watch(f"bal:{a}")
                current = int(p.get(f"bal:{a}") or 0)
                if current < n:
                    raise Low(a)
                p.multi()
                p.set(f"bal:{a}", current - n)
                p.execute()
                break
            except redis.WatchError:
                continue


def snapshot(r, a):
    with r.pipeline() as p:
        p.hset(f"acct:{a}", "seen", 1)
        p.incr(f"views:{a}")
        p.execute()


def acquire(r, a, token):
    r.set(f"lock:{a}", token)


def release(r, a, token):
    r.eval(RELEASE, 1, f"lock:{a}", token)


def balance(r, a):
    return int(r.get(f"bal:{a}") or 0)
'''

OPS = {"open_account": ("a",), "deposit": ("a", "n"), "credit": ("a", "n"), "tally": ("a",),
       "withdraw": ("a", "n"), "snapshot": ("a",), "acquire": ("a", "token"),
       "release": ("a", "token"), "balance": ("a",)}
DOMAINS = {"a": ["x", "y"], "n": [1, 2, 3], "token": ["t1", "t2"]}


class WatchError(Exception):
    pass


class FakeRedis:
    """Enough of redis-py, on a dict, for serial runs. ``log`` records every store command."""

    def __init__(self, data, log):
        self.data, self.log = data, log

    def _cmd(self, name):
        self.log.append(name)

    def get(self, k):
        self._cmd("GET")
        return self.data.get(k)

    def set(self, k, v):
        self._cmd("SET")
        self.data[k] = str(v)
        return True

    def incrby(self, k, n):
        self._cmd("INCRBY")
        self.data[k] = str(int(self.data.get(k, 0)) + n)
        return int(self.data[k])

    def decrby(self, k, n):
        return self.incrby(k, -n)

    def incr(self, k):
        return self.incrby(k, 1)

    def decr(self, k):
        return self.incrby(k, -1)

    def hget(self, h, f):
        self._cmd("HGET")
        return self.data.get((h, f))

    def hset(self, h, f, v):
        self._cmd("HSET")
        self.data[(h, f)] = str(v)
        return 1

    def hsetnx(self, h, f, v):
        self._cmd("HSETNX")
        if (h, f) in self.data:
            return 0
        self.data[(h, f)] = str(v)
        return 1

    def hincrby(self, h, f, n):
        self._cmd("HINCRBY")
        self.data[(h, f)] = str(int(self.data.get((h, f), 0)) + n)
        return int(self.data[(h, f)])

    def delete(self, k):
        self._cmd("DEL")
        return int(self.data.pop(k, None) is not None)

    def eval(self, script, n, key, token):
        assert heldout.normalize_script(script) == heldout.normalize_script(heldout.RELEASE_SCRIPT)
        self._cmd("EVAL")
        if self.data.get(key) == str(token):
            self.data.pop(key)
            return 1
        return 0

    def pipeline(self, transaction=True):
        self._cmd(f"PIPELINE(transaction={transaction})")
        return FakePipe(self)


class FakePipe:
    """redis-py's modes: after watch() commands run at once; after multi(), or with no watch,
    they are queued until execute()."""

    def __init__(self, r):
        self.r, self.queue, self.immediate = r, [], False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def watch(self, *keys):
        self.r._cmd("WATCH")
        self.immediate = True

    def multi(self):
        if self.queue:
            raise RuntimeError("commands queued before multi")
        self.immediate = False

    def execute(self):
        out = [getattr(self.r, name)(*args) for name, args in self.queue]
        self.queue = []
        return out

    def __getattr__(self, name):
        def call(*args):
            if self.immediate:
                return getattr(self.r, name)(*args)
            self.queue.append((name, args))
            return self
        return call


def load(source):
    stub = types.ModuleType("redis")
    stub.WatchError, stub.Redis = WatchError, object
    saved = sys.modules.get("redis")
    sys.modules["redis"] = stub
    try:
        module = types.ModuleType("toy")
        exec(compile(source, "toy", "exec"), module.__dict__)
        return module
    finally:
        if saved is None:
            del sys.modules["redis"]
        else:
            sys.modules["redis"] = saved


def run_serial(module, calls):
    data, log, out = {}, [], []
    client = FakeRedis(data, log)
    for op, args in calls:
        try:
            out.append(["ok", getattr(module, op)(client, **args)])
        except Exception as exc:
            out.append(["error", type(exc).__name__])
    return out, data, log


def random_calls(rng):
    calls = []
    for _ in range(rng.randint(1, 8)):
        op = rng.choice(sorted(OPS))
        calls.append((op, {a: rng.choice(DOMAINS[a]) for a in OPS[op]}))
    return calls


class SitesTest(unittest.TestCase):
    def setUp(self):
        self.sites = heldout.find_sites(TOY)

    def test_every_idiom_is_found_with_its_stratum(self):
        found = {(s["operator"], s["function"], s["stratum"]) for s in self.sites}
        self.assertEqual(found, {
            ("O1", "deposit", "unguarded"), ("O1", "credit", "guarded"),
            ("O1", "tally", "unguarded"), ("O2", "withdraw", "guarded"),
            ("O3", "snapshot", "unguarded"), ("O5", "release", "unguarded")})

    def test_queued_pipeline_commands_and_reads_are_not_sites(self):
        self.assertFalse(any(s["function"] in ("balance", "open_account", "acquire")
                             for s in self.sites))
        self.assertEqual(sum(s["function"] == "snapshot" for s in self.sites), 1)  # not p.incr

    def test_summary_and_ids(self):
        self.assertEqual(heldout.summary(self.sites)["operator_kinds"], ["O1", "O2", "O3", "O5"])
        self.assertEqual(len({s["id"] for s in self.sites}), len(self.sites))
        self.assertEqual(heldout.find_sites(TOY), self.sites)  # deterministic


class MutationTest(unittest.TestCase):
    def setUp(self):
        self.sites = {s["function"]: s for s in heldout.find_sites(TOY)}
        self.base = load(TOY)

    def mutant(self, function):
        return heldout.mutate(TOY, self.sites[function])

    def test_each_mutant_changes_one_site_and_the_store_commands(self):
        _, _, log = run_serial(load(self.mutant("deposit")), [("deposit", {"a": "x", "n": 2})])
        self.assertEqual(log, ["GET", "SET"])
        _, _, log = run_serial(load(self.mutant("tally")), [("tally", {"a": "x"})])
        self.assertEqual(log, ["HGET", "HSET"])
        _, _, log = run_serial(load(self.mutant("withdraw")),
                               [("open_account", {"a": "x"}), ("deposit", {"a": "x", "n": 3}),
                                ("withdraw", {"a": "x", "n": 1})])
        self.assertNotIn("WATCH", log)
        _, _, log = run_serial(load(self.mutant("snapshot")), [("snapshot", {"a": "x"})])
        self.assertEqual(log[0], "PIPELINE(transaction=False)")
        _, _, log = run_serial(load(self.mutant("release")), [("release", {"a": "x", "token": "t1"})])
        self.assertEqual(log, ["DEL"])
        for function in self.sites:  # every other operation is unchanged
            text = self.mutant(function)
            others = [f for f in OPS if f != function]
            for f in others:
                self.assertEqual(_function_source(text, f), _function_source(TOY, f), (function, f))

    def test_o1_o2_o3_mutants_are_serially_equivalent(self):
        rng = random.Random(11)
        workloads = [random_calls(rng) for _ in range(400)]
        for function in ("deposit", "credit", "tally", "withdraw", "snapshot"):
            mutant = load(self.mutant(function))
            for calls in workloads:
                base_out, base_data, _ = run_serial(self.base, calls)
                mut_out, mut_data, _ = run_serial(mutant, calls)
                self.assertEqual((base_out, base_data), (mut_out, mut_data), (function, calls))

    def test_o5_differs_serially_when_a_non_holder_releases(self):
        calls = [("acquire", {"a": "x", "token": "t1"}), ("release", {"a": "x", "token": "t2"})]
        self.assertNotEqual(run_serial(self.base, calls)[1],
                            run_serial(load(self.mutant("release")), calls)[1])

    def test_unknown_site_is_refused(self):
        with self.assertRaises(LookupError):
            heldout.mutate(TOY, {"id": "O1:balance:1:0", "operator": "O1", "function": "balance",
                                 "line": 1, "col": 0})


def _function_source(text, name):
    import ast
    tree = ast.parse(text)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.unparse(fn)


class SelectionTest(unittest.TestCase):
    @staticmethod
    def sites(*strata):
        return [{"id": f"O1:f:{i}:0", "operator": "O1", "stratum": s} for i, s in enumerate(strata)]

    def test_strata_follow_the_first_bit(self):
        self.assertEqual(heldout.strata_for("7f" + "0" * 62)["alpha"], "guarded")
        self.assertEqual(heldout.strata_for("80" + "0" * 62)["alpha"], "unguarded")

    def test_seeded_cyclic_order_and_discards(self):
        seed = "2b" * 32  # first bit 0: alpha guarded, 3 candidates
        bases = {"alpha": self.sites("guarded", "guarded", "guarded", "unguarded"),
                 "beta": self.sites("unguarded", "unguarded", "guarded")}
        strata = heldout.strata_for(seed)
        start = heldout.start_index(seed, "alpha", strata["alpha"],
                                    sum(s["stratum"] == strata["alpha"] for s in bases["alpha"]))
        rejected = {bases["alpha"][[i for i, s in enumerate(bases["alpha"])
                                    if s["stratum"] == strata["alpha"]][start]]["id"]}
        out = heldout.select(seed, bases, lambda base, site: site["id"] not in rejected)
        self.assertEqual(out["alpha"]["discarded"], sorted(rejected))
        self.assertEqual(out["alpha"]["chosen"]["stratum"], strata["alpha"])
        self.assertEqual(out, heldout.select(seed, bases, lambda b, s: s["id"] not in rejected))

    def test_shortfall_and_no_mutant(self):
        seed = "00" * 32  # alpha guarded, beta unguarded
        out = heldout.select(seed, {"alpha": self.sites("unguarded"), "beta": self.sites("unguarded")},
                             lambda base, site: base == "alpha")
        self.assertEqual(out["alpha"]["stratum_used"], "unguarded")
        self.assertIn("no guarded site", out["alpha"]["shortfall"])
        self.assertIsNone(out["beta"]["chosen"])  # every site failed the filter: no mutant
        self.assertEqual(len(out["beta"]["discarded"]), 1)


class CommitmentTest(unittest.TestCase):
    def test_salted_commitment_round_trip_and_tamper(self):
        with tempfile.TemporaryDirectory() as root:
            d = Path(root) / "heldout" / "alpha"
            d.mkdir(parents=True)
            (d / "service.py").write_text("x = 1\n")
            c = heldout.commit(root, "c2", ("alpha",))
            self.assertEqual(c["files"], 1)
            self.assertTrue(heldout.verify_commitment(root, "c2", c))
            again = heldout.commit(root, "c2", ("alpha",))
            self.assertNotEqual(again["commitment_sha256"], c["commitment_sha256"])  # fresh salt
            (d / "service.py").write_text("x = 2\n")
            self.assertFalse(heldout.verify_commitment(root, "c2", again))
            self.assertNotIn("x = 1", json.dumps(c))

    def test_write_mutant_points_the_view_at_the_mutant(self):
        with tempfile.TemporaryDirectory() as root:
            d = Path(root) / "heldout" / "alpha"
            d.mkdir(parents=True)
            (d / "target.json").write_text(json.dumps({"target": "alpha", "variants": {},
                                                       "model_view": {"files": {}}}))
            heldout.write_mutant(root, "alpha", "alpha_m", "y = 2\n")
            t = json.loads((Path(root) / "heldout/alpha_m/target.json").read_text())
            self.assertEqual(t["variants"], {"buggy": "heldout.alpha_m.service",
                                             "fixed": "heldout.alpha.service"})
            self.assertEqual(t["model_view"]["files"], {"service.py": "heldout/alpha_m/service.py"})


if __name__ == "__main__":
    unittest.main()


_run_spec = importlib.util.spec_from_file_location("run_heldout",
                                                   ROOT / "experiments/heldout-v1/run_heldout.py")
run_heldout = importlib.util.module_from_spec(_run_spec)
_run_spec.loader.exec_module(run_heldout)


class RunnerRulesTest(unittest.TestCase):
    def test_stop_rules(self):
        execution = {"event": "execution", "record": {"verdict": "VIOLATION", "soundness_problems": []}}
        self.assertEqual(run_heldout.stop_reason(execution, "alpha", {"alpha"}), "VIOLATION on base alpha")
        self.assertIsNone(run_heldout.stop_reason(execution, "alpha_m", {"alpha"}))  # expected there
        stress = {"event": "stress", "record": {"verdict": "VIOLATION", "soundness_problems": []}}
        self.assertIsNotNone(run_heldout.stop_reason(stress, "beta", {"beta"}))
        unsound = {"event": "execution", "record": {"verdict": "PASS", "soundness_problems": ["x"]}}
        self.assertIn("soundness", run_heldout.stop_reason(unsound, "alpha_m", set()))
        check = {"event": "verification", "result": {"corrected": {"verdicts": {"PASS": 5, "VIOLATION": 1}}}}
        self.assertIn("corrected variant", run_heldout.stop_reason(check, "alpha_m", set()))
        clean = {"event": "verification", "result": {"corrected": {"verdicts": {"PASS": 6}}}}
        self.assertIsNone(run_heldout.stop_reason(clean, "alpha_m", set()))

    def test_plan_order_and_not_run_records(self):
        cfg = json.loads((ROOT / "experiments/heldout-v1/config.json").read_text())
        plan = run_heldout.plan_of(cfg, ["alpha_m", "beta_m"], ["alpha", "beta"], [1, 2])
        self.assertEqual(plan[0], ("alpha_m", 1, "M0"))
        self.assertEqual([m for t, s, m in plan[:6]], ["M0", "M1", "M3+", "M3+arg", "M4", "A2"])
        self.assertEqual(len(plan), 2 * 2 * 6 + 2 * 2 * 5)
        self.assertTrue(all(t.endswith("_m") for t, _, _ in plan[:24]))  # mutants first
        record = run_heldout.not_run("alpha", "M4", 3, "model cost cap")
        sys.path.insert(0, str(ROOT / "src"))
        from mylonite import analysis
        self.assertIsNone(analysis.outcome(record, "e1"))

    def test_cost_cap_never_cuts_a_trial_midway(self):
        class Inner:
            spent, trial = 0.0, None

            def __call__(self, body, round_no):
                return None, {"model": "muse-spark-1.3"}
        inner = Inner()
        capped = run_heldout.CappedModel(inner, cap=1.0, reserve=0.25, targets={}, root=ROOT)
        self.assertFalse(capped.can_start_trial())  # 5 × 0.25 = 1.25 > 1.0
        capped = run_heldout.CappedModel(inner, cap=30.0, reserve=0.25, targets={}, root=ROOT)
        inner.spent = 28.0
        self.assertTrue(capped.can_start_trial())
        inner.spent = 28.8
        self.assertFalse(capped.can_start_trial())
        inner.spent = 29.8
        with self.assertRaises(RuntimeError):
            capped({}, 1)
        inner.spent = 0.0
        capped.trial, capped.condition = "alpha_m/M4/1", "M4"
        capped({}, 1)
        self.assertEqual(capped.model_strings, {"muse-spark-1.3": 1})


_c6_spec = importlib.util.spec_from_file_location("c6_extended",
                                                  ROOT / "experiments/heldout-v1/c6_extended.py")
c6 = importlib.util.module_from_spec(_c6_spec)
_c6_spec.loader.exec_module(c6)

NESTED = '''
import redis
RELEASE = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"


def release(r, a, token):
    if token:
        try:
            r.eval(RELEASE, 1, f"lock:{a}", token)
        except redis.ResponseError:
            pass


def explicit(r, a):
    with r.pipeline() as p:
        p.multi()
        p.set(f"x:{a}", 1)
        p.execute()


def _take(r, a):
    r.decrby(f"bal:{a}", 1)


def spend(r, a):
    _take(r, a)


def balance(r, a):
    return int(r.get(f"bal:{a}") or 0)
'''


class ReviewFindingsTest(unittest.TestCase):
    """Regression tests for the independent review of C1b (2026-11-01)."""

    def test_one_release_call_is_one_site(self):
        sites = [s for s in heldout.find_sites(NESTED) if s["operator"] == "O5"]
        self.assertEqual(len(sites), 1)

    def test_a_pipeline_with_explicit_multi_is_not_an_o3_site(self):
        self.assertFalse(any(s["function"] == "explicit" for s in heldout.find_sites(NESTED)))

    def test_o2_mutant_has_no_dead_retry_loop(self):
        site = next(s for s in heldout.find_sites(TOY) if s["operator"] == "O2")
        text = _function_source(heldout.mutate(TOY, site), "withdraw")
        self.assertNotIn("while True", text)
        self.assertNotIn("WatchError", text)
        self.assertNotIn("watch(", text)

    def test_commitments_cover_the_whole_mounted_tree(self):
        with tempfile.TemporaryDirectory() as root:
            d = Path(root) / "heldout" / "alpha"
            d.mkdir(parents=True)
            for f in heldout.TARGET_FILES:
                (d / f).write_text("x\n")
            (Path(root) / "heldout" / "__init__.py").write_text("")
            c = heldout.commit(root, "c2", ("alpha",))
            self.assertEqual(c["files"], 4)
            (Path(root) / "heldout" / "common.py").write_text("y = 1\n")  # importable, uncommitted
            with self.assertRaises(ValueError):
                heldout.commit(root, "c2", ("alpha",))
            self.assertFalse(heldout.verify_commitment(root, "c2", c, exact=True))
            self.assertTrue(heldout.verify_commitment(root, "c2", c, exact=False))
            (Path(root) / "heldout" / "common.py").unlink()
            cache = d / "__pycache__"
            cache.mkdir()
            (cache / "service.cpython-312.pyc").write_bytes(b"\0")
            self.assertFalse(heldout.verify_commitment(root, "c2", c, exact=True))
            (Path(root) / "heldout" / "__init__.py").write_text("import os\n")
            self.assertFalse(heldout.verify_commitment(root, "c2", c, exact=False))

    def test_beacon_is_bound_to_the_round_and_normalized(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "private").mkdir()
            import hashlib
            signature = "a5" * 48
            randomness = hashlib.sha256(bytes.fromhex(signature)).hexdigest()
            response = {"round": 7, "randomness": randomness.upper(), "signature": signature}
            (Path(root) / "private" / "drand.json").write_text(json.dumps(response))
            self.assertEqual(heldout.beacon(root, 7)[0], randomness)
            with self.assertRaises(ValueError):
                heldout.beacon(root, 8)
            for bad in ({"round": 7, "randomness": "zz", "signature": signature},
                        {"round": 7, "randomness": "ab" * 32, "signature": signature}):
                (Path(root) / "private" / "drand.json").write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    heldout.beacon(root, 7)

    def test_discards_come_from_the_committed_filter_not_the_record(self):
        """A record that claims discards the C2-committed filter results do not support does
        not survive the replay verify_all makes."""
        sites = {"alpha": [{"id": f"a{i}", "stratum": "guarded"} for i in range(5)],
                 "beta": [{"id": f"b{i}", "stratum": "unguarded"} for i in range(4)]}
        seed = "1f" * 32
        passes = {("alpha", s["id"]) for s in sites["alpha"]} | {("beta", s["id"]) for s in sites["beta"]}
        honest = heldout.select(seed, sites, lambda b, s: (b, s["id"]) in passes)
        self.assertEqual(honest["alpha"]["discarded"], [])
        start = honest["alpha"]["chosen"]["id"]
        wanted = next(s["id"] for s in sites["alpha"] if s["id"] != start)
        forged = heldout.select(seed, sites, lambda b, s: b == "beta" or s["id"] == wanted)
        self.assertNotEqual(forged["alpha"], honest["alpha"])  # the replay would expose it

    def test_replaying_a_record_reproduces_it(self):
        """verify_all replays select() with the record's choice as the only success: any other
        choice or discard list would not match."""
        sites = {"alpha": [{"id": f"a{i}", "stratum": "guarded"} for i in range(5)],
                 "beta": [{"id": f"b{i}", "stratum": "unguarded"} for i in range(4)]}
        seed = "1f" * 32
        failing = {"a0", "a1", "a2", "a3", "b0", "b1", "b2"}
        record = heldout.select(seed, sites, lambda b, s: s["id"] not in failing)
        chosen = {b: r["chosen"]["id"] for b, r in record.items()}
        replay = heldout.select(seed, sites, lambda b, s: s["id"] == chosen[b])
        self.assertEqual(replay, record)
        forged = heldout.select(seed, sites, lambda b, s: s["id"] in ("a4", "b3"))
        if forged["alpha"]["chosen"]["id"] != chosen["alpha"]:
            self.assertNotEqual(forged, record)

    def test_c6_follows_helpers_to_operations(self):
        ops = {"release": {}, "explicit": {}, "spend": {}, "balance": {}}
        self.assertEqual(c6.operations_reaching(NESTED, "_take", ops), ["spend"])
        self.assertEqual(c6.operations_reaching(NESTED, "release", ops), ["release"])
        self.assertEqual(c6.operations_reaching(NESTED, "nowhere", ops), sorted(ops))

    def test_same_error_means_the_same_exception_type(self):
        self.assertEqual(run_heldout.error_type("error:ModelAPIError: HTTP 500 a"), "ModelAPIError")
        self.assertEqual(run_heldout.error_type("error:ModelAPIError: HTTP 502 b"), "ModelAPIError")
        self.assertIsNone(run_heldout.error_type("verified"))
        unsound = {"event": "verification", "result": {"corrected": {"verdicts": {"PASS": 6},
                                                                      "soundness_problems": 1}}}
        self.assertIn("soundness", run_heldout.stop_reason(unsound, "alpha_m", set()))
