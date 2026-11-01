"""Held-out construction tooling, v1.0 minimum scope (docs/HELDOUT_PROTOCOL.md, C1b; class A,
docs/AMENDMENTS.md AM-001). Host side, standard library only.

  heldout.py sites <base.py>                  site counts per operator and stratum
  heldout.py check-bases <sealed root>        the C2 checks, in the sandbox, including the
                                              serial-equivalence filter for every site
  heldout.py commit-c2 <sealed root> <round>  salted commitment of the bases and the filter's
                                              results, naming drand round R (at least 6 hours
                                              ahead, from <root>/private/drand_info.json)
  heldout.py generate <sealed root>           C4: the mutants for the committed R; no Docker
  heldout.py commit-c4 <sealed root>          salted commitment of bases and mutants
  heldout.py verify <sealed root>             C2 and C4 bind the sealed files, and each mutant
                                              is mutate(base, chosen site) for the committed R

The sealed root lives outside the repository. Its layout:
  <root>/heldout/<name>/{__init__.py, service.py, target.json}   bases (C2) and mutants (C4)
  <root>/heldout/__init__.py
  <root>/private/                    salts, full manifests, generation record (never committed)
It is mounted read-only at /app/heldout (Sandbox.target_root), so a module imports as
``heldout.<name>.service``. A commitment hashes **every** file under ``heldout/`` and refuses any
file other than ``heldout/__init__.py`` and each target's three files (``__pycache__``
included), since everything there is importable. Only commitments and the beacon's public
response are written into the repository (experiments/heldout-v1/sealed/).

**Base dialect.** The operators find their sites only in these forms. ``r`` is an operation's
first parameter, the store client (redis-py, per connection):
- atomic counters: ``r.incr(k)``, ``r.decr(k)``, ``r.incrby(k, n)``, ``r.decrby(k, n)``,
  ``r.hincrby(h, f, n)``. Each is a whole statement, the value of a one-name assignment, or a
  returned value, possibly inside ``int(...)``, with key and amount built only from names,
  constants, f-strings and arithmetic;
- optimistic transactions::

      with r.pipeline() as p:
          while True:
              try:
                  p.watch(...)
                  ...reads through p...
                  p.multi()
                  ...writes through p...
                  p.execute()
                  break
              except redis.WatchError:
                  continue

- MULTI/EXEC blocks: ``with r.pipeline() as p:`` with queued writes and ``p.execute()``, and no
  ``watch``;
- lock release by compare-and-delete: ``r.eval(NAME, 1, key, token)`` as a whole statement, an
  assignment's value or a returned value, where ``NAME`` is a module-level string equal, after
  normalization, to ``RELEASE_SCRIPT``.

Counters written any other way, for example ``+=`` on a value read earlier, are not sites. The
dialect lets an author hide a site that way; that is disclosed, not prevented.

**Operators (v1.0).** These are the plan's §4.2 operators, as the protocol revised them:

  O1  an atomic update becomes read, compute, write (GET + SET, or HGET + HSET)
  O2  an optimistic transaction loses its WATCH: the watch goes, the reads before ``multi()``
      go to the client, and the retry loop around it (``while True`` / ``except WatchError``),
      which could no longer retry anything, goes too
  O3  a MULTI/EXEC block becomes a non-transactional pipeline (only a block with no explicit
      ``multi()``: with one, redis-py would still send MULTI/EXEC)
  O5  a compare-and-delete lock release becomes an unconditional DEL

**Not implemented, recorded before C2 as the protocol requires:**
  O4  (a check inside a server-side script moves to the client) needs a translation of Lua
      into Python, which is not mechanical enough to trust;
  O6  (a state write moves before its guard) changes serial behavior by construction. The
      serial-equivalence filter would discard every such mutant.

**Strata.** A site is guarded if, in its function, it lies inside an ``if`` or ``while`` whose
test reads the store, or comes after such an ``if`` whose body or ``else`` always leaves the
function (``raise`` or ``return``) in the same block or an enclosing one. Otherwise it is
unguarded. A test reads the store if it calls a method of the client, calls a module function
with the client as an argument, or uses a variable assigned from such a call. The strata are
syntactic and per function: a site in a helper that runs only after a store check elsewhere, or
in a ``for`` over a store read, is unguarded. An author could move a site between strata by
refactoring. That is disclosed, not prevented.

**Live sites.** A site counts toward C2's minimums only if its mutant is serially equivalent to
the base and changes the store command stream on at least one of the equivalence workloads. C4
uses the frozen filter, serial equivalence, and records whether the chosen mutant changes the
command stream.
"""

import ast
import copy
import hashlib
import json
import random
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))

BASES = ("alpha", "beta")
COUNTERS = {"incr": ("get", "set", "+", 1), "decr": ("get", "set", "-", 1),
            "incrby": ("get", "set", "+", None), "decrby": ("get", "set", "-", None),
            "hincrby": ("hget", "hset", "+", None)}
