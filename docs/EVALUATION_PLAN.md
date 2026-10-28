# Evaluation Plan

Status: **Approved design (2026-10-28, D-014 amended by D-018), not yet frozen.** It is
pre-registered in two steps:
1. The **pilot** (§9) runs on development targets on Oct 29 and may change budgets, domain sizes,
   and trial counts, which are recorded under "Deviations".
2. After the pilot, this file is frozen by commit **before** any held-out run. Later changes go in
   the dated "Deviations" section and are never edited silently.

## 1. Questions

**RQ1 (central, worded as in the team handoff).** Can Meta Muse, using repository context and
execution feedback, find real concurrency failures more efficiently than random or systematic
exploration, under comparable execution budgets and the same correctness contracts?

**RQ2.** Where does any difference come from: the workload (operations, arguments, setup) or the
schedule hint?

**RQ3.** Does any advantage survive when model latency and cost are counted?

**RQ4.** Is every reported failure real? This covers reproduction reliability, correct and
weak-contract controls, and corrected versions.

**RQ5.** Does Muse reduce the human effort of writing the target spec? Measured as the fraction
of drafted catalog entries and contract clauses accepted unchanged, and the edits needed.

A negative answer to RQ1 is a valid result and will be reported as one.

## 2. Definitions

- **Execution:** one run of a workload under one schedule, including reset, setup, the concurrent
  round, and observation.
- **Search executions:** concurrent executions plus any profiling or setup-exploration runs a
  method itself requests. This is the budget unit.
- **Oracle executions:** serial-reference runs (§6.3 of `ARCHITECTURE.md`). They are computed by
  the same code for every method and **reported separately**, not charged to the search budget.
- **Violation:** verdict `VIOLATION(clause)` against the target's owner-approved contract.
  `OBSERVATION` verdicts are reported but never counted as bugs.
- **Verified violation:** replays **20/20** from fresh resets with identical trace hashes, and,
  where a corrected version exists, the **same workload explored exhaustively** on it produces no
  violation. Anything below 20/20 is "reproducible k/20" and is not counted as verified.
- **Distinct bug:** for benchmark targets, attributed by fix toggles: the violation disappears
  when only that bug's fix is applied. For real-world targets, attributed by violated clause plus
  root-cause line, judged by two team members independently before they see which method found
  it.
- **Budget:** `B_exec` search executions per trial, plus a wall-clock cap per trial that
  includes model latency. Both values are set by the pilot. Starting values: `B_exec = 300`,
  15 minutes.
- **Trial:** one independent search by one method on one target with its own seed. For Muse,
  this means a fresh planning session.

## 3. Methods compared

All methods share the catalog, value domains, contract, executor, proxy, oracle, and accounting.
Only workload choice and scheduling policy vary.

| ID | Method | Workload choice | Schedule | Status |
|---|---|---|---|---|
| M0 | **Stress** | Random over catalog × domains | Real concurrency; the proxy records the command order it saw so that a hit can be replayed | Required. What practitioners do today. |
| M1 | **Random** | Random | `random(seed)` | Required |
| M3+ | **Conflict-directed systematic, with greybox setup search** | Profile each operation through the proxy to get per-key read/write sets; grow setup sequences that reach new keys or commands; enumerate conflicting pairs and triples with colliding arguments | `exhaustive` | Required. **The strongest non-LLM baseline.** |
| M4 | **Muse** | Model proposals with feedback; no failing schedules or traces from other methods ever in the prompt | `hint → exhaustive` | Required |
| A2 | Muse without source | Catalog and domains only | `hint → exhaustive` | Required. Is reading code what helps? |
| M2 | PCT | Random | `pct(seed, d=2,3)` | If time allows |
| A1 | Muse workloads, random schedules | Model | `random(seed)` | If time allows (RQ2) |
| A4 | Muse ranks M3+ candidates | M3+ | `exhaustive` | If time allows |

**Fairness rules.**
1. Value domains are identical for all methods and pre-registered per target in its spec (sizes
   included). For third-party targets they come from the target's own fixtures or load
   generator. For our services they are written with the service, before any method runs.
2. Muse sees no information the baselines are denied, except source code; A2 removes that.
3. The same seed list is used for every method. 20 trials for **every** method.
4. Prompt audit: the evaluation harness asserts that no prompt contains a recorded failing
   decision list, trace, or held-out source.
