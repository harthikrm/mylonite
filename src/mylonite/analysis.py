"""Pre-registered analysis for held-out targets (docs/FREEZE.md §4; EVALUATION_PLAN.md §6–§7).
Standard library only.

Every rule that decides a comparison is code here, frozen with the methods: failures and
censoring, ties, errored and missing trials, pairing, the stronger-baseline rule (D-034, extended
to every conventional baseline), multiplicity, and break-even. Lower is better for every metric.

Pairing: M4 and A2 have no seed, and every other method draws from its own seed stream
(``M0:<seed>``, ``M1:<seed>``, ``M3+:<seed>``). A Muse trial and a baseline trial with the same
seed number share no randomness, so every Muse comparison is between independent samples. Only
M3+ and M3+arg share a stream; their seed-by-seed differences are reported (``paired``), and the
intersection–union rule below is valid however the two comparisons are correlated.
"""

import collections
import itertools
import math
import random

ALPHA = 0.05
BOOTSTRAP_RESAMPLES = 10_000
Z95 = 1.959963984540054
MUSE = ("M4", "A2")
CONVENTIONAL = ("M0", "M1", "M3+", "M3+arg")
GROUPS = {"conventional": CONVENTIONAL, "systematic": ("M3+", "M3+arg"), "M0": ("M0",),
          "M1": ("M1",)}
CONFIRMATORY = ("conventional", "systematic")  # the others are secondary
METRICS = ("e1", "seconds", "dollars")
MAX_ERROR_FRACTION = 0.10
MAX_INCONCLUSIVE_FRACTION = 0.01
FAIL = math.inf


# --- trials ---------------------------------------------------------------------------------------

def is_error(trial):
    return trial["status"].startswith("error")


def spent(trial, metric):
    """What the trial had used, for one metric, when it stopped."""
    if metric == "e1":
        return trial["e1_executions"] if trial["status"] == "verified" else trial["executions"]
    if metric == "seconds":
        return trial["method_s"]
    if metric == "dollars":
        return trial["model_usd"] + trial["compute_usd"]
    raise ValueError(metric)


def outcome(trial, metric):
    """("found", cost), ("failed", None) or ("censored", cost spent).
    - found: a verified violation, at this cost;
    - failed: the method's own plan ran out (it would never find it); the time budget ran out,
      which is a failure within the budget every method shares (900 method-seconds); or a Muse
      trial errored;
    - censored: the execution budget ran out, so its cost to find in seconds or dollars is
      unknown and above what it had spent.
    None for a trial left out: an errored baseline trial, or one not run. Any other status is
    refused."""
    status = trial["status"]
    if status == "verified":
        return "found", spent(trial, metric)
    if status in ("search_plan_exhausted", "censored:time"):
        return "failed", None
    if status == "censored:executions":
        return "censored", spent(trial, metric)
    if is_error(trial):
        return ("failed", None) if trial["method"] in MUSE else None
    if status == "not_run":
        return None
    raise ValueError(f"unknown trial status: {status!r}")


def value(trial, metric, budget):
    """A trial's own value, for medians and success counts: its cost if found, otherwise a
    failure (B_exec + 1 executions, infinite seconds and dollars)."""
    got = outcome(trial, metric)
    if got is not None and got[0] == "found":
        return got[1]
    return budget + 1 if metric == "e1" else FAIL


def attempts(trials):
    """One record per (target, method, seed). The crash rule (HELDOUT_PROTOCOL.md C5) allows a
    second attempt only after an error. Muse uses its first attempt, so an error is a failure
    and never a fresh draw; a baseline, whose seed fixes its search, uses the second. Anything
    else is refused."""
    by_key = collections.defaultdict(list)
    for trial in trials:
        by_key[(trial["target"], trial["method"], trial["seed"])].append(trial)
    chosen = []
    for key, runs in by_key.items():
        if len(runs) > 2 or (len(runs) == 2 and not is_error(runs[0])):
            raise ValueError(f"{key}: {len(runs)} attempts; a re-run is allowed only after an error")
        chosen.append(runs[0] if key[1] in MUSE else runs[-1])
    return chosen


def require_complete(trials, targets, methods, seeds):
    """Every (target, method, seed) must have a record, a ``not_run`` one included."""
    have = {(t["target"], t["method"], t["seed"]) for t in trials}
    missing = [k for k in itertools.product(targets, methods, seeds) if k not in have]
    if missing:
        raise ValueError(f"missing trials: {missing[:10]}{' …' if len(missing) > 10 else ''}")