RELEASE_SCRIPT = ("if redis.call('get', KEYS[1]) == ARGV[1] then "
                  "return redis.call('del', KEYS[1]) else return 0 end")
IMPLEMENTED = ("O1", "O2", "O3", "O5")
FILTER_KEYS = ("serially_equivalent", "changes_commands")
NOT_IMPLEMENTED = {"O4": "needs a Lua-to-Python translation", "O6": "never serially equivalent"}
PURE = (ast.Name, ast.Constant, ast.JoinedStr, ast.FormattedValue, ast.BinOp, ast.UnaryOp,
        ast.Attribute, ast.Subscript, ast.operator, ast.unaryop, ast.Load)


def normalize_script(text):
    return re.sub(r"\s+", " ", text.replace('"', "'")).strip().lower()


# --- sites ----------------------------------------------------------------------------------------

def _is_pure(node):
    return all(isinstance(n, PURE) for n in ast.walk(node))


def _client_call(node, clients, attrs=None):
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id in clients
            and (attrs is None or node.func.attr in attrs))


class _Function:
    """One operation: its client name, pipeline names, and which expressions read the store."""

    def __init__(self, fn, module_functions):
        self.fn, self.client = fn, fn.args.args[0].arg
        self.module_functions = module_functions
        self.pipes = {item.optional_vars.id for node in ast.walk(fn) if isinstance(node, ast.With)
                      for item in node.items
                      if isinstance(item.optional_vars, ast.Name)
                      and _client_call(item.context_expr, {self.client}, {"pipeline"})}
        self.tainted = set()
        for _ in range(3):  # variables assigned from store reads, to a fixed point
            for node in ast.walk(fn):
                if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)) and node.value \
                        is not None and self.reads(node.value):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    self.tainted |= {n.id for t in targets for n in ast.walk(t)
                                     if isinstance(n, ast.Name)}

    def reads(self, expr):
        stores = {self.client} | self.pipes
        for node in ast.walk(expr):
            if _client_call(node, stores):
                return True
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in self.module_functions
                    and any(isinstance(a, ast.Name) and a.id in stores for a in node.args)):
                return True
            if isinstance(node, ast.Name) and node.id in self.tainted:
                return True
        return False


def _always_exits(stmts):
    return bool(stmts) and isinstance(stmts[-1], (ast.Raise, ast.Return))


def _counter_call(stmt, client):
    """The one atomic-counter call a statement of a permitted form makes, or None."""
    value = _simple_value(stmt)
    if value is None or not _client_call(value, {client}, COUNTERS):
        return None
    attr = value.func.attr
    expected = {"incr": 1, "decr": 1, "incrby": 2, "decrby": 2, "hincrby": 3}[attr]
    if len(value.args) != expected or value.keywords or not all(map(_is_pure, value.args)):
        return None
    return value


def _simple_value(stmt):
    """The value of a whole-statement expression, a one-name assignment or a return, unwrapped
    from ``int(...)``; None for any other statement."""
    if isinstance(stmt, ast.Expr):
        value = stmt.value
    elif isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
        value = stmt.value
    elif isinstance(stmt, ast.Return) and stmt.value is not None:
        value = stmt.value
    else:
        return None
    if (isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "int"
            and len(value.args) == 1):
        value = value.args[0]
    return value


def _release_call(stmt, client, scripts):
    node = _simple_value(stmt)
    if (node is not None and _client_call(node, {client}, {"eval"}) and len(node.args) == 4
            and isinstance(node.args[0], ast.Name) and node.args[0].id in scripts
            and isinstance(node.args[1], ast.Constant) and node.args[1].value == 1
            and _is_pure(node.args[2])):
        return node
    return None


def _pipeline_with(stmt, client):
    if isinstance(stmt, ast.With) and len(stmt.items) == 1:
        item = stmt.items[0]
        if isinstance(item.optional_vars, ast.Name) and _client_call(item.context_expr, {client},
                                                                        {"pipeline"}):
            return item.optional_vars.id
    return None


def _watch_block(stmts, pipe):
    """(index of ``pipe.watch(...)``, index of ``pipe.multi()``) in one statement list, or None."""
    def is_call(stmt, attr):
        return isinstance(stmt, ast.Expr) and _client_call(stmt.value, {pipe}, {attr})
    watch = next((i for i, s in enumerate(stmts) if is_call(s, "watch")), None)
    multi = next((i for i, s in enumerate(stmts) if is_call(s, "multi")), None)
    return (watch, multi) if watch is not None and multi is not None and watch < multi else None


def _statement_lists(node):
    for field in ("body", "orelse", "finalbody"):
        if isinstance(getattr(node, field, None), list):
            yield getattr(node, field)
    for handler in getattr(node, "handlers", []):
        yield handler.body


