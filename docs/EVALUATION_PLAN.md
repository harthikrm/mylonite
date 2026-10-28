# Evaluation Plan

Status: **Pre-registration draft (Phase 0).** Once the team approves it, this file is frozen by
commit before any held-out run. Later changes go in a dated "Deviations" section at the end and
are never edited silently.

## 1. Questions

**RQ1 (central).** Under equal budgets and the same oracle, does Muse-guided workload selection
reach a first *verified* non-serializable outcome in fewer executions than (a) uncontrolled
stress, (b) random workloads with random or PCT scheduling, and (c) conflict-directed systematic
search?

**RQ2.** Where does any difference come from: the workload (operations, arguments, setup) or the
schedule hint?

**RQ3.** Does the advantage, if any, survive when model latency and cost are counted?

**RQ4.** Is every reported failure real? This covers reproduction reliability and the
false-positive rate on correct services.

**RQ5.** Do results on held-out, never-published bugs match results on the development set,
including the public bug OTel #3824?

The hypotheses we expect to **fail** are written down too (§9). A negative result for RQ1 is a
valid outcome and will be reported as one.

## 2. Definitions

- **Execution:** one run of a workload under one schedule, including reset, setup, the concurrent
  round, and observation. Serial-reference runs used by the oracle **count** toward the budget.
  Replay-verification runs do not count, but are reported separately.
- **Violation:** oracle verdict `VIOLATION` (`ARCHITECTURE.md` §6).
- **Verified violation:** a violation whose recorded schedule reproduces in ≥ 19 of 20 replays in
  fresh environments. For benchmark targets with ground truth it must also **not** occur on the
  fixed variant under the same workload and schedule.
- **Distinct bug:** a verified violation is attributed to injected bug *b* if it disappears when
  only *b*'s fix is applied. For real-world targets, distinct bugs are distinguished by root
  cause, judged by two team members independently before seeing which strategy found them.
- **Budget:** `B_exec = 300` executions per trial (tentative; recalibrated on the dev set before
  freezing). A secondary wall-clock cap of 15 minutes per trial includes model latency.
- **Trial:** one independent search run of one strategy on one target with its own seed. For
  Muse this means a fresh planning session.

## 3. Methods compared

All methods share the catalog, value domains, executor, proxy, oracle, and budget accounting
(`ARCHITECTURE.md` §7). Only workload choice and scheduling policy vary.

| ID | Method | Workload choice | Schedule | Notes |
|---|---|---|---|---|
| M0 | **Stress** | Random over catalog × domains | None (pass-through, real concurrency) | What practitioners do today. Measures natural reproduction rate. |
| M1 | **Random** | Random | `random(seed)` | Strong naive baseline (Thomson et al.: 43/49 SCTBench bugs). |
| M2 | **PCT** | Random | `pct(seed, d=2)` and `d=3` | Probabilistic guarantee for shallow bugs. |
| M3 | **Conflict-directed systematic** | Profile each operation alone with sampled args → per-key read/write sets → enumerate pairs and triples with write-write or read-write conflicts on the same key, with colliding arguments | `exhaustive` per workload | **Strongest non-LLM baseline.** No model, language-agnostic, close in spirit to ACIDRain's 2AD. |
| M4 | **Muse** | Model proposals with feedback | `hint → exhaustive` | The system under evaluation. |
| A1 | Muse workloads, random schedules | Model | `random(seed)` | Isolates the schedule hint (RQ2). |
| A2 | Muse, no source code | Model sees catalog and domains only | `hint → exhaustive` | Is reading code what helps? |
| A3 | Muse, obfuscated source | Identifiers renamed, comments stripped | `hint → exhaustive` | Sensitivity to names, comments, and memorized issue text. |
| A4 | Muse, M3 workloads | M3's conflict candidates, re-ranked by the model | `exhaustive` | Model as a ranker on top of the baseline (cheaper use of the model). |

If time allows, POS or SURW is added as an extra scheduling policy for M1. The literature reports
both beat PCT on standard suites, but our workloads are small enough that `exhaustive` usually
dominates.

**Fairness rules.**
1. Value domains are identical for all methods. They come from the target spec, not from the
   model. Example values are harvested from the target's own fixtures or load generator
   (for OTel: its Locust load generator), as a careful engineer would do.
2. The model sees no information baselines are denied except source code, and A2 removes that.
3. M3's profiling executions count against its budget.
4. Every method uses the same random seeds list. M3 and the exhaustive enumerator randomize their
   enumeration order by seed, so they also produce distributions.

## 4. Targets

### 4.1 Development set (used to build and tune; results reported but never used for claims of generalization)

