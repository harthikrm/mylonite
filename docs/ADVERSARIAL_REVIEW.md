# Adversarial Design Review

Purpose: attack Mylonite as a skeptical reviewer would, before we spend eight days on it. Each
attack lists the evidence, our response, and what is left over. Sources are in `PRIOR_ART.md`.
This review changed the project. It moved the model's role from choosing interleavings to
choosing workloads, added a non-LLM conflict-directed baseline, and made #3824 a
development-only target.

## 0. The strongest arguments against Mylonite, ranked

1. **The model may add nothing measurable.** For the bugs in scope (2 operations, ~3 store
   commands each), exhaustive enumeration of interleavings takes a handful of executions, and a
   proxy-level read/write profile finds conflicting operation pairs without any model. On the
   OTel cart, a random pair of `AddItem` calls on a 2-user domain collides half the time.
   *If this holds on the held-out set, Muse's contribution to discovery is zero.*
2. **The headline bug is not ours to discover.** #3824 is public, with root cause, reproduction
   steps, and a complete fix PR. The model may have memorized it. Any "Mylonite found it" framing
   is indefensible.
3. **It is narrow.** Store-mediated races over RESP are one slice of concurrency bugs. In-memory
   races, deadlocks, distributed faults, and SQL isolation are all out of scope for P0.
4. **The closest prior work appeared this month and already beats strong baselines, slightly.**
   REINS (Oct 2026) does LLM-guided controlled scheduling, and Fray exposes an LLM scheduling
   interface. A judge who knows them will ask what is new.
5. **"Non-serializable" is not always "bug".** Some APIs are intentionally last-writer-wins or
   eventually consistent. A spec-free oracle can flag designed behavior.
6. **Determinism at the wire is empirical, not guaranteed.** Multiplexed clients, timers, and
   background work in the service can make replays diverge.
7. **The benchmark is ours.** Held-out bugs written by the team, using textbook mutation
   operators, look like textbook bugs, which is exactly what LLMs are good at recognizing.

Why we still proceed: arguments 1, 2, 4 and 7 are addressed by evaluation design, not by
argument. Argument 3 is accepted as scope. Arguments 5 and 6 are addressed by labeling and
measurement. If argument 1 holds, the project still delivers deterministic, spec-free
reproduction of a real unfixed bug class in unmodified services, and an honest negative result
on model guidance. We consider that a legitimate frontier result, though less flashy.

## 1. Technical feasibility

| Attack | Evidence | Response | Residual |
|---|---|---|---|
| *Can we reliably control schedules?* | No mature Python scheduler exists. Thread-level control needs per-runtime tools (Fray, Coyote, Loom). | We do not control threads. We control the order in which data commands reach a single-threaded store. Delay-only rules (`ARCHITECTURE.md` §5.2) keep every schedule reachable in reality. | Multiplexed connections (StackExchange.Redis, ioredis) need execution order separated from reply order. Validated by gate G1 with a fallback. |
| *Can we detect incorrect outcomes without inventing requirements?* | Writing models for Porcupine or Knossos takes effort; LLM-invented invariants are unreliable. | Serial-equivalence (Line-Up idea): compare against every serial order of the same requests, masking fields that vary between identical serial runs. No requirement is invented; the system is compared with itself. | Flags intentional weak-consistency designs. We report "non-serializable outcome", not "bug". |
| *Which languages and runtimes are realistic?* | Docker, Python 3.14, and Node 26 installed; no Go or Java. | Service language does not matter (wire level). Harness in Python. Dev fixtures in Python and Node. | Protocol, not language, is now the constraint: RESP2 only in P0. |
| *What instrumentation is necessary?* | — | None in the service. A proxy in the store path, plus a target spec. | Services that cache state in memory between requests break the reset assumption; checked per target. |
| *Can we produce reproducible failure traces?* | `seed` deprecated; model non-deterministic. | Reproducibility comes from recorded schedule files and pinned images, never from re-querying the model. Model I/O is recorded for the search itself. | Replay rate is measured, not assumed. |

## 2. Research validity

