# D1 baseline experiment: results (run 2026-10-29 at `c927e5c`)

**No model calls. $0 in API credits. Exploratory, development-only, n = 5 per method.**
Pre-registered in `PROTOCOL.md` (`c927e5c`) before any trial at seeds 1–5.

| What | Where |
|---|---|
| Run | `results/20261029-125353/` (manifest, trials, summary, pre-run reports); raw log in `runs/d1base-20261029-125353/` (git-ignored) |
| Validity | `check_validity.py`: **ALL PASS** (V1–V10) |
| Analysis | `analysis.json`, from `analyze.py` |
| Pre-run checks at `c927e5c` | `sandbox_check`: ALL PASS. `stall`: fixed build 0/1,200 inconclusive on the pair part, 1/4,000 on the random part; buggy build 0/5,200 |

## 1. Every method verified the lost update in every trial

E₁ is the number of search executions up to the first verified violation (M3+ profiling
included). Medians and Success@b are over 5 seeds.

| Method | E₁, seeds 1–5 | Median E₁ (range) | Success@10 | Success@30 | Success@300 | Median method-seconds | Median ms per execution |
|---|---|---|---|---|---|---|---|
| **M0** stress | 25, 6, 5, 7, 14 | **7** (5–25) | 3/5 | 5/5 | 5/5 | **0.052** | 6.9 |
| **M1** random | 122, 18, 141, 15, 14 | 18 (14–141) | 0/5 | 3/5 | 5/5 | 0.143 | 7.4 |
| **M3+** systematic | 23, 23, 23, 23, 23 | 23 (23–23) | 0/5 | 5/5 | 5/5 | 0.121 | 5.1 |

- **Wilson 95% intervals** for 5/5: 0.57–1.00; for 3/5: 0.23–0.88; for 0/5: 0.00–0.43.
  Five seeds cannot separate the methods statistically, and no test is claimed.
- **Witnesses.** Every witness is two `AddItem` calls for the same user. Each one:
  - replayed 20/20 with an identical trace hash;
  - passed every schedule on the #3825 build (exhaustive, 6 schedules), with no soundness
    problem.
- **Clean run:**
  - none of the 482 search executions was inconclusive (372 concurrent, plus M3+'s 110 serial
    profiles);
  - no verification needed a re-run;
  - no violation appeared on the corrected build;
  - no forced decision.
- **Cost:**
  - compute: at most $0.000012 per trial;
  - verification, not charged: 0.14–0.29 s per trial;
  - the whole run, 15 trials with bring-up, took 13 s of wall-clock.
- **Why M3+ is always 23.** Its 22 profiles of the empty state come first. The first
  contract-relevant pair it explores violates on its first schedule whatever the seed's order,
  so E₁ = 22 + 1 every time.
- **M0 in detail:**
  - 52 stress executions with 5 hits, a hit rate of 9.6%;
  - all 5 hits were the only 5 draws of two `AddItem` calls for one user: **every such draw
    lost an update in real timing**. The 5 same-user `AddItem` ∥ `EmptyCart` draws passed;
  - every hit reproduced on the first controlled schedule, so 1 exploration execution per
    trial.

## 2. Predictions (`PROTOCOL.md` §5)

| | Prediction | Outcome |
|---|---|---|
| P1 | All 15 verify within 1,000 | **Correct** |
| P2 | Median E₁: M3+ in 23–80, M1 in 10–100, M0 in 10–150 | **Wrong for M0** (7). Right for M1 (18) and M3+ (23) |
| P3 | M3+ has the lowest median E₁; M3+ and M1 within 2× on method-seconds | **Wrong**: stress (M0) is lowest on E₁ and on method-seconds. The 2× part is correct (0.121 s vs 0.143 s) |
| P4 | Every trial under 2 method-seconds | **Correct** (largest: M1 seed 3, 1.06 s) |
| P5 | No violation on the corrected build | **Correct** (V7) |
| P6 | Every median E₁ above 10, so the plan's "within a handful of executions" is false | **Wrong for M0.** Stress needed a median of 7 executions, which is a handful. M1 (18) and M3+ (23) needed more |
| P7 | Muse's break-even above 0.1 s in every scenario | **Correct** (§3) |