def find_sites(source):
    """Every site in a base, in source order: dicts with id, operator, function, line, col,
    stratum and detail."""
    tree = ast.parse(source)
    functions = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    scripts = {t.id for n in tree.body if isinstance(n, ast.Assign)
               and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)
               and normalize_script(n.value.value) == normalize_script(RELEASE_SCRIPT)
               for t in n.targets if isinstance(t, ast.Name)}
    sites = []
    for fn in tree.body:
        if not isinstance(fn, ast.FunctionDef) or not fn.args.args:
            continue
        info = _Function(fn, functions)

        def site(operator, node, guarded, detail):
            sites.append({"operator": operator, "function": fn.name, "line": node.lineno,
                          "col": node.col_offset, "stratum": "guarded" if guarded else "unguarded",
                          "detail": detail})

        def visit(stmts, guarded):
            for stmt in stmts:
                call = _counter_call(stmt, info.client)
                if call is not None:
                    site("O1", stmt, guarded, call.func.attr)
                if _release_call(stmt, info.client, scripts) is not None:
                    site("O5", stmt, guarded, "compare-and-delete release")
                pipe = _pipeline_with(stmt, info.client)
                if pipe is not None:  # a transaction's stratum is that of its with statement
                    blocks = [lst for n in ast.walk(stmt) for lst in _statement_lists(n)
                              if _watch_block(lst, pipe)]
                    has_watch = any(_client_call(n, {pipe}, {"watch"}) for n in ast.walk(stmt))
                    has_multi = any(_client_call(n, {pipe}, {"multi"}) for n in ast.walk(stmt))
                    keyword = stmt.items[0].context_expr.keywords
                    if blocks:
                        site("O2", blocks[0][_watch_block(blocks[0], pipe)[0]], guarded, "watch")
                    elif not has_watch and not has_multi and not keyword:
                        site("O3", stmt, guarded, "transactional pipeline")
                inner = guarded
                if isinstance(stmt, (ast.If, ast.While)) and info.reads(stmt.test):
                    inner = True
                for block in _statement_lists(stmt):
                    visit(block, inner)
                if (isinstance(stmt, ast.If) and info.reads(stmt.test)
                        and (_always_exits(stmt.body) or _always_exits(stmt.orelse))):
                    guarded = True

        visit(fn.body, False)
    sites.sort(key=lambda s: (s["line"], s["col"], s["operator"]))
    for s in sites:
        s["id"] = f"{s['operator']}:{s['function']}:{s['line']}:{s['col']}"
    return sites


def summary(sites):
    kinds = sorted({s["operator"] for s in sites})
    strata = {k: sum(s["stratum"] == k for s in sites) for k in ("guarded", "unguarded")}
    return {"operator_kinds": kinds, "sites_per_stratum": strata,
            "meets_c2": len(kinds) >= 3 and min(strata.values()) >= 3}


# --- mutation ---------------------------------------------------------------------------------------

def _fresh_name(fn, preferred=("updated", "new_value", "result_value")):
    used = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)} | {a.arg for a in ast.walk(fn)
                                                                       if isinstance(a, ast.arg)}
    return next(n for n in preferred if n not in used)


def _find(tree, site):
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == site["function"])
    for node in ast.walk(fn):
        for block in _statement_lists(node):
            for i, stmt in enumerate(block):
                if (stmt.lineno, stmt.col_offset) == (site["line"], site["col"]):
                    return fn, block, i
    raise LookupError(site["id"])


def _is_watch_retry(loop, block):
    """``while True: try: <block> except <...>WatchError: continue``, with <block> ending in
    ``break``."""
    if not (isinstance(loop, ast.While) and isinstance(loop.test, ast.Constant)
            and loop.test.value is True and not loop.orelse and len(loop.body) == 1):
        return False
    attempt = loop.body[0]
    if not (isinstance(attempt, ast.Try) and attempt.body is block and len(attempt.handlers) == 1
            and not attempt.orelse and not attempt.finalbody):
        return False
    handler = attempt.handlers[0]
    kind = handler.type
    named = (isinstance(kind, ast.Attribute) and kind.attr == "WatchError") or \
        (isinstance(kind, ast.Name) and kind.id == "WatchError")
    return (named and len(handler.body) == 1 and isinstance(handler.body[0], ast.Continue)
            and bool(block) and isinstance(block[-1], ast.Break))


def _unwrap_retry_loop(fn, block):
    """After O2, nothing is watched, so the retry loop can never retry: replace it with its body,
    without the final ``break``. A transaction written without a watch looks like this, so the
    mutant does not keep a loop that is obviously dead."""
    for node in ast.walk(fn):
        for parent in _statement_lists(node):
            for k, loop in enumerate(parent):
                if _is_watch_retry(loop, block):
                    parent[k:k + 1] = block[:-1]
                    return True
    return False