def outcomes_of(trials, target, method, metric):
    """(outcomes, left_out) for one method on one target."""
    got, left_out = [], 0
    for trial in trials:
        if trial["target"] == target and trial["method"] == method:
            o = outcome(trial, metric)
            if o is None:
                left_out += 1
            else:
                got.append(o)
    return got, left_out


def comparable(x, y):
    """Two groups' outcomes on a common scale. Both are truncated at τ, the smallest cost spent
    by any trial censored at the execution budget, in either group: beyond τ nothing is known
    for that trial, so every cost above τ, and every non-finding, ranks as one tied failure.
    For E₁ every such trial stopped at B_exec, so τ = B_exec and nothing changes. Seconds and
    dollars are where it matters: a baseline censored at 1,000 cheap executions stopped long
    before a Muse trial could, and a Muse success that costs more than that is not counted as
    better."""
    tau = min((c for kind, c in x + y if kind == "censored"), default=FAIL)

    def score(o):
        kind, c = o
        return c if kind == "found" and c <= tau else FAIL
    return [score(o) for o in x], [score(o) for o in y], tau


# --- statistics -------------------------------------------------------------------------------

def midranks(values):
    """Ranks 1..n; tied values share the mean of their ranks."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks, i = [0.0] * len(values), 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def mann_whitney(x, y):
    """Exact two-sided p-value of the Wilcoxon–Mann–Whitney test, conditional on ties: the share
    of all ways of choosing len(x) of the pooled values whose mid-rank sum S lies at least as far
    from its mean E as the observed one (|S − E| ≥ |s − E|). No normal approximation and no Monte
    Carlo. Doubled mid-ranks are integers, so the comparison is exact."""
    n, pooled = len(x), list(x) + list(y)
    size = len(pooled)
    if n == 0 or n == size:
        return 1.0
    doubled = [round(2 * r) for r in midranks(pooled)]
    observed, center, total = sum(doubled[:n]), n * (size + 1), sum(doubled)
    counts = [[0] * (total + 1) for _ in range(n + 1)]  # counts[k][s]: k-subsets with sum s
    counts[0][0] = 1
    for d in doubled:
        for k in range(n, 0, -1):
            row, prev = counts[k], counts[k - 1]
            for s in range(total, d - 1, -1):
                if prev[s - d]:
                    row[s] += prev[s - d]
    extreme = abs(observed - center)
    hits = sum(c for s, c in enumerate(counts[n]) if c and abs(s - center) >= extreme)
    return hits / math.comb(size, n)


def a12(x, y):
    """Vargha–Delaney Â₁₂ for lower-is-better values: P(x < y) + P(x = y) / 2. Above 0.5 favors
    x; ties count one half."""
    wins = sum((a < b) + 0.5 * (a == b) for a in x for b in y)
    return wins / (len(x) * len(y))


def holm(pvalues):
    """Holm-adjusted p-values, in the input order."""
    m = len(pvalues)
    adjusted, running = [0.0] * m, 0.0
    for rank, i in enumerate(sorted(range(m), key=lambda i: pvalues[i])):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


def wilson(k, n, z=Z95):
    if n == 0:
        return 0.0, 1.0
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def median(values):
    """The ⌈n/2⌉-th smallest value. With every failure at one point (B_exec + 1, or infinity)
    this is the Kaplan–Meier median, and it is always an observed value, never the average of a
    success and a failure. It is a failure value ("not reached") when more than half of the
    trials failed; with exactly half, it is the largest success."""
    return sorted(values)[(len(values) - 1) // 2]


def bootstrap_median_ci(values, label):
    """Percentile bootstrap, 95%, with a fixed seed per label so the interval is reproducible."""
    rng, n = random.Random(f"bootstrap:{label}"), len(values)
    meds = sorted(median([values[rng.randrange(n)] for _ in range(n)])
                  for _ in range(BOOTSTRAP_RESAMPLES))
    return meds[int(0.025 * BOOTSTRAP_RESAMPLES)], meds[int(0.975 * BOOTSTRAP_RESAMPLES) - 1]


# --- comparisons -------------------------------------------------------------------------------

def compare_two(trials, target, metric, first, second):
    """One method against another on one target and metric, or None if either has no trials."""
    x, left_x = outcomes_of(trials, target, first, metric)
    y, left_y = outcomes_of(trials, target, second, metric)
    if not x or not y:
        return None
    sx, sy, tau = comparable(x, y)
    return {"p": mann_whitney(sx, sy), "a12": a12(sx, sy), "n": [len(x), len(y)],
            "left_out": [left_x, left_y], "truncated_at": tau}


def compare(trials, target, metric, muse="M4"):
    """The Muse condition against each conventional baseline that ran on this target."""
    out = {}
    for baseline in CONVENTIONAL:
        result = compare_two(trials, target, metric, muse, baseline)
        if result is not None:
            out[baseline] = result
    return out


def group_p(per_baseline, members):
    """Intersection–union. Muse is better than a group only if it is better than every member,
    so the group's p-value for "better" is the largest member's, and 1 unless every member's
    Â₁₂ favors Muse. "Worse" needs one member only: the smallest p-value among the members Muse
    loses to. That is liberal, deliberately, and it works against Muse. None if a member did not
    run (the cell is "not tested")."""
    if any(b not in per_baseline for b in members):
        return None
    stats = [per_baseline[b] for b in members]
    better = max(s["p"] for s in stats) if all(s["a12"] > 0.5 for s in stats) else 1.0
    losing = [s["p"] for s in stats if s["a12"] < 0.5]
    return better, (min(losing) if losing else 1.0)


def classify(raw):
    """``raw``: {cell: (p_better, p_worse) or None}. Holm across the tested cells, separately for
    "better" and "worse". A cell is "better", "worse", "no significant difference" (not a claim
    of equivalence) or "not tested"."""
    tested = sorted(k for k, v in raw.items() if v is not None)
    better = holm([raw[k][0] for k in tested])
    worse = holm([raw[k][1] for k in tested])
    out = {k: {"verdict": "not tested"} for k, v in raw.items() if v is None}
    for k, hb, hw in zip(tested, better, worse):
        out[k] = {"verdict": "better" if hb <= ALPHA else "worse" if hw <= ALPHA
                  else "no significant difference",
                  "p_better": raw[k][0], "p_better_holm": hb, "p_worse": raw[k][1],
                  "p_worse_holm": hw}
    return out


def verdicts(cells):
    """``cells``: {(target, metric): compare(...)}. For each group, Holm runs across every
    tested cell (each held-out buggy target × each co-primary metric)."""
    out = {}
    for group, members in GROUPS.items():
        raw = {k: group_p(per_baseline, members) for k, per_baseline in cells.items()}
        for (target, metric), result in classify(raw).items():
            out[f"{group}|{target}|{metric}"] = result | {"confirmatory": group in CONFIRMATORY}
    return out


def condition_verdicts(trials, targets):
    """M4 against A2 (does reading the source help? RQ2; secondary). Errors count as failures
    for both, since both are Muse conditions."""
    raw = {}
    for target in targets:
        for metric in METRICS:
            r = compare_two(trials, target, metric, "M4", "A2")
            raw[(target, metric)] = None if r is None else (
                r["p"] if r["a12"] > 0.5 else 1.0, r["p"] if r["a12"] < 0.5 else 1.0)
    return {f"M4 vs A2|{t}|{m}": v for (t, m), v in classify(raw).items()}


def paired(trials, target, budget, a="M3+", b="M3+arg"):
    """Seed-by-seed E₁ of two methods that share a seed stream (descriptive; no test)."""
    by = {(t["method"], t["seed"]): t for t in trials
          if t["target"] == target and outcome(t, "e1") is not None}
    seeds = sorted({s for m, s in by if m == a} & {s for m, s in by if m == b})
    rows = [(s, value(by[(a, s)], "e1", budget), value(by[(b, s)], "e1", budget)) for s in seeds]
    return {"seeds": len(rows), "differ": sum(x != y for _, x, y in rows),
            f"{b}_lower": sum(y < x for _, x, y in rows), f"{a}_lower": sum(x < y for _, x, y in rows),
            "rows": rows}


def false_positives(trials, controls):
    """On a correct base nothing may violate the contract. Counts every VIOLATION a base gave:
    in a control trial's scheduled executions, its stress runs (M0) and its serial profiles (M3+
    stops with an error on one), and on the corrected variant while a mutant's witness was
    verified. Also the control hits that replayed every time: a base has no corrected variant,
    so no hit there is ever "verified"."""
    rows = [t for t in trials if t["target"] in controls]
    counters = [t.get("counters", {}) for t in rows]
    checks = [v for t in trials for v in [t.get("verification")] +
              [u["verification"] for u in t.get("unverified_violations", [])] if v]
    out = {"scheduled": sum(c.get("VIOLATION", 0) for c in counters),
           "stress": sum(c.get("stress_VIOLATION", 0) for c in counters),
           "profile": sum("a serial run violated the contract" in t["status"] for t in rows),
           "corrected_variant": sum((v.get("corrected") or {}).get("verdicts", {}).get("VIOLATION", 0)
                                    for v in checks),
           "replaying_on_controls": sum(u["verification"]["replay_violations"]
                                        == u["verification"]["replays"]
                                        for t in rows for u in t.get("unverified_violations", [])),
           "control_trials": len(rows)}
    out["total"] = out["scheduled"] + out["stress"] + out["profile"] + out["corrected_variant"]
    return out


# --- break-even ---------------------------------------------------------------------------------

def cost_lines(trials, target, method, unit, price):
    """Each trial's cost to its first verified violation as a function of the cost per execution
    c: a line (slope, intercept) in c, or None for infinite.
    - found: E·c plus its other cost (seconds: method seconds minus execution seconds; dollars:
      model dollars as compute-seconds at the nominal price);
    - a baseline stopped by either budget: the lower bound (executions + 1)·c plus what it had
      spent, so a baseline is never made to look slower than it is;
    - anything else (a plan run out, a Muse trial stopped by a budget, a Muse error): infinite."""
    lines = []
    for trial in trials:
        if trial["target"] != target or trial["method"] != method:
            continue
        o = outcome(trial, "e1")
        if o is None:
            continue
        other = (trial["method_s"] - trial["exec_s"] if unit == "seconds"
                 else trial["model_usd"] / price)
        if o[0] == "found":
            lines.append((o[1], other))
        elif trial["status"].startswith("censored") and method not in MUSE:
            lines.append((trial["executions"] + 1, other))
        else:
            lines.append(None)
    return lines


def median_at(lines, c):
    return median([FAIL if l is None else l[0] * c + l[1] for l in lines])


def break_even(trials, target, muse, baseline, price=None, unit="seconds"):
    """Where the Muse condition's median cost to the first verified violation falls below the
    baseline's, as the cost per execution c varies. Medians of lines are piecewise linear, so
    the answer is exact at the lines' crossing points.
    - "breaks_even": Muse is cheaper for every c above ``c``, and not cheaper just below it;
    - "always": cheaper at every c ≥ 0;
    - "never": not cheaper for large c (whatever happens at small c);
    - "undetermined": both medians are infinite for large c."""
    m = cost_lines(trials, target, muse, unit, price)
    b = cost_lines(trials, target, baseline, unit, price)
    if not m or not b:
        return {"status": "undetermined"}
    finite = [l for l in m + b if l is not None]
    points = sorted({(q[1] - p[1]) / (p[0] - q[0]) for p, q in itertools.combinations(finite, 2)
                     if p[0] != q[0] and (q[1] - p[1]) / (p[0] - q[0]) > 0})
    big = 2 * (points[-1] if points else 1.0) + 1.0
    if median_at(m, big) == FAIL:
        return {"status": "undetermined" if median_at(b, big) == FAIL else "never"}
    if not median_at(m, big) < median_at(b, big):
        return {"status": "never"}
    edges = [0.0] + points  # interval i is [edges[i], edges[i + 1]); the last one is unbounded
    probes = [(lo + hi) / 2 for lo, hi in zip(edges, edges[1:])] + [big]
    losing = [i for i, p in enumerate(probes) if not median_at(m, p) < median_at(b, p)]
    if losing:
        return {"status": "breaks_even", "c": edges[losing[-1] + 1]}
    if median_at(m, 0.0) < median_at(b, 0.0):
        return {"status": "always", "c": 0.0}
    return {"status": "breaks_even", "c": 0.0}


SEVERITY = {"always": 0, "breaks_even": 1, "undetermined": 2, "never": 3}


def least_favorable(results):
    """Of several break-evens, the one least favorable to Muse: "never", then "undetermined",
    then the largest crossing cost. None if there is nothing to compare."""
    return max(results, key=lambda r: (SEVERITY[r["status"]], r.get("c") or 0.0), default=None)


def crossing(e_m, l_m, e_b, l_b):
    """The same question for medians given directly (scenario estimates, where Muse has not
    run): where E_m·c + L_m = E_b·c + L_b. Muse is cheaper above c* = (L_m − L_b) / (E_b − E_m)
    when E_b > E_m; otherwise never, unless both E are equal and Muse's overhead is smaller."""
    if e_b > e_m:
        c = (l_m - l_b) / (e_b - e_m)
        return ("always", 0.0) if c <= 0 else ("breaks_even", c)
    return ("always", 0.0) if e_b == e_m and l_m < l_b else ("never", None)


