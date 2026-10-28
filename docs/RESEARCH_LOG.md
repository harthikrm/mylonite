# Research Log

Dated record of what was read, what was learned, and what remains uncertain. Newest entries go
at the bottom. Labels: **FACT** (read in a primary source; URL given), **HYPOTHESIS** (a claim
we intend to test), **ASSUMPTION** (taken as true for planning, not yet checked),
**OBSERVATION** (something we ran and saw; none yet).

Method for Phase 0: four parallel research passes using read-only web and GitHub API access:
(1) Meta Model API and hackathon rules, (2) OTel #3824 and NVIDIA OO-Agents, (3) existing tools,
(4) research literature. No repository was cloned and no third-party code was executed. Some
pages were read through an automated fetcher that returns a model-written summary of the page,
so quotations from those pages are close to verbatim but not guaranteed. Items marked
"re-verify" should be read by a human.

---

## 2026-10-27: Environment

- FACT: Host is macOS (Darwin 25.5.0). Installed: Git 2.50.1, gh 2.95.0 (logged in), Docker
  29.5.3 (Docker Desktop, 18 CPUs, ~8.3 GB memory to the VM), Python 3.14.5, Node 26.7.0. Not
  installed: Go, a Java runtime, uv, gitleaks, trufflehog, detect-secrets.
- Consequence: the harness is in Python; no toolchain installs on Day 1; secret scanning in
  Phase 0 is a pattern scan (see the commit notes).

## 2026-10-27: Meta Model API (https://dev.meta.ai/docs/overview and linked pages)

- FACT: model IDs `muse-wonder-1.0` (preview), `muse-spark-1.3` ("recommended for new work"),
  `muse-spark-1.2`, `muse-spark-1.1`, Contributor variants `muse-spark-1.3-contributor` and
  `muse-spark-1.2-contributor`; also `muse-image-1.0`, `muse-voice-transcribe-1.0`, `sam-3.1`.
  1,048,576-token context; text output. https://dev.meta.ai/docs/models
- FACT: no max output tokens on the models page. The only figure seen is `"output": 131072`
  inside an OpenCode config example. https://dev.meta.ai/docs/coding-agents (re-verify)
- FACT: Llama is not mentioned on the overview, models, or open-weight pages. Open-weight models
  (Muse Spark Open, Muse Glimmer) are self-hosted, not on the Model API.
  https://dev.meta.ai/docs/open-weight-models
- FACT: base URL `https://api.meta.ai/v1`; `Authorization: Bearer $MODEL_API_KEY`; keys start
  `LLM_`, per team, with shared rate limits. https://dev.meta.ai/docs/authentication
- FACT: endpoints `/v1/responses` (recommended), `/v1/chat/completions` (OpenAI-compatible),
  `/v1/messages` (Anthropic-compatible). No Meta-branded SDK. https://dev.meta.ai/docs/protocols,
  https://dev.meta.ai/docs/sdks
- FACT: structured output via `json_schema` with constrained decoding. Strict mode needs a plain
  object root, `additionalProperties: false`, and every property required, with no
  `allOf`/`oneOf`. No recursion; depth ≤ 10; ≤ 5,000 properties; ≤ 1,000 enum values.
  https://dev.meta.ai/docs/structured-output (re-verify strict-mode rules)
- FACT: `tool_choice` only `auto` on Chat Completions and Responses; tool `strict` does not
  guarantee argument validity. https://dev.meta.ai/docs/tool-calling
- FACT: `seed` deprecated and best-effort; temperature default 1.0, which the model is "tuned to
  run at"; `stop`, `n>1`, `logprobs`, `logit_bias` return 400; reasoning cannot be disabled;
  `reasoning_effort` from minimal to max. https://dev.meta.ai/docs/protocols/chat-completions,
  https://dev.meta.ai/docs/reasoning
- FACT: pricing and rate limits as recorded in `HACKATHON_COMPLIANCE.md` §6.
  https://dev.meta.ai/docs/pricing-rate-limits
- FACT: Standard-mode content is not used for training; Contributor mode may be; the ToS forbids
  confidential code in Contributor; Responses `store` defaults to true with no stated retention;
  the AUP prohibits unauthorized vulnerability scanning. https://dev.meta.ai/legal/terms-of-service,
  https://dev.meta.ai/legal/acceptable-use-policy
- HYPOTHESIS: a strict planner schema generated from the catalog is accepted and yields ≥ 90%
  usable plans. Tested by gate G0.
- ASSUMPTION: nullable types (`["string","null"]`) are accepted in strict mode. Unverified.

