# Decision Log

Format: each decision has an ID, date, status, context, decision, and consequences.
Statuses: **Accepted** (in force), **Proposed** (awaiting team approval), **Rejected**,
**Open** (needs input), **Superseded**. Never delete an entry; supersede it.

---

## D-001 Phase 0 is documentation only
- Date: 2026-10-27. Status: **Accepted** (team brief).
- Decision: Phase 0 produces research, architecture, threat model, evaluation design, and the
  repository. No application code, no dependency installs, no third-party code execution, no
  benchmarks.
- Consequence: everything in `docs/` is provisional until Phase 1 experiments confirm it.

## D-002 Repository location and Git policy
- Date: 2026-10-27. Status: **Accepted** (location chosen by Claude; the brief contained a
  placeholder path).
- Decision: `/Users/harthikmallichetty/Desktop/MetaMorphic/mylonite`, branch `main`, local only.
  No remote, no push without explicit team approval. `.env` and run artifacts are git-ignored.
- Consequence: the team should confirm the path or move the repository before Phase 1.

## D-003 The model chooses; it never writes code that runs and never decides a verdict
- Date: 2026-10-27. Status: **Accepted 2026-10-28**.
- Context: prompt injection through target source; LLM false-discovery rates (IRIS 84.82%);
  non-reproducible model output (`seed` deprecated).
- Decision: all model output is data validated against a strict schema and the human-written
  operation catalog. Execution, verdicts, replay, and minimization are deterministic code.
  Explanations are labeled as unverified commentary.
- Consequence: no CodeAct-style agents in P0. Any future relaxation requires a revised threat
  model first.

