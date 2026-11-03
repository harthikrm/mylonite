# Hackathon submission text (draft)

**Status: draft for the owner. Not submitted, and nothing is public.** The portal's form fields are
not visible in advance (`HACKATHON_COMPLIANCE.md` §1), so the text comes in sections to paste in
as the form asks. `[TODO]` marks what only the owner can fill in. Every number is tied to a
results file under "Sources". An independent fact-check (an AI agent, not a person) found 20
problems in the first draft; all are corrected here.

---

## Name

**Mylonite**, by team MetaMorphic. Meta AI Developer Hackathon, *Push the Frontier*, Indie
Developer track `[TODO: confirm the track]`.

## Tagline

Change the order. Reveal the fault.

## One-line description

Mylonite uses Muse Spark to choose which requests to race against a Redis-backed service. It
proves every bug with a replayable schedule, and it measures, against strong non-AI baselines,
when the model's choice is worth its cost.

## Short description (about 130 words)

Two correct request handlers can still lose data when they run at the same moment against a
shared Redis or Valkey key. Unit tests and race detectors miss this kind of bug: there is no
data race in any process.
- **What Mylonite does:** it puts a delay-only proxy in front of the store and controls the
  order the service's commands reach it. Muse Spark reads the service's source and proposes
  experiments as schema-checked JSON: which requests to race, with what setup, and in which
  command order.
- **Who decides:** deterministic code, never the model, decides what counts as a failure. Each
  failure is replayed 20 times before it is reported.
- **What we measured:** in a pre-registered evaluation on two bugs generated after our method
  freeze, Muse needed a median of 1 execution to find each one. The best non-AI method needed
  764 and 97. But one execution takes about 9 ms, so that systematic search was still faster and
  cheaper. We report both.
- **Limits:** this is a small, single-developer evaluation, with limitations listed below.

## Full description

### The problem

A lost update needs only two requests. Each reads a value from the store, computes, and writes
it back, so the second write erases the first.
- **A real example:** issue #3824 in the OpenTelemetry Demo is this bug, in the C# cart service.
  Two concurrent "add to cart" calls, and one item disappears. It was still open when last
  checked, on Nov 1.
- **Why tools miss it:** tests run requests one at a time. Memory race detectors see nothing,
  because the shared state is a key in Valkey, reached over a socket.

### How Mylonite uses Muse Spark

`muse-spark-1.3`, in Standard mode with `reasoning_effort` medium, is the only model in
Mylonite's runtime. In each trial, Muse gets up to 5 planning rounds.
- **What it sees:**
  - the service's operation catalog, value domains and correctness contract;
  - its source code, with comments and docstrings removed;
  - from round 2 on, feedback on its own earlier experiments.
- **The contamination audit:** before each request is sent, it is checked for test labels,
  fixture IDs, harness paths, search artifacts, and any identifier or line found only in the
  corrected code. A request with a match is refused.
- **What it returns:** up to 3 experiments per round, as JSON under a strict schema. Each one
  names a setup, the concurrent calls with their arguments, and a hint for the order in which
  the store commands should run.
  - Every experiment must pass the validator that defines the shared search space. The
    baselines draw only from that same space.
- **What it never does:** run code, or decide a verdict. The harness runs Muse's experiments
  through the proxy: the hinted order first, then other orders, up to 50 per experiment. A
  contract oracle in plain code decides.
- **Verification:** each violation is replayed 20 times with an identical trace hash, and it
  must not occur in the corrected version of the service.

### What we built during the hackathon

All code was written from Oct 28, 2026 on (first commit `b120740`):
- the delay-only proxy (RESP2 and RESP3 framing; it never re-encodes a byte) and its scheduler,
  with exhaustive enumeration of command orders, trace hashing and a soundness check;
- the contract oracle;
- the sandboxed executor;
- the Muse planner client and its contamination audit;
- four non-AI baselines:
  - stress (M0);
  - random search (M1);
  - a conflict-directed systematic search (M3+);
  - an argument-aware variant of it (M3+arg);
- a no-source ablation of Muse (A2);
- the pre-registered analysis code;
- the held-out tooling: mutation generator, runner and ground-truth search;
- two development fixtures, and two held-out base services.

### How we evaluated it

We wrote the plan before the results, and the evaluation could make Muse look bad:
- **A method freeze** fixed the prompt, the parameters, the budgets and every analysis rule
  before any held-out target existed. It is recorded as a manifest of file hashes, checked
  before every held-out run.
- **Two new base services** were written after the freeze and committed. A public drand
  randomness round, published after that commit, then chose one mutation site in each. The
  mutants were sealed outside the repository, and nobody opened them until the results were
  committed.
- **Strong baselines.** Muse counts as better only if it beats every conventional method,
  including the systematic search built for this bug class.
- **Three metrics, never combined:** executions to the first verified violation (E₁),
  method-seconds, and dollars. Each gets an exact Mann–Whitney test, with Holm correction.
- **Negative controls:** each unmutated base service is run as a control. Any violation there is
  a false positive.
