# Held-out Evaluation Protocol (sole developer)

Status: **Proposed 2026-10-28 (D-020); needs the owner's approval before the freeze.**
It replaces the "Author" bullet of `EVALUATION_PLAN.md` §4.2 if approved.

## Premise

One person may write the base services, the contracts, the planner prompt, the methods, and the
analysis. **Independence is not claimed.** The protocol aims at two weaker properties that can
be defended:
1. The author's knowledge cannot choose **which bugs exist or where they are**.
2. The **order** of every step can be checked afterwards from the repository.

## Threats this protocol addresses

| ID | Threat | Main control |
|---|---|---|
| H1 | The prompt or methods are tuned on held-out targets | The freeze (step C1) precedes any held-out code |
| H2 | Bugs are placed where a code-reading model does well | Mechanical injection at sites chosen by public randomness (C3–C4) |
| H3 | A contract or catalog reveals the bug | Contracts are written for the correct base, before any mutant exists (C2). Normalized model view and audit (`src/mylonite/audit.py`) |
| H4 | Bad results are dropped or re-run | Every generated target is reported. One pre-registered exclusion rule (C6). Trial logs are append-only |
| H5 | The model memorized a public bug | Bases are new code, not public. Any open-source race fix used is a separate stratum, never pooled |
| H6 | Distinct bugs or verification are judged with bias | One mutation per mutant, so attribution holds by construction. Verification is automated (`methods.verify`) |

## Steps, each a commit whose hash the next step records

**C1 — Freeze** (proposed: Oct 31, 12:00 ET). Frozen, and pinned by the SHA-256 of every file
under `src/` and `experiments/<held-out>/`, not only the prompt fingerprint:
- prompt, schemas, `prompt_fingerprint`;
- methods and budgets;
- verification;
- the analysis script;
- the composition rules below;
- the mutation script, with its operators and site classifier;
- the held-out runner: blind output (progress counts only), a crash rule, and the sealed-root
  mount;
- **a specification for each of the 8 bases**: domain, number of operations, number of
  lifecycle or "distractor" operations, and precondition depth (the number of setup calls needed
  before the mutated path can run).

Fixing the specs at C1 limits the author's freedom to shape the bases against a baseline,
for example by adding distractors that starve M3+.

The commit is tagged `freeze`. No held-out base service exists yet.

**C2 — Base services** (after C1; proposed by Oct 31, 23:59 ET). Eight correct base services,
each with:
- a catalog, value domains, an observation, and an owner contract;
- a declared `model_view`.

Each must pass three checks:
- the serial-validity check (150 random serial workloads, no violation);
- the pass-through check;
- the contamination audit.

Plus one weak-contract target: a documented last-writer-wins service whose non-atomic update the
contract allows; it must PASS.

The C2 commit message names the beacon round for C3: the first drand mainnet round after the C2
commit time + 10 minutes.

**Mandatory external timestamp.** Commit times are self-asserted. Without an external
timestamp, the author could backdate C2 to name a round that is already published, or re-roll by
recommitting.
- The C2 commit hash is therefore published before the named round: a push to the project's
  GitHub repository, or an OpenTimestamps submission.
- Either one is a public action and needs the owner's approval at the time.
- If neither happens before the round, C2 is redone with a later round. The abandoned C2 hash is
  reported.

**C3 — Randomness.** The seed is the drand round named in C2 (League of Entropy, publicly
verifiable). Nobody, including the author, can know it before it is published.

**C4 — Generation** (no human choice).
- The frozen mutation script enumerates the candidate sites in each base, for the six operators
  in `EVALUATION_PLAN.md` §4.2. It classifies each site as **guarded** (inside a branch that
  depends on a store read, so a precondition is needed) or **unguarded**.
- With the seed, it then assigns:
  - 2 bases as correct controls (unmutated);
  - 1 base for an equivalence-preserving rewrite (for example `INCRBY` into an equivalent script);
  - the other 5 bases to mutation, plus one more mutant from a second site of a randomly chosen
    base, for 6 mutants.