## D-004 Architecture: delay-only command scheduler at the store wire boundary (Option B)
- Date: 2026-10-27. Status: **Accepted 2026-10-28**.
- Context: `ARCHITECTURE_OPTIONS.md`. The real bug (#3824) is in an unmodified C# service;
  memory-level tools cannot see store-mediated races; interleaving search alone is saturated in
  the literature.
- Decision: a RESP2 proxy between service and Valkey/Redis that only delays commands; services
  run unmodified in containers.
- Rejected alternatives: Option A as the primary design (Python-only; cannot run #3824
  unmodified), kept as a fallback. Option C (agentic code execution) for security and
  evaluability. Option D (Muse + Fray/Lincheck) for runtime mismatch.
- Consequence: scope is store-mediated races. Determinism is measured, not guaranteed.

## D-005 Tool implementation language: Python 3
- Date: 2026-10-27. Status: **Accepted 2026-10-28**.
- Context: Python 3.14 and Node 26 installed; no Go or Java. asyncio suits a proxy. Muse is
  reachable with the OpenAI-compatible SDK or plain HTTPS.
- Decision: harness, proxy, scheduler, oracle, and evaluation in Python 3. Dependencies pinned
  with hashes, kept minimal (expected: an HTTP or OpenAI client, a JSON Schema validator, a gRPC
  client for the OTel target).
- Open sub-question: whether 3.14 has wheels for every needed package (gRPC in particular).
  Fallback: run the harness in a pinned Python 3.12 container.

## D-006 First protocol RESP2; first real target OTel Demo cart at tag 3.1.0
- Date: 2026-10-27. Status: **Accepted 2026-10-28**.
- Decision: target `open-telemetry/opentelemetry-demo` at tag `3.1.0`
  (`dedc0178918e260823323b8d95005a8cb924b007`), scenario A. Pin image digests on Day 1. Do not
  track `main`; the cart store file changed on 2026-10-27 (TLS and password support, #4215).
- Consequence: Postgres and SQL are P2. Scenario B is P1.

## D-007 Oracle: serial-equivalence with Jepsen semantics; the model is never the oracle
- Date: 2026-10-27. Status: **Accepted 2026-10-28**.
- Decision: compare masked concurrent outcomes with all serial orders of `ok` operations (plus
  subsets of `info` operations). Volatile fields are detected by running each serial order twice.
  Failed operations must have no effect. Model-proposed invariants (P1) must hold on all serial
  runs and remain `candidate` until a human confirms them.
- Consequence: reports say "non-serializable outcome". A human decides whether the API's
  contract was violated.

## D-008 Model configuration
- Date: 2026-10-27. Status: **Accepted 2026-10-28**, verified by the Day-1 smoke test.
- Decision: `muse-spark-1.3`, Standard mode (never Contributor for any non-public code),
  structured output with `strict: true`, `reasoning_effort: medium`, default temperature,
  `store: false` if honored, record and replay all model I/O. No other LLM provider is used in
  Mylonite's runtime.

## D-009 Structured output instead of tool calling
- Date: 2026-10-27. Status: **Accepted 2026-10-28**.
- Context: `tool_choice` supports only `auto`, and tool `strict` does not guarantee valid
  arguments; JSON-schema output is constrained decoding.
- Decision: planner and explainer use `json_schema` structured output. No model-invoked tools.

## D-010 Baselines include a conflict-directed systematic search (M3)
- Date: 2026-10-27. Status: **Accepted 2026-10-28**.
- Context: the adversarial review found that a proxy-level read/write profile can identify
  conflicting operations without a model.
- Decision: M3 is the bar the model must beat. M0 stress, M1 random, and M2 PCT are also
  required.

## D-011 OTel #3824 is a development target, not evidence of discovery
- Date: 2026-10-27. Status: **Accepted 2026-10-28**.
- Context: public issue with root cause and fix PR; memorization risk.
- Decision: no "discovery" claims on #3824. Generalization claims come only from the sealed
  held-out set.

## D-012 Sandbox: hardened Docker containers, no egress; no third-party code on the host
- Date: 2026-10-27. Status: **Accepted 2026-10-28**.
- Decision: flags in `THREAT_MODEL.md` §6; `internal: true` Compose networks; no host mounts
  besides a read-only target copy; never the Docker socket. gVisor or VMs deferred.
- Consequence: residual VM-escape risk accepted for curated open-source targets only.

## D-013 No agent framework, no microservices, no message queues
- Date: 2026-10-27. Status: **Accepted**.
- Decision: a single Python process (plus the proxy) orchestrates everything. NVIDIA OO-Agents is
  a source of ideas, not a dependency: it is alpha, supports Python 3.12–3.13, and runs
  model-written code by default.

## D-014 Evaluation is pre-registered; prompt freeze Oct 31 23:59 ET
- Date: 2026-10-27. Status: **Accepted 2026-10-28**.
- Decision: `EVALUATION_PLAN.md` frozen by commit after approval; prompt and schema hashes
  recorded; held-out archive hash committed before running; all trials reported.

## D-015 Muse's claimed role is workload selection, not interleaving selection
- Date: 2026-10-27. Status: **Accepted 2026-10-28**.
- Context: interleaving search is saturated (random 43/49 on SCTBench), and LLM-chosen
  interleavings already exist (REINS, Fray MCP).
- Decision: the measured claim is about choosing operations, arguments, and setup. Schedule hints
  are kept but evaluated separately (ablation A1), with no claim made in advance.

## D-016 License for the public repository
- Date: 2026-10-27. Status: **Open**.
- Proposal: Apache-2.0, matching the OTel demo and most tools we reference. It is compatible
  with the hackathon's broad license grant to organizers. Needs team approval before
  publishing.

## D-018 Phase 0 review corrections
- Date: 2026-10-28. Status: **Accepted 2026-10-28**.
- Context: `PHASE0_REVIEW.md` found that D-004's proxy rule allowed reordering commands within
  one connection, which is unsound. It also found that D-007 imposed serializability as every
  target's contract, against the handoff's Risk C, and treated errors as "no effect", which is
  false for the cart.
- Decision: the owner approved A1–A9 and A11 in `PHASE0_REVIEW.md` §4 on 2026-10-28. A10 (team
  roster, held-out author) is still open. These amend D-004, D-007, D-010, D-014, and D-015, and
  replace the Phase 0 roadmap order.
- Consequence: `ARCHITECTURE.md` §5–§6 and §9, `EVALUATION_PLAN.md`, `ROADMAP.md`, and
  `THREAT_MODEL.md` were rewritten to match.

## D-019 Pass RESP3 through instead of refusing HELLO 3
- Date: 2026-10-28. Status: **Accepted** (technical correction found by the tracer).
- Context: the review proposed refusing `HELLO 3` so clients stay on RESP2. In the tracer,
  redis-py 8.1 (the current release) sent `HELLO 3` on connect and raised an error instead of
  falling back.
- Decision: the proxy frames RESP3 and passes `HELLO` through unchanged. Push frames are forwarded
  to the client as-is.
- Consequence: unmodified services using RESP3 clients work. Client-side-caching invalidation
  pushes are forwarded but not scheduled.

## D-017 Team size, roles, and held-out author
- Date: 2026-10-27. Status: **Open**.
- Needed by Oct 28: who is on the team (≤ 4 for Indie), who owns W1–W4, and who authors the
  held-out set (must not be the prompt author). Solo fallback: sealed-seed mutation script.
- 2026-10-28: the owner may be the sole developer. The proposed held-out protocol for that case
  is D-020.

## D-020 Sole-developer held-out protocol
- Date: 2026-10-28. Status: **Accepted in principle** by the owner on 2026-10-28, with methods
  frozen before any held-out defect is constructed. Still open: the freeze date, the Python-only
  scope, and the timestamp mechanism (D-028).
- Decision: `docs/HELDOUT_PROTOCOL.md`. In short:
  - freeze methods and prompt first;
  - write correct base services and their contracts after the freeze;
  - inject bugs mechanically at sites chosen by a public randomness beacon (drand);
  - evaluate blind and automatically;
  - report every target, with one pre-registered exclusion rule.
- Consequences:
  - Independence is not claimed.
  - Two owner choices are attached: moving the method freeze to Oct 31 12:00 ET, and the
    Python-only injection scope (which relaxes §4.2's multiplexed-client rule).
  - A mutation script must be built and tested before the freeze.

## D-021 The model sees a declared view, checked by an audit and noninterference tests
- Date: 2026-10-28. Status: **Accepted** (technical; closes the three leaks the tracer found).
- Decision: `planner.build_request` is the only way to build a request (ARCHITECTURE.md §8.3a).
  `audit.assert_clean` gates every call. The contamination tests treat information flow as the
  property to test, not keywords.
- Consequences:
  - Planner prompt is now version `planner-v1-2026-10-28`.
  - The tracer's Muse phase (`planner-v0`) can only be re-run at commit `750c51e`.

## D-022 One host-side trial runner for every method
- Date: 2026-10-28. Status: **Accepted** (technical).
- Decision: M1, M3+ and M4 run as host-side strategies over a persistent executor session.
  `methods.Trial` is the only code that counts executions, enforces the budgets, and calls
  verification.
- Consequences:
  - Equal accounting holds by construction.
  - M3+ profiling counts as executions.
  - Method seconds exclude harness round trips and verification, which are reported separately.

## D-023 M3+ explores contract-relevant pairs first; pilot budget 1,000
- Date: 2026-10-28. Status: **Accepted** (technical; **disclosed post-emulation change**).
- Context: an independent review emulated the executor in memory. Breadth-first M3+ spent its
  300-execution budget on D3's lifecycle pairs (`publish`, `retire`, `restock`), whose conflicts
  never touch stock, before profiling the state where the bug becomes reachable. Both baselines
  would then be censored on D3 by construction.
- Decision:
  - At each state, M3+ first explores pairs that conflict on a key read by the contract's own
    observation operation, one per command signature. The rest are deferred until the frontier
    is exhausted, never dropped. This uses only M3+'s own profiles and the shared contract.
  - The pilot budget becomes 1,000, with Success@100/300/1,000 reported.
- Consequences:
  - The change was made after learning of a weakness on a development fixture. It strengthens
    the baseline, the conservative direction for any claim about M4.
  - M3+ is frozen with everything else at C1, before held-out code exists.


## D-024 M3+arg: an argument-aware variant of M3+, as an additional baseline
- Date: 2026-10-28. Status: **Accepted** by the owner on 2026-10-28 (**post-pilot development**).
  The original M3+ and every pilot and A2 result stay as they are. The emulated M3+arg numbers
  below are estimates, not measurements. Implemented on 2026-10-31 (D-033).
- Context:
  - M3+'s pair priority (D-023) keeps one pair per command signature. Calls that differ only in
    argument values share a signature.
  - On D3 the one prioritized `purchase ∥ purchase` pair is chosen at random among quantity
    combinations. With probability 2/9 per seed, it is a pair that cannot violate.
  - The pilot's seed 5 hit this case: E₁ = 775 against 211–246 for the other seeds
    (`experiments/2026-10-28-a2-no-source/RESULTS.md` §5).
- Proposal:
  - A new method ID, `M3+arg`, identical to M3+ until its frontier is exhausted.
  - Then, ahead of the other deferred pairs, it explores the pairs M3+ deferred only because they
    share a signature with a representative it already explored.
  - `M3+` stays as pre-registered. It is not altered, renamed or replaced.
- Evidence (estimate only, not a run):
  - The emulator replays `methods.run_m3plus` over the pilot's recorded profiles and
    exploration outcomes, and reproduces all 5 seeds exactly.
  - Its M3+arg estimate: 211, 246, 211, 211, 555. The same as M3+ on seeds 1–4, and 775 → 555 on
    seed 5. Every pair it reaches has a recorded cost.
  - The alternative, which explores variants right after their representative at each state,
    estimates 281–311 on seeds 1–4. It was rejected because it is worse in the typical case.
- If accepted: freeze M3+arg at C1 with everything else, and run it beside M3+ (not instead of
  it) on held-out targets. Report both.

## D-025 Multiplexed store clients: read-ahead, attribution by running operation, TCP_NODELAY
- Date: 2026-10-28. Status: **Accepted** (technical; found by the D1 gate, before any D1 experiment).
- Context:
  - The D1 cart (StackExchange.Redis 3.2.1) puts every operation on **one RESP3 connection**.
  - The proxy read a connection's next command only after the previous one ran. A command
    queued behind a held one was invisible, so its operation looked "running"; every such
    decision waited for the 300 ms Δq timeout.
  - Attribution was by connection, so every command on the shared connection was credited to
    the first operation.
  - On D1 this gave 3–6 forced decisions and 0.9–1.8 s per execution (an artifact), with
    misattributed traces. The soundness check did not flag it.
- Decision:
  - For a target whose spec says `"store_client": "multiplexed"`, a second thread per
    connection reads commands as they arrive and registers them with the scheduler.
  - Each command belongs to the operation running when it arrived (`ARCHITECTURE.md` §5.3).
    Only a connection's head command can be chosen.
  - A forced decision on a shared connection is a soundness problem: attribution would no
    longer be guaranteed, so the execution is inconclusive.
  - **The client's transaction lock is modeled.** StackExchange.Redis holds the connection
    from writing `WATCH`/`MULTI` until it writes the closing command (confirmed with `MONITOR`).
    - While a block is open, the other operations count as blocked, not running.
    - When it closes, the single blocked operation is the one that writes next.
    - Two or more blocked operations cannot be told apart, so that execution is inconclusive.
    - A gated write during the lock means the model is wrong, and is flagged.
    - Without this, the #3825 cart was inconclusive in 12 of 18 schedules of one workload.
  - Per-connection targets keep the original single-thread path and attribution. Reading ahead
    there costs about 2 ms per D3 execution and gains nothing.
  - The proxy sets `TCP_NODELAY` on both of its sockets, as Valkey and the clients do. Without it,
    two replies in a row on one connection waited for a delayed ACK: about 48 ms instead of 5 ms
    per D1 execution.
- Evidence (`experiments/2026-10-28-d1-gate/`):
  - All 30 pilot trials re-run from the recorded Muse answers give identical results. All 6,766
    events are identical: every decision list, verdict and trace hash, every profile and every
    verification. The 10 planner requests are byte-identical.
  - On D3 the per-execution time is unchanged within noise in a same-session A/B: old proxy 8.2
    and 8.5 ms, new 8.0 and 8.2 ms.
- Consequences:
  - D2 and D3 behave exactly as in the pilot and A2.
  - D1 schedules are controllable: 0 forced decisions, about 5 ms per execution, once warm.
    With three or more concurrent operations, some schedules of the transactional (#3825) cart
    remain inconclusive by design.
  - Residual timing assumption: after a block closes, the blocked operation writes before the
    owner's next command. The #3825 code sleeps at least 2 ms before retrying, and replay checks
    would expose a violation of this assumption.
  - Out-of-process services run as hardened containers on the internal network, with their own
    image and explicit environment (`Sandbox.start_service`).
  - The D1 executor image (`docker/executor-d1.Dockerfile`) adds pinned `grpcio`. The D2/D3 image is
    unchanged.

## D-026 Re-scope: AI-guided concurrency counterexample generation, verified deterministically
- Date: 2026-10-28. Status: **Accepted** by the owner after the pilot and A2.
- Decision:
  - The claim is about generating concurrency counterexamples, with AI guidance, that are
    verified deterministically (replay, corrected variant, the contract oracle).
  - **Execution efficiency (E₁) is reported separately from wall-clock time and total cost**,
    with the break-even per-execution cost for each target.
  - No claim that Muse "wins" overall. The question is where AI-directed experiments give
    measurable engineering value over strong conventional methods.
- Consequences:
  - Every comparison table gets separate E₁, method-seconds and dollar columns.
  - The D1 gate (`experiments/2026-10-28-d1-gate/`) measures the real cart's per-execution cost
    against the A2 break-even estimates.

## D-027 A3 interface obfuscation: designed, not run
- Date: 2026-10-28. Status: **Accepted for design only** (owner, 2026-10-28). Implementing and
  running it need a separate approval.
- Decision: `docs/A3_DESIGN.md`.
  - A mechanical, order-preserving renaming of operations, arguments, string values, errors,
    key prefixes and source identifiers, in Muse's view only.
  - Plans are translated back by code before validation, so the oracle, budgets and
    verification are unchanged.
  - Baselines must behave identically on both specs (checked event by event).
  - An audit and a noninterference test show that original names cannot reach the model.
- Not applicable to D1: its names are the public gRPC API.

## D-028 External timestamp for the freeze and the sealed bases
- Date: 2026-10-28. Status: **Proposed** (owner decision; every submission is a public action).
- Decision (proposal): `docs/HELDOUT_PROTOCOL.md`, "External timestamp mechanism".
  - Salted SHA-256 commitments to the C1 and C2 manifests.
  - Timestamped with two RFC 3161 TSAs and OpenTimestamps.
  - Only digests leave the machine before the reveal at C6.
- Rejected as primary: a GitHub push (it publishes the repository and relies on the platform's
  clock).

## D-029 D1 contract approved; D1 limited to 2 concurrent calls for every method
- Date: 2026-10-29. Status: **Accepted.** The contract and the no-model D1 baseline experiment
  were approved by the owner on 2026-10-29; the size limit is technical.
- Decision:
  - The D1 contract `no_lost_quantity` (`item_quantity_conserved`, `targets/d1-otel-cart/target.json`)
    is approved as proposed in the gate report §3, including its caveat: the maintainers have
    neither confirmed nor disputed #3824.
  - A target spec may lower the shared concurrent-size maximum for every method, never raise it
    (`space.max_concurrent`). D1 sets 2.
- Why the limit: with 3 or more concurrent calls on the multiplexed client, two operations can
  queue behind one transaction. Which one writes next is up to the client, so the corrected
  build's execution cannot be attributed and a correct witness could never be verified. The
  lost update needs only 2 calls.
- Consequences:
  - M1's draws on D1 have exactly 2 concurrent calls; M3+ already explores pairs only; a future
    M4 or A2 request on D1 shows `concurrent_max: 2` in its limits.
  - D2 and D3 are unchanged: the pilot regression is identical in every event.

## D-030 Resume attribution decided at arrival; verification re-runs inconclusive executions
- Date: 2026-10-29. Status: **Accepted** (technical; before any D1 trial at seeds 1–5).
- Context:
  - The gate's 1.7% fixed-build stall was attributed, untested, to CPU starvation. The raw
    records show a harness race instead. When a transaction closed, `block_closed` took a
    snapshot of the operations that were not done as the ones blocked. An operation that had
    already finished in the cart, but whose reply had not reached the harness, was in it. The
    other operation's retry was credited to it, the next command was unattributed, and Δq
    forced a decision. Every one of the 17 stalls in 1,200 runs was an `unattributed WATCH`.
  - After the fix, a rarer case remains: a cart pause longer than Δq (300 ms) mid-operation,
    1 in 4,000 random fixed-build executions, 0 in 4,600 buggy ones. It forces a decision, which
    is correctly inconclusive. Its cause is untested (the 1-CPU limit and the cart's
    info-level console logging are candidates).
- Decision:
  - The set of blocked operations is computed when the next command arrives, not when the
    block closes, so operations that finished in between are excluded. A unit test reproduces
    the race and fails on the old code.
  - Verification (`methods.verify`) re-runs an INCONCLUSIVE execution, replay or corrected,
    at most `inconclusive_reruns` times (D1: 2). A run that completes with the wrong verdict or
    trace hash is never re-run. Re-runs and their causes are listed in the verification result.
    The default is 0, so the pilot and A2 configurations behave as before.
- Evidence (`experiments/2026-10-29-d1-baselines/results/diagnostics/`):
  - fixed build, 1,200 cycled schedules of the gate's 2-operation workloads: 17 inconclusive
    before, 0 after, same session;
  - buggy build: identical verdicts (195 violations) before and after;
  - all 30 pilot trials re-run from recorded answers are identical in all 6,766 events.
- Consequences:
  - The gate's "untested hypothesis: `--cpus 1` starves the .NET thread pool" was wrong for the
    1.7%. Recorded as an erratum in the gate report.

## D-031 M0 (stress) as implemented
- Date: 2026-10-29. Status: **Accepted** (implements a required method; before any D1 trial at
  seeds 1–5).
- Decision:
  - M0 draws workloads as M1 does (its own seed stream) and runs each once without schedule
    control. The concurrent calls start together, with the proxy in pass-through
    (`executor.stress_once`). The oracle reads only states and outcomes, so the verdict needs
    no schedule.
  - On a hit, M0 explores that workload depth-first under the scheduler, up to `K`, and the
    first controlled violation goes through the shared verification (`methods.run_m0`). Every
    stress and exploration execution counts.
- **Deviation from `EVALUATION_PLAN.md` §3:** the plan's M0 replays "the command order the proxy
  saw". On a multiplexed client that order cannot be attributed to operations without control
  (D-025), so the hit is reproduced instead. On per-connection targets the plan's version would
  be possible, but it is not built.
- Consequences: a stress hit that does not reproduce under the scheduler is not a finding; the
  trial continues.

## D-032 THREAT_MODEL §8 for running third-party code without a model
- Date: 2026-10-29. Status: **Accepted** for no-model runs; **open** for model runs on
  third-party code.
- Decision: `experiments/2026-10-29-d1-baselines/SECURITY_CHECK.md` records every §8 item for
  running the D1 cart without a model. The evidence is `sandbox_check.py` at the
  pre-registration commit and `tests/test_sandbox.py`.
  - Met: the static flag set (now unit-tested); no egress; non-root; a read-only root; all
    capabilities dropped; limits holding against fork-bomb, busy-loop, memory and tmpfs
    fixtures; the canary key absent from every container; images built from source; the
    soundness check on every trace.
  - Deviation: the executor has two read-only binds of our own `src/` and `fixtures/`.
  - Open:
    - NuGet packages are not hash-locked;
    - Docker Desktop file sharing is at its default (the owner's setting);
    - there is no pre-commit secret hook;
    - no fixture shows that a hung service always ends as INCONCLUSIVE rather than a trial
      error;
    - every model-path item for third-party targets.
- The gate ran the cart before this record existed. That is disclosed in the record and in the
  gate's errata.

## D-033 M3+arg as implemented
- Date: 2026-10-31. Status: **Accepted** (implements D-024; the owner approved implementation
  on 2026-10-31, "Yes, implement it"). No M3+arg trial at seeds 1–5 on any target.
- Decision:
  - `methods.run_m3plus_arg`, registered as `M3+arg`, is `run_m3plus` with
    `promote_variants=True`.
  - It uses M3+'s seed stream (`M3+:<seed>`). So it is M3+ exactly until the frontier is
    exhausted.
  - **Variants.** At each state, a deferred pair is a variant if its command signature equals
    that of a pair explored at that state. The signature (`methods.pair_signature`) is both
    profiles' commands and key digests.
    - The same signature means the same commands at the same state.
    - So a variant was deferred only by the one-pair-per-signature rule: it is the same calls
      with other argument values.
  - **Order after the frontier.**
    - First the variants: states in breadth-first order, and M3+'s shuffled order within a
      state.
    - Then the other deferred pairs, in M3+'s order.
    - Nothing is dropped or added.
  - This is D-024's proposal, and the A2 emulator's prototype, line for line.
  - **For M3+, the change is a refactor.**
    - The signature becomes a named function.
    - The deferred list is split in two, and the first part is always empty for M3+.
    - M3+'s counters are unchanged. M3+arg adds `m3arg_variants_promoted`.
- Evidence (no model calls; development seeds only):
  - `tests/test_m3arg.py`:
    - **On a two-state fake, seeds 1–5:** the same pairs as M3+, and M3+'s order through the
      frontier. Then the variants, state by state, then the rest.
    - **On the pilot's recorded D3 data, with no execution:**
      - M3+ still reproduces every profile and exploration in the pilot logs.
      - `methods.run_m3plus_arg`, used in place of the emulator's prototype, gives D-024's
        estimate exactly: 211, 246, 211, 211, 555. No pair it reaches lacks a recorded cost.
    - **With the promotion switched off,** both checks fail: 775 on seed 5, and a different
      order.
  - **Same-session regression** on the working tree that became this commit (`methods.py`
    sha256 `07676669…`):
    - all 30 pilot trials are identical in all 6,766 events;
    - raw output in `runs/d1gate-regression-20261031-130057/` (git-ignored).
  - **Smoke at seed 0, with the pilot's settings, not data** (`runs/m3arg-smoke-20261031-130325/`):
    - **D2:** M3+ and M3+arg are identical, at E₁ 8. The hit came before the frontier was
      exhausted.
    - **D3:** seed 0 hit the blind spot.
      - M3+ reached E₁ 775 and M3+arg 555, with the same witness: stock 2, `purchase` 2 ∥ 1.
      - The event streams are identical through the last profile (event 328). They first
        differ at the start of an exploration, and 8 variants were promoted.
      - Both witnesses verified 20/20. The corrected build passed all 6 schedules.
- Consequences:
  - **Where M3+arg can differ from M3+:** only on a run where M3+ exhausts its frontier
    without a verified hit.
    - On D1 and D2, M3+ hit before that in every recorded trial. So M3+arg would have been
      identical there.
    - On the pilot's D3 seeds, the estimate differs only on seed 5.
  - M3+arg's D3 numbers at seeds 1–5 are still the emulator's estimate, not a run. A run needs
    its own pre-registration, and seed 0 is now used.
  - M3+arg freezes at C1 with everything else, and runs beside M3+ on held-out targets (D-024;
    `EVALUATION_PLAN.md`, post-pilot amendment).