- **Scale:** 20 trials per method per target.
- **Spend:** $25.01 of Muse calls over both held-out runs, and $25.45 including development.

### Results on the held-out bugs

These are the only effectiveness claims. Both bugs turned out to be lost updates.

| | `alpha_m` (guarded site) | `beta_m` (unguarded site) |
|---|---|---|
| Muse with source (M4), median E₁ | **1**: 20 of 20 found at execution 1 | **1**: 15 of 20 at execution 1, 4 later (38–88), 1 failed |
| Best conventional method, median E₁ | 764 (M3+, 17 of 20 found) | 97 (M3+, 20 of 20) |
| M4 against the conventional baselines, E₁ | **better** (Holm p = 8.7e-11) | **better** (p = 2.0e-5) |
| M4, method-seconds and dollars | **worse** (p = 1.0e-7) | **worse** (p = 8.7e-11) |
| Muse without source (A2) | no significant difference on E₁; worse on seconds and dollars | worse on every metric |

- **Controls:** 200 trials on the correct bases gave 0 false positives.
- **The cost of a find:** M4's median is 42–60 s and $0.03–0.05. The systematic search's is
  1–7 s, at under $0.001.
- **Break-even:** by the frozen formula, M4 would be faster than every baseline only if one
  execution cost more than 0.055 s (`alpha_m`) or 0.62 s (`beta_m`). The measured cost is about
  0.009 s.
- **Errors count as failures.** One M4 and one A2 trial ended in a harness error, and count as
  failures.

### Results on the development targets

