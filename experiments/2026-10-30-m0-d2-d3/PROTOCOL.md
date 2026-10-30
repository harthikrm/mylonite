# Stress (M0) on D2 and D3 (pre-registered 2026-10-30, before any M0 trial at seeds 1–5)

**No model calls. Exploratory, development-only.** Approved by the owner on 2026-10-30:
"pre-register and run M0 stress on D2 and D3, seeds 1-5, no model calls, same rules as the
pilot."

**Why.** M0 is a required method ("what practitioners do today", `EVALUATION_PLAN.md` §3) that
the pilot never ran. On D1 it was the strongest conventional method
(`../2026-10-29-d1-baselines/RESULTS.md`). The pilot's D2 and D3 comparisons, and the D3
break-even (about 60 ms per execution for M4, 215 ms for A2, against M3+), rest on M1 and M3+
only.

The pilot, A2, the D1 gate and the D1 baselines are not changed (V10).

## 1. Same rules as the pilot

| Setting | Here | Pilot |
|---|---|---|
| Targets | D2 (`d2_counter`), D3 (`d3_inventory`), unchanged since the pilot | Same files (V10) |
| Seeds | 1–5 | 1–5 |
| `B_exec`, method-seconds, `K` | 1,000; 900; 50 | Same |
| Verification | 20 replays; corrected build exhaustive, cap 5,000, then 2,000 bounded random; **no inconclusive re-runs** | Same (D-030's re-runs are D1 only) |
| Executor | Δq 300 ms, round timeout 10 s; image `sha256:fc531f25…` | Same image |
| Space | setup ≤ 6, 2–4 concurrent calls | Same |
| Order | one sandbox per target; seeds in order | Same |

**M0** is `methods.run_m0` as used on D1 (D-031):
- M1's workload draw, seeded `M0:<seed>`, one uncontrolled execution each;
- on a hit, depth-first exploration of that workload under the scheduler, up to `K`, then the
  shared verification;
- every execution counts.

D2 and D3 are in-process Python services with one store connection per operation.

**Same-session timing reference.** After the M0 trials, `regression.py` re-runs all 30 pilot
trials: M1, M3+, and M4 from the recorded answers (no API call). They must be identical to the
pilot event for event (V9). Their method-seconds are the reference for comparing M0's
method-seconds, because machine noise between sessions is about ±25%.

**Smoke run (seed 0, budget 200; not data):**
- D2: verified at E₁ = 11 (one stress hit in 9; the witness has 4 concurrent calls; corrected
  build 2,520/2,520 PASS);
- D3: 200 stress runs, all PASS, censored;
- no inconclusive execution.

## 2. Predictions (written before any trial at seeds 1–5)

Pilot E₁:
- D2: M1 9, 5, 7, 5, 1 (median 5); M3+ 8 on every seed; M4 1.
- D3: M1 censored 5/5; M3+ 211, 246, 211, 211, 775; M4 1.

- **P1 (D2).** All 5 M0 trials verify within 1,000 executions.
- **P2 (D2).** M0's median E₁ is between 2 and 15. Basis:
  - about 31% of M1-style draws contain two `award`s for one member (exact: (2/16 + 5/16 + 8/16)/3
    over 2, 3 and 4 concurrent calls);
  - real timing loses an update in some fraction of those;
  - the seed-0 smoke gave 11.
- **P3 (D3).** M0 is censored at 1,000 in all 5 trials. Basis: the D3 fixture's exact
  probability that a draw *can* reach the failure is 8.6 × 10⁻⁶. Even if real timing always hit,
  P(any of 5,000 draws succeeds) ≈ 4%.
- **P4.** No violation on any corrected build. At most 1% of search executions are
  inconclusive.
- **P5.** The same-session regression is identical in all 30 trials.

**Interpretation rules, fixed now:**
- **If P3 holds,** the strongest conventional method on D3 is still M3+. The pilot's D3
  break-even stands, recomputed on same-session numbers.
- **If M0 verifies on D3 in any trial,** the D3 design's precondition model is wrong. That is
  investigated before any conclusion, and the break-even is recomputed against M0.
- **On D2,** the strongest conventional method is whichever has the lowest median E₁ among M0,
  M1 and M3+. Ties are reported as ties.

## 3. Validity criteria (`check_validity.py`, written with this protocol)

- **V1.** The manifest's commit is the run commit, on a clean tree. `config.json` matches the
  committed file. The executor and Valkey images are the pilot's.
- **V2.** Exactly 10 trials: M0 × 2 targets × seeds 1–5. No `error:` status.
- **V3.** Every verified trial:
  - 20/20 replays violate, with one trace hash;
  - the corrected build's mode is recorded;
  - every corrected schedule passed, with no soundness problem.
- **V4.** Every search execution is a valid workload for its target (`space.workload_problems`).
- **V5.** At most 1,000 executions per trial. A censored trial is censored exactly at the
  budget, or at the method-seconds cap.
- **V6.** E₁ recomputed from the raw log equals the trial's. Logged executions add up to the
  trial's count.
- **V7.** No corrected-build execution in any verification reported a violation.
- **V8.** At most 1% of search executions are inconclusive, per target.
- **V9.** The same-session regression ran at the run commit, on a clean tree: 30/30 identical
  trials and event streams, 0 differences.
- **V10.** Unchanged since `c301ecf`:
  - the pilot, A2, D1 gate and D1 baseline directories, and `fixtures/`;
  - `fixtures/` also has no change since the pilot's commit `db1f84f`.

A failed criterion is reported with the results. The run is not repeated silently.

## 4. Analyses (`analyze.py`, written with this protocol; no further method runs)

- **Per target, M0:**
  - E₁ values, median (censored = 1,001), Success@10, @30, @100, @300 and @1,000 with Wilson
    95% intervals, and method-seconds;
  - stress hit rate, hits that did not reproduce under the scheduler, exploration executions.
- **Per target, all methods side by side:**
  - M0 (this run);
  - M1, M3+ and M4 (same-session regression, whose E₁ equals the pilot's by V9);
  - A2 (A2's recorded trials; different session).
  - Median method-seconds from the same session where available.
- **Break-even per execution** against each conventional method's median E₁, with
  t* = L / (E_b − E_m), where L and E_m are each Muse condition's recorded median model seconds
  and median E₁ (M4 from the pilot, A2 from the A2 run).
  - For a censored baseline, E_b ≥ 1,001, so t* is an upper bound and reported as "≤".
  - These are recorded Muse numbers, not new ones. They are compared with each method's measured
    seconds per execution.
- **Which conventional method is strongest** per target, on median E₁ and on median method-seconds to a verified violation (censored trials count as the method-seconds cap + 1, as E₁ counts censored trials as `B_exec` + 1).

## 5. Known limitations

- D2 and D3 are author-written fixtures. Their bugs are known to the author, and Muse's view
  names the bug classes (`HYPOTHESIS_KINDS`).
- Real timing is not seeded, so M0 trials are not exactly reproducible. Their witnesses are,
  through verification.
- n = 5 per target, one machine.