## 2026-10-27: Hackathon rules

- FACT: binding rules are the "Hackathon Terms & Conditions ('Official Rules') and Event Waiver",
  dated Oct 25, 2026. https://cerebralvalley.ai/e/meta-ai-developer-hackathon/waiver
- FACT: deadline Nov 4, 9:00 PM ET; Indie track allows teams ≤ 4; judging weights Impact 30,
  Use of Meta AI Tooling 25, Technical Depth 20, Demo 25; $150 API credit for a 10-day window.
  Full detail in `HACKATHON_COMPLIANCE.md`.
- Not found: public-repository requirement, video length, the "problem statements" behind the
  Impact criterion, and rules on pre-existing code or AI assistants.

## 2026-10-27: OpenTelemetry Demo #3824

- FACT: "Cart service has no atomicity guarantees — concurrent AddItem calls lose updates, and
  checkout's EmptyCart can silently discard items added during checkout". Opened 2026-08-10, open,
  no labels, no maintainer comment. Verified by the reporter against `6c4b663a`.
  https://github.com/open-telemetry/opentelemetry-demo/issues/3824
- FACT: at tag `3.1.0`, `src/cart/src/cartstore/ValkeyCartStore.cs` `AddItemAsync`: `HashGetAsync`
  (line 140) → parse and modify → `HashSetAsync` (line 165) → `KeyExpireAsync` (line 166). No
  transaction or script. `EmptyCartAsync` uses an unconditional `HashSetAsync` (line 187). The
  `_locker` guards only connection setup. Connection string uses `allowAdmin=true`; on first
  connect the store writes the test key `cart` = `OK`. (Read from the file as fetched via
  `gh api`.)
- FACT: cart is C# on `net10.0`, ASP.NET Core gRPC, StackExchange.Redis; `CART_PORT=7070`; cart
  registers no gRPC reflection; OpenFeature with a flagd provider is configured in `Program.cs`.
  **Corrected 2026-10-28:** the Valkey image `9.1.2-alpine3.24` is from `main`. At tag `3.1.0`
  the `.env` pins `9.0.4-alpine3.23` and `IMAGE_VERSION=3.0.0`.