5. Hint `command` enums are generated per target from the commands seen while running each
   catalog operation once, alone, in pass-through. They are never taken from a search run or a
   failing trace. (The Oct 28 tracer took them from its witness; changed for the pilot.)
6. Planner input hygiene: source files are presented under neutral paths, and no prompt carries
   words that label the target as a test case or its variant (`buggy`, `fixed`, `fixture`,
   `mutant`, fixture IDs). The prompt audit (rule 4) checks for these words too.

## 4. Targets

### 4.1 Development set (used to build, tune, and pilot; reported but never used for generalization claims)

| ID | Target | Contract source | Bug |
|---|---|---|---|
| D2 | Python counter fixture (redis-py, per-connection) | Fixture spec: "every successful increment is counted" | `GET` then `SET` lost update. Corrected: `INCR`. |
| D3 | Python precondition fixture (≥ 8 operations) | Fixture spec | Check-then-act that needs a specific setup state |
| D4 | Node fixture (ioredis, multiplexed) | Fixture spec | Lost update over one shared connection |
| D1 | **OTel Demo cart, built from source at tag `3.1.0`**, scenario A | Issue #3824 and the `AddItem` API meaning (quantity is added) | Concurrent `AddItem` lost update. Corrected: cart built with PR #3825's cart changes. Public bug, possibly memorized: never a discovery claim. |
| D-ctl | Correct and weak-contract variants of D2–D4 | Fixture spec | None; must PASS |

### 4.2 Held-out set (sealed; the only source of effectiveness claims)

- **Size:** 6 buggy services, 2 correct controls, 1 weak-contract control (for example,
  documented last-writer-wins, which must PASS), and 1 equivalent mutant (for example, a `WATCH`
  transaction replaced by a Lua script).
- **Preferred sources:** real before/after Redis race fixes from open-source history (Q-E3),
  wrapped in a minimal service. Otherwise, services written for the purpose.
- **Author:** not the prompt author. If the team is one person, a sealed-seed mutation script is
  applied to correct base services written **before** any prompt work. The seed is revealed only
  at evaluation time.
- **Timing:** sealed by Oct 31, 23:59 ET at the latest. Its SHA-256 is committed before the
  first held-out run; it is published only after the evaluation.
- **Composition rules, fixed now:**
  - Python and Node services; at least 2 use a multiplexed client.
  - At least half have ≥ 8 catalog operations.
  - At least half need a semantic precondition reached through setup.
  - At least a third are shallow: any two writers on the same key trigger them. These are the
    cases where we expect baselines to tie or win.
  - Comments stripped, neutral identifiers, no issue numbers, no READMEs.
- **Mutation operators** (store-level):
  1. Replace an atomic command with read-then-write.
  2. Remove `WATCH` or watch the wrong key.
  3. Split a `MULTI/EXEC` or Lua script.
  4. Move a check outside the atomic section.
  5. Release a lock with an unconditional `DEL`.
  6. Write a state transition before its guard.

### 4.3 Real-world stretch (P1)

| ID | Target | Status |
|---|---|---|
| R1 | OTel scenario B: `PlaceOrder` vs `AddItem` | About 12 containers, valid payment/address/product arguments. The clearest test of the precondition hypothesis. Time-boxed to 4 hours. |
| R2 | A second open-source Redis race | Found during Q-E3 search. |

## 5. Contamination and bias controls

| Risk | Control |
|---|---|
| Muse memorized #3824 | D1 is development only. **Memorization probe:** ask Muse, with no code, what concurrency bug the OTel demo cart has, and record the answer. Catalog names (`CartService/AddItem`) cannot be obfuscated, so A3-style renaming is not used on D1. |
| Prompt tuned to the test set | Prompt and schemas frozen Oct 31, 23:59 ET; SHA-256 recorded in every result file. Held-out results with any other hash are discarded. |
| Held-out leakage | Sealed archive outside the repository; hash committed first; prompt audit (fairness rule 4). |
| Labels in planner input | Fairness rules 5 and 6. Found in the Oct 28 tracer: a "buggy variant" docstring (removed before the call), a `fixtures/dev/` path, and a witness-derived command enum. |
| Confirmation bias | Verdicts come from the contract oracle and replay only; distinct bugs come from fix toggles. |
| Benchmarks that favor the model | Composition rules fixed above before authoring, including the mandatory shallow third. All targets reported. |
| Cherry-picking | Every trial logged; the analysis script is committed before the held-out run. |

