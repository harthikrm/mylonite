# Experiment 2026-10-28: tracer bullet on fixture D2 (gate T0)

**Question.** Does the whole chain work end to end on the simplest real case, inside the sandbox?
The chain is: unmodified client code → delay-only proxy → real Valkey → scheduler → contract
oracle → replay → corrected variant.

**This is not an effectiveness result.** D2 is a deliberately shallow fixture. The comparison
that matters is the pilot (Oct 29) and the held-out evaluation.

## Setup

| Item | Value |
|---|---|
| Fixture | `fixtures/dev/d2_counter/service.py`: loyalty points; `award` does `GET` then `SET` (buggy); `service_fixed.py` uses `INCRBY` |
| Contract | `no_lost_award` (`counter_conserved`), sourced from the fixture's docstring, approved by the team |
| Store | `ghcr.io/valkey-io/valkey@sha256:107b2031…` (9.0.4-alpine3.23, the version pinned by OTel demo 3.1.0) |
| Client | redis-py 8.1.0 (hash-pinned), one connection per operation, RESP3 negotiated by the client |
| Executor image | `python@sha256:5dde0937…` (3.13-slim) + `docker/requirements.lock` |
| Sandbox | `docker network create --internal`; both containers `--read-only --cap-drop ALL --security-opt no-new-privileges --pids-limit 256 --memory 512m --cpus 1`, non-root; executor driven over stdin/stdout; only `src/` and `fixtures/` mounted read-only |
| Race workload | two concurrent `award(m1, 1)` |
| Commands | `run_tracer.py --only baseline`; `--only muse` (one model call, then verify); `--only verify` (no model call) |

## Results (baseline phase, run 2026-10-28 01:04 CDT; full numbers in `results.json`)

| Check | Result |
|---|---|
| Egress from the sandbox | Blocked: TCP to 1.1.1.1:443 fails; DNS for pypi.org fails |
| Valkey container policy (from `docker inspect`) | read-only, user 999:1000, caps dropped, pids 256, 512 MiB, 0 mounts, not privileged |
| Pass-through changes nothing | 0 mismatches in 50 paired runs (through the proxy vs directly to Valkey) |
| Systematic (exhaustive) on the race workload | 20 schedules (search space exhausted), **12 violate** `no_lost_award`, first at schedule 2; 0 forced decisions; 0 soundness problems |
| Witness | `admit:0, admit:1, exec:0 (GET), exec:1 (GET), exec:0 (SET), exec:1 (SET)` → balance 1, contract allows 2 |
| Replay | **20/20** violations, 1 distinct trace hash, identical to the witness |
| Random workload + random schedule | 20/20 trials found it within 300; executions to first violation: median **11** (range 1–42) |
| Corrected variant (`INCRBY`) | 3 workloads explored exhaustively (6 schedules each): **18/18 PASS** |
| Mean time per execution | 5.9 ms (reset, round, observation, oracle) |

## Findings

1. **The mechanics work.**
   - The real lost update was reproduced deterministically against real Valkey through an
     unmodified client.
   - It was replayed 20/20.
   - The corrected variant passes exhaustive exploration of the same workloads.
2. **RESP3 is required.** redis-py 8.1 negotiates RESP3 and does not fall back when `HELLO 3` is
   refused. The proxy now frames RESP3 (D-019). Refusing RESP3, as the review proposed, would have
   broken unmodified clients.
3. **As predicted, this bug is shallow.**
   - Random search found it in a median of 11 executions, about 65 ms.
   - Exhaustive search found it at schedule 2.

   There is no room for a model to help on D2, by design. D2 tests mechanics only.
4. **Executions are cheap (≈ 6 ms).** For fixtures like this, the evaluation budget is dominated by
   model latency, not execution time. That makes the co-primary cost metric decisive.

## Muse phase (run 2026-10-28 02:36 CDT)

**Input.** The planner saw:
- the service source, line-numbered and wrapped as untrusted;
- the catalog and value domains;
- the contract.

It never saw the witness, any schedule, or any search result. Its output was constrained by a
strict JSON schema: operations, argument values and command names are enums. Prompt version
`planner-v0-2026-10-28`, `reasoning_effort: medium`, one call.