| Attack | Evidence | Response | Residual |
|---|---|---|---|
| *Does an LLM genuinely improve schedule exploration?* | Random scheduling found 27 SCTBench bugs within 2 schedules. REINS beat the best baseline by 1 program in a single run. | We **do not claim** it improves interleaving search. Schedule hints are measured (ablation A1) but expected to be negligible. The claim under test is workload selection. | Workload selection may also show no gain; reported as is. |
| *Could deterministic or randomized testing find the same defects faster?* | Yes, for shallow bugs (Thomson et al.; Lu et al.). | M1, M2, and M3 are run on every target under equal budgets; shallow targets are mandatory in the held-out set; cost-adjusted results reported. | — |
| *How do we avoid giving the model the answers?* | #3824 is public; Defects4J and SWE-bench memorization is documented. | #3824 is development only; obfuscated-source ablation (A3); held-out services are new code, sealed, hash-committed, authored after the prompt freeze, with comments stripped and neutral identifiers. | Training cutoff of `muse-spark-1.3` is unknown. |
| *How do we prevent evaluator contamination and confirmation bias?* | Klees et al.: problems in all 32 fuzzing evaluations examined. | Pre-registered plan and analysis script; verdicts from oracle and replay only; distinct bugs attributed by fix toggles; all trials reported. | Team members can still unconsciously shape fixtures. The composition rules are fixed before authoring. |
| *What is the strongest realistic baseline?* | ACIDRain's conflict analysis; Lincheck and Fray random scenarios. | **M3, conflict-directed systematic search**: dynamic per-key read/write sets from the proxy, enumerate conflicting pairs and triples with colliding arguments, exhaustive interleavings. No model. | M3's argument sampling is our design; a better-engineered M3 could do even better. We will publish it. |
| *Is the held-out benchmark representative?* | Mutation operators produce textbook patterns. | Composition rules (size, preconditions, shallow share) plus the R1/R2 real-world stretch targets. | Generalization beyond our benchmark is **not** claimed. |

## 3. Product value

| Attack | Response | Residual |
|---|---|---|
| *Who would use it?* | Backend teams on Redis/Valkey-backed services (carts, quotas, inventory, locks); reviewers of fixes; maintainers receiving race reports (`PROBLEM.md` §4). | Not validated with any real user. Q-P3. |
| *What expensive problem does it solve?* | Turning "intermittent, can't reproduce" into a replayable counterexample, for a class of bugs existing detectors cannot see. | No quantitative cost evidence (Q-P1, Q-P2). |
| *How does it fit a workflow?* | Local run against Compose → verified counterexample → fix → replay file becomes a regression test. CI integration is P2. | Writing the target spec is friction; generation from proto or OpenAPI reduces it. |
| *Why not an existing tool?* | Thread-level testers cannot see store state; TSan cannot see non-data races; Jepsen targets databases and is heavy; Antithesis is sales-gated; load tests lack an oracle and reproducibility. | A team could hand-write a Jepsen-style test for their one critical path. For a single known path, that is a fair alternative. |
| *What evidence would justify adoption?* | Verified, replayable counterexamples on real code, zero false positives on correct controls, and a fix check. | Requires more real-world targets than we can reach in 8 days (R2 is P1). |

## 4. Hackathon viability

| Attack | Response | Residual |
|---|---|---|
| *Meaningful technical progress by Nov 4?* | P0 is deliberately small: proxy, scheduler, oracle, strategies, one real bug, evaluation. Gates G0–G3 with explicit fallbacks (`ROADMAP.md`). | The proxy on a multiplexed client is the single biggest risk. Fallback A exists. |
| *Can a judge understand it in three minutes?* | "Two people add to cart at once and an item vanishes. Here is the exact order of writes that causes it, proven against every serial order, on the real unmodified service. Here is how Muse chose what to test, and how it compares with simpler methods." | The baseline comparison must fit one chart. |
| *Does Muse play a substantive role?* | Reads a service in any language; proposes workloads with valid setup; explains verified traces with checked line references. Its contribution is measured, not asserted. | If the measurement is null, the 25% tooling criterion is weaker. That is honest, and the explanation and precondition story still uses the model. |
| *Can the whole demo run reliably?* | Pinned images, recorded replay files, recorded model I/O as fallback, rehearsed on a clean machine. | Live Docker on a laptop during judging is a risk. A recorded video is the primary artifact. |
| *What is the smallest compelling product?* | One command: point Mylonite at the OTel cart → verified lost-update counterexample in under a minute → replay 20/20 → the baseline chart. | — |

## 5. Things that would make us stop or pivot

- G1 fails on both the wire and the in-process fallback by Oct 30: no controlled reproduction is
  possible in time. **Pivot**: stress-based reproduction plus the serial-equivalence oracle, with
  the model choosing workloads. The claim shrinks to "spec-free detection".
- Muse cannot produce valid plans after schema simplification (G2). **Pivot**: model as ranker
  over M3 candidates (A4).
- Any false positive on a correct control that we cannot explain as a harness bug. **Stop
  claims** until fixed; the oracle is the product's foundation.
