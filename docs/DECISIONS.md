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

## D-017 Team size, roles, and held-out author
- Date: 2026-10-27. Status: **Open**.
- Needed by Oct 28: who is on the team (≤ 4 for Indie), who owns W1–W4, and who authors the
  held-out set (must not be the prompt author). Solo fallback: sealed-seed mutation script.