My seed-0 smoke (M0 77, M1 39, M3+ 23) misled P2, P3 and P6 for M0. One seed of a method whose
hit rate is about 10% says little.

## 3. Revised break-even (estimates: Muse has not run on D1)

t* is the per-execution cost at which Muse, finding the bug on its **first** execution, would
tie each baseline's median. L and C are the gate's two Muse scenarios, measured on D3.

| Muse scenario | vs M0 (E_b 7) | vs M1 (E_b 18) | vs M3+ (E_b 23) | Measured D1 seconds per execution |
|---|---|---|---|---|
| M4-like: 1 call, 12.6 s, $0.027 | **2.1 s** (in dollars: 407 s) | 0.74 s | 0.57 s | 0.005–0.008 |
| A2-like: 2 calls, 30.1 s, $0.054 | **5.0 s** | 1.77 s | 1.37 s | 0.005–0.008 |

- **Against the strongest conventional method, stress**, an execution would have to cost about
  300–720 times what it costs on D1 before Muse could tie, even at E₁ = 1.
- **On wall-clock alone:** stress reaches a verified bug in a median of 0.05 method-seconds;
  one Muse call takes about 12.6 s.

## 4. What this answers

1. **Cost on the real cart.** Every conventional method reaches a verified, replayable lost
   update in 5–141 executions and 0.03–1.06 method-seconds, for a negligible compute cost.
2. **Strongest method on D1: stress.** Plain stress testing finds it fastest. Its only hurdle is
   drawing two `AddItem` calls for one user (expected in 1 draw in 18; here 5 in 52). Real
   timing then loses the update every time, and the hit reproduces under control at once.
   Random search is weaker because it must also draw a bad interleaving (2 of the 8 schedules of
   such a pair). M3+ is deterministic here, at 23.
3. **Break-even.** It is now 0.57–5.0 s per execution, depending on the scenario and the
   baseline, against 5–8 ms measured. D1 cannot show execution-cost value for Muse.
4. **The plan's "within a handful of executions"** holds for stress, but not for random or
   systematic search.

**For the project:**
- **D1 is a confirmed "baselines win" case.** As pre-stated, it is the realism anchor and not a
  Muse comparison.
- **Stress was never run on D2 or D3.** It is "what practitioners do today" and a required method
  (`EVALUATION_PLAN.md` §3). On D3, M1 is censored at 1,000 executions in every pilot trial.
  Stress draws the same workloads, so it is likely to fail there as well (an untested
  prediction). The pilot's efficiency signal on D3 is against M1 and M3+ only.
- Running M0 on D2 and D3 is the cheapest way to complete the conventional baseline set there:
  no model, $0, minutes.

## 5. Limitations and observations

- **Not the demo exactly.** The cart has 1 CPU and no flagd or collector, and stress goes
  through the proxy in pass-through. Stress's hit rate depends on both: the gate's direct,
  no-proxy race lost 94% of fixed `AddItem` pairs.
- **n = 5 on one target, one machine.** #3824 is public. No discovery or memorization claim.
- **M3+arg (D-024) is not implemented.** M2 (PCT) did not run.
- **Residual harness events in the pre-run checks:**
  - one `unscheduled INFO` on the fixed build in 4,000 random executions. A command the cart's
    store client sent on its own during a round: possibly StackExchange.Redis's periodic
    configuration check, not verified. It is flagged and inconclusive, as it should be;
  - one cart pause longer than Δq in an earlier dev-tree check (`results/diagnostics/`).

  Neither occurred during the 15 trials.
- **The THREAT_MODEL §8 open items for no-model runs** are in `SECURITY_CHECK.md`:
  - NuGet packages not hash-locked;
  - Docker Desktop file sharing at its default;
  - no pre-commit secret hook;
  - no hang fixture end to end.