| Item | Value |
|---|---|
| Model | `muse-spark-1.3` (as returned by the API) |
| Latency | 9.34 s |
| Tokens | 1,156 prompt (0 cached), 2,823 completion (2,161 of them reasoning) |
| Cost | $0.0134 at Spark Standard prices |
| Hypotheses | 1: `lost_update` on `points:{member}`, with code refs to lines 16–18 (the `GET`, the add, the `SET`), which is correct |
| Experiments | 3 proposed, 3 valid, 0 rejected by the local validator |
| Hint adherence | 4/4, 6/6, 4/4 hint steps followed |
| Executions to first violation | **1** (each of the 3 experiments violated on its first execution) |

**Verification** (`--only verify`, no model call): every hit met the definition of verified.

| Experiment | Witness | Rerun reproduces it | Replay | Corrected variant, same workload |
|---|---|---|---|---|
| `award(m1,1)` ∥ `award(m1,2)` | 0 → 2 (contract allows 3) | at execution 1, same trace hash | 20/20, 1 hash | 6/6 PASS, exhausted |
| 3 × `award(m1,2)` | 0 → 2 (allows 6) | at execution 1, same trace hash | 20/20, 1 hash | 90/90 PASS, exhausted |
| setup `award(m1,2)`; `award(m1,1)` ∥ `award(m1,1)` | 2 → 3 (allows 4) | at execution 1, same trace hash | 20/20, 1 hash | 6/6 PASS, exhausted |

**Comparison on D2.** Indicative only: Muse is n = 1 here, and D2 is a development fixture.

| Method | Executions to first violation | Wall-clock to first violation | Model cost |
|---|---|---|---|
| Exhaustive DFS | 2 | ≈ 12 ms | $0 |
| Random workload + schedule (20 trials) | median 11 (1–42) | ≈ 65 ms (median) | $0 |
| Muse hint-first (1 call) | 1 | ≈ 9.35 s (9.34 s model + 11 ms) | $0.013 |

## Muse findings

5. **The Muse path works end to end.**
   - Strict-schema output parsed.
   - Every experiment passed local validation.
   - Every hint was followed exactly.
   - Every hit was verified by replay and by the corrected variant.
6. **On a shallow bug, Muse loses on the cost metric.** It wins on executions (1 vs 2 vs 11) but
   is about 140 times slower in wall-clock than random search and is the only method that costs
   money. This is the result the plan predicted for shallow bugs. RQ1 is decided by the Oct 29
   pilot on D3 (a precondition bug) and the held-out set, not here.
7. **Leaks found in the planner input.**
   - The fixture's docstring said "buggy variant". Removed before the call. Docstrings do not
     change behavior, so the baseline stands.
   - The source path `fixtures/dev/d2_counter/service.py` was still visible. Muse echoed it in
     its code refs.
   - The schema's command enum (`GET`, `SET`) was taken from the witness trace. Both commands
     are visible in the source, so this told Muse nothing new here, but the method is wrong.

   Fairness rules 5 and 6 (EVALUATION_PLAN.md §3) now forbid all three. They must be
   implemented before the pilot.
8. **Reporting bug, fixed.** `executor.explore` returned `exhausted=True` when a guided first
   schedule hit a violation, so a one-execution run was reported as a fully explored space.
   - Fixed, with a regression test (`ExploreTest`).
   - The three affected flags in `results.json` were corrected; an errata note is recorded
     there.
   - Baseline numbers were not affected: no baseline job used a guided first schedule.
9. **Memorization cannot be ruled out here.** `GET`-then-`SET` is the textbook lost update. D2
   says nothing about whether Muse reasons about unfamiliar code.

## Reproducing

- The recorded numbers come from commit `750c51e`; re-run there for an exact reproduction.
- The baseline phase has not been re-run since. Later commits touch what it uses:
  - The executor's one-shot mode is kept.
  - The pass-through check now also compares each call's result.
  - The D2 spec gained a `model_view`.
  - D2's contract clause was renamed, with the same semantics.

  Re-running it at HEAD would overwrite `results.json`.
- The Muse phase used planner `planner-v0-2026-10-28`, with a witness-derived command enum and
  the raw source path. The planner API has since changed (D-021). Re-run that phase at commit
  `750c51e`.