These were known while the rules were written, so they are never pooled with the held-out
results.
- **The real OpenTelemetry cart (#3824):** reproduced under control and replayed 20 out of 20
  times. With no schedule control, 942 of 1,000 natural races lost an update.
  - Stress testing found the bug in a median of 7 executions (n = 5, exploratory), at 5–9 ms
    each.
  - We did not run Muse there:
    - its source view parses Python only, so M4 cannot read the C# service under the freeze;
    - the bug is public, so a result would carry a memorization caveat;
    - our estimate shows that even finding it on the first execution, Muse would need
      executions at least 230× more expensive than they are to break even (230–420× in its
      best case).
- **Two Python fixtures, written by us** (n = 5 each):
  - **Executions:** Muse with source found each bug on its first execution in every trial. The
    best conventional medians were 5 (random search) and 211 (systematic search). Without the
    source, Muse also found the simpler fixture's bug on its first execution.
  - **Wall-clock:** a conventional method won on every development target. M4's median was
    12.6–14.2 s per find. The best conventional method's was under 2 s (0.05 s and 1.7 s).

### What we learned

- **Where Muse helped:** on these two mutants, Muse with the source needed a median of 1
  execution. In each mutant, the mutated line is the only non-atomic counter update.
  - We think Muse finds the bug by reading that line. That is a hypothesis, which the ablation
    supports: without the source, Muse was no better than conventional search.
- **When that pays off:** only when executions are expensive. When a test execution costs
  milliseconds, a fast systematic search beats a model call that takes 40 seconds.
- **What our tests can't say:** Muse repeats nearly the same plan from trial to trial. So 20
  trials on one bug measure how reliable it is on that bug, not whether it generalizes; that
  needs more bugs, not more seeds.

### Limitations, disclosed

- **Single developer.** The two held-out defects were generated by mechanical mutation of base
  services written after the method freeze, at sites chosen with a public randomness beacon. No
  independent author was involved.
- **AI assistance.** An AI coding assistant (Claude Code, by Anthropic) wrote most of the code
  and documents, under the developer's direction, with each decision approved by the developer.
  Every commit is co-authored by it.
  - It proposed the analysis rules and wrote the held-out base services, at the developer's
    request.
  - Reviews described as independent were done by separate AI agents, not by people.
  - It is not part of Mylonite's runtime: Muse is the only model Mylonite calls.
- **Smaller than planned:**
  - 2 held-out bugs from 2 bases, instead of 6 from 8;
  - both are lost updates, in small Python services using one connection per client;
  - no weak-contract control and no equivalent mutant.
- **Gaps that favor Muse:**
  - there were no decoy edits, and the mutated lines are the only non-atomic counter update in
    each file;
  - no stratum of shallow bugs, where baselines were expected to win, was guaranteed.
- **Found at the reveal, not disclosed before:** the mutation tool reformats the whole mutant
  file, so it looks different from its base. The style is uniform within a mutant, and no method
  sees both files in one trial.
- **Timing and trust:**
  - The method freeze was 5 hours late, and is recorded as a deviation.
  - Its analysis rules were written after the development results were known.
  - A fallback the plan allowed (gate F) was not taken, by the developer's decision.
  - The mutation tool, the runner and the ground-truth script were written after the freeze.
  - Commit times are self-asserted, and the freeze manifests are not yet anchored externally.
  - FreeTSA timestamped the base services 6 hours before the beacon round. Its certificate chain
    has not been verified, and the OpenTimestamps receipts are still pending.
  - The blindness is procedural. With the beacon value and the frozen script, the developer
    could have worked out the mutated site.
- **The held-out run was restarted once,** after a harness defect: a connection reset escaped
  the retry rule.
  - Under our pre-registered amendment rule, the first run stays primary for the trials it
    finished. The restart supplies the rest, labeled post-observation: 60 trials on `beta_m`,
    and all 200 control trials.
  - On the restart alone, every confirmatory verdict is the same, and two secondary ones change.
- **Verification depth:** for 26 of A2's 32 verified witnesses, the corrected-variant check was
  bounded rather than exhaustive, as the frozen rule allows.
- **Untested conditions:** our timings are on fast, local targets. Slow or remote targets are
  where the break-even says Muse could win, if its execution advantage carries over, and we did
  not test them.

### What's next

- held-out bugs of other kinds (check-then-act, multi-key, lock) and in other languages, with
  decoy edits;
- targets where an execution is genuinely expensive, to test whether Muse's execution
  advantage holds and pays off;
- a C# source view (a new method freeze), for C# services other than the public cart bug.

### Built with, and used but not built

- **Meta:** Muse Spark (`muse-spark-1.3`) through the Meta Model API, using structured output,
  `reasoning_effort` and automatic prompt caching.
- **Used, not built** `[TODO: license of each]`:
  - the OpenTelemetry Demo (Apache-2.0), pinned at tag `3.1.0` and not vendored. Its
    upstream NuGet packages are pinned by version, not hash. The corrected build uses PR
    #3825's cart change;
  - Valkey 9.0.4, pinned by image digest;
  - `python:3.13-slim`, pinned by digest;
  - .NET SDK 10.0.401 and runtime-deps 10.0.12-alpine3.23 images;
  - Python packages `redis` 8.1.0, `grpcio` 1.84.0 and `typing-extensions` 4.15.0;
  - Docker;
  - the drand beacon, FreeTSA and the OpenTimestamps calendars.
- **Libraries:** the host-side harness uses the Python standard library only.

### Team

`[TODO: names of every team member (up to 4), named by the Representative; each confirms
eligibility. "Single developer" above must match this list.]`

---

## Sources for every number

| Claim | Source |
|---|---|
| Held-out verdicts, medians, p-values, break-even, controls | `experiments/heldout-v1-analysis/RESULTS.md`, `report_primary.json` |
| M4's `beta_m` E₁ per trial | `experiments/heldout-v1/results/*/trials.jsonl` (primary combination: `analyze_heldout.py`) |
| Spend: $25.01 held-out, $25.45 total | `experiments/heldout-v1/results/*/manifest.json`; the pilot, A2 and tracer results ($0.1516, $0.2667, $0.0134) |
| Restart, its rules, post-observation trials | `docs/AMENDMENTS.md` AM-002; `docs/DECISIONS.md` D-043 to D-045 |
| Freeze, lateness, gate F, deviations | `docs/FREEZE.md` §1, §5, §8; `docs/HELDOUT_PROTOCOL.md` "Minimum scope" |
| Beacon, timestamps, sealing | `docs/DECISIONS.md` D-041, D-042; `experiments/heldout-v1/sealed/` |
| OTel cart: 20/20 replay, 942 of 1,000 | `experiments/2026-10-28-d1-gate/README.md` |
| OTel cart: stress median 7, 5–9 ms, Python-only view, 230–420× | `experiments/2026-10-29-d1-baselines/RESULTS.md`, `experiments/2026-11-01-d1-recheck/RESULTS.md` §3, §7 |
| Fixtures: executions, A2 on D2, wall-clock | `experiments/2026-10-29-pilot/RESULTS.md`, `experiments/2026-10-28-a2-no-source/RESULTS.md`, `experiments/2026-10-30-m0-d2-d3/RESULTS.md` §3 |
| Dependencies | `docker/*.Dockerfile`, `docker/*.lock`, `targets/d1-otel-cart/Dockerfile` |

## Still to do before submitting

- [x] README.md rewritten (`cc37224`, `619c32e`). Its first screen shows Muse's role, and it
      was fact-checked against the sources.
- [ ] Public repository: needs the owner's approval and a license (Apache-2.0 proposed, D-016).
      The full-history secret scan is done (`8644b99`): 0 hits, see
      `experiments/2026-11-03-secret-scan/`. The author email becomes public on push.
- [ ] The license of each dependency listed above. Three are known from package metadata:
      `redis` (MIT), `grpcio` (Apache-2.0) and `typing-extensions` (PSF-2.0). Still to confirm:
      Valkey, `python:3.13-slim`, and the .NET images.
- [ ] 3-minute demo video, showing Muse's role in the first 30 seconds.
- [ ] Team members named; track confirmed.
- [ ] Owner's decisions:
  - publish the sealed held-out directory (the C6 reveal);
  - anchor the freeze manifests externally (OTS).
- [ ] Re-read the rules page on Nov 4, then submit by 6 PM ET (hard deadline 9 PM ET).