def per_execution_seconds(trials, target):
    """The target's measured cost of one execution, shared by every method: the median over
    trials of execution seconds per execution."""
    rates = [t["exec_s"] / t["executions"] for t in trials
             if t["target"] == target and outcome(t, "e1") is not None and t["executions"]]
    return median(rates) if rates else None


# --- the whole report ---------------------------------------------------------------------------

def error_flags(trials, target):
    """Methods whose share of errored trials on this target is over MAX_ERROR_FRACTION, or whose
    executions were more than 1% INCONCLUSIVE. Flagged, never excluded: verdicts are still
    computed, with Muse errors as failures."""
    out = []
    for method in sorted({t["method"] for t in trials if t["target"] == target}):
        mine = [t for t in trials if t["target"] == target and t["method"] == method]
        executions = sum(t.get("executions", 0) for t in mine)
        inconclusive = sum(t.get("counters", {}).get("INCONCLUSIVE", 0) for t in mine)
        if sum(map(is_error, mine)) > MAX_ERROR_FRACTION * len(mine):
            out.append(f"{method}: errors")
        if executions and inconclusive > MAX_INCONCLUSIVE_FRACTION * executions:
            out.append(f"{method}: inconclusive")
    return out


def analyze(trials, cfg, buggy_targets, control_targets=(), muse_conditions=("M4", "A2")):
    """Everything §7 reports. ``buggy_targets`` are the held-out mutants that C6 shows to be
    buggy; ``control_targets`` are the bases."""
    budget, price = cfg["budget"]["executions"], cfg["prices"]["compute_per_second"]
    if isinstance(cfg["methods"], dict):
        require_complete(trials, buggy_targets, cfg["methods"]["buggy"], cfg["seeds"])
        require_complete(trials, control_targets, cfg["methods"]["negative_controls"], cfg["seeds"])
    else:
        require_complete(trials, buggy_targets, cfg["methods"], cfg["seeds"])
    trials = attempts(trials)
    cut = {t["target"] for t in trials if t["status"] == "not_run" and t["method"] in CONVENTIONAL}
    trials = [t for t in trials if t["status"] != "not_run"]
    report = {"targets": {}, "verdicts": {}, "comparisons": {},
              "conventional_trials_cut": sorted(cut),
              "flags": {t: error_flags(trials, t) for t in buggy_targets},
              "false_positives": false_positives(trials, set(control_targets))}
    for muse in muse_conditions:
        cells = {(target, metric): {} if target in cut else compare(trials, target, metric, muse)
                 for target in buggy_targets for metric in METRICS}  # a cut baseline: not tested
        report["verdicts"][muse] = verdicts(cells)
        report["comparisons"][muse] = {f"{t}|{m}": c for (t, m), c in cells.items()}
    if set(MUSE) <= set(muse_conditions):
        report["verdicts"]["M4 vs A2"] = condition_verdicts(trials, buggy_targets)
    for target in buggy_targets:
        present = sorted({t["method"] for t in trials if t["target"] == target})
        row = {"per_execution_s": per_execution_seconds(trials, target), "methods": {}}
        for method in present:
            mine = [t for t in trials if t["target"] == target and t["method"] == method
                    and outcome(t, "e1") is not None]
            e1 = [value(t, "e1", budget) for t in mine]
            row["methods"][method] = {
                "trials": len(e1), "verified": sum(v <= budget for v in e1),
                "median_e1": median(e1) if e1 else None,
                "median_e1_ci": bootstrap_median_ci(e1, f"{target}:{method}:e1") if e1 else None,
                "success_at": {b: {"k": sum(v <= b for v in e1), "n": len(e1),
                                   "wilson": wilson(sum(v <= b for v in e1), len(e1))}
                               for b in cfg["report_success_at"]}}
        for muse in muse_conditions:
            if muse not in present:
                continue
            for unit in ("seconds", "dollars"):
                each = {b: break_even(trials, target, muse, b, price, unit)
                        for b in CONVENTIONAL if b in present}
                row.setdefault("break_even", {}).setdefault(muse, {})[unit] = {
                    "each": each,
                    "systematic": least_favorable([each[b] for b in GROUPS["systematic"] if b in each]),
                    "conventional": least_favorable(list(each.values()))}
        if {"M3+", "M3+arg"} <= set(present):
            row["m3plus_vs_m3plus_arg"] = paired(trials, target, budget)
        report["targets"][target] = row
    return report
