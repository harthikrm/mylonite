# D1 re-check at freeze v1.0: results and feasibility verdict (run 2026-11-01)

**No model calls. No method trials. $0.** Run `results/20261101-030634.json`, at `6b7e12a`
(the pre-registration commit, on top of freeze v1.0 `da3ca57`), with a clean tree and
`freeze/manifest.py check` passing. Raw records are in `runs/d1recheck-20261101-030634/`
(git-ignored). The pre-run THREAT_MODEL §8 check passed in full
(`results/pre_run/d1sec-20261101-030628.json`). The break-even estimates are in
`analysis.json`, from `breakeven.py`.

**Verdict: AI-guided experiment selection is not valuable on D1.** That holds by a factor of
230–1,500 in time and about 10⁴–10⁵ in dollars, even in Muse's best case. The value on D1 is the
deterministic, verified counterexample, which any method reaches in well under a second (§5).

## 1. The authentic bug and its revision (facts; read-only GitHub API on 2026-11-01, local checkout)

- **Revision under test.** `open-telemetry/opentelemetry-demo` tag `3.1.0` = `dedc0178`. The
  local checkout's HEAD is that commit. `ValkeyCartStore.cs` at 3.1.0 has SHA-256 `9f04993d…`,
  the same as the buggy image's build context (`build.json`).
- **The defect** (`src/cart/src/cartstore/ValkeyCartStore.cs` at 3.1.0, `AddItemAsync`, lines
  127–176):
  - `HashGetAsync` reads the cart (line 140);
  - the protobuf is changed in memory (`existingItem.Quantity += quantity`);
  - `HashSetAsync` writes it back (line 165), then `KeyExpireAsync`.

  There is no transaction, script or version check. Two concurrent adds for one user can both
  read the old cart, and one write overwrites the other.
- **Upstream today.**
  - Issue #3824 is still open, with no labels, 2 comments, last updated 2026-08-10.
  - PR #3825 (head `060ee206`) was closed unmerged on 2026-09-17.
  - `main` is at `33bd8231` (2026-10-29). Its store file (blob `c603b272`, last changed in
    `841adc01` on 2026-10-28) still does `HashGetAsync` (line 151), then `HashSetAsync`
    (line 176), with no transaction. **The defect is unfixed upstream.**
- **Corrected build.** 3.1.0 with only `ValkeyCartStore.cs` replaced by #3825's head version
  (SHA-256 `d18a915e…`). It uses an optimistic transaction (`WATCH` plus a condition,
  `MULTI`/`EXEC`, up to 30 retries). It was never merged, so "corrected" means "this proposed
  fix", not an upstream release.

## 2. Real execution dependencies (from the 3.1.0 source, and observed)