## 6. Metrics

Co-primary:
1. **E₁:** search executions to the first verified violation, right-censored at `B_exec`.
2. **Cost to first verified violation:** wall-clock time (including model latency) and dollars
   (tokens at list price plus container-seconds at a fixed nominal rate).

Secondary:
3. Success@B: fraction of trials with a verified violation within budget.
4. Oracle executions, reported per method.
5. Distinct verified bugs over all trials.
6. Reproduction rate (k/20) and fraction of executions with `forced` decisions.
7. **False-positive rate:** verified violations on correct controls, weak-contract controls,
   equivalent mutants, and corrected versions. Any non-zero value blocks claims until explained.
8. Plan validity: first-try and after one repair.
9. Hint adherence.
10. RQ5: draft acceptance rate for catalog entries and contract clauses.
11. Explanation reference accuracy.

## 7. Analysis (pre-registered)

- Per target: Wilson 95% intervals for success rates; median E₁ with bootstrap 95% intervals
  (10,000 resamples); survival curves.
- M4 vs each required baseline per target: Mann–Whitney U on E₁ (censored values = `B_exec` + 1),
  Vargha–Delaney Â₁₂ (≥ 0.71 = large). Holm correction across the 6 held-out buggy targets.
- Summary: targets where M4 is better, tied, or worse than M3+, separately for the shallow and
  precondition subsets, on both co-primary metrics.
- Development and held-out results are never pooled.

## 8. Independent verification of each reported failure

1. Replay 20/20 with identical trace hashes from fresh resets.
2. Recompute the oracle from scratch.
3. Corrected version: exhaustive exploration of the same workload must PASS.
4. For D1, additionally show that the same requests issued serially through the API give the
   contract-expected quantity.
5. Publish the replay file and pinned build so others can re-run it.

## 9. Pilot value checkpoint (Oct 29)

- Targets D2 and D3. Methods M1, M3+, M4. 5 trials each.
- Purpose: measure execution time, model latency, and tokens; calibrate `B_exec` and the
  wall-clock cap; and give the owner an early look at whether M4 is competitive at all.
- **Owner decision after the pilot:** continue as planned, re-scope, or re-frame the claim (for
  example, toward RQ5 and verified reproduction). The pilot cannot produce effectiveness claims.

## 10. Expected results (written before running)

- Shallow targets, including D1: M1 and M3+ find the bug within a handful of executions. M4 ties
  on executions and loses on cost.
- Precondition targets: M4 beats M1. Against M3+ it is uncertain, and this is the comparison that
  decides RQ1.
- Schedule hints: little effect.
- Controls: no verified violations.
- RQ5: plausible drafting value, unmeasured so far.

## 11. Stop/go gates

| Gate | When | Go if | Otherwise |
|---|---|---|---|
| T0 | Oct 28 | Tracer bullet on D2 end to end: controlled reproduction 20/20, corrected version PASS, one Muse call validated and executed, costs recorded. | Name the blocker; fix before anything else. |
| P1 | Oct 29 EOD | Pilot complete; owner decision recorded. | Owner decides scope and claim. |
| K | **Oct 30 EOD (kill gate)** | D1 verified on the real cart; #3825-patched cart PASSES under exhaustive exploration of the same workload. | If the proxy fails on the multiplexed client: Fallback A for fixtures, D1 by stress with a measured rate, and the claim narrows. |
| F | Oct 31, 23:59 ET | Prompt and schema frozen; held-out sealed; pre-registration frozen. | Reduce Muse's role to A4 and freeze that instead. |
| G3 | Nov 2, 12:00 ET | Held-out evaluation complete for the required methods. | Report what completed, with trial counts stated. |

## 12. Budget

- **Model:** the owner-approved cap is **≈ $100** of the $150 credit (A8). Estimate:
  10 held-out targets × 20 trials × ≤ 5 calls × ≈ $0.063 ≈ $63 for M4, plus ≈ $25 for A2,
  plus ≈ $10 for the pilot, spec drafting, and the demo. Re-estimated after Day 1 token
  measurement. The orchestrator stops at the cap.
- **Executions:** measured on Day 1; the plan is re-budgeted if one execution takes more than
  0.5 s.

## Deviations

None yet.