- For the mutants, at least 3 sites are guarded and at least 2 unguarded, when such sites exist.
  Otherwise the shortfall is recorded.
- The script also applies **style-only rewrites at decoy sites** in every target, controls
  included (for example reordering independent statements, or renaming locals). Injected code
  should then not stand out by style alone, and a code reader cannot spot the mutant by its diff
  style.
- Output goes to a sealed directory **outside the repository**. Only the SHA-256 manifest is
  committed.
- The sandbox and audit need a configurable target root for this. Today they assume
  `repo/fixtures`; the change is part of C1.
- The author does not open the generated files.

**C5 — Evaluation.** The harness runs every required method on every sealed target with the
frozen config:
- each trial's model input passes the audit;
- each verified violation passes replay and the corrected (base) variant.

No human reads target code or intermediate results before the results commit:
- The held-out runner prints progress counts only; results go to files.
- **Crash rule:** a trial that ends in a harness error is re-run once with the same seed. Both
  outcomes are reported.
- No code changes are made during C5. If one becomes unavoidable, C5 restarts from scratch
  under a new freeze, and the aborted run is reported.

**C6 — Ground truth, then reveal.** After the results commit:
- a mutant is **shown-buggy** if **any** method (M4 included) produced a verified violation on
  it in C5;
- an extended search then covers the rest: M1 and M3+ at 10× `B_exec`, plus exhaustive
  exploration of the mutated operation paired with itself and every other catalog call, from
  every frontier state M3+ reaches. Anything it verifies is also shown-buggy;
- not-shown-buggy mutants are reported separately and excluded from the E₁ comparison for every
  method alike; this is the only exclusion rule;
- the sealed directory is then published.

## Composition rules (fixed at C1; revised from §4.2 for one author)

- Python services only for mechanical injection. Node and multiplexed-client targets would need
  a second mutation implementation. If one is built, it is reported as its own stratum; this
  deviates from §4.2's "at least 2 multiplexed" and is **an owner decision**.
- At least half of the bases have ≥ 8 catalog operations.
- Mutant strata come from the guarded/unguarded site classes above, instead of being authored to
  order.
- Identifiers name the domain (`reserve`, `balance`) and never a defect. Comments and bare strings
  are removed from the model view by construction.

## What this protocol cannot rule out

- **Style bias in the bases.** The author knows the prompt and might write code that is easy for
  an LLM to read. Partial controls: A2 (no source) measures how much reading code helps, and the
  bases are written to a domain list fixed at C1.
- **Self-asserted commit times.** Commit order is visible, and C3's beacon round bounds C4 from
  below. An upper bound needs an external timestamp. Optional: post the C1 and C2 hashes
  publicly, which needs the owner's approval for any public action.
- **Operator coverage.** Six operators do not cover every real race. Results speak to this mutant
  population only.
- **Operators the harness cannot expose today.** The proxy runs `WATCH`…`EXEC` as one unit, so
  "watch the wrong key" (operator 2) can never be exposed by any method. Either the proxy gates
  commands inside `WATCH` up to `MULTI` before C1, or operator 2 is removed at C1. Similarly,
  conflicts use only a command's first key, so multi-key commands and scripts are approximated.
  This affects M3+'s pair filter, not verification.
- **Small n.** With 6 buggy targets and 20 trials per method, per-target comparisons are coarse.
  Claims are per target, with intervals (`EVALUATION_PLAN.md` §7).

**Wording for the submission:** "Single developer. Held-out targets were generated by mechanical
mutation of base services written after the method freeze, at sites chosen with a public
randomness beacon. No independent author was involved."

## Work this creates

- Mutation script with the 6 operators and the site classifier, with unit tests: Oct 30–31,
  before C1.
- 8 base services plus 1 weak-contract target: after C1.
- Beacon fetch: one public HTTPS GET by the owner, or by the assistant with approval.