| Dependency | What the cart does with it | In our sandbox | Effect on the operations under test |
|---|---|---|---|
| Valkey (`VALKEY_ADDR`) | Required. The cart exits at start without it. `ValkeyCartStore.Initialize` connects at start, and every operation uses one multiplexed StackExchange.Redis connection | Valkey 9.0.4, pinned by digest, behind the proxy | This is the shared state; the race lives here |
| flagd (OpenFeature `FlagdProvider`) | Optional. At 3.1.0, only `EmptyCart` evaluates a flag (`cartFailure`, default 0). If it were positive, a share of empty-cart calls would go to a store at `badhost:1234` | Absent. The provider initializes, no error is logged, and the evaluation returns the default | None: `EmptyCart` takes the normal path, at about the same per-call latency as `AddItem` (§4) |
| OTel collector (OTLP export of logs, traces and metrics) | Optional. Export runs in the background | Absent, with no egress | None on requests |
| OpAMP client | Starts only if `OPAMP_SERVER_ENDPOINT` is set (`Program.cs` lines 102–122) | Not set, so it is not started | None |
| Newer `main` | `GetCart` also evaluates a flag (`cartMetricCardinalityOverflow`, added by #4087 on 2026-10-13) | Not tested: we run 3.1.0 | Would add one flag evaluation per `GetCart` with flagd present |

**Reset.** `FLUSHALL` is a sufficient reset: the same serial workload twice from a reset gives
the same carts on both builds, so the cart keeps no state of its own between requests. A reset
by restarting the cart would cost its start-to-ready time instead (§4).

## 3. Pass criteria (PROTOCOL.md §3): all hold

| | Criterion | Result |
|---|---|---|
| 0 | Sandbox check before the run | ALL PASS: fork bomb, busy loop, memory and tmpfs limits; read-only root; noexec /tmp; no egress; canary key absent; no Docker socket or home mount; non-root |
| 1 | Serial semantics | Both builds: adds of 1, 2 and 3 give 6, and 2 gives 2; the same twice from a reset; `EmptyCart` empties |
| 2 | Defect | Buggy build: violations in all 4 buggy workloads (same item 2/8 schedules, two items 2/8, three adds 72/132, add vs empty 1/7). Every first violation replayed **20/20 with one trace hash**. The two-user control had 0 of 8 |
| 3 | Corrected behavior | #3825 build: **0 violations** in every stage (gate_k, 300 cost executions, 1,000 natural rounds, verification). Every 2-operation workload passed, with no inconclusive schedule. Three adds: 60 PASS, 24 inconclusive, as designed (D-029) |
| 4 | Frozen verification | `methods.verify` with the held-out settings, on the same-item witness: **verified**. 20/20 replays with an identical hash; corrected build exhaustive, 6/6 PASS; 0.13 s |
| 5 | Natural race, no proxy | Buggy: **92.7%** of 1,000 rounds lost an update (gate: 94.2%). Fixed: 0% |
| 6 | Harness | 0 soundness problems, 0 harness errors and 0 forced decisions outside the three-add fixed workload. 0 problem executions in every cost row. Clean tree; `freeze-v1.0` is an ancestor |

## 4. Measured costs shared by every method (medians of 300 executions; warm cart, 1 CPU)

| What | Median | p90 | Gate, Oct 28 | Prediction (±25%) |
|---|---|---|---|---|
| Reset (`FLUSHALL`) and observe 2 carts | 2.3 ms | 3.0 ms | 2.4 ms | held |
| Same-item pair, depth-first, buggy build | 5.6 ms | 8.7 ms | 4.7 ms | held (+21%) |
| Same-item pair, depth-first, #3825 build | **9.1 ms** | 18.2 ms | (gate row invalid) | new: the transactional fix's retries cost about 3.5 ms more |
| An M1 draw (random workload and schedule) | 5.9 ms | 7.7 ms | 7.3 ms | held (−19%) |
| An M3+ profile (one call after a random setup) | 7.1 ms | 9.3 ms | 7.6 ms | held |
| Host round trip (excluded from method-seconds) | 0.4–0.7 ms | | 0.6 ms | |
| Serial per-call latency: `AddItem` / `GetCart` / `EmptyCart` | 0.77 / 0.44 / 1.15 ms | | | held: `EmptyCart` is within 1 ms of `AddItem` |
| Reset by restart: cart start to ready | 1.2 s per build | | 1.7 s | **missed** (−29%). Not needed: `FLUSHALL` suffices |
| Verifying one witness (20 replays + exhaustive corrected check) | 0.13 s | | 0.14–0.29 s per trial | held |

- **One D1 execution costs about 5–9 ms** for every method, including the reset. Stress
  executions in the baseline experiment were 6.8 ms.
- **One-time costs:** building the images, 34 s on Oct 28; bringing up Valkey, the executor and
  both carts, with warm-up, a few seconds.
- **Without flagd, the collector and OpAMP:** the cart log's 10,782 lines contain only the flag
  provider's two initialization lines, and no export or OpAMP lines. `EmptyCart` is not
  slowed.

## 5. Break-even on D1 (estimates: Muse has never run on D1)

- **Formula.** The frozen `analysis.crossing`, c* = (L_m − L_b) / (E_b − E_m).
- **Baselines.** The D1 baseline experiment's medians (Kaplan–Meier, n = 5):
  - M0 (stress): E₁ 7;
  - M1: 18;
  - M3+: 23.

  Their non-execution overheads are about 1–2 ms.
- **Muse scenarios.** Measured on D3 in development runs:
  - M4-like: one call, median 12.6 s (range 11.1–13.8), $0.016;
  - A2-like: two calls, median 30.1 s (21.5–44.4), $0.037.
- Muse's E₁ is taken at its best case, 1, and at 3.

| Muse scenario | vs M0 (stress), the least favorable | vs M1 | vs M3+ | Measured D1 execution | Short by (vs M0) |
|---|---|---|---|---|---|
| M4-like, E_m = 1 | **2.1 s** per execution (dollar tie: 243 compute-s) | 0.74 s | 0.57 s | 0.005–0.009 s | 230–420× in time; about 4 × 10⁴ in dollars |
| M4-like, E_m = 3 | 3.1 s (365 compute-s) | 0.84 s | 0.63 s | | 350–630× |
| A2-like, E_m = 1 | 5.0 s (551 compute-s) | 1.77 s | 1.37 s | | 560–1,000× |
| A2-like, E_m = 3 | 7.5 s (827 compute-s) | 2.0 s | 1.5 s | | 830–1,500× |

- **Even a restart-per-execution harness would not reach it.** That is 1.2 s plus about 6 ms per
  execution, still below stress's 2.1 s break-even in Muse's best case. Such a harness is not
  needed: `FLUSHALL` is a complete reset for this cart (§2).
- **On wall-clock alone:**
  - stress reaches a verified, replayable lost update in a median of 0.05 method-seconds, plus
    0.13–0.29 s of verification that every method pays;
  - one Muse call takes 11–14 s.
- **M4 cannot run on D1 under freeze v1.0.** Its model view parses Python only, and the cart's
  C# raises `SyntaxError`. A C# view would be a method change (class C, `AMENDMENTS.md`).
- A2, which needs no source, could run. But #3824 is public, so its result would also carry a
  memorization caveat.

## 6. What this establishes, and what it does not

**Facts (measured today, with the frozen code):**
- the authentic upstream defect reproduces on the unmodified 3.1.0 service, under control and
  in real timing;
- the oracle accepts every serial outcome and rejects the lost update;
- the unmerged #3825 fix passes every 2-operation workload exhaustively;
- one execution costs 5–9 ms, and a verification 0.13 s;
- the defect is still present on upstream `main`.

**Estimates:** every break-even above. They use D3 model latencies and the n = 5 D1 baseline
medians.

**Not shown:**
- Muse's behavior on D1;
- the cart under the demo's full deployment (flagd, the collector, the load generator, more than
  1 CPU);
- stress without our proxy in pass-through. The natural race says the proxy does not create the
  bug: 92.7% lost without it.

## 7. Recommendation for D1

- **No-go for a Muse comparison on D1.**
  - No E₁ Muse could reach changes the verdict: the best case still needs executions 230× more
    expensive than they are.
  - M4 cannot run on D1 without a class C change.
  - The bug is public.
- Keep D1 as the realism anchor and as the pre-stated case where baselines win.
- The deliverable on D1 is a verified, replayable counterexample from a real, unmodified C#
  service with a multiplexed client, and a check of the unmerged fix.