| ID | Target | Bug | Why |
|---|---|---|---|
| D1 | OTel Demo cart, tag `3.1.0`, scenario A | Concurrent `AddItem` lost update (#3824) | Real, unfixed, any-language service. **Public since 2026-08-10, so the model may have seen it.** |
| D2–D4 | Three small fixture services we write (Python + redis-py; one Node + ioredis for a multiplexed client) | Lost update via `GET/SET`; check-then-act on a stock counter; non-atomic two-key transfer | Exercise per-connection and multiplexed clients; tune the pipeline |
| D5 | Correct variants of D2–D4 | None | False-positive check during development |

### 4.2 Held-out set (sealed; used for claims)

- **Size:** 8 buggy services + 4 correct controls + 2 *equivalent mutants* (code changes that look
  like bugs but are still serializable, for example replacing a `WATCH/MULTI` transaction with a
  Lua script). The size is set by authoring time; at least 6 buggy services is the minimum to
  report anything.
- **Author:** a team member who does **not** write or tune prompts. If the team is one person,
  the held-out set is produced by a mutation script applied to correct services with a sealed
  seed. The operators are listed below, and the seed is revealed only at evaluation time.
- **Timing:** authored after the prompt freeze (Oct 31, 23:59 ET) or, if authored earlier, kept
  sealed from the prompt author. The SHA-256 of the sealed archive is committed before the first
  held-out run.
- **Composition rules, fixed now:**
  - Services in Python (redis-py) and Node (ioredis), at least 3 in Node.
  - **At least half** have ≥ 8 catalog operations. Real services have many endpoints; a tiny API
    favors random search.
  - **At least half** of the bugs require a semantic precondition reached through setup, for
    example a coupon that exists and is active, stock exactly 1, or an order in state `PAID`.
  - **At least a quarter** are shallow: any two writers on the same key trigger them. These are
    the cases where we expect baselines to tie or win.
  - Comments stripped; identifiers neutral (no `race`, `unsafe`, `todo`, `lock_bug`); no issue
    numbers; READMEs omitted.
- **Mutation operators** (store-level analogues of concurrency mutation operators):
  1. Replace an atomic command (`INCRBY`, `HINCRBY`, `SET NX`, `GETDEL`) with read-then-write.
  2. Remove `WATCH` or watch the wrong key.
  3. Split a `MULTI/EXEC` or Lua script into separate commands.
  4. Move a precondition check outside the atomic section (check-then-act).
  5. Replace a token-checked lock release with an unconditional `DEL`.
  6. Reorder a state-transition write before its guard.

### 4.3 Real-world stretch (P1)

| ID | Target | Status |
|---|---|---|
| R1 | OTel Demo scenario B: `PlaceOrder` vs `AddItem` (item neither ordered nor left in cart) | Needs ~12 containers and valid payment, address, and product arguments. This is the clearest test of the precondition hypothesis. P1. |
| R2 | A second open-source service with a Redis read-modify-write race | To be found on Day 1–2 (`OPEN_QUESTIONS.md` Q-E3). Prefer an issue filed after the model's training cutoff, which is unknown. |

## 5. Contamination and bias controls

| Risk | Control |
|---|---|
| The model memorized #3824 (public issue with root cause and fix PR) | D1 is **development only**. Report A3 (obfuscated) on D1. Never claim "discovery" on D1; claim reproduction and verification. |
| Prompt tuned to the test set | Prompt and planner schema frozen Oct 31, 23:59 ET; their SHA-256 is recorded in every result file. Held-out results produced with any other hash are discarded. |
| Held-out bugs leak into the prompt or context | Sealed archive outside the repository; hash committed first; held-out services published only after the evaluation. |
| Developer confirmation bias in what counts as a bug | Verdicts come from the oracle and replay only. Distinct-bug attribution uses fix toggles, not judgment. |
| Benchmarks designed to favor the model | Composition rules fixed above before authoring, including mandatory shallow bugs. All targets reported, including losses. |
| Cherry-picking runs | Every trial is logged. The analysis script is committed before the held-out run and reports all trials. |
| Model non-determinism | 10 Muse trials per target (cost-limited) vs 20 for other methods; variance reported. |

## 6. Metrics

Primary:
1. **E₁:** executions to first verified violation, per trial, right-censored at `B_exec`.
2. **Success@B:** fraction of trials finding a verified violation within budget.

Secondary:
3. **T₁:** wall-clock time to first verified violation, including model latency.
4. **Cost:** model tokens and dollars per trial and per verified bug (Meta list prices; see
   `HACKATHON_COMPLIANCE.md` §6), plus execution container-seconds.
5. **Distinct bugs:** number of distinct verified bugs found per method over all trials.
6. **Reproduction rate:** replays reproducing the violation out of 20, plus the fraction of
   executions with `forced` decisions.
7. **False-positive rate:** verified violations on correct controls and equivalent mutants.
   **Expected 0 by construction; any non-zero value is a harness or oracle bug and blocks claims.**
8. **Plan validity:** fraction of Muse responses passing validation on the first try and after
   one repair.
9. **Hint adherence:** fraction of model schedule hints the scheduler could follow.
10. **Explanation reference accuracy (P1):** fraction of `{path, line}` references that pass the
    checker.

## 7. Analysis (pre-registered)

- Per target: success rates with Wilson 95% intervals; median E₁ with bootstrap 95% intervals
  (10,000 resamples); survival curves (fraction of trials that have found the bug by execution
  *k*).
- Pairwise M4 vs each baseline per target: Mann–Whitney U on E₁ (censored values set to
  `B_exec + 1`) and the Vargha–Delaney Â₁₂ effect size. Â₁₂ ≥ 0.71 is called "large". Holm
  correction across targets.
- Across targets: number of targets where M4 is significantly better, tied, or worse than M3,
  the strongest baseline. Reported separately for the shallow and precondition subsets.
- Cost-adjusted view: E₁ converted to wall-clock using measured mean execution time plus measured
  model latency.
- Dev and held-out results are never pooled.

## 8. Independent verification of each reported failure

For every violation shown in the README or demo:
1. Replay the recorded schedule 20 times from a fresh reset; report k/20 and trace-hash agreement.
2. Recompute the serial outcome set from scratch, not from cache.
3. For benchmark targets, run the same workload and schedule on the fixed variant and require no
   violation.
4. For D1 (#3824), additionally show the raw Valkey value before and after (hash only in the
   report), and show that issuing the same two requests serially through the API gives quantity 2.
5. Publish the replay file so anyone can re-run it with the pinned images.

## 9. Expected results (written before running, to keep us honest)

- **Shallow targets, including D1:** M1, M2, and M3 find the bug within a handful of executions;
  M4 ties on executions and loses on wall-clock and cost. M0 (stress) finds it intermittently.
- **Precondition targets:** M4 or A4 beat M1/M2 clearly. Against M3, the result depends on
  whether M3's profiling reaches the deep operations with sampled arguments. This is the
  comparison that decides RQ1.
- **Schedule hints (RQ2):** little effect, because workloads are small enough for exhaustive
  enumeration.
- **False positives:** zero from the oracle; candidate invariants (P1) may produce some, which is
  why they are never labeled verified.

If M4 does not beat M3 on the precondition subset, the project's claim becomes: "Deterministic,
spec-free reproduction of store-mediated races in unmodified services; LLM guidance did not
outperform conflict-directed search on our benchmark." We will report that as the result.

## 10. Stop/go criteria

| Gate | When | Go if | Otherwise |
|---|---|---|---|
| G0 | Oct 28 EOD | Meta API returns schema-valid `PlannerOutput` in ≥ 9 of 10 calls on a fixture; proxy in pass-through changes no outcome on D2 over 50 serial runs. | Fix schema (flatten, drop nullable unions) or switch endpoint; proxy bugs block everything else. |
| G1 | Oct 29 EOD | D2 forced lost-update schedule reproduces 20/20 with identical trace hashes; D5 correct variant shows 0 violations over all exhaustive schedules of every 2-op workload; D1 reproduced via proxy ≥ 19/20. | **Fallback A** (`ARCHITECTURE_OPTIONS.md` §7): in-process gated client for Python fixtures; D1 by stress with measured rate. If only multiplexed attribution fails, use barrier mode for D1. |
| G2 | Oct 31, 23:59 ET | All methods run end-to-end on the dev set with results files; plan validity ≥ 90% after ≤ 1 repair; prompt frozen and hashed. | Reduce Muse's role to A4 (ranking M3 candidates) and freeze that instead. |
| G3 | Nov 2, 12:00 ET | Held-out evaluation complete for M0–M4 with planned trial counts. | Report whatever completed, with reduced trials stated; cut A1–A4 first. |
| Kill | Nov 1, 12:00 ET | At least one verified violation end-to-end on any target. | Stop all P1 work; the demo is a single fixture plus D1 by stress. |

## 11. Budget for the evaluation

- Executions: 14 held-out targets × 5 baseline configurations × 20 trials × ≤ 300 executions,
  at ~0.1 s per execution **[UNVERIFIED]** ≈ 12 CPU-hours worst case. Most trials stop early.
  Parallelize across Compose projects.
- Model: 14 targets × 10 trials × ≤ 5 planner calls ≈ 700 calls ≈ $45 at the estimated $0.063
  per call. Ablations A1–A4 on a 6-target subset: ≈ $40 more. Development and demo: ≈ $40.
  Total ≈ $125 of the $150 credit. Re-estimate after measuring real token counts on Oct 28.

## Deviations

None yet.
