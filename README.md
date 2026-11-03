# Mylonite

**Change the order. Reveal the fault.**

Mylonite tests services that keep shared state in Redis or Valkey for concurrency bugs that unit
tests and race detectors miss. So far it has found lost updates (on held-out and real targets)
and a check-then-act race (on a development fixture).

**Meta's Muse Spark (`muse-spark-1.3`, Standard mode, `reasoning_effort` medium) is the planner.**
- **What Muse does:** it reads the service's source and its operation catalog, then proposes
  experiments as strict-schema JSON: which requests to race, after which setup, and in which
  order their store commands should run.
- **What runs them:** a delay-only proxy controls the order in which the service's commands
  reach the store.
- **Who decides:** a contract oracle, in plain code, decides whether an outcome is a bug. Muse
  never does. Every bug is replayed 20 times, with an identical trace, before it is reported.

**What we found** (pre-registered, on 2 bugs generated after our method freeze):
- Muse needed a median of **1 execution** to find each bug. The best non-AI method needed
  **764** and **97**.
- But one execution costs about 9 ms there. So the systematic search was still **faster and
  cheaper**, and Muse lost on time and dollars.
- No method raised a false alarm on the 200 control trials.

[Results](#results) · [Limitations](#limitations) · [Reproduce](#reproduce) ·
[Full held-out report](experiments/heldout-v1-analysis/RESULTS.md)

Team **MetaMorphic**, Meta AI Developer Hackathon, *Push the Frontier*. Built Oct 27 – Nov 4,
2026 (the team's building period); the submission deadline is Nov 4.
**Status:**
- built and evaluated;
- the repository is local, and not yet public;
- the license is to be decided (Apache-2.0 proposed, D-016).

## The problem

Two requests each read a value from the store, compute, and write it back. The second write
erases the first.
- **A real example:** in the OpenTelemetry Demo's C# cart service, two concurrent "add to cart"
  calls lose an item. The bug is
  [open-telemetry/opentelemetry-demo#3824](https://github.com/open-telemetry/opentelemetry-demo/issues/3824),
  still open when last checked on Nov 1.
- **Why tools miss it:** unit tests run one request at a time. Memory race detectors see nothing,
  because the shared state is a key in Valkey, reached over a socket.
- Details: [docs/PROBLEM.md](docs/PROBLEM.md).

## How it works

```
 Muse Spark ──► experiments as strict-schema JSON (setup, concurrent calls, a command-order hint)
                          │ validated against the same search space every method uses
 harness ──► service under test (unmodified, in a Docker sandbox)
                          │ store commands
                 Mylonite proxy ── decides when each command reaches Valkey (delay only)
                          │
 oracle (code): does the outcome break the service's contract?
        yes ──► replay the schedule 20× with one trace hash, check the corrected version ──► verified
```

- **Delay-only control.** The proxy never alters a command. It only decides when each one
  runs, so every schedule it produces could happen in production through ordinary delay. It
  frames RESP2 and RESP3.
- **Contract first.** Each target has a written contract. The oracle's invariant kinds are code,
  and a contract only selects them.
- **What Muse sees:**
  - the catalog, value domains and contract;
  - the source, with comments removed;
  - from round 2, feedback on its own experiments.

  Up to 5 rounds, with up to 3 experiments per round. A contamination audit refuses any request
  that contains test labels, fixture IDs, search artifacts, or code found only in the corrected
  version.
- **The model chooses; it never writes code that runs.** Its output is validated data, and the
  verdict comes from deterministic code.

Design: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Results

### Held-out bugs: the only source of effectiveness claims

**Setup.**
- Two base services were written after the method freeze, committed and timestamped.
- A public [drand](https://drand.love) randomness round, published afterwards, chose one
  mutation site in each.
- The mutants were sealed outside the repository, and not opened before the results were
  committed. The blindness is procedural: with the beacon value and the frozen script, the
  developer could have worked out each site.
- 20 trials per method per target.
- Muse is "better" only if it beats every conventional method. The tests are exact Mann–Whitney,
  with Holm correction.

Both bugs turned out to be lost updates.

Median executions to the first verified bug (E₁), with 95% bootstrap intervals. "Not reached"
means more than half the trials failed.

| Method | `alpha_m` | `beta_m` |
|---|---|---|
| **M4: Muse with source** | **1** [1, 1] (20 of 20) | **1** [1, 1] (19 of 20) |
| A2: Muse without source | 401 [254, not reached] (13 of 20) | 137 [137, 201] (19 of 20) |
| M3+: conflict-directed systematic search | 764 [546, 856] (17 of 20) | 97 [82, 127] (20 of 20) |
| M3+arg: argument-aware M3+ | 764 [546, 856] (17 of 20) | 97 [82, 127] (20 of 20) |
| M1: random search | not reached (0 of 20) | 292 [131, 582] (18 of 20) |
| M0: stress | not reached (0 of 20) | 205 [131, 300] (20 of 20) |

**Verdicts for M4 against the conventional methods:**
- **E₁: better** on both bugs (Holm p = 8.7e-11 and 2.0e-5).
- **Method-seconds and dollars: worse** on both (Holm p = 1.0e-7 and 8.7e-11).
  - A find costs M4 a median of 42–60 s and $0.03–0.05. M3+ needs 1–7 s, at under $0.001.
- **Break-even:** by the frozen formula, M4 would be faster only if one execution cost more than
  0.055 s (`alpha_m`) or 0.62 s (`beta_m`). The measured cost is 0.009 s.

**Muse without source (A2)** was never better than the conventional methods. It was worse on
time and dollars on both bugs, and also on E₁ on `beta_m`.

**Negative controls:** 200 trials on the unmutated bases, with 0 false positives.

Spend: $25.01 of Muse calls, over two held-out runs. Report:
[experiments/heldout-v1-analysis/RESULTS.md](experiments/heldout-v1-analysis/RESULTS.md).

### Development targets

These were known while the analysis rules were written, so they are never pooled with the
held-out results.
- **The real OpenTelemetry cart (#3824)** ([gate](experiments/2026-10-28-d1-gate/README.md),
  [baselines](experiments/2026-10-29-d1-baselines/RESULTS.md),
  [re-check](experiments/2026-11-01-d1-recheck/RESULTS.md)):
  - Reproduced under control and replayed 20 of 20 times. Without schedule control, 942 of 1,000
    natural races lost an update.
  - Stress found the bug in a median of 7 executions (n = 5), at 5–9 ms each.
  - Muse did not run there: its source view parses Python only, and the bug is public.
  - By our estimate, even a first-execution find would leave Muse short of break-even by at least
    230×. Verdict: AI guidance is not valuable on this target.
- **Two Python fixtures, written by the developer** ([pilot](experiments/2026-10-29-pilot/RESULTS.md),
  [no-source ablation](experiments/2026-10-28-a2-no-source/RESULTS.md),
  [stress](experiments/2026-10-30-m0-d2-d3/RESULTS.md), n = 5):
  - **Executions:** Muse with source found each bug on its first execution. The best
    conventional medians were 5 and 211.
  - **Without the source:** Muse also found the simpler fixture's bug at once, and the other at
    a median of 71.
  - **Wall-clock:** a conventional method still won on both.
  - The prompt's list of hypothesis kinds is the developer's prior, and it names these bug
    classes.

### What this means

- **Where Muse helped:** with the source, it picks the right experiment almost at once. On the
  held-out bugs, without the source, it was no better than conventional search. We think it
  reads the faulty line, which is a hypothesis.
- **When it could pay off:** when executions take milliseconds, a fast systematic search beats a
  model call that takes 40 seconds. By the frozen break-even, Muse could be faster only if an
  execution cost more than 0.055–0.62 s. We did not test such targets.
- **What this does not show:** Muse repeats nearly the same plan from trial to trial. So 20
  trials on one bug measure its reliability on that bug, not that it generalizes.

## Limitations

- **Single developer.** The two held-out defects were generated by mechanical mutation of base
  services written after the method freeze, at sites chosen with a public randomness beacon. No
  independent author was involved.
- **Deviations from the plan, which apply to every held-out result above** (`FREEZE.md` §5):
  - 2 held-out bugs, instead of the 6 planned;
  - no weak-contract control and no equivalent mutant;
  - Python services with per-connection clients only;
  - no guaranteed shallow stratum, which is where baselines were expected to win;
  - no decoy edits: the mutated lines are the only non-atomic counter update in each file, which
    favors Muse;
  - the mutation script, the held-out runner and the ground-truth script were written after the
    freeze.
- **Timing and trust:**
  - The method freeze was 5 hours late.
  - The freeze manifests are not anchored externally, so the freeze time is self-asserted. The
    base services' commitment has a FreeTSA timestamp from before the beacon round.
- **The held-out run was restarted once,** after a harness defect (AM-002). Every `beta_m` cell
  and all the controls include post-observation trials from the restart. The restart alone gives
  the same confirmatory verdicts.
- **Found at the reveal:** the mutation tool reformats the whole mutant file. Its style is
  uniform, and no method sees a mutant and its base in the same trial.
- Full list: [docs/SUBMISSION.md](docs/SUBMISSION.md) ("Limitations, disclosed") and the held-out
  [report](experiments/heldout-v1-analysis/RESULTS.md).

**Scope.**
- **What it tests:** races mediated by Redis/Valkey.
- **What it does not test:** in-process data races, deadlocks, SQL isolation, or crash and
  partition faults.
- **How to use it:** Mylonite is a **defensive** tool, for code you own or are authorized to
  test. Run it in local, disposable sandboxes with synthetic data.

## Reproduce

**Requirements:**
- Python 3. The host-side harness uses the standard library only; we ran Python 3.14.
- Docker, for the sandboxed executor and Valkey.
- A Meta Model API key, only for new Muse calls. Copy `.env.example` to `.env`. The key is never
  passed into a sandbox.

```bash
python3 -I -m unittest discover -s tests
```

```bash
python3 freeze/manifest.py check
```

```bash
python3 experiments/heldout-v1-analysis/analyze_heldout.py
```

- **The first command** runs the 129 unit tests, with no Docker needed. 2 tests are skipped
  unless `grpcio` is installed.
- **The second** checks the HEAD commit against the latest method-freeze manifest (v1.2).
- **The third** recomputes every held-out verdict from the committed C5 results, with no Docker
  and no API call. It rewrites the reports in place.
  - The three reports come out byte for byte the same; `git diff` then shows only the commit id
    recorded in `inputs.json`.

```bash
python3 experiments/2026-10-29-pilot/run_pilot.py --replay-model experiments/2026-10-29-pilot/results/20261028-165020/model_calls.jsonl
```

- **This command** re-runs the 30-trial development pilot with Docker, answering Muse's calls from
  its recorded responses, so it makes no API call.
  - It needs a clean tree and the executor image. Build the image first with
    `docker build -t mylonite-exec:dev -f docker/executor.Dockerfile docker`, the same command
    `Sandbox.build_executor_image` runs.
  - It writes a new results directory under `experiments/2026-10-29-pilot/results/`.
  - A record of one such replay: [experiments/2026-11-03-pilot-replay/](experiments/2026-11-03-pilot-replay/README.md).
- **The demo video** has not been made yet. The pilot replay and the D1 gate are the replayable
  demonstrations.
- **Not reproducible yet:**
  - re-running the held-out trials needs the sealed held-out directory, which is published only
    with the owner's approval;
  - it also needs an API key, and costs about $20.
- **The D1 cart** is built from the upstream source at a pinned commit; see the
  [gate README](experiments/2026-10-28-d1-gate/README.md).

## Built during the hackathon, and used but not built

**Built** (first commit `b120740`, Oct 28, 2026):
- the proxy and scheduler;
- the oracle;
- the sandboxed executor;
- the Muse planner client and contamination audit;
- the baselines M0, M1, M3+ and M3+arg, and the A2 ablation;
- the pre-registered analysis;
- the held-out tooling, the fixtures and the held-out bases.

**Used, not built.** A license marked "to confirm" must be checked before publication.
- the Meta Model API (Muse Spark), under Meta's Model API terms;
- the OpenTelemetry Demo (Apache-2.0), pinned at tag `3.1.0` and not vendored.
  - Its NuGet packages are pinned by version, not by hash.
  - The corrected cart build uses PR #3825's cart change.
- Python packages, with licenses from their package metadata: `redis` 8.1.0 (MIT), `grpcio`
  1.84.0 (Apache-2.0) and `typing-extensions` 4.15.0 (PSF-2.0);
- container images, all pinned by digest, licenses to confirm: Valkey 9.0.4, `python:3.13-slim`,
  and the .NET SDK 10.0.401 and runtime-deps images;
- Docker;
- drand, FreeTSA and OpenTimestamps.

**AI assistance:** an AI coding assistant (Claude Code, by Anthropic) wrote most of this
repository's code and documents, under the developer's direction and approval.
- It proposed the analysis rules and wrote the held-out base services.
- Reviews called "independent" were done by separate AI agents, not by people.
- It is not part of Mylonite's runtime: Muse is the only model Mylonite calls.

## Documents

| Document | Contents |
|---|---|
| [heldout-v1-analysis/RESULTS.md](experiments/heldout-v1-analysis/RESULTS.md) | The held-out results, sensitivity analyses and independent review |
| [SUBMISSION.md](docs/SUBMISSION.md) | The hackathon submission text (draft) and its full list of limitations |
| [FREEZE.md](docs/FREEZE.md) | The method freeze: what is frozen, the analysis rules, the stop rules |
| [HELDOUT_PROTOCOL.md](docs/HELDOUT_PROTOCOL.md) | How the held-out bugs were built, sealed and revealed |
| [AMENDMENTS.md](docs/AMENDMENTS.md) | Changes after the freeze, including the AM-002 restart |
| [EVALUATION_PLAN.md](docs/EVALUATION_PLAN.md) | Methods compared, metrics, statistics, deviations |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, proxy semantics, oracle, model interface |
| [THREAT_MODEL.md](docs/THREAT_MODEL.md) | Sandbox, trust boundaries, abuse cases |
| [PROBLEM.md](docs/PROBLEM.md) and [PRIOR_ART.md](docs/PRIOR_ART.md) | The failure class, #3824, related work |
| [DECISIONS.md](docs/DECISIONS.md) and [RESEARCH_LOG.md](docs/RESEARCH_LOG.md) | Every decision, and dated findings labeled as fact or hypothesis |
| [HACKATHON_COMPLIANCE.md](docs/HACKATHON_COMPLIANCE.md) | Rules, Meta API terms, submission checklist |

## License

To be decided before publication. Apache-2.0 is proposed; see
[docs/DECISIONS.md](docs/DECISIONS.md), D-016.
