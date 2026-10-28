# Phase 0 Review

Date: 2026-10-28. Scope: everything in commit `b120740` plus the team handoff of 2026-10-27.

**Who reviewed.** The assistant that wrote Phase 0 reviewed it, which is a self-review. To get a
read not anchored on the author's conclusions, a separate reviewer agent read the documents cold
against the handoff's checklist, without seeing the author's reasoning. Load-bearing facts were
then re-checked against primary sources. Every finding below says which of these produced it and
whether it was verified.

**Owner decision (2026-10-28):** A1–A9 and A11 approved; A10 open. The corrections in §3 are now
folded into `ARCHITECTURE.md`, `EVALUATION_PLAN.md`, `ROADMAP.md`, and `THREAT_MODEL.md`.

**Bottom line.** The direction (store-mediated races, delay-only control, a deterministic oracle,
Muse proposing experiments) survives review. Two parts of the written design are **wrong as
written** and must be corrected before any code exists:
1. the proxy's ordering rule (R1), and
2. the oracle's correctness contract (R2–R4).

The evaluation is over-scoped and its accounting is biased. The day order front-loads
infrastructure and puts the value question too late. Phase 1 should not start until the owner
approves the corrections in §4.

## 1. Status of facts

### Confirmed
- Repository: `/Users/harthikmallichetty/Desktop/MetaMorphic/mylonite`, branch `main`, one commit
  `b120740`, no remote. 13 documents plus `.gitignore`, `.editorconfig`, `.env.example`.
- OTel #3824: open, unlabeled, created 2026-08-10. PR #3825: closed unmerged on 2026-09-17.
  Tag `3.1.0` resolves to `dedc0178…` and is the latest release (2026-09-18). Checked with `gh`
  on 2026-10-28.
- `ValkeyCartStore.cs` at `3.1.0`: `HashGetAsync` at line 140, `HashSetAsync` at 165,
  `KeyExpireAsync` at 166, unconditional empty-cart write at 187. **Every exception is converted
  to `FailedPrecondition`** (lines 168–171 and 190–193). `Ping()` uses the same multiplexer.
- The race logic is identical in `3.0.0` and `3.1.0` (diff: `object` → `Lock`, explicit
  `(byte[])` casts only).
- **Correction:** at tag `3.1.0` the demo's `.env` pins `VALKEY_IMAGE=…valkey:9.0.4-alpine3.23`
  and `IMAGE_VERSION=3.0.0`. Valkey 9.1.2 is on `main`. The docs said 9.1.2 and have been
  corrected. Prebuilt images are therefore not proven to match the source we read.
- Meta structured output, from the docs and the cookbook: JSON-schema constrained decoding;
  `anyOf` allowed below the root; non-recursive `$ref`/`$defs` allowed; `text.format` on the
  Responses API (`response_format` there returns 400); prompt caching automatic on identical
  prefixes. Model `muse-spark-1.3`, base URL `https://api.meta.ai/v1`, key in `MODEL_API_KEY`.
- REINS (arXiv 2610.13421, Zhang, Pasareanu, Yang, submitted 9 Oct 2026). The abstract says the
  LLM produces constraints on event orders and variable states for a controlled scheduler. It
  does not choose inputs or workloads.
- Meta's own cookbook includes a lost-update race (`02_agent_patterns/.../async_counter.py`). Muse
  fixes it in an agent loop **given a failing test**, which positions Mylonite one step earlier:
  finding and proving the race when no test exists.
- Participant-guide rules (team-reported, now in `HACKATHON_COMPLIANCE.md`): public repository
  required, 3-minute video required, new contributions must be identified, three judging stages.

### Proposed (nothing below is approved)
Architecture Option B, the oracle, Muse's role, baselines, held-out design, roadmap, sandbox
design. All of `DECISIONS.md` D-003 … D-017 except D-001, D-002, D-013.

### Unverified
- That wire-level control works on StackExchange.Redis's multiplexed connection.
- That the cart starts without flagd or the collector.
- That a Docker `internal: true` network can expose a published port to the host. The reviewer
  believes it cannot. Assume it cannot.
- Execution time per run; model latency and tokens per call.
- Every expected result in `EVALUATION_PLAN.md` §9.
- REINS's single-run methodology and numbers: from a fetcher's summary of the full paper,
  not read by a human.

## 2. Findings

Severity: **C** critical (a wrong result is possible), **H** high, **M** medium. "Source" says
who found it: CR = cold reviewer, SR = self-review, H = handoff. "Verified" means checked
against a primary source or by reasoning shown here.