- FACT: fix PR #3825 (optimistic concurrency with `Condition.HashEqual`) was closed unmerged by
  the stale bot on 2026-09-17. PR #3988 (merged 2026-09-18) re-enabled cart tests against an
  in-memory store, with no concurrency test. The racy code is present on 3.0.0, 3.1.0 (latest
  release, 2026-09-18), and `main` (`8f640ded`, 2026-10-27, which added TLS and password support
  in #4215).
- FACT: scenario B path in checkout (Go): `PlaceOrder` → `GetCart` → `chargeCard` → `shipOrder` →
  `emptyUserCart` (error ignored). The `intlShippingSlowdown` flag sleeps 5 or 10 s in shipping for
  non-US addresses, which widens the window.
- FACT: `compose.yaml` ("Core/minimal demo services") has 20 services. Cart `depends_on`
  valkey-cart, otel-collector, and flagd. Scenario B needs ~12 containers.
- OBSERVATION: none. **Not reproduced yet.**
- HYPOTHESIS: scenario A can be forced deterministically at the proxy despite StackExchange.Redis
  multiplexing, by separating execution order from per-connection reply order. Tested by G1.
- ASSUMPTION: cart starts without flagd and the collector (exporter and feature-flag failures are
  non-fatal). Unverified; if false, add both containers.
- Other repository issues reviewed: #3989 (C++ currency map data race; in-memory, out of scope),
  #4157 (ignored `EmptyCart` errors; partial failure, not a race), #3504, #3930, #3879, #3865,
  #4106, PR #4219. None is a better store-mediated race candidate.

## 2026-10-27: NVIDIA Object-Oriented Agents

- FACT: Python framework where LLM-implemented methods are declared by type and docstring;
  strategies Predict, CodeAct (default), and Decide; typed validation with retry; tracing.
  Apache-2.0, alpha v0.0.10, Python `>=3.12,<3.14`, LiteLLM-based.
  https://github.com/NVIDIA-NeMo/labs-OO-Agents
- FACT: no relation to the OTel demo or #3824 found.
- Decision impact: ideas only (D-013).

## 2026-10-28: Tools survey

- FACT: summaries and URLs in `PRIOR_ART.md` §2.2. Key points: Porcupine is Go-only with no
  maintained Python port; Jepsen history semantics `invoke/ok/fail/info`; Antithesis has no free
  access; rr is Linux-only; no mature Python controlled scheduler; Fray ships an MCP server for
  LLM-driven scheduling; Coyote's last NuGet release was Mar 2024.

## 2026-10-28: Literature survey

- FACT: summaries and URLs in `PRIOR_ART.md` §2.1 and §2.3–2.5. Decisive findings:
  - Thomson et al.: naive controlled random found 43 of 49 SCTBench bugs, 27 within 2 schedules.
  - PCT assumes the bug-triggering input is given.
  - ACIDRain: 22 verified attacks in 12 apps, with manual reproduction and 200 ms proxy delays.
  - REINS (arXiv 2610.13421, Oct 2026): LLM-guided controlled C/C++ scheduling; 48/52 vs RFF 47;
    single run per tool.
- Impact on design: the model's role moved from interleavings to workloads (D-015); M3 baseline
  added (D-010); #3824 demoted to dev-only (D-011).
- Not verified: TaxDC percentages, Feral Concurrency Control numbers (primary PDF unreachable),
  SURW's full paper and budget, ConMAn mutation operators.

## 2026-10-28: Team handoff, re-verification, and independent review

- Team handoff received. New inputs:
  - Participant-guide rules: public repository and 3-minute video required, new contributions
    identified, three judging stages.
  - The Agents 102 session.
  - $200 Claude credits.
  - The cookbook URL.
  - Risk C: respect each application's actual consistency contract.
  - A proposed day order.
  All recorded in `HACKATHON_COMPLIANCE.md` and `PHASE0_REVIEW.md`.
- FACT (re-checked with `gh`): #3824 open; #3825 closed unmerged 2026-09-17; tag `3.1.0` =
  `dedc0178…` = latest release.
- FACT: at `3.1.0`, `.env` pins `VALKEY_IMAGE=…9.0.4-alpine3.23` and `IMAGE_VERSION=3.0.0`.
  `ValkeyCartStore.cs` differs between `3.0.0` and `3.1.0` only cosmetically (`object` → `Lock`,
  `(byte[])` casts). The race logic is identical.
- FACT: the cart wraps every storage exception in `FailedPrecondition` (lines 168–171, 190–193 at
  `3.1.0`). Consequence: an error status does not imply "no effect" (`PHASE0_REVIEW.md` R3).
- FACT: Meta structured-output docs, re-read: `anyOf` allowed below the root; non-recursive
  `$ref`/`$defs` allowed; `strict: false` currently behaves like `strict: true`; Responses API uses
  `text.format`. https://dev.meta.ai/docs/structured-output
- FACT: quickstart confirms `muse-spark-1.3`, `https://api.meta.ai/v1`, `MODEL_API_KEY`, and that
  the OpenAI SDK does not read `MODEL_API_KEY` automatically. https://dev.meta.ai/docs/quickstart
- FACT: cookbook (MIT, pushed 2026-10-24): prompt caching is automatic on identical prefixes; an
  agent-loop recipe has Muse fix an asyncio lost-update race given failing tests.
  https://github.com/meta-models/meta-model-cookbook
- FACT: REINS abstract: "Agent-guided Thread Scheduling for Concurrency Bug Detection and
  Reproduction" (Zhang, Pasareanu, Yang; 9 Oct 2026). The LLM produces event-order and state
  constraints. Six new real-world bugs, three confirmed. https://arxiv.org/abs/2610.13421
- Review outcome: two critical design errors (the proxy reordered within one connection; the
  oracle imposed serializability as every target's contract) and several high-severity findings.
  See `PHASE0_REVIEW.md`.
- Observation on tooling: the fetched Meta and arXiv pages came back wrapped in text styled as
  instructions to the fetching agent, which the agent ignored. This is a reminder that any text
  pulled into a prompt can carry instructions (`THREAT_MODEL.md` T1).

## 2026-10-28: Tracer bullet, first observations

Details in `experiments/2026-10-28-tracer/README.md`.
- OBSERVATION: the executor and Valkey on a Docker `internal: true` network have no egress (TCP
  and DNS blocked). Container-name DNS inside the network works.
- OBSERVATION: the proxy in pass-through changed no outcome in 50 paired runs.
- OBSERVATION: fixture D2's lost update was found by exhaustive search (12/20 schedules violate,
  first at #2) and replayed 20/20 with one trace hash. The `INCRBY` variant passed 18/18
  exhaustively explored schedules.
- OBSERVATION: random workload + random schedule found it in a median of 11 executions (1–42) over
  20 trials. About 6 ms per execution.
- OBSERVATION: redis-py 8.1 negotiates RESP3 and does not fall back when `HELLO 3` is refused. The
  review's "refuse HELLO 3" proposal was wrong for current clients; the proxy now frames RESP3
  (D-019).
- OBSERVATION: one Muse planner call (`muse-spark-1.3`, `reasoning_effort: medium`, 9.34 s,
  1,156 + 2,823 tokens, $0.0134):
  - correctly named the lost update with correct line references;
  - proposed 3 experiments, all valid, each violating on its first execution;
  - all 3 verified: rerun with the same hash, replay 20/20, corrected variant exhaustive PASS
    (6, 90, 6 schedules).
- INTERPRETATION: on D2 Muse wins on executions (1 vs random median 11) and loses on
  wall-clock (≈ 140×) and dollars. As predicted for a shallow bug; this is not evidence for RQ1.
- OBSERVATION: three leaks in the planner input: a "buggy variant" docstring (removed before the
  call), the `fixtures/dev/` path, and a command enum taken from the witness. EVALUATION_PLAN.md
  fairness rules 5–6 added; they must be implemented before the Oct 29 pilot.
- OBSERVATION: `executor.explore` misreported a guided-first-schedule hit as `exhausted`. Fixed,
  with a test; errata recorded in the tracer's `results.json`.

## 2026-10-28: Pre-pilot integrity work

- DECISION (D-021): the model sees only a declared view.
  - Contamination is tested as information flow: changing anything outside the view (corrected
    variant, paths, IDs, provenance, stray result files, comments, docstrings, schedules in
    feedback) must leave the request byte-for-byte unchanged.
  - Keyword and overlap detectors are a second layer, each tested on a planted positive.
- OBSERVATION: the noninterference test found a gap in the first normalizer. Only a function's
  first docstring was dropped, so a later bare string reached the model. All bare string
  statements are now dropped.
- OBSERVATION: the same tests found that the result-key detector missed escaped quotes inside the
  JSON body. Fixed: the raw message is scanned too.
- DECISION (D-022): one host-side trial runner for M1, M3+ and M4, over a persistent executor
  session. M3+ is implemented:
  - breadth-first over setup states;
  - per-state profiling of every call (charged);
  - pairs filtered by the two-transaction conflict-cycle condition.
- OBSERVATION: the harness had two crash paths, both now fixed:
  - setup calls that raise (common in random D3 workloads) crashed executions;
  - the pass-through check crashed on rejected calls. It now records them, and compares each
    call's result or error as well as the final state.
- OBSERVATION: D3 fixture validated without any search method (author-constructed witness):
  - 0/50 pass-through mismatches;
  - 150/150 serial runs PASS on both variants;
  - the witness replays 20/20, and 120 of 192 schedules of its workload violate;
  - every setup step is necessary;
  - the corrected `EVAL` variant passes exhaustively.
- PREDICTION (before any method ran on D3): M1 finds D3 with probability ≈ 0.08% within 300
  executions (exact computation over an abstract model). Only M4 vs M3+ is informative on D3.
- OBSERVATION: harness smoke runs, which are not pilot data:
  - D2 with a stub model: all three methods found and verified the bug;
  - D3 at a budget of 30: all censored, as expected;
  - a replayed M4 trial reproduced its witness hash exactly.
- PROPOSAL (D-020): sole-developer held-out protocol (`docs/HELDOUT_PROTOCOL.md`). Awaiting the
  owner's decision.
- OBSERVATION (independent pre-pilot review, a fresh agent given the code rather than my
  conclusions):
  - Its in-memory emulation of the executor reproduced the D3 validation numbers exactly.
  - It showed breadth-first M3+ censored at 300 executions on D3 in 20/20 seeds, finding it at
    421–791. A hand count agrees: lifecycle pairs at depth 2 cost about 250 schedules.
  - My earlier claim that "on D3 only M4 vs M3+ is informative" was therefore wrong at
    B_exec = 300.
- DECISION (D-023, disclosed): M3+ explores contract-relevant pairs first; the pilot budget is
  1,000, with Success@100/300/1,000.
- OBSERVATION: the same review found more problems, all fixed with tests:
  - hint steps were silently skipped when an operation's first command was not the hinted one,
    which would have made "hints have little effect" true by construction;
  - feedback echoed model-written text, which could trip the audit and end an M4 trial;
  - one transient error could end the whole pilot without writing results;
  - the summary median ignored censored trials;
  - the read spy covered only `Path.read_text`.
- OBSERVATION: protocol gaps the review raised are addressed in `HELDOUT_PROTOCOL.md`: backdating
  (external timestamp now mandatory), bases shaped against M3+ (base specs fixed at C1), mutant
  style (decoy rewrites), C6 labeling, blindness and crash rules, and the `WATCH` operator the
  harness cannot expose.

## 2026-10-28: Pilot value checkpoint

Run on the evening of Oct 28, ahead of the planned Oct 29 date, at `db1f84f` with live Muse calls
approved by the owner. Details are in `experiments/2026-10-29-pilot/RESULTS.md`.
- OBSERVATION: every validity criterion (`READINESS.md` §8.B) passed, and no stop condition
  occurred. The checker reads the raw run and catches a planted fault for each criterion.
- OBSERVATION: the replay from recorded answers, at the run's commit, matched all 30 trials.
- OBSERVATION, D2: every method was verified 5/5. Median E₁: M1 5, M3+ 8, M4 1. M4 used about
  240–300× the baselines' method seconds and $0.014 per trial.
- OBSERVATION, D3:
  - M1 was censored 5/5, as predicted.
  - M3+ was verified 5/5, at E₁ 211, 246, 211, 211, 775 (Success@300 4/5), close to the
    reviewer's emulation.
  - M4 was verified 5/5 at E₁ = 1, at a median of 12.6 method seconds against M3+'s 1.7, and
    $0.016 per trial.
- OBSERVATION: every Muse plan named the bug's lines in the shown source. Each trial hit on its
  first execution, so feedback rounds and depth-first search were never exercised live.
- INTERPRETATION: the pilot cannot tell reading code apart from planning, because A2 (no source)
  was not run. No outperformance claim is made.
- OBSERVATION: both of §8.D's D3 clauses, *continue* and *re-scope*, fire on this outcome. The
  pre-registered rule had no precedence for this case. Under §8.D, the owner decides.
- OBSERVATION: M3+'s pair priority ignores argument values. On seed 5, its one prioritized
  `purchase ∥ purchase` pair could not violate, and the violating pair came 18 pairs later.
  Fixing this would be a post-pilot baseline change and needs the owner's decision.
- OBSERVATION: in 3 of the 5 D3 trials, the hint-advance rule (review fix #3) ran a command that
  Muse's hint had omitted.

## 2026-10-28: Ablation A2, Muse without source (exploratory)

Pre-registered at `aa1f4eb` before any A2 call; run at that commit. Details are in
`experiments/2026-10-28-a2-no-source/RESULTS.md`.
- OBSERVATION: the round-1 A2 requests equal the pilot's recorded requests minus the source
  block, byte for byte. Source rewrites cannot change them (tested). Every validity criterion
  (V1–V6) passed. The replay reproduced all 10 trials. Cost: $0.27.
- OBSERVATION: D2: A2 at E₁ = 1 in 5/5. D3: A2 verified 5/5 at E₁ 1, 1, 114, 71, 71 (median 71),
  against M4's 1 ×5 and M3+'s median 211. A2 took a median of 30.9 method seconds and $0.037 per
  trial.
- OBSERVATION: without source, Muse still named `check_then_act` on `purchase` in 5/5. In 3/5
  its round-1 setups ran `publish` before `restock`, so no round-1 experiment could violate. Its
  own execution feedback (`publish → InsufficientStock`) fixed the order in round 2, 3/3.
- OBSERVATION: each D3 Muse trial's E₁ splits exactly into executions on experiments that could
  not violate plus the hit's schedule index (1 for a hint hit, 7 = the 6th depth-first schedule
  otherwise).
- INTERPRETATION: on D3 the source supplied the precondition order, not the bug. Schedule hints
  were worth about 5 executions per hit.
- OBSERVATION: M3+'s argument-blindness hits 2/9 of seeds on D3 (derived from the code). An
  emulator over the recorded pilot data reproduces M3+ exactly. It estimates the proposed
  `M3+arg` (D-024, Proposed) at 211, 246, 211, 211, 555 against M3+'s 211, 246, 211, 211, 775.
- RECOMMENDATION (author's; the owner decides): re-scope. Keep the executions claim, report the
  wall-clock and dollar break-even per target (about 60 ms per execution for M4 on D3), measure
  per-execution cost on D1 early, and keep A2 required on held-out targets.

## Open threads carried into Phase 1

See `OPEN_QUESTIONS.md`. Most urgent: G0 smoke tests, cart startup dependencies, team roster,
and a human read of REINS.
