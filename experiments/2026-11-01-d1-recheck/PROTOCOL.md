# D1 re-check at freeze v1.0 (pre-registered 2026-11-01, before the run)

Run at the commit that adds this file, on top of freeze v1.0 (`da3ca57`, tag `freeze-v1.0`;
manifest `b07fec5`). `recheck.py` refuses a dirty tree or a failing
`freeze/manifest.py check`. A smoke run of the script (n = 30, in a scratch clone, not data)
checked only that it works.

**No model calls and no method trials.** It compares no methods and runs nothing that searches
for the bug. D1 is a development and feasibility target (`docs/FREEZE.md` §3). The D1 gate
(`../2026-10-28-d1-gate/`) and the D1 baseline experiment (`../2026-10-29-d1-baselines/`) are
not changed.

## 1. Why

The owner asked for the D1 feasibility gate to be prioritized after the freeze:
- inspect the authentic bug and its revision;
- establish the cart's real execution dependencies;
- reproduce the defect safely;
- verify the oracle and the corrected behavior;
- measure the execution and reset costs every method shares;
- compute realistic break-evens;
- decide whether AI-guided experiment selection is valuable on this target.

Most of this was measured on Oct 28–29, on code that has since changed in harness details
(D-029–D-031) and in M3+arg. This run repeats the measurements **with the frozen code** and adds
what was never measured: the frozen verification timed on a D1 witness, the corrected build's
cost of an execution (the gate's row for it was invalid), and per-operation latency with the
services the cart runs without.

## 2. What runs (`recheck.py`), on one bring-up

All stages use the executor path that every method shares: reset (`FLUSHALL`), setup, scheduled
round, observation, oracle. The images are the gate's (`../2026-10-28-d1-gate/build.json`).

| Stage | What | From |
|---|---|---|
| bring-up | Valkey, the executor with the proxy, both carts. Start-to-ready per cart, which is the cost of a reset by restart | `d1.bringup`, unchanged |
| serial | Serial adds of 1, 2 and 3 give 6, and of 2 give 2; the same twice from a reset; `EmptyCart` empties | `gate.stage_serial`, unchanged |
| gate_k | 5 fixed workloads on both builds, depth-first to exhaustion; the first violation replayed 20 times | `gate.stage_gate_k`, unchanged |
| verification | The frozen `methods.verify`, with the held-out settings (20 replays, corrected exhaustive ≤ 5,000, 2 re-runs of an inconclusive execution), on the same-item workload's first violation, timed | new |
| dependencies | `AddItem`, `GetCart`, `EmptyCart`, each 5 times serially, 100 executions each, against an empty workload: per-call latency. Then the cart's whole log, scanned for flagd, OTLP and OpAMP | new |
| costs | 300 executions each: floor (reset and observe), the same-item workload depth-first on each build, M1 draws, M3+ profiles | `gate.stage_costs`, unchanged since its post-gate fix |
| natural | No proxy: the cart talks to Valkey directly, and 1,000 rounds of two `AddItem` calls are released together, per build | `gate.stage_natural`, unchanged |

**Before the run, at the same commit:** `../2026-10-29-d1-baselines/sandbox_check.py`
(THREAT_MODEL §8 for no-model runs, D-032), unchanged. It must pass in full, and its report is
copied into the results.

## 3. Pass criteria (all must hold; otherwise the failure is reported, not fixed in place)

1. **Serial.** Both builds match the contract, give the same result twice from a reset, and
   `EmptyCart` empties.
2. **Defect.** On the buggy build:
   - every workload except `ctl_two_users` has at least one violation;
   - every first violation replays 20/20 with one trace hash;
   - `ctl_two_users` has none.
3. **Corrected behavior.**
   - The fixed build has 0 violations in every stage.
   - Its 2-operation workloads are all PASS, with no inconclusive schedule.
   - `A_three_adds` may be inconclusive; D-029 explains why, and every method on D1 is limited
     to 2 calls.
4. **Verification.** `verified` is true, with corrected mode `exhaustive`.
5. **Natural.** At least 85% of buggy rounds lose an update (the gate: 94.2%). 0 fixed rounds
   do.
6. **Harness.**
   - 0 soundness problems, 0 harness errors and no forced decision in serial, gate_k and
     verification. The exception is `A_three_adds` on the fixed build, which is inconclusive by
     design (D-029): with three operations, two queue behind one transaction;
   - in the costs stage, at most 1% of any row's executions are inconclusive or have problems.
     D-030 measured a residual cart pause in 1 of 4,000 fixed-build executions;
   - the run is at a clean tree, and `freeze-v1.0` is an ancestor of its commit.

## 4. Predictions (not pass criteria; machine variance between sessions is about ±25%)

- **Medians within ±25% of the gate's:**
  - floor 2.44 ms;
  - same-item depth-first on the buggy build 4.67 ms;
  - M1 draws 7.26 ms;
  - M3+ profiles 7.55 ms.
- **Start to ready** about 1.7 s per cart.
- **Per-call latency:** `EmptyCart`, the only one of the three that evaluates a flag (`cartFailure`)
  at 3.1.0, is within 1 ms of `AddItem`. So running without flagd adds no measurable delay.
- **Verification** of one witness under 1 s.

## 5. What it cannot show

- Anything about Muse on D1: Muse does not run. Break-evens stay estimates (`RESULTS.md`).
- The demo's own deployment. There is no flagd, collector or load generator; the cart has 1 CPU;
  and stress goes through the proxy.

## 6. Cost and safety

- $0 and about a minute.
- Containers as in D-032: no egress, read-only roots, all capabilities dropped, non-root.
- The run refuses a dirty tree.
- The unrelated containers on the machine are not touched.
