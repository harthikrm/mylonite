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
  Workloads with more than 5,000 schedules on the corrected version are checked on the first
  5,000 depth-first schedules plus 2,000 random ones and reported as **verified (bounded)**
  (`methods.verify`). Verification runs are never charged to a method.
- **Distinct bug:** for benchmark targets, attributed by fix toggles: the violation disappears
  when only that bug's fix is applied. For real-world targets, attributed by violated clause plus
  root-cause line, judged by two team members independently before they see which method found
  it.
- **Budget:** `B_exec` search executions per trial, plus a cap on **method seconds** per trial,
  plus a cap of `K` schedules per explored workload (M3+ pairs, M4 experiments). Pilot values:
  `B_exec = 1000`, 900 s, `K = 50` (`experiments/2026-10-29-pilot/config.json`). Success is
  also reported at 100 and 300 executions, read off E₁. The plan's starting value was 300; it
  was raised before any run on D3 because breadth-first M3+ cannot reach D3's precondition
  within 300 (D-023).
- **Method seconds:** trial wall-clock time minus harness overhead (process and container round
  trips, measured per request as round trip minus the executor's own timing) and minus
  verification. Model latency and the method's own computation are included.
- **Trial:** one independent search by one method on one target with its own seed. For Muse,
  this means a fresh planning session.

## 3. Methods compared

All methods share the catalog, value domains, contract, executor, proxy, oracle, and accounting.
Only workload choice and scheduling policy vary.

| ID | Method | Workload choice | Schedule | Status |
|---|---|---|---|---|
| M0 | **Stress** | Random over catalog × domains | Real concurrency; the proxy records the command order it saw so that a hit can be replayed | Required. What practitioners do today. |
| M1 | **Random** | Per execution: 0–6 setup calls and 2–4 concurrent calls, lengths uniform, each call's operation and arguments uniform | `random(seed)` | Required |
| M3+ | **Conflict-directed systematic, with greybox setup search** | Breadth-first over setup states. At each state, profile every catalog call alone through the proxy (one execution each) to get its command sequence with key digests. A call whose behavior (operation, command names, outcome) is new and which leads to a new store-state digest extends the frontier (≤ 6 setup calls). Then every pair of calls whose profiles admit an unserializable interleaving (`methods.unserializable_pair`: the two-transaction conflict-cycle condition) is explored. Pairs with a conflict on a key read by the contract's observation are explored first, one per command signature; the rest are deferred until the frontier is exhausted, never dropped (`methods.pair_priority`, D-023). Seeds only shuffle call and pair order. Pairs only; triples are not implemented. Novelty ignores argument values, so M3+ builds one state per new behavior (for example, a single restock quantity) | `exhaustive`, ≤ `K` per pair | Required. **The strongest non-LLM baseline.** |
| M3+arg | **M3+, argument-aware** (post-pilot addition) | As M3+, with M3+'s seed stream, until its frontier is exhausted. Then, ahead of its other deferred pairs, the pairs it deferred only because they share a command signature with a pair it explored at the same state: the same calls with other argument values (`methods.run_m3plus_arg`, D-024, D-033) | `exhaustive`, ≤ `K` per pair | Run beside M3+ on held-out targets, never instead of it. Both are reported |
| M4 | **Muse** | Up to 5 planning rounds per trial. Each round makes one call returning ≤ 3 experiments; each valid experiment runs hint-first, then depth-first. A hint lists store commands in the order they should run; an operation's earlier, unlisted commands run as needed to reach the listed one (`scheduler.HintPolicy`). The next round's request adds feedback on the model's own experiments only (`planner.feedback_entry`: workload, schedules explored, outcome, command names and observations of the first schedule) | `hint → exhaustive`, ≤ `K` per experiment | Required |
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
5. The hint `command` enum is the proxy's full gated-command vocabulary
   (`resp.HINT_VOCABULARY`), identical for every target. It never comes from a search run or a
   trace. (The Oct 28 tracer took it from its witness; replaced.)
6. **Model view.** The model sees only what `planner.build_request` assembles:
   - catalog, domains, limits and observation;
   - the contract's correctness conditions, without provenance fields;
   - the files declared under `model_view`, shown under their declared display names, with
     comments and every bare string statement removed (`planner.model_view_source`);
   - feedback on its own experiments.

   `audit.assert_clean` runs on every request before it is sent. It checks three things:
   - no search artifacts (schedule labels, digests, verdict words, result keys);
   - no test-case labels, harness paths or fixture IDs in target-dependent text;
   - no identifier or line that exists only in the corrected variant.

   `tests/test_contamination.py` checks the flow itself:
   - changing anything outside the view leaves the request byte-for-byte unchanged, and changing
     anything inside it does not;
   - only the declared files are read;
   - every detector fires on a planted positive;
   - a contaminated request is refused before any model call.
7. **Shared space and accounting.** Every method builds workloads from `space.py` (same
   catalog, domains, limits, validator). Every execution, including M3+ profiling, goes through
   `methods.Trial`, which counts it against the same `B_exec` and method-seconds cap. M3+ pairs
   and M4 experiments share the per-workload cap `K`. The contract is checked by the same oracle
   on every execution.
8. Every method's first violation goes through the same `methods.verify`. Verification runs are
   not charged and are reported separately.

## 4. Targets

### 4.1 Development set (used to build, tune, and pilot; reported but never used for generalization claims)

| ID | Target | Contract source | Bug |
|---|---|---|---|
| D2 | Python counter fixture (redis-py, per-connection) | "A member's balance equals the sum of the points of all successful award calls for that member." | `GET` then `SET` lost update. Corrected: `INCRBY`. |
| D3 | Python inventory fixture (8 operations, 24 calls; `fixtures/dev/d3_inventory/DESIGN.md`) | "A product's stock, as returned by stock(sku), is never negative." | Check-then-act in `purchase` (`GET` stock → compare → `DECRBY`). Reachable only after `create`, `restock`, `publish`; then two purchases that each fit and together exceed the stock. Corrected: check and decrement in one `EVAL`. Validated without search in `experiments/2026-10-28-d3-fixture/`. |
| D4 | Node fixture (ioredis, multiplexed) | Fixture spec | Lost update over one shared connection |
| D1 | **OTel Demo cart, built from source at tag `3.1.0`**, scenario A | Issue #3824 and the `AddItem` API meaning (quantity is added) | Concurrent `AddItem` lost update. Corrected: cart built with PR #3825's cart changes. Public bug, possibly memorized: never a discovery claim. |
| D-ctl | Correct and weak-contract variants of D2–D4 | Fixture spec | None; must PASS |

### 4.2 Held-out set (sealed; the only source of effectiveness claims)

- **Size:** 6 buggy services, 2 correct controls, 1 weak-contract control (for example,
  documented last-writer-wins, which must PASS), and 1 equivalent mutant (for example, a `WATCH`
  transaction replaced by a Lua script).
- **Preferred sources:** real before/after Redis race fixes from open-source history (Q-E3),
  wrapped in a minimal service. Otherwise, services written for the purpose.
- **Author:** not the prompt author. If the team is one person: `docs/HELDOUT_PROTOCOL.md`
  (proposed, D-020). In short:
  - base services are written after the method freeze;
  - bugs are injected mechanically at sites chosen by a public randomness beacon;
  - evaluation is blind and automated;
  - every target is reported.
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
| Prompt tuned to the test set | Prompt, schemas and method code frozen before any held-out code exists (`HELDOUT_PROTOCOL.md` C1). The prompt fingerprint **and the SHA-256 of every file under `src/`** are recorded in every result manifest. Held-out results with any other hashes are discarded. |
| Author priors in the instructions | `planner.HYPOTHESIS_KINDS` names `lost_update` and `check_then_act`, which are exactly D2's and D3's bug classes and the classes the held-out mutation operators produce. It is the same for every target, but it is the author's prior. Disclosed; A2 does not remove it. |
| Held-out leakage | Sealed archive outside the repository; hash committed first; prompt audit (fairness rule 4). |
| Labels and answers in planner input | Fairness rules 5–6. All three leaks found in the Oct 28 tracer are closed:<br>• the "buggy variant" docstring (bare strings are now removed);<br>• the `fixtures/dev/` path (display names now);<br>• the witness-derived command enum (target-independent now).<br>The noninterference tests also found that later bare strings in a function survived the first normalizer; fixed. |
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

- Targets D2 and D3. Methods M1, M3+, M4. 5 trials each (seeds 1–5). Pre-registered config:
  `experiments/2026-10-29-pilot/config.json`. Readiness review and pass/fail criteria:
  `experiments/2026-10-29-pilot/READINESS.md`.
- Purpose: measure execution time, model latency, and tokens; calibrate `B_exec` and the
  wall-clock cap; and give the owner an early look at whether M4 is competitive at all.
- **Owner decision after the pilot:** continue as planned, re-scope, or re-frame the claim (for
  example, toward RQ5 and verified reproduction). The pilot cannot produce effectiveness claims.

## 10. Expected results (written before running)

- Shallow targets, including D1: M1 and M3+ find the bug within a handful of executions. M4 ties
  on executions and loses on cost.
- D3, M1: censored in every trial. Computed before running: ≈ 2.6 × 10⁻⁶ per execution, about
  0.08% chance within 300 (`experiments/2026-10-28-d3-fixture/`).
- D3, M3+: an independent reviewer's in-memory emulation of the executor (not the real system)
  predicts the following:
  - Before D-023, censored at 300 in 20/20 seeds, finding it at 421–791 executions.
  - With contract-directed priority, 16/20 found within 300, at 161–285.
  - Expected verified in most or all trials within 1,000.

  On D3 the question is how M4 compares with M3+ on executions and on cost. M1 tells us little
  there.
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

None yet (nothing has been frozen).

### Pre-pilot amendments (2026-10-28, before any method ran on D3)

- Fairness rules 5–8 rewritten or added. M1, M3+ and M4 specified as implemented.
- Budget: per-workload cap `K` and method seconds defined. Verification (bounded) defined.
- D2's contract statement reworded to state the property rather than the failure ("no award may
  be lost under concurrency"); its clause was renamed `balance_matches_awards`. Same oracle, same
  semantics.
- D3 defined and validated. The M1 prediction was recorded.
- The held-out author rule points to the sole-developer protocol (proposed).
- After an independent pre-pilot review (`experiments/2026-10-29-pilot/READINESS.md` §4):
  - M3+ got contract-directed pair priority (D-023), a disclosed change that strengthens the
    baseline;
  - `B_exec` went from 300 to 1,000, with Success@100/300/1,000;
  - hint semantics are fixed (steps were silently skipped);
  - model-written text is no longer echoed in feedback;
  - any error ends only its own trial;
  - there is a model retry rule;
  - non-smoke runs are refused on a dirty tree;
  - commands the proxy does not schedule are flagged as soundness problems.

### D1 baseline amendments (2026-10-29, before any D1 trial at seeds 1–5)

- **M0 as implemented** (D-031). Stress runs M1's draw without schedule control. A hit is
  reproduced by depth-first exploration under the scheduler, and every execution counts. This
  replaces "replay the command order the proxy saw", which a multiplexed client makes
  impossible to attribute.
- **D1's concurrent size is 2 for every method** (D-029). A target spec may lower the shared
  maximum, never raise it.
- **Verification re-runs an inconclusive execution**, at most `inconclusive_reruns` times
  (D-030; D1: 2). A completed run with the wrong verdict or trace is never re-run. §8's "20/20"
  counts completed replays. Re-runs are reported.

### Post-pilot amendment (2026-10-31, before the method freeze)

- **M3+arg is added as a conventional baseline** (D-024 accepted 2026-10-28; implemented in
  D-033). It runs beside M3+ on held-out targets, and both are reported. M3+ is unchanged: the
  pilot's 30 trials still reproduce event for event.
- How M3+arg enters §7's comparisons (for example, against the better of M3+ and M3+arg per
  target) is fixed at the freeze, not here.