| # | Sev | Finding | Source | Verdict |
|---|---|---|---|---|
| R1 | C | **The proxy can produce unreachable schedules.** `ARCHITECTURE.md` §5.4 lets the proxy execute commands from one TCP connection out of arrival order. Valkey executes a connection's commands in order, and the client's send order can encode in-process synchronization (for example, a handler that pipelines `SET` before releasing a mutex). Reordering within a connection can therefore manufacture a lost update that cannot happen, which is a false positive. The §5.4 example never needed that freedom: #3824's bad order is already the FIFO order. | CR | **Accepted.** The "delay-only is sound" argument holds **across** connections, not within one. |
| R1b | H | Quiescence has no states for "reply held behind FIFO" or "blocked inside the process". Admission has no timeout, so it can deadlock (the cart's reconnect path writes synchronously while holding `_locker`). Admission order is not enumerated, so "exhaustive" misses schedules. Pass-through commands *do* wait behind held ones on a shared connection. `WATCH` must open a per-connection block. | CR | Accepted. |
| R2 | C | **Serializability is imposed as every target's contract.** This contradicts the handoff's Risk C ("never claim a bug based on a fabricated invariant"; respect the application's actual contract). The "0 false positives by construction" claim is circular: every control is serializable code we wrote. The handoff's step 2 (an independent expected-state invariant) was replaced, not kept. | CR + H | **Accepted.** |
| R3 | H | **"`fail` has no effect" is wrong for this target.** The cart turns any exception into `FailedPrecondition`, including one raised after `HSET` succeeded. The oracle would drop that operation from the serial set while its write is visible, and report a false violation. | CR, verified at `3.1.0` lines 168–171 | Accepted. Default every non-OK status to `info` (may or may not have taken effect). |
| R4 | H | The oracle compares any serial order even when one operation returned before another was invoked, which causes false negatives. Detecting volatile fields from two runs misses low-entropy fields such as second-resolution timestamps, which causes false positives. | CR | Accepted. Respect real-time order; compare only contract-declared fields. |
| R5 | H | **Accounting bias.** Serial-oracle runs are charged per *new* workload, which penalizes random strategies that try many workloads. M3's profiling is charged but Muse's code reading is free in E₁. Trial counts are unequal (10 vs 20). Workload and domain sizes are not pre-registered. | CR | Accepted. |
| R6 | H | **M3 is handicapped.** It has no setup search, yet ≥ half the held-out bugs need setup. Blinding is weak: in solo mode the prompt author writes the base services; nothing bans failing traces in prompts; the hint enum in the example is #3824-specific. | CR | Accepted. |
| R7 | H | **Day order.** The handoff puts the first controlled fault, a baseline, and a Muse run on Oct 28, the value question on Oct 29, and the external defect plus a corrected version on Oct 30. Phase 0 put the first Muse run on Oct 30, the value question on Nov 2, and the kill gate on Nov 1. | H + CR | Accepted. The value question is the project's reason to exist and must be answered first. |
| R8 | H | "Replay against a corrected implementation" is undefined: decision lists diverge on changed code. There is no corrected-cart run at all. | CR + H | Accepted. Explore the same workload **exhaustively** on the fixed version; build a #3825-patched cart. |
| R9 | H | **Over-scoped evaluation:** 14 held-out services, 5 methods + 4 ablations, Holm correction underpowered at n = 10/20, a worst-case runtime estimate that assumed 0.1 s per execution. | CR + SR | Accepted. |
| R10 | M | **Sandbox gaps.** Published ports likely do not work on an `internal: true` network. The trace channel out of the sandbox is unspecified. Docker Desktop shares `/Users`, and the checklist omits restricting it (the project directory holds `.env`). Hardened flags are written for `docker run` while execution uses Compose, with no lint. | CR | Accepted. Run the executor **inside** the internal network; the host orchestrator talks to it over stdin/stdout. |
| R11 | M | **Muse's role is thin where it matters for judging.** The docs predict no gain on the only real bug, and the fallbacks shrink Muse further. Stage 1 of judging is "baseline viability and Meta model usage". | CR + H | Accepted. Proposal in §3. |
| R12 | M | D-015 changes the *mechanism* hypothesis (workloads vs schedules) without surfacing it as an owner decision. | CR | Partly accepted. The research question is unchanged: efficiency vs random/systematic exploration under equal budgets. What changes is the hypothesis about where a gain would come from. Surfaced as decision A3. |
| R13 | M | Inconsistencies: "verified" defined as 20/20, ≥ 19/20, and N/N in different files; 12 vs 14 targets; held-out "authored after freeze" vs "sealed Oct 31"; `.env.example` pointing to the wrong section; README stating unexecuted behavior as fact; REINS described as "one-program margin" while omitting its 38-bug RaceBench margin and six real-world bugs. | CR, verified | Accepted. The factual ones are fixed now (§5). |
| R14 | M | A top professional would add: a Day-1 tracer bullet; an automatic soundness checker over every trace; a passthrough-changes-nothing test; command-level partial-order reduction (commands on different keys commute); a memorization probe (ask Muse about the OTel cart bug with no code, since A3 cannot hide `CartService/AddItem`); an existing RESP parser; refusing `HELLO 3`; real before/after Redis race fixes as held-out defects; a pilot before pre-registration. | CR | Accepted. Cheap, and each one prevents a specific failure. |
| R15 | M | Spending ≈ $125 of a $150 credit while a payment method is attached risks overage. Posting a reproduction to #3824 or creating a public remote are public actions. | CR | Accepted. Both need owner approval; set a spend alert or cap if the console allows. |

Not accepted as stated:
- *"The demo features Muse on a contaminated bug."* Partly valid. #3824 stays the real-world
  reproduction anchor because a real unfixed bug is the strongest credibility signal we have.
  The demo must not present Muse as *discovering* it, and the value claim must come from held-out
  and precondition targets.

## 3. Corrected design (proposed)

**3.1 Proxy rule (fixes R1, R1b).**
- Per connection, commands execute and replies return strictly in arrival order. The scheduler
  may delay the head of a connection; it chooses freely only **among connections**.
- Admitting each operation is itself a scheduling decision, enumerated by `exhaustive`.
- Quiescence tracks four states per operation: `held`, `reply-pending`, `running`, `done`.
  Admission and quiescence both time out and record a `forced` decision.
- `WATCH…EXEC/DISCARD/UNWATCH` and `MULTI…EXEC` are blocks on their connection.
- A soundness checker runs on every trace and rejects any run that broke per-connection order or
  sent a command before a reply it depends on.
- On a multiplexed client (the C# cart), this makes some real schedules unreachable. That is a
  *false-negative* risk, which we state; it is never a false positive.

**3.2 Contract-first oracle (fixes R2–R4).** Each target spec gets a `contract` block, approved by
the owner, with a cited source (API docs, docstring, issue, or our own spec for fixtures):
- *State invariants*, the handoff's independent expected-state check. Example for the cart:
  "after `AddItem(u, p, q)` calls that returned OK, the quantity of `p` in `GetCart(u)` is the
  previous quantity plus the sum of their `q`". These are the primary oracle.
- *Atomicity declarations*: which operations must be serializable with which.
  Serial-equivalence applies only to those operations and only to the contract's declared
  fields.
- *Allowed anomalies*, such as last-writer-wins fields, retryable aborts, or idempotent retries.
- *Error semantics*: every non-OK status is `info` unless the contract declares a status as
  "no effect".
- Serial orders must respect real-time order (linearizability when one operation returned before
  another started).

Results that break serializability but no contract clause are reported as **observations**, never
as bugs. The negative controls must include at least one **weak-contract** service (for example,
documented last-writer-wins) that must PASS.

**3.3 Muse's role (fixes R11; owner decides, see A3).** Three jobs, each measured separately:
1. **Experiments, for the research question.** Workload, setup, and schedule hint, with no failing
   schedules in the prompt. Ablations separate workload from hint. The research question stays as
   the handoff states it.
2. **Contract and catalog drafting.** From source, Muse drafts the operation catalog, setup recipes,
   and candidate contract clauses with citations to code lines. A human approves or edits each one.
   Metric: fraction accepted unchanged, and edits needed. This tackles the hardest practical
   problem in the prior art (writing the oracle). The model is never the final oracle, because
   the human approves and the check is deterministic.
3. **Explanation** of verified traces, with every code reference machine-checked (P0-minimal).

Muse's role is then substantive for judging stage 1 even if (1) shows no efficiency gain.

**3.4 Evaluation (fixes R5, R6, R8, R9).**
- **Methods:** M0 stress (recorded through the proxy so its command order can be replayed),
  M1 random, M3+ conflict-directed **with greybox setup search** (setup sequences grown by new
  key/command coverage seen at the proxy), M4 Muse, A2 Muse without source. M2 (PCT) and A1 only
  if time allows: with partial-order reduction, `exhaustive` covers our workload sizes.
- **Targets:** 6 held-out buggy services, 2 correct, 1 weak-contract, and 1 equivalent mutant.
  Prefer real before/after Redis race fixes from open-source history where any are found
  (Q-E3). Base services are written by someone other than the prompt author, or generated by a
  sealed-seed script.
- **Accounting:**
  - Primary E₁ = search executions (concurrent runs plus M3+ profiling and setup runs).
  - Co-primary = wall-clock time including model latency, and dollars (tokens plus
    container-seconds).
  - Oracle serial runs are computed identically for every method and reported separately.
  - 20 trials for every method.
  - Workload and domain sizes are pre-registered per target.
- **Corrected versions:** the same workload explored exhaustively on the fixed build must PASS.
  For #3824: a cart image built in a container from PR #3825's cart changes.
- **Verified** means 20/20 replays with identical trace hashes. Anything less is reported as
  "reproducible k/20".
- **Pilot first:** run the Oct 29 value checkpoint on dev targets, then freeze the
  pre-registration, then run the held-out set.

**3.5 Sandbox (fixes R10).**
- The executor and proxy run as containers on the `internal: true` network.
- The host orchestrator (the only process with the API key and internet) sends experiment JSON
  to the executor over stdin and reads size-capped JSON results from stdout.
- Docker Desktop file sharing is restricted, and `.env` is never bind-mounted.
- A Compose lint rejects `privileged`, `network_mode: host`, `cap_add`, `docker.sock`, and
  writable bind mounts.
- Images are built from source at the pinned commit inside a builder container. Network is
  allowed at build time only.

**3.6 Revised order (fixes R7), aligned with the handoff.**

| Day | Goal | Gate |
|---|---|---|
| Oct 28 (today) | **Tracer bullet on fixture D2** (Python + redis-py, documented contract "no increment is lost"): FIFO proxy, exhaustive + random search, oracle, replay, **one Muse planner call** without the schedule, corrected variant (`INCR`) explored exhaustively → PASS, costs recorded. Attend Agents 102 (12–1 PM ET). | End to end on one fixture, or the blocker is named. |
| Oct 29 | Precondition fixture D3; M1, M3+, M4 loop; **value checkpoint pilot** (5 trials each on D2 and D3). Bring up the OTel cart from source in the sandbox. | Owner reviews pilot numbers and decides go, re-scope, or pivot of the claim. |
| Oct 30 | **External defect:** #3824 scenario A on the real cart through the proxy; #3825-patched cart explored exhaustively → PASS. Muse contract and catalog drafting for the cart. | **Kill gate:** a verified violation on at least one target, else cut to fixtures plus stress. |
| Oct 31 | Prompt freeze; held-out set sealed (hash committed); controls including weak-contract. | Freeze hashes recorded. |
| Nov 1–2 | Held-out evaluation; analysis; minimizer and timeline if time allows; reproducibility docs. | G3 as before. |
| Nov 3 | Freeze; record the 3-minute video. | — |
| Nov 4 | Repository published (with approval) and submitted by 6 PM ET. | — |

## 4. Decisions the owner must make before Phase 1

| ID | Decision | Recommendation |
|---|---|---|
| A1 | Adopt the corrected proxy rule (§3.1) | Yes. This corrects an error; it is not a preference. |
| A2 | Contract-first oracle, with an owner-approved contract per target (§3.2) | Yes. |
| A3 | Muse's three roles (§3.3); research question kept exactly as in the handoff | Yes. |
| A4 | Revised day order, with the value checkpoint Oct 29 and the kill gate Oct 30 (§3.6) | Yes. |
| A5 | Reduced evaluation scope and the accounting rules (§3.4) | Yes. |
| A6 | Build the cart and a #3825-patched cart from source inside a builder container, with network at build time only | Yes. Needed to know which code we test. |
| A7 | Executor inside the internal network; host orchestrator over stdin/stdout (§3.5) | Yes. |
| A8 | Model budget cap (≈ $100 of $150) and a spend alert | Yes. |
| A9 | No public actions without separate approval: no comment on #3824, no GitHub remote yet | Yes. |
| A10 | Team roster (≤ 4), owners of W1–W4, and the held-out author (not the prompt author) | Needed today. |
| A11 | Commit these review corrections to `main` | Yes, after approval. |

## 5. Applied before approval (factual corrections only)

- `HACKATHON_COMPLIANCE.md`: participant-guide rules (public repository, 3-minute video, new
  contributions, judging stages, discouraged categories); Agents 102 session; Claude and partner
  credits; verified structured-output and caching facts; submission checklist.
- Valkey pin and image caveat (`ARCHITECTURE.md` §4, `PROBLEM.md` §3, `RESEARCH_LOG.md`).
- REINS described fairly (`ARCHITECTURE_OPTIONS.md`, `PRIOR_ART.md`, `ADVERSARIAL_REVIEW.md`).
- Structured-output schema rules (`ARCHITECTURE.md` §8.3).
- Errata banners on `ARCHITECTURE.md` §5 and §6, and on `EVALUATION_PLAN.md`, pointing here until
  the owner approves the rewrite.
- README wording (designed behavior vs. demonstrated behavior); `.env.example` section reference;
  open questions answered (Q-M1 partly, Q-M4); research log entry for 2026-10-28.

Design changes in §3 are **not** applied to the architecture and evaluation documents until the
owner approves them.
