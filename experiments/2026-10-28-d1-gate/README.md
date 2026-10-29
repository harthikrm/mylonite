# D1 feasibility gate: the real OTel Demo cart (2026-10-28)

No model calls were made. Nothing was pushed or published. The pilot (`ecf37d9`) and A2
(`aa1f4eb`, `e136f20`) directories are unchanged.

| What | Where |
|---|---|
| Harness changes | `9dc696e`, `bf8701c` (D-025) |
| Gate run | `results/20261028-193603.json`, at `bf8701c` on a clean tree; raw records in `runs/d1gate-20261028-193603/` (git-ignored) |
| Break-even analysis | `analysis.json`, from `analyze.py` |
| Pilot regression | `regression.py`; report in `runs/d1gate-regression-*/report.json` |
| Build provenance | `build.json`, `../../targets/d1-otel-cart/` |

## 1. Target, source and bug history (read-only GitHub API, 2026-10-28)

- **Revision.** `open-telemetry/opentelemetry-demo` tag `3.1.0` = `dedc0178` (2026-09-18). Its
  `ValkeyCartStore.cs` is blob `1f4b9037`, last changed on 2026-08-04 (`ed6f1303`).
- **The defect.** `AddItemAsync` reads the cart with `HashGetAsync`, changes it in memory, and
  writes it back with `HashSetAsync` (sent as `HMSET`), then `KeyExpireAsync`. There is no
  transaction, script or version check. `EmptyCartAsync` overwrites the cart unconditionally.
- **Still on `main`.** `main` at `841adc01` (today) still has the same read-modify-write.
- **#3824** (2026-08-10): open, unlabeled, two comments, no maintainer response.
- **The fix, #3825.**
  - The reporter's fix: an optimistic transaction (`WATCH` plus a condition, then
    `MULTI`/`EXEC`, retried up to 30 times).
  - A maintainer commented on style only. It was closed as stale on 2026-09-17, unmerged.
  - Its base blob is `1f4b9037`, the 3.1.0 file exactly. So "fixed" means 3.1.0 with only that
    file replaced from head `060ee206`.
- **Existing tests.** #3988 re-enabled the cart tests, but against an in-memory store. Nothing
  exercises the Valkey store under concurrency.

## 2. Is the authentic defect reproducible? **Yes**, on the unmodified service, built from source

The two images were built in containers from a reviewed Dockerfile with upstream's digests
(`targets/d1-otel-cart/`, 34 s). Each depth-first exploration below ran on the real cart through
the proxy, with no forced decisions.

