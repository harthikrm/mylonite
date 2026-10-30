# Stress (M0) on D2 and D3: results (run 2026-10-30 at `1f7207b`)

**No model calls. $0 in API credits. Exploratory, development-only, n = 5 per target.**
Pre-registered in `PROTOCOL.md` (`1f7207b`) before any trial at seeds 1–5. The 10 trials took
2 min 6 s, verification included. The same-session re-run of the pilot followed.

| What | Where |
|---|---|
| Run | `results/20261030-175616/`; raw log in `runs/m0-20261030-175616/` (git-ignored) |
| Validity | `results/20261030-175616/validity.txt`: **9 of 10 pass; V9 fails on the letter** (§4) |
| Analysis | `analysis.json`, from `analyze.py` |
| Same-session reference | `results/20261030-175616/same_session_regression/`: the 30 pilot trials re-run, **identical in all 6,766 events** |

## 1. Results beside the pilot's methods

E₁ is the number of search executions up to the first verified violation; censored trials count
as 1,001.
- M1, M3+ and M4 are from the same-session regression. Their E₁ is identical to the pilot's.
- Method-seconds for M4 and A2 include their recorded model latency.

**D2** (lost award; 2 operations):

| Method | E₁, seeds 1–5 | Median E₁ | Success@10 | Median method-seconds |
|---|---|---|---|---|
| **M0 stress** (new) | 9, 5, 25, 32, 4 | 9 | 3/5 | 0.074 |
| M1 random | 9, 5, 7, 5, 1 | **5** | 5/5 | 0.048 |
| M3+ systematic | 8, 8, 8, 8, 8 | 8 | 5/5 | **0.044** |
| M4 Muse (recorded answers) | 1, 1, 1, 1, 1 | 1 | 5/5 | 14.1 |
| A2 Muse, no source (A2 run) | 1, 1, 1, 1, 1 | 1 | 5/5 | 16.3 |

**D3** (oversold stock after a restock and publish):

| Method | E₁, seeds 1–5 | Median E₁ | Success@1,000 | Median method-seconds to a verified bug |
|---|---|---|---|---|
| **M0 stress** (new) | censored ×5 | > 1,000 | 0/5 | none (8.2 s per 1,000 runs) |
| M1 random | censored ×5 | > 1,000 | 0/5 | none |
| M3+ systematic | 211, 246, 211, 211, 775 | **211** | 5/5 | **1.84** |
| M4 Muse (recorded answers) | 1, 1, 1, 1, 1 | 1 | 5/5 | 12.6 |
| A2 Muse, no source (A2 run) | 1, 1, 114, 71, 71 | 71 | 5/5 | 30.9 |

**Every M0 witness verified:**
- 20/20 replays with one trace hash;
- the corrected build exhaustive, every schedule PASS (6 for the 2-call witnesses, 2,520 for the
  4-call ones);
- no inconclusive execution among 5,075 search executions;
- no violation on any corrected build.

The 4-call witnesses took 24–31 s each to verify. Verification isn't charged to any method,
but a practitioner would pay for it.

## 2. Predictions (`PROTOCOL.md` §2)

| | Prediction | Outcome |
|---|---|---|
| P1 | D2: all 5 M0 trials verify | **Correct** |
| P2 | D2: M0 median E₁ in 2–15 | **Correct** (9) |
| P3 | D3: M0 censored in all 5 | **Correct.** 5,000 stress runs and no hit |
| P4 | No corrected-build violation; at most 1% inconclusive | **Correct** (0 and 0) |
| P5 | Same-session regression identical | **Correct** in content: 30/30, 6,766 events. V9 still fails on the letter (§4) |

## 3. What this shows

- **Stress is not uniformly strong.**
  - D1: 5 of 5 draws that could fail lost an update in real timing.
  - D2: 5 of 12 did. D2 is an in-process Python service with a synchronous store client.
  - D2's 4-call witnesses then needed up to 17 controlled schedules to reproduce.
  - So stress is the strongest conventional method on D1 (median 7), the weakest on D2 (median
    9, against 5 and 8), and fails on D3.
  - Why real timing hits less often on D2 is not measured. A **hypothesis**: thread start-up and
    the interpreter lock often let one call finish its `GET` and `SET` before the other's `GET`,
    while the cart's async path leaves a wider window.
- **D3's conclusion stands.** Stress draws the same workloads as random search and never reaches
  the precondition: the fixture's design gives about 1 chance in 116,000 per draw.
  - The strongest conventional method on D3 is still M3+.
  - The pilot's break-even stands, on same-session numbers. Muse ties M3+ at 60 ms per
    execution (M4) or 215 ms (A2), against 8.7 ms measured, a factor of 7–25.
  - Against stress or random search, the break-even is at most 12.6 ms (M4) or 32 ms (A2). These
    are upper bounds, because both are censored.
- **D2 is another "baselines win" case on wall-clock.**
  - Muse would tie the conventional methods at 1.8–4.1 s per execution.
  - Against the best of them on E₁ (M1, median 5), it would need 3.5–4.1 s.
  - The measured cost is 5.5–8.6 ms.
- **For the project:** the pilot's D3 efficiency signal was against M1 and M3+. It now holds
  against all three required conventional methods. On every development target, the
  conventional methods win on wall-clock. Muse's only advantage is execution count on D3, where
  a precondition is deep.

## 4. V9: failed on the letter, with its cause

- **The criterion.** The same-session regression must run at the run commit on a clean tree.
  Its record says `1f7207b… dirty`.
- **Cause: a defect in `run_m0.py`'s ordering.** It writes this run's own results directory
  (`results/20261030-175616/`, untracked) before it starts the regression. It then records
  `git status`, which counts those new files.
- **After the run:**
  - no tracked file differs from `1f7207b` (`git diff --name-only 1f7207b` is empty);
  - the only untracked files are that results directory's seven files;
  - nothing was edited during the run, which was a single command.
- **Consequences:**
  - The regression's content, 30/30 trials and 6,766 events identical, does not depend on this.
  - The run is not repeated, as the protocol requires.
  - The runner is left as it ran (its hash is in the manifest). The fix for future runners is to
    run the regression before writing results, and to record tracked-file changes separately
    from untracked outputs.

## 5. Limitations

- **Author-written fixtures,** whose bugs the author knows. Muse's view names their bug classes.
- **Real timing is not seeded,** so M0's E₁ would differ on a re-run. Its witnesses replay
  exactly.
- **n = 5 per target, one machine.** The 5/12 and 5/5 hit rates are small samples.
- **A2's method-seconds come from its own session** (2026-10-28). All other times are from this
  session.