def mutate(source, site):
    """The base's source with exactly one site rewritten, as normalized Python."""
    tree = ast.parse(source)
    if site["id"] not in {s["id"] for s in find_sites(source)}:
        raise LookupError(f"not a site of this base: {site['id']}")
    fn, block, i = _find(tree, site)
    client = fn.args.args[0].arg
    stmt = block[i]
    if site["operator"] == "O1":
        call = _counter_call(stmt, client)
        read, write, sign, default = COUNTERS[call.func.attr]
        target = call.args[:2] if read == "hget" else call.args[:1]
        amount = call.args[-1] if default is None else ast.Constant(default)
        tmp = _fresh_name(fn)
        current = ast.Call(ast.Name("int", ast.Load()),
                           [ast.BoolOp(ast.Or(), [ast.Call(ast.Attribute(ast.Name(client, ast.Load()), read, ast.Load()),
                                                           copy.deepcopy(target), []),
                                                  ast.Constant(0)])], [])
        compute = ast.Assign([ast.Name(tmp, ast.Store())],
                             ast.BinOp(current, ast.Add() if sign == "+" else ast.Sub(),
                                       copy.deepcopy(amount)))
        store = ast.Expr(ast.Call(ast.Attribute(ast.Name(client, ast.Load()), write, ast.Load()),
                                  copy.deepcopy(target) + [ast.Name(tmp, ast.Load())], []))

        class Replace(ast.NodeTransformer):
            def visit_Call(self, node):
                return ast.Name(tmp, ast.Load()) if node is call else self.generic_visit(node)
        rest = Replace().visit(stmt)
        block[i:i + 1] = [compute, store] + ([] if isinstance(rest, ast.Expr)
                                            and isinstance(rest.value, ast.Name) else [rest])
    elif site["operator"] == "O2":
        pipe = stmt.value.func.value.id
        watch, multi = _watch_block(block, pipe)

        class ToClient(ast.NodeTransformer):
            def visit_Call(self, node):
                self.generic_visit(node)
                if _client_call(node, {pipe}) and node.func.attr not in ("multi", "execute"):
                    node.func.value = ast.Name(client, ast.Load())
                return node
        for j in range(watch + 1, multi):
            block[j] = ToClient().visit(block[j])
        del block[watch]
        _unwrap_retry_loop(fn, block)
    elif site["operator"] == "O3":
        stmt.items[0].context_expr = ast.Call(
            ast.Attribute(ast.Name(client, ast.Load()), "pipeline", ast.Load()), [],
            [ast.keyword("transaction", ast.Constant(False))])
    elif site["operator"] == "O5":
        scripts = {t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets
                   if isinstance(t, ast.Name)}
        call = _release_call(stmt, client, scripts)

        class Delete(ast.NodeTransformer):
            def visit_Call(self, node):
                if node is call:
                    return ast.Call(ast.Attribute(ast.Name(client, ast.Load()), "delete", ast.Load()),
                                    [node.args[2]], [])
                return self.generic_visit(node)
        block[i] = Delete().visit(stmt)
    else:
        raise ValueError(site["operator"])
    return ast.unparse(ast.fix_missing_locations(tree)) + "\n"


# --- C4 selection -----------------------------------------------------------------------------------

def strata_for(seed_hex):
    """Most significant bit of the seed's first byte 0: alpha guarded, beta unguarded."""
    first = int(seed_hex[:2], 16) >> 7
    return {"alpha": "guarded", "beta": "unguarded"} if first == 0 else \
        {"alpha": "unguarded", "beta": "guarded"}


def start_index(seed_hex, base, stratum, n):
    digest = hashlib.sha256(f"{seed_hex}|{base}|{stratum}".encode()).digest()
    return int.from_bytes(digest, "big") % n


def select(seed_hex, sites_by_base, equivalent):
    """Per base: the first site, in the seeded cyclic order of its stratum, whose mutant is
    serially equivalent (``equivalent(base, site)``). Returns {base: record}; every discard and
    shortfall is in the record."""
    out = {}
    for base, stratum in strata_for(seed_hex).items():
        sites = sites_by_base[base]
        record = {"stratum_assigned": stratum, "shortfall": None, "discarded": [], "chosen": None}
        candidates = [s for s in sites if s["stratum"] == stratum]
        if not candidates:
            other = "unguarded" if stratum == "guarded" else "guarded"
            record["shortfall"] = f"no {stratum} site; took {other}"
            stratum, candidates = other, [s for s in sites if s["stratum"] == other]
        record["stratum_used"] = stratum
        if candidates:
            start = start_index(seed_hex, base, stratum, len(candidates))
            for k in range(len(candidates)):
                site = candidates[(start + k) % len(candidates)]
                if equivalent(base, site):
                    record["chosen"] = site
                    break
                record["discarded"].append(site["id"])
        out[base] = record
    return out


