# D1 baseline experiment (pre-registered 2026-10-29, before any D1 trial at seeds 1–5)

**No model calls. Exploratory, development-only.** One real-world target, three conventional
methods, 5 seeds each. Approved by the owner on 2026-10-29, together with the D1 contract (D-029).
Nothing here compares Muse with anything: Muse does not run.

The gate (`../2026-10-28-d1-gate/`), the pilot (`ecf37d9`) and A2 (`aa1f4eb`, `e136f20`) are not
changed, apart from an erratum section added to the gate report (§8).

## 1. Questions

1. On the real cart, how many executions, method-seconds and dollars do strong conventional
   methods need to reach a **verified** lost update? (E₁ distribution, Success@b, cost.)
2. Which conventional method is strongest on D1, on each co-primary metric?
3. With measured E₁ in place of the gate's seed-0 values, what per-execution cost would Muse have
   to beat on D1 (break-even, D-026)? These remain estimates: Muse does not run.
4. Is the plan's own prediction right that baselines find shallow bugs "within a handful of
   executions" (`EVALUATION_PLAN.md` §10)?

## 2. What changed since the gate, and why (all before any trial at seeds 1–5)

| Change | Why | Evidence |
|---|---|---|
| **The D1 contract is approved** (D-029) | Owner, 2026-10-29 | `targets/d1-otel-cart/target.json` |
| **Exactly 2 concurrent calls on D1, for every method** (D-029) | With 3 or more, two operations can queue behind one transaction on the multiplexed client and cannot be attributed on the corrected build, so a witness could not be verified (gate report §7, item 2). The bug needs only 2 | `space.max_concurrent`; tests |
| **Resume attribution is decided when the next command arrives** (D-030) | The gate's 1.7% fixed-build stall was a harness race, not CPU starvation: an operation that had finished in the cart, but whose reply had not reached the harness, was taken as blocked, and the other operation's retry was credited to it | `results/diagnostics/`: 17/1,200 inconclusive before, 0/1,200 after, same session; a unit test reproduces the race |
| **Verification re-runs an inconclusive execution, at most twice** (D-030) | A residual cart pause longer than Δq (1 in 4,000 random fixed-build executions; cause untested) forces a decision, which is correctly inconclusive, and would make a correct witness fail verification by chance. A run that completes with the wrong verdict or trace is never re-run | `methods.verify`; tests. The pilot config sets no re-runs, and all 30 pilot trials re-run identically |
| **M0 (stress) is implemented** (D-031) | Required by the plan, never built. §3 | `methods.run_m0`, `executor.stress_once`; tests |
| **THREAT_MODEL §8 items for no-model third-party runs are checked** (D-032) | The gate ran the cart before this was done | `SECURITY_CHECK.md`, `sandbox_check.py` |

## 3. Methods (all share D1's catalog, domains, limits, contract, oracle, budget and verification)

| ID | Workload choice | Schedule | Notes |
|---|---|---|---|
| **M0** stress | M1's draw (seeded `M0:<seed>`) | None: the 2 calls start together and run in real time, proxy in pass-through | On a hit, the same workload is explored depth-first under the scheduler, up to `K` = 50 schedules, and the first controlled violation goes to verification. **Deviation from the plan's M0 row**: the plan replays the command order the proxy saw, but on a multiplexed client that order cannot be attributed to operations. Every stress and exploration execution counts toward E₁ |
| **M1** random | 0–6 setup calls, exactly 2 concurrent calls, uniform | `random(seed)` | As in the pilot, with D1's size limit |
| **M3+** conflict-directed systematic | Greybox breadth-first setup search; pairs that can interleave unserializably, contract-relevant first (D-023) | Exhaustive per pair, ≤ `K` | As in the pilot. Pairs only, which matches D1's size limit |

**Not run:** M3+arg (D-024, not implemented), M2 (PCT), and every Muse condition.

## 4. Fixed settings (`config.json`)

- **Seeds** 1–5. Seed 0 was used by the gate and by the smoke run, and is excluded.
- **Budgets:** `B_exec` 1,000, 900 method-seconds, `K` = 50. Success is reported at 10, 30, 100,
  300 and 1,000.
- **Verification**, not charged:
  - 20 replays;
  - the corrected build explored exhaustively (cap 5,000, then 2,000 bounded random);
  - inconclusive executions re-run at most twice.
- **Executor:** Δq 300 ms, round timeout 10 s. Prices are the pilot's.
- **One bring-up for all 15 trials:**
  - Valkey, the executor with the proxy, and both cart builds, warmed up as in the gate;
  - every execution starts from `FLUSHALL`;
  - order: for each seed, M0, then M1, then M3+.
