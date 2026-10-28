# Mylonite

**Change the order. Reveal the fault.**

Mylonite is a proposed concurrency-testing tool for services that keep shared state in a data
store. It is designed to control the order in which a service's store commands run, to check
each outcome against the service's stated contract, and to use Meta's Muse Spark model to decide
which requests to race. By design, every failure it reports is reproduced from a recorded
schedule, and a model never decides what counts as a failure. None of this has been built or
run yet.

Team **MetaMorphic**, for the Meta AI Developer Hackathon (Oct 27 – Nov 4, 2026), theme
*Push the Frontier*, Indie Developer track (pending confirmation).

## Status

**Phase 0 complete: research, architecture, threat model, and evaluation design. No application
code exists yet.** Nothing described below has been run. A review on 2026-10-28
([docs/PHASE0_REVIEW.md](docs/PHASE0_REVIEW.md)) found two design errors: within-connection
reordering in the proxy, and serializability imposed as every target's contract. The team
approved the corrections, and Phase 1 began with a tracer bullet on a fixture.

## The problem in one example

The OpenTelemetry Demo's cart service (C#) stores each cart as one blob in Valkey. `AddItem`
reads the blob, adds the item in memory, and writes the blob back. Two `AddItem` calls at the same
moment both read the old cart, and the second write erases the first item. The bug is
[open-telemetry/opentelemetry-demo#3824](https://github.com/open-telemetry/opentelemetry-demo/issues/3824).
It is open, its fix PR was closed as stale, and the code is unchanged in release 3.1.0. Unit
tests pass, and race detectors see nothing, because there is no data race in any process. The
"shared memory" is a key in Valkey. Details: [docs/PROBLEM.md](docs/PROBLEM.md).

## How it is meant to work

```
 Muse Spark ──► proposed experiment (validated JSON: which requests, which arguments, which setup)
                          │
 harness ──► service under test (unmodified, any language, in a sandbox)
                          │ store commands
                 Mylonite proxy  ── decides the order commands reach Valkey (delay only)
                          │
 oracle: does the outcome break the service's approved contract?
        yes ──► replay the recorded schedule 20× ──► verified counterexample
```

- **Delay-only control.** The proxy never alters commands. It only delays them, so every schedule
  it produces could happen in production through ordinary network delay.
- **Contract first.** Each target's correctness contract is approved by a human, cites its
  source, and may be drafted by Muse. No invariant is invented.
- **The model chooses; it never writes code that runs.** Muse's output is validated data. The
  verdict comes from deterministic code.

Design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Alternatives considered:
[docs/ARCHITECTURE_OPTIONS.md](docs/ARCHITECTURE_OPTIONS.md).

## Central hypothesis, and what would falsify it

> Under equal execution budgets and the same oracle, Muse-guided **workload selection** reaches a
> first verified non-serializable outcome in fewer executions than stress testing, random or PCT
> scheduling, and a conflict-directed systematic search that uses no model, especially when the
> bug needs a semantic precondition.

We expect the model **not** to help on shallow bugs, where simple search is already very fast;
the OTel cart bug is one of them. We will publish the comparison either way, including if the
model loses. Protocol, baselines, contamination controls, and stop/go gates:
[docs/EVALUATION_PLAN.md](docs/EVALUATION_PLAN.md).

## Boundaries

In scope first: races mediated by Valkey/Redis (RESP2), such as lost updates, check-then-act,
destructive overwrites, non-atomic multi-key updates, and unsafe store-based locks, in services
written in any language.

Not in scope: in-process data races and deadlocks (use ThreadSanitizer, the Go race detector,
Fray, Loom, or Shuttle), SQL isolation inside the database engine, and crash or partition faults
(use Jepsen or Antithesis).

Mylonite is a **defensive** tool for testing code you own or are authorized to test, in local
disposable sandboxes with synthetic data.

## Intended demonstration (3 minutes)

1. Two concurrent "add to cart" requests on the real, unmodified OpenTelemetry Demo cart; one
   item disappears.
2. Muse reads the C# source and proposes the experiment.
3. The proxy timeline shows the exact command order; the observed quantity matches no serial
   order; replay reproduces it 20 times out of 20.
4. One chart: executions to first verified failure for each method on held-out bugs, including
   cases where Muse did not help.

#3824 is public and may be in the model's training data, so it is a **reproduction** showcase,
not a discovery claim. Claims about effectiveness come only from the sealed held-out benchmark.

## Documents

| Document | Contents |
|---|---|
| [PROBLEM.md](docs/PROBLEM.md) | The failure class, #3824 in detail, users, and why it is costly |
| [PRIOR_ART.md](docs/PRIOR_ART.md) | What is solved, what is hard, competitors, and differentiation, with sources |
| [ADVERSARIAL_REVIEW.md](docs/ADVERSARIAL_REVIEW.md) | The strongest arguments against Mylonite and our responses |
| [ARCHITECTURE_OPTIONS.md](docs/ARCHITECTURE_OPTIONS.md) | Three architectures compared and the recommendation |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, proxy semantics, oracle, model interfaces (provisional) |
| [THREAT_MODEL.md](docs/THREAT_MODEL.md) | Assets, trust boundaries, abuse cases, sandbox, acceptance checklist |
| [EVALUATION_PLAN.md](docs/EVALUATION_PLAN.md) | Pre-registered experiments, metrics, statistics, stop/go gates |
| [ROADMAP.md](docs/ROADMAP.md) | Day-by-day plan to Nov 4 with cutoffs and fallbacks |
| [DECISIONS.md](docs/DECISIONS.md) | Decision log |
| [RESEARCH_LOG.md](docs/RESEARCH_LOG.md) | Dated findings: facts, hypotheses, assumptions |
| [HACKATHON_COMPLIANCE.md](docs/HACKATHON_COMPLIANCE.md) | Rules, Meta API terms, budget, submission checklist |
| [OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md) | What must be answered before and during Phase 1 |
| [PHASE0_REVIEW.md](docs/PHASE0_REVIEW.md) | Independent review of Phase 0: errors found, proposed corrections, decisions pending |

## Repository conventions

- `docs/` holds documentation. Application code (`src/`), throwaway spikes (`experiments/`), and
  evaluation code (`eval/`) stay separate (`ARCHITECTURE.md` §10).
- Third-party code is never vendored; targets are referenced by pinned commit and image digest.
- Secrets live only in a local `.env` (git-ignored); see `.env.example`.
- AI coding assistants were used to prepare this repository, and this will be disclosed in the
  submission.

## License

To be decided before publication (Apache-2.0 proposed; see `docs/DECISIONS.md`, D-016).
