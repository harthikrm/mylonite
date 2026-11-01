# Held-out Evaluation Protocol (sole developer)

Status:
- **Approved in principle** by the owner on 2026-10-28 (D-020).
- **Frozen at v1.0** (2026-11-01, `docs/FREEZE.md`) with the **minimum scope** below (D-037), which
  the owner set on 2026-11-01: "a minimum held-out scope of two previously unseen concurrency
  defects, with corrected negative controls and 20 trials per method per target where feasible."
- The minimum scope replaces the 8-base plan for v1.0. Every rule of the sections after it still
  applies unless the minimum scope changes it.
- The external timestamp mechanism (D-028) is still a proposal: each submission needs the owner's
  approval.
- It replaces the "Author" bullet of `EVALUATION_PLAN.md` §4.2.

## Minimum scope v1.0 (2026-11-01; D-037)

**What is evaluated.**

| | Count | Methods, 20 trials each (seeds 1–20) |
|---|---|---|
| Mutants (buggy targets) | 2, one per base | M0, M1, M3+, M3+arg, M4, A2 |
| Bases (negative controls; each is also its mutant's corrected variant) | 2 | M0, M1, M3+, M3+arg, M4 |

- "Where feasible" is defined in advance: every conventional trial runs. Model trials run in the
  config's order (mutants first) until the strict cost cap. Any trial not run is reported, with
  its place in that order (`experiments/heldout-v1/config.json`).
- **Any VIOLATION verdict on a base,** whether in a control trial or during a witness's
  corrected-variant check, is a false positive. A base has no corrected variant, so no hit on
  it can be "verified". It stops the run and blocks every claim until explained (`FREEZE.md`
  §6).

**Base specifications, fixed now.** Writing these before the bases limits the author's freedom
to shape a base against a baseline.

| Base | Domain | Catalog operations | Lifecycle or distractor operations | Precondition depth |
|---|---|---|---|---|
| α | Event seat reservations | ≥ 8 | ≥ 2 | ≥ 2: an event must exist and be on sale before a reservation can succeed |
| β | Background-job leases | 6–8 | ≥ 1 | 1: a job must be enqueued before it can be leased |

Every base:
- is Python with redis-py on per-connection clients, in the executor image used for D2 and D3;
- is **deterministic**: no randomness, no wall-clock reads, and no behavior that depends on a
  TTL expiring. Lease tokens, for example, are derived from arguments. Replays must reproduce
  20/20;
- has identifiers that name the domain and never a defect;
- has a correct owner contract, written for the base before any mutant exists;
- passes the C2 checks below;
- contains sites of at least 3 operator kinds, and **at least 3 sites in each stratum**
  (guarded and unguarded), as the frozen mutation script classifies them. This is checked at
  C2, so that the beacon has a real choice.

**Operators for v1.0** (the plan's §4.2 list, with one change):
1. An atomic update becomes read, compute, write.
2. **An optimistic transaction loses its `WATCH`.** "Watch the wrong key" is dropped. The proxy
   runs `WATCH`…`EXEC` as one unit, so no method could ever expose it (see "What this protocol
   cannot rule out").
3. A `MULTI`/`EXEC` block becomes non-transactional.
4. A check inside a server-side script moves to the client: read, check, then write.
5. A compare-and-delete lock release becomes an unconditional `DEL`.
6. A state write moves before its guard.

**Every mutant must be serially equivalent to its base.** Outcomes and observations must be
identical on two sets of serial workloads, with the same seeds for both:
- 150 random serial workloads;
- every setup on the base's M3+ frontier, followed by each catalog call. Random workloads rarely
  reach a depth of 2 or more.

A site whose mutant differs serially is not a concurrency defect. It is discarded, the next site
in the seeded order is used, and every discard is reported.

**Where things go.**
- The held-out runner is `experiments/heldout-v1/run_heldout.py`. It refuses to run from any
  other path, and unless `freeze/manifest.py check` passes.
- Committed manifests of sealed material (C2, C4) go in `experiments/heldout-v1/sealed/`.
- Results go in `experiments/heldout-v1/results/`.
- The sealed files themselves stay outside the repository.

**Steps and schedule.** Each step is a commit; the next step records its hash.

| Step | What | By (ET) |
|---|---|---|
| C1 | The freeze, v1.0 (`FREEZE.md`). External anchor of its manifest: proposed, needs approval | Nov 1 |
| C1b | **Class A tooling** (`AMENDMENTS.md`), before any base exists, then a new manifest (v1.1). (1) The mutation script: site enumeration for the operators above; the guarded/unguarded classifier (a site inside a branch that depends on a store read is guarded); the serial-equivalence filter; the C4 selection rules; unit tests on toy code that is not a base. Every operator it cannot implement is listed before C2. (2) The held-out runner: `manifest.py check` first; progress counts only on screen; the crash rule; the strict cost cap; the model-string check against the pilot's `muse-spark-1.3`; `not_run` records for trials the cap cuts; a target root outside the repository; a stop on any VIOLATION on a base. (3) **The C6 extended-search script.** It decides the only exclusion rule, so it must exist before any outcome. (4) A configurable target root for the sandbox and the audit | Nov 2, 12:00 |
| C2 | Bases α and β, with catalogs, value domains, observations, contracts and model views. Checks: serial validity (150 random serial workloads, no violation), pass-through, contamination audit, determinism, ≥ 3 operator kinds, ≥ 3 sites per stratum. A salted manifest of the sealed directory. The commit message names the drand round R as a number. Externally timestamped as soon as the owner approves (D-028) | Nov 2, 20:00 |
| C3 | drand round R (public HTTPS GET; the owner approves) | after C2 |
| C4 | Generation, with no human choice (rules below). Output is sealed outside the repository, and only its SHA-256 manifest is committed | right after C3 |
| C5 | Evaluation with the frozen config, blind | Nov 3 |
| C6 | Ground truth, then reveal (the original C6 rule); publication needs the owner's approval | Nov 3 |

**Round R and the timestamp.**
- **R is named as a number in the C2 commit message.** It is the first drand mainnet round
  scheduled at least 6 hours after the C2 commit time, computed from the chain's published
  genesis time and period.
- **The first R named is binding.** C2 is never redone to get another round. This supersedes
  the older C2 text ("C2 is redone with a later round"), which would let the author compute
  C4's outcome for a published round privately and re-roll.
- The ordering is externally verified if a timestamp of the C2 manifest predates R's
  publication: an RFC 3161 signed time, or an OpenTimestamps Bitcoin attestation (a pending
  calendar receipt trusts the calendar). Otherwise the results report it as unverified, and
  C4 proceeds anyway.

**C4 generation rules.** The seed is round R's `randomness` field, as a lowercase hex string.
1. The bases are ordered α, β.
2. Strata:
   - if the most significant bit of the seed's first byte is 0, α's mutant must come from a
     guarded site and β's from an unguarded one;
   - otherwise it is the reverse;
   - a base with no site in its stratum takes the other stratum, and the shortfall is recorded.
3. Within a base and stratum, sites are listed in source order, n of them. The first index tried
   is int(SHA-256(UTF-8 of `"<seed>|<base>|<stratum>"`), big-endian) mod n. The next indices
   follow in cyclic order until a mutant passes the serial-equivalence filter.
4. If no site passes, the base yields no mutant. That is reported, and v1.0 then has 1 mutant.
5. No human opens a generated file before the C5 results commit.

**Cut-off.** If C5 has not started by **Nov 3, 18:00 ET**:
- there is no held-out claim;
- the submission reports the frozen protocol and how far it got.

A partial C5, for example one cut short by the cost cap, is reported with its trial counts.

**Deviations from the original plan, disclosed wherever results appear:**
- 2 buggy targets instead of 6, and 2 bases instead of 8;
- no weak-contract control and no equivalent mutant;
- no guaranteed shallow stratum: both bases need a precondition;
- no style decoys, which favors source-reading M4;
- Python with per-connection clients only (§4.2 asked for at least 2 multiplexed clients);
- the mutation script, runner and C6 script are written after the freeze (C1b), not before
  it;
- the C2 external timestamp is no longer mandatory: it needs approval;
- the freeze is late (`FREEZE.md` §1).

**Blindness is procedural.** The author could work out the mutated site from R and the frozen
script without opening a file, and progress timing could hint at outcomes. Neither is
prevented, only disclosed.

**Not counted toward the minimum.** A real open-source race fix (R2) can be added as a separate
stratum, never pooled. Its defect is public, so it is not "previously unseen" by the model or
the author.

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

The commit is tagged `freeze-v1.0` (the v1.0 freeze, `FREEZE.md`). No held-out base service exists yet.

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
- The C2 commitment is therefore timestamped externally before the named round, by the
  mechanism below (proposed), or by a push to the project's GitHub repository.
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

## External timestamp mechanism (proposed 2026-10-28, D-028)

Goal: anyone can later check that the freeze (C1) and the sealed bases (C2) existed before a
given time, while **nothing but a 32-byte digest leaves the machine before C6**.

**What is committed.** A plain-text manifest per step, kept with the sealed material:
- **C1:** the `freeze` tag's commit and tree hashes, the SHA-256 of every file under `src/` and
  of the held-out experiment directory, and the prompt fingerprint.
- **C2:** the SHA-256 of every file in the sealed directory (bases, contracts, catalogs), plus
  the C2 commit hash.

The published value is `SHA-256(salt ‖ manifest)`, with a fresh 32-byte random salt per step,
kept private with the sealed material. Without the salt nobody can confirm a guess about a
small file, for example a suspected mutant.

**Where it is timestamped.** Two independent mechanisms, both digest-only:
1. **RFC 3161 time-stamp authorities.** These return a signed time within seconds.
   - Request with `openssl ts -query -data <file> -sha512 -no_nonce -cert -out <file>.tsq`.
   - Send by HTTP POST with `Content-Type: application/timestamp-query`.
   - Verify with `openssl ts -verify -data <file> -in <file>.tsr -CAfile <ca> -untrusted <tsa.crt>`.
   - Use FreeTSA (`https://freetsa.org/tsr`; these commands are from its documentation) and a
     second public TSA chosen at use time. Two TSAs mean no single signer has to be trusted.
2. **OpenTimestamps.** Submit the same digest to the public calendars: the OpenTimestamps client
   defaults are `a.pool.opentimestamps.org`, `b.pool.opentimestamps.org`,
   `a.pool.eternitywall.com` and `ots.btc.catallaxy.com`, and submission is an HTTP POST of the
   digest to `/digest`. After a few hours the proof upgrades to a Bitcoin block attestation, which
   anyone can verify without trusting a calendar.

`openssl` and `curl` are already on the host, so no new dependency is needed to submit. OTS
proofs are verified later with the client inside a container.

**Ordering with the beacon.** C2 names drand round R. The RFC 3161 time of the C2 commitment
must come before R's scheduled publication time (genesis + period × R), with a margin of at
least 2 minutes. Otherwise C2 is redone with a later round, as above, and the abandoned
commitment is reported.

**Reveal (C6).** Publish the manifests, the salts, the sealed directory, the `.tsr` tokens and
the `.ots` proofs. Verification is a hash comparison plus the two time checks.

**What it does not prove.** That nothing else was prepared earlier; that the author did not
look at the sealed files (the blind runner and the order of commits address that); or anything
about C4–C5 beyond the beacon's lower bound and the results commit's own timestamp (which
should be stamped the same way).

**Rejected as primary.**
- A GitHub push publishes the repository early and relies on the platform's clock.
- A public gist or notary repository holding only digests is acceptable as a fallback, but it
  is still platform-trusted.
- drand alone gives only a lower bound.

**Approval.** Every submission sends data to an external service, even if only a digest. It is
done by the owner, or by the assistant only after the owner approves that specific submission.

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