# --- sealed material ----------------------------------------------------------------------------------

SEALED = HERE / "sealed"  # commitments and the beacon's public response, in the repository
TARGET_FILES = ("__init__.py", "service.py", "target.json")


def hash_tree(root):
    """{path under root: SHA-256} for every file under <root>/heldout/, nothing skipped. A symbolic
    link anywhere under it is refused: a linked directory would be neither hashed nor refused."""
    import os
    files = {}
    for dirpath, dirnames, filenames in os.walk(Path(root) / "heldout"):
        for entry in dirnames + filenames:
            if (Path(dirpath) / entry).is_symlink():
                raise ValueError(f"symbolic link under heldout/: {Path(dirpath) / entry}")
        for name in filenames:
            path = Path(dirpath) / name
            files[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(sorted(files.items()))


def sealed_files(root, names):
    """``hash_tree``, refusing any file other than heldout/__init__.py and each named target's
    three files: everything under heldout/ is importable, so nothing else may be there."""
    files = hash_tree(root)
    allowed = {"heldout/__init__.py"} | {f"heldout/{n}/{f}" for n in names for f in TARGET_FILES}
    extra = sorted(set(files) - allowed)
    if extra:
        raise ValueError(f"unexpected files under heldout/: {extra}")
    return files


def commit(root, step, names, sites=None):
    """Write the full manifest and a fresh salt under <root>/private/, and return the commitment
    to put in the repository: SHA-256(salt ‖ manifest), the file count and the names. At C2 the
    manifest also holds every site and the filter's result for it, so the commitment binds
    them before the beacon is known."""
    private = Path(root) / "private"
    private.mkdir(exist_ok=True)
    content = {"step": step, "files": sealed_files(root, names)}
    if sites is not None:
        content["sites"] = sites
    manifest = json.dumps(content, indent=1, sort_keys=True).encode()
    salt = secrets.token_bytes(32)
    (private / f"{step}_manifest.json").write_bytes(manifest)
    (private / f"{step}_salt.hex").write_text(salt.hex() + "\n")
    return {"step": step, "names": list(names), "files": len(json.loads(manifest)["files"]),
            "commitment_sha256": hashlib.sha256(salt + manifest).hexdigest()}


def verify_commitment(root, step, commitment, exact=True):
    """The private manifest matches the commitment, and the files match the manifest. ``exact``:
    the tree holds exactly those files (C4); otherwise the manifest's files are unchanged and
    others may have been added since (C2, after C4)."""
    private = Path(root) / "private"
    manifest = (private / f"{step}_manifest.json").read_bytes()
    salt = bytes.fromhex((private / f"{step}_salt.hex").read_text().strip())
    if hashlib.sha256(salt + manifest).hexdigest() != commitment["commitment_sha256"]:
        return False
    try:
        now = hash_tree(root)
    except ValueError:
        return False
    recorded = json.loads(manifest)["files"]
    if exact:
        try:
            return recorded == sealed_files(root, commitment["names"])
        except ValueError:
            return False
    return all(now.get(path) == digest for path, digest in recorded.items())


def committed(name):
    """A file under experiments/heldout-v1/sealed/ as committed at HEAD (not the working copy)."""
    path = f"experiments/heldout-v1/sealed/{name}"
    done = subprocess.run(["git", "-C", str(REPO), "show", f"HEAD:{path}"], capture_output=True)
    if done.returncode:
        raise FileNotFoundError(f"{path} is not committed")
    return json.loads(done.stdout)


def beacon(root, round_number):
    """Round R's randomness from the saved drand response: the round must be R, and the value 64
    hex digits, lowercased so that one value gives one choice."""
    response = json.loads((Path(root) / "private" / "drand.json").read_text())
    if response.get("round") != round_number:
        raise ValueError(f"the saved drand response is round {response.get('round')}, not {round_number}")
    randomness = str(response.get("randomness", "")).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", randomness):
        raise ValueError("the saved drand response has no 64-hex-digit randomness")
    signature = str(response.get("signature", ""))
    if not re.fullmatch(r"[0-9a-fA-F]+", signature) or \
            hashlib.sha256(bytes.fromhex(signature)).hexdigest() != randomness:
        raise ValueError("the saved drand response's randomness is not SHA-256 of its signature")
    return randomness, response


def committed_sites(root):
    """The sites and filter results bound by the C2 commitment, per base."""
    return json.loads((Path(root) / "private" / "c2_manifest.json").read_text())["sites"]


def verify_all(root):
    """Every check a C5 run or C6 needs before trusting the sealed root. Returns problems, or []:
    - C2 binds the bases (unchanged since), and C4 binds every file now under heldout/;
    - the bases in C4 are the bases of C2;
    - the C4 record is for the round named at C2, with the committed beacon response's
      randomness;
    - replaying the C4 rules, with the record's discards as the only failures of the filter,
      gives the record's choice;
    - each mutant is exactly mutate(base, chosen site), and its target spec is write_mutant's."""
    problems = []
    try:
        c2, c4 = committed("c2_commitment.json"), committed("c4_commitment.json")
        response = committed(f"drand_round_{c2['round']}.json")
    except FileNotFoundError as exc:
        return [str(exc)]
    if not verify_commitment(root, "c2", c2, exact=False):
        problems.append("the bases differ from the C2 commitment")
    if not verify_commitment(root, "c4", c4, exact=True):
        problems.append("the sealed files differ from the C4 commitment")
    path = Path(root) / "private" / "c4_record.json"
    if not path.exists():
        return problems + ["no C4 record"]
    record = json.loads(path.read_text())
    if record["round"] != c2["round"] or response.get("round") != c2["round"]:
        problems.append("the C4 record or the beacon response is not for the round named at C2")
    if record["randomness"] != str(response.get("randomness", "")).lower():
        problems.append("the C4 record's randomness is not the committed beacon's")
    sources = {b: (Path(root) / "heldout" / b / "service.py").read_text() for b in BASES}
    bound = committed_sites(root)
    sites = {b: [{k: v for k, v in s.items() if k not in FILTER_KEYS} for s in bound[b]]
             for b in BASES}
    for b in BASES:
        if sites[b] != find_sites(sources[b]):
            problems.append(f"{b}: the committed sites are not the sites of the committed base")
    passes = {(b, s["id"]) for b in BASES for s in bound[b] if s["serially_equivalent"]}
    replay = select(record["randomness"], sites, lambda base, site: (base, site["id"]) in passes)
    for base in BASES:
        mine, theirs = record["record"][base], replay[base]
        if (mine["discarded"], mine["chosen"]) != (theirs["discarded"], theirs["chosen"]):
            problems.append(f"{base}: the C4 record does not follow the C4 rules")
        mutant_dir = Path(root) / "heldout" / f"{base}_m"
        if mine["chosen"] is None:
            if mutant_dir.exists():
                problems.append(f"{base}: a mutant exists although none was chosen")
            continue
        if (mutant_dir / "service.py").read_text() != mutate(sources[base], mine["chosen"]):
            problems.append(f"{base}_m is not mutate({base}, chosen site)")
        expected = mutant_spec(root, base, f"{base}_m")
        if json.loads((mutant_dir / "target.json").read_text()) != expected:
            problems.append(f"{base}_m's target spec is not the base's, as write_mutant makes it")
    return problems


# --- executions (sandbox) -----------------------------------------------------------------------------

def serial_workloads(target, n=150, seed="heldout-serial"):
    """Random workloads (space.random_workload), to be run with the serial schedule:
    PrefixPolicy([]) runs the concurrent calls one after another."""
    from mylonite import space
    rng = random.Random(seed)
    return [space.random_workload(target, rng) for _ in range(n)]


def outcome_of(record):
    """What a serial run shows from outside: setup outcomes, each call's value or error, the
    observations before and after, and the verdict."""
    return [record["setup_outcomes"], [[o.get("value"), o.get("error")] for o in record["ops"]],
            record["pre"], record["post"], record["verdict"]]


def commands_of(record):
    return [e["cmd"] for e in record["trace"] if e["event"] == "exec"]


def frontier(session, target, variant):
    """The setups M3+'s greybox search reaches (its frontier), found with M3+'s own rule on
    profiles of the given variant. Seeded order; no pairs are explored."""
    import collections
    from mylonite import methods

    class Recorder:
        def __init__(self):
            self.setups, self.stats = [], collections.Counter()

        def profile(self, setup, call):
            if setup not in self.setups:
                self.setups.append(setup)
            out, _ = session.request({"op": "profile", "variant": variant, "setup": setup,
                                      "call": call})
            return out

        def explore(self, workload, cap, first_policy=None):
            return [], True
    recorder = Recorder()
    methods.run_m3plus(recorder, target, "heldout-frontier", {"schedules_per_experiment": 1})
    return recorder.setups


def run(session, variant, workload, retries=2):
    """One serial run. A harness error (not the service's) is retried, at most twice."""
    for _ in range(retries + 1):
        record = session.request({"op": "execute", "variant": variant, "workload": workload,
                                  "policy": {"kind": "prefix", "prefix": []}})[0]
        if not record["harness_error"]:
            return record
    return record


def equivalence_workloads(session, target, variant="base"):
    """150 random serial workloads, and every frontier setup followed by each catalog call. The
    call runs as the workload's one operation, so its return value is compared too."""
    from mylonite import space
    work = serial_workloads(target)
    for setup in frontier(session, target, variant):
        work += [{"setup": setup, "concurrent": [call]} for call in space.op_calls(target)]
    return work


def compare_variants(session, target, work):
    """(serially equivalent, changes the command stream) for the mutant ("buggy") against its
    base ("base"). A run with a harness error after retries counts as a difference."""
    equivalent, changed = True, False
    for workload in work:
        a, b = run(session, "base", workload), run(session, "buggy", workload)
        if outcome_of(a) != outcome_of(b) or a["harness_error"] or b["harness_error"]:
            return False, changed
        changed = changed or commands_of(a) != commands_of(b)
    return equivalent, changed


def load_target(root, name):
    return json.loads((Path(root) / "heldout" / name / "target.json").read_text())


def probe(root, base, site, label):
    """Is this site live? Its mutant, in a temporary directory that is removed afterwards, must
    be serially equivalent to the base and change the command stream."""
    from mylonite.sandbox import Sandbox
    name = f"{base}_{label}"
    source = (Path(root) / "heldout" / base / "service.py").read_text()
    write_mutant(root, base, name, mutate(source, site))
    target = load_target(root, name)
    target["variants"] = {"buggy": f"heldout.{name}.service", "base": f"heldout.{base}.service"}
    box = Sandbox(f"mylonite-{label}-{base}", REPO, target_root=Path(root) / "heldout")
    box.up()
    try:
        with box.session(target) as session:
            return compare_variants(session, target, equivalence_workloads(session, target))
    finally:
        box.down()
        if label == "probe":
            shutil_rmtree(Path(root) / "heldout" / name)


def check_base(root, name):
    """The C2 checks of one base, in the sandbox: serial validity (150 random serial workloads,
    no violation), determinism (each twice, same outcome), pass-through, the contamination audit
    of its first request, and the minimums counted on live sites only."""
    from mylonite import audit, planner
    from mylonite.sandbox import Sandbox
    target = load_target(root, name)
    target["variants"] = {"base": f"heldout.{name}.service"}
    source = (Path(root) / "heldout" / name / "service.py").read_text()
    sites = find_sites(source)
    filtered = []
    for site in sites:
        equivalent, changed = probe(root, name, site, "probe")
        filtered.append(dict(site, serially_equivalent=equivalent, changes_commands=changed))
    live = [s for s in filtered if s["serially_equivalent"] and s["changes_commands"]]
    report = {"sites": summary(sites), "live_sites": summary(live),
              "dead_sites": [s["id"] for s in filtered if s not in live],
              "filtered_sites": filtered,
              "service_sha256": hashlib.sha256(source.encode()).hexdigest()}
    body = planner.build_request(target, root)
    report["audit_findings"] = audit.findings(body, target, root)
    box = Sandbox(f"mylonite-c2-{name}", REPO, target_root=Path(root) / "heldout")
    box.up()
    try:
        one = box.run_executor({"target": target, "variant": "base", "jobs": [
            {"id": "pt", "kind": "passthrough_check", "workload": w, "repeat": 3}
            for w in serial_workloads(target, n=20, seed="heldout-passthrough")]})
        report["passthrough_mismatches"] = sum(j["summary"]["mismatches"] for j in one["jobs"])
        report["egress_probe"] = one["egress_probe"]
        with box.session(target) as session:
            verdicts, nondeterministic = {}, 0
            for workload in serial_workloads(target):
                first, second = run(session, "base", workload), run(session, "base", workload)
                verdicts[first["verdict"]] = verdicts.get(first["verdict"], 0) + 1
                nondeterministic += outcome_of(first) != outcome_of(second)
            report["serial_verdicts"], report["nondeterministic"] = verdicts, nondeterministic
    finally:
        box.down()
    report["passes"] = (report["live_sites"]["meets_c2"] and not report["audit_findings"]
                        and report["passthrough_mismatches"] == 0 and report["nondeterministic"] == 0
                        and set(report["serial_verdicts"]) == {"PASS"})
    return report


def generate(root):
    """C4, with no free input and no Docker.
    - Round R comes from the committed C2 commitment, and the randomness from the saved drand
      response for R.
    - The filter is the frozen one, serial equivalence. Its results were computed at C2, for
      every site, before R was known, and are bound by the C2 commitment. So the choice is
      deterministic, and nobody can claim a discard.
    - It refuses unless the bases still match C2 exactly, and if C4 has run before.
    - Whether the chosen mutant changes the command stream is recorded, not used.
    Nothing about the choice is printed; the record goes to <root>/private/c4_record.json."""
    c2 = committed("c2_commitment.json")
    if not verify_commitment(root, "c2", c2, exact=True):
        raise SystemExit("refusing: the sealed root differs from the C2 commitment")
    if (Path(root) / "private" / "c4_record.json").exists():
        raise SystemExit("refusing: C4 has already run for this sealed root")
    randomness, _ = beacon(root, c2["round"])
    sources = {b: (Path(root) / "heldout" / b / "service.py").read_text() for b in BASES}
    bound = committed_sites(root)
    sites = {b: [{k: v for k, v in s.items() if k not in FILTER_KEYS} for s in bound[b]]
             for b in BASES}
    for b in BASES:
        if sites[b] != find_sites(sources[b]):
            raise SystemExit(f"refusing: the committed sites of {b} are not its sites")
    flags = {(b, s["id"]): s for b in BASES for s in bound[b]}
    record = select(randomness, sites,
                    lambda base, site: flags[(base, site["id"])]["serially_equivalent"])
    for base, rec in record.items():
        if rec["chosen"] is None:
            shutil_rmtree(Path(root) / "heldout" / f"{base}_m")
        else:
            rec["chosen_changes_commands"] = flags[(base, rec["chosen"]["id"])]["changes_commands"]
            write_mutant(root, base, f"{base}_m", mutate(sources[base], rec["chosen"]))
    (Path(root) / "private" / "c4_record.json").write_text(json.dumps(
        {"round": c2["round"], "randomness": randomness, "record": record}, indent=1))
    return {b: r["chosen"] is not None for b, r in record.items()}


def mutant_spec(root, base, name):
    """The base's target spec, with the mutant as the variant under test, the base as the
    corrected variant, and the model view on the mutant."""
    target = json.loads((Path(root) / "heldout" / base / "target.json").read_text())
    target["target"] = name
    target["variants"] = {"buggy": f"heldout.{name}.service", "fixed": f"heldout.{base}.service"}
    target["model_view"] = {"files": {"service.py": f"heldout/{name}/service.py"}}
    return target


def write_mutant(root, base, name, source):
    dst = Path(root) / "heldout" / name
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "__init__.py").write_text("")
    (dst / "service.py").write_text(source)
    (dst / "target.json").write_text(json.dumps(mutant_spec(root, base, name), indent=1,
                                                sort_keys=True) + "\n")