| Workload | Buggy build: schedules / violations | Replay of first violation | Fixed build (#3825) |
|---|---|---|---|
| `AddItem(u1,P,1)` ∥ `AddItem(u1,P,1)` | 8 / 2 | 20/20, identical trace hash | 6 schedules: 5 PASS, 1 inconclusive (stall) |
| `AddItem(u1,P,1)` ∥ `AddItem(u1,Q,2)`: a product vanishes | 8 / 2 | 20/20 | 6/6 PASS |
| three `AddItem`s on u1 | 132 / 72 | 20/20 | 82: 47 PASS, 35 inconclusive, 0 violations |
| setup `AddItem`; `AddItem` ∥ `EmptyCart`: emptied item survives | 7 / 1 | 20/20 | 6/6 PASS |
| control: `AddItem(u1)` ∥ `AddItem(u2)` | 8 / 0 | n/a | 6/6 PASS |

- **What a violation looks like.** Both `HGET`s run before either `HMSET`; each request succeeds,
  and the cart shows 1 instead of 2.
- **Without the proxy** (`natural.py`: cart connected to Valkey directly, two `AddItem`s released
  together, 1,000 rounds):
  - buggy: **942 of 1,000** lost an update;
  - fixed: 0 of 1,000.

  So the defect does not depend on our scheduler. In real timing it is close to certain.
- **Serial semantics** (`EVALUATION_PLAN.md` §8.4): through the proxy, adds of 1, 2 and 3 give 6,
  and `EmptyCart` gives an empty cart. The same serial workload twice from a reset gives the same
  result on both builds, so there is no hidden state and `FLUSHALL` is a sufficient reset.
- **Gate K** (the corrected build passes exhaustive exploration of the same workload):
  - **met** for three of the four 2-operation buggy workloads;
  - **not cleanly met** for the 2-operation same-item workload (1 stalled schedule of 6) and
    for 3-operation workloads (§7).
  - No violation was observed on the fixed build in any execution.

## 3. Is the oracle defensible? **Yes, with one caveat; proposed, awaiting your approval**

- **The invariant.** A new kind, `item_quantity_conserved`, with unit tests. Per user and
  product, the final quantity must be the initial quantity plus the successful adds. If an
  `EmptyCart` may have taken effect, it may instead be the sum of any subset of the adds.
- **It is a conservation law, not linearizability.** It ignores real-time order, so every serial
  outcome is accepted, and some violations are missed rather than invented. Non-OK statuses
  count as "may or may not have applied", which the cart needs because it turns every exception
  into `FailedPrecondition`.
- **Sources.** The cart's own serial behavior (§2), the add-quantity code, and #3824's statement.
  Plus the control: different users never violate.
- **Caveat.** The maintainers have neither confirmed nor disputed that concurrent adds must be
  conserved; the demo is a reference app.

## 4. Is the environment isolated enough? **Yes for this curated target, with gaps in the formal checklist**

- **Container settings, as Docker applied them.** Every container:
  - runs on an `internal` network with no published port, and the egress probe was blocked
    (TCP to 1.1.1.1 and DNS);
  - has a read-only root filesystem, all capabilities dropped and `no-new-privileges`;
  - is non-root (cart UID 1654), with a pids limit of 256 and no host mounts;
  - has 160 MB of memory for the cart (as in the demo's compose file) and size-capped logs.
- **Build.** Third-party code ran only inside BuildKit containers (NuGet restore and publish) and
  the cart container. Nothing from the checkout ran on the host.
- **Gaps:**
  - NuGet packages are pinned by version, not by hash (upstream has no lock file).
  - The build stage has network access (T6/T10 residual).
  - `THREAT_MODEL.md` §8's checklist (fork-bomb and infinite-loop fixtures, canary key, compose
    lint, Docker Desktop file sharing) has not been completed and recorded. That is a
    prerequisite the threat model sets for running third-party code, and I ran the cart without
    it.

## 5. Measured costs (same conditions for every method; no added delays)

Medians over 300 executions each, executor-side, warm cart:

| Execution type | Median | p90 |
|---|---|---|
| Floor: reset (`FLUSHALL`) and observe 2 carts | 2.4 ms | 2.8 ms |
| Scenario A, depth-first | 4.7 ms | 5.4 ms |
| An M1 draw (random workload and schedule) | 7.3 ms | 9.7 ms |
| An M3+ profile (one call after a random setup) | 7.6 ms | 9.4 ms |

- **Other costs:**
  - `FLUSHALL` alone takes 0.04 ms; warm gRPC calls take 0.4–0.8 ms.
  - The host round trip, excluded from method seconds, is 0.6 ms.
  - Cart start to ready takes 1.7 s; a reset never needs it.
- **Same-day reference.** A D3 execution takes 8.0–8.5 ms, so D1 executions cost about the same
  as D3's.
- **Machine variance** between sessions is about ±25% (the pilot measured D3 at 7.2 ms).
- **Fixed build.** 5 of 300 executions stalled for 300–555 ms (§7). Its cost row in the results
  file is invalid and excluded: the gate script replayed the buggy build's 8 schedule prefixes on
  the fixed build's 6-schedule tree, so 75 executions diverged by construction. `gate.py` has
  been corrected since the run.

## 6. Baselines, and the revised break-even

**Feasibility (one trial each, seed 0, outside the planned seeds 1–5; not results):**
- **M1** verified at **E₁ = 30**, in 0.21 method-seconds.
- **M3+** verified at **E₁ = 23**, in 0.11 method-seconds.
- Each witness replayed 20/20, and the fixed build passed all 6 schedules of it.
- **M3+arg** (D-024) is not implemented yet. **Stress** is feasible: §2's no-proxy run is one.

**Break-even** (`analysis.json`): the per-execution cost at which Muse would tie, under the most
favourable assumption for Muse (E₁ = 1).
- These are estimates, because Muse has not run on D1. They use D3's measured latency and a
  D1-sized prompt of about 10k tokens, at about $0.027 per call.

| Muse scenario | Ties M1 at | Ties M3+ at | Measured D1 execution | Short by |
|---|---|---|---|---|
| M4-like: 1 call, 12.6 s | 0.43 s per execution | 0.57 s per execution | 7.3 ms | 60–79× |
| A2-like: about 30 s, 2 calls | 1.04 s | 1.37 s | 7.3 ms | 143–188× |
| In dollars (M4-like: $0.027 against compute at $1.11e-5 per second) | 84 s per execution | 111 s per execution | 7.3 ms | about 10⁴× |

- **Compared with D3.** The D3 break-even was 60 ms (M4) and 215 ms (A2). D1's is about 10×
  higher, because its baselines need about 25 executions instead of about 211, while an
  execution costs the same.
- **On wall-clock alone:** Muse's first call (about 12.6 s) takes 60–115× longer than either
  baseline's whole search to a verified bug.

## 7. Necessary changes to the experiment harness

Done (`9dc696e`, `bf8701c`; D-025):
- **Read-ahead and attribution on a multiplexed connection.** Before this, every decision waited
  the 300 ms Δq timeout, and commands were credited to the wrong operation.
- **`TCP_NODELAY` on the proxy's sockets.** Without it, a delayed ACK inflated each D1 execution
  from about 5 ms to 48 ms.
- **The client's transaction lock is modeled.** Without it, the fixed build was inconclusive in
  12 of 18 schedules.
- **Out-of-process services**, a gRPC adapter, a D1 executor image, and the cart invariant.
- **Warm-up before measurement.** A cold fixed cart stalls on its first transaction.
- **Regression check.** All 30 pilot trials re-run from recorded answers are identical in all
  6,766 events. D3's speed is unchanged in a same-session A/B.

Still needed before a D1 experiment:
1. **The fixed-build stall.** 1.7% of executions, so a 6-schedule check would fail about 10% of
   the time (an estimate: 1 − 0.983⁶).
   - Hypothesis (untested): our `--cpus 1` limit starves the .NET thread pool while a caller
     waits on the client's lock. The demo sets no CPU limit.
   - Test: rerun with the cart at `--cpus 2`. If confirmed, record the cart's limit as a
     per-image exception.
2. **Verifying 3- and 4-operation witnesses.** On the fixed build these are often inconclusive by
   design (two operations queued behind one transaction). Either fix D1's concurrent size at 2
   for every method, or shrink witnesses before verification.
3. **For M4 or A2 on D1:**
   - a C# source normalizer (the current one parses Python);
   - an audit of the fix-only material (#3825's file), instead of the variant's module;
   - the memorization probe.
4. **Process.** Complete and record `THREAT_MODEL.md` §8, and implement M3+arg (D-024).
5. **Your approval** of the D1 contract.

## 8. The smallest controlled experiment worth running next

A **D1 baseline experiment with no model calls**:
- **What runs.** M1, M3+ and stress, seeds 1–5, `B_exec` 1,000, concurrent size fixed at 2 for
  every method. Pre-registered first, after items 1–2 above.
- **Cost and time.** $0 and under 5 minutes.
- **What it gives.**
  - D1's real E₁ distribution and verification rate.
  - It tests the plan's own prediction that baselines find shallow bugs within a handful of
    executions. The seed-0 trials say 23–30 executions rather than a handful.

A Muse run on D1 is **not** worth its credits for the effectiveness question: even E₁ = 1 cannot
reach break-even, by a factor of 60 or more. If you want D1 model data, the informative use is
RQ5: let Muse draft the D1 contract and catalog, compare them with §3, and run the memorization
probe. That is 1–2 calls, under $0.10, and needs your approval.

## 9. Recommendation: continue the re-scoped project; change D1's role; do not stop

- **Continue.**
  - The harness now controls a real, unmodified C# service with a multiplexed client. That was
    the single biggest risk named in Phase 0.
  - The authentic defect reproduces under control, replays 20/20, and the unmerged fix is checked
    against the same workloads.
  - Verified counterexamples with deterministic replay are an engineering deliverable that does
    not depend on Muse beating anything.
- **Change direction for D1.** It cannot show value for Muse:
  - it is shallow (94% of natural races lose an update);
  - an execution costs about 7 ms;
  - the baselines verify it in 0.1–0.2 s.

  Keep D1 as the realism anchor and as a pre-stated "baselines win" case, not as a Muse
  comparison.
- **Where Muse could still add measurable value:**
  - **Expensive executions.** About 0.06–1.4 s each, depending on depth. For example, targets
    that need a process restart to reset (the cart measured 1.7 s), or real multi-service
    workflows (R1, scenario B: about 12 containers).
  - **Deep preconditions**, as D3 showed.
  - **Contract and catalog drafting** (RQ5).

  The held-out set should report each target's per-execution cost and break-even beside E₁.
- **Not stop.**
  - On D3, the execution-efficiency signal is real.
  - The wall-clock deficit is a fact about cheap targets, now quantified, not a defect of the
    approach.

## 10. Remaining risks

- **Lock-model assumption.** It assumes the blocked operation writes before the owner's retry,
  and the retry sleeps at least 2 ms. Replay checks would catch a breach.
- **Memorization.** #3824 is public and Muse's training cutoff is unknown, so there is no
  discovery claim on D1.
- **Not the demo exactly.** No flagd or collector, and 1 CPU. Flag evaluation returns its
  default, and telemetry export fails in the background.
- **Single seed-0 baselines.** Feasibility only.
- **Machine noise** of about ±25% between sessions. Break-evens compare same-session numbers
  where it matters.