- **Code:** run at the commit that adds this protocol, or a later one that changes only
  documentation; `run_d1.py` refuses a dirty tree. The images are the gate's (`build.json`).
- **Pre-run checks at the same commit** (`sandbox_check.py`; `stall.py` with 1,200 pair and
  4,000 random executions per build). Their reports are copied into the results directory.

## 5. Predictions (written before any trial at seeds 1–5)

The smoke run at seed 0, with the final code, gave E₁ = 77 (M0), 39 (M1) and 23 (M3+). The
gate's seed-0 trials gave 30 (M1, with sizes 2–4) and 23 (M3+).

- **P1.** All 15 trials verify within 1,000 executions.
- **P2.** Median E₁: M3+ between 23 and 80; M1 between 10 and 100; M0 between 10 and 150.
- **P3.** M3+ has the lowest median E₁. On method-seconds, M3+ and M1 are within a factor of 2 of
  each other.
- **P4.** Every trial reaches a verified violation in under 2 method-seconds.
- **P5.** No violation on the corrected build anywhere, including in failed verifications.
- **P6.** The plan's "within a handful of executions" is false for D1 if "handful" means 10 or
  fewer: every method's median E₁ is above 10.
- **P7.** Muse's break-even per-execution cost on D1 stays above 0.1 s in every scenario, 14 or
  more times D1's measured cost.

These are exploratory predictions, not hypotheses with decision rules. n = 5 per method, and the
analysis is descriptive.

## 6. Validity criteria (`check_validity.py`, written with this protocol)

- **V1.** The manifest's commit is the run commit, the tree was clean, and `config.json` matches
  the committed file. The images match `build.json` and the gate's executor image.
- **V2.** Exactly 15 trials, one per method and seed. No `error:` status.
- **V3.** Every verified trial:
  - 20/20 replays violate, with identical trace hashes;
  - the corrected build was explored exhaustively;
  - every corrected schedule passed, with no soundness problem.
- **V4.** Every search execution, including stress runs, is a valid D1 workload
  (`space.workload_problems` is empty), so exactly 2 concurrent calls.
- **V5.** Budgets: at most 1,000 executions per trial. A censored trial is censored exactly at
  the budget.
- **V6.** E₁ recomputed from the raw log equals the trial's E₁. The verification that ended the
  trial is the first verified one.
- **V7.** No corrected-build execution in any verification, verified or not, reported a violation.
- **V8. Harness health.**
  - At most 1% of each method's search executions are inconclusive.
  - Every verification re-run is listed, with its cause.
- **V9. Pre-run checks:**
  - `sandbox_check` ALL PASS at the run commit;
  - `stall` at the run commit: 0 inconclusive in the pair part, at most 0.1% in the random part,
    and 0 unstable schedules.
- **V10.** The pilot and A2 directories, the gate's results and the target's build files are
  byte-identical to `20f1666`.

Any failed criterion is reported with the results. The run is not repeated silently. A re-run
needs a recorded reason, and both runs are reported.

## 7. Analyses (no further method runs)

- **Per method:**
  - the raw E₁ values, their median (censored = 1,001), min–max and Success@b, with Wilson 95%
    intervals;
  - method-seconds;
  - compute dollars (no model dollars exist).
- **M0 only:**
  - the stress hit rate (hits / stress executions);
  - how often a hit reproduced under the scheduler;
  - stress versus exploration executions.
- **Break-even** (`analyze.py`):
  - t* = L / (E_b − E_m), with each method's measured median E_b and its measured seconds per
    execution;
  - E_m = 1, with the gate's two latency scenarios (M4-like 12.6 s per call; A2-like 30 s over
    2 calls) and the dollar version;
  - labeled as estimates.
- **The plan's §10 prediction**, checked against P6.

## 8. Known limitations (stated before the run)

- **The cart has 1 CPU** (the demo sets no CPU limit), and there is no flagd or collector.
- **Stress runs through the proxy in pass-through**, not directly against Valkey (the gate's
  `natural.py` did that), so every method sees the same network path.
- **#3824 is public.** This experiment makes no discovery claim of any kind.
- **Single target, 5 seeds, one machine**, with about ±25% machine noise between sessions.
- **The gate report's errata** (added with this protocol): the executor container has two
  read-only host mounts (`src`, `fixtures`), contrary to "no host mounts" in its §4. The stall
  hypothesis in its §7 was wrong (D-030).