def shutil_rmtree(path):
    import shutil
    if path.exists():
        shutil.rmtree(path)


def round_time(root, round_number):
    """When drand round R is scheduled: genesis + (R - 1) × period, from the chain's info
    response saved as <root>/private/drand_info.json (fetched with the owner's approval)."""
    info = json.loads((Path(root) / "private" / "drand_info.json").read_text())
    return info["genesis_time"] + (round_number - 1) * info["period"]


def write_committed_file(name, obj):
    SEALED.mkdir(exist_ok=True)
    (SEALED / name).write_text(json.dumps(obj, indent=1, sort_keys=True) + "\n")
    print(f"wrote {SEALED / name}; commit it")


def main():
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "sites":
        print(json.dumps(summary(find_sites(Path(args[1]).read_text())), indent=1))
    elif len(args) == 2 and args[0] == "check-bases":
        reports = {b: check_base(args[1], b) for b in BASES}
        private = Path(args[1]) / "private"
        private.mkdir(exist_ok=True)
        (private / "c2_check.json").write_text(json.dumps(reports, indent=1, default=str))
        print(json.dumps({b: {k: v for k, v in r.items() if k != "filtered_sites"}
                          for b, r in reports.items()}, indent=1, default=str))
        sys.exit(0 if all(r["passes"] for r in reports.values()) else 1)
    elif len(args) == 3 and args[0] == "commit-c2":
        root, round_number = args[1], int(args[2])
        check = json.loads((Path(root) / "private" / "c2_check.json").read_text())
        for b in BASES:
            source = (Path(root) / "heldout" / b / "service.py").read_text()
            if not check[b]["passes"] or \
                    check[b]["service_sha256"] != hashlib.sha256(source.encode()).hexdigest():
                sys.exit(f"refusing: {b} has no passing check-bases report for its current source")
        scheduled = round_time(root, round_number)
        if scheduled < time.time() + 6 * 3600:
            sys.exit(f"refusing: round {round_number} is scheduled less than 6 hours from now")
        sites = {b: check[b]["filtered_sites"] for b in BASES}
        write_committed_file("c2_commitment.json",
                             {**commit(root, "c2", BASES, sites), "round": round_number,
                              "round_scheduled_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                                   time.gmtime(scheduled))})
    elif len(args) == 2 and args[0] == "generate":
        print(json.dumps({"mutants_written": generate(args[1])}))  # which bases yielded one
    elif len(args) == 2 and args[0] == "commit-c4":
        c2 = committed("c2_commitment.json")
        names = BASES + tuple(f"{b}_m" for b in BASES if (Path(args[1]) / "heldout" / f"{b}_m").exists())
        _, response = beacon(args[1], c2["round"])
        write_committed_file(f"drand_round_{c2['round']}.json", response)
        write_committed_file("c4_commitment.json", commit(args[1], "c4", names))
    elif len(args) == 2 and args[0] == "verify":
        problems = verify_all(args[1])
        print(json.dumps({"problems": problems}, indent=1))
        sys.exit(1 if problems else 0)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
