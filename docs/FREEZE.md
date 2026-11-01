# Method freeze v1.0

Status: **frozen.** The freeze commit is the commit that adds this file. It is tagged
`freeze-v1.0` (local tag) and named, with the SHA-256 of every tracked file, in
`freeze/v1.0/MANIFEST.json`, which is committed immediately after it. Changes after this point
follow `docs/AMENDMENTS.md`. Decisions: D-035 (this freeze and its deviation), D-036 (analysis
rules), D-037 (minimum held-out scope), D-038 (amendment policy).

## 1. Protocol deviation: the freeze is late, and gate F's fallback is not taken

- **Deadline.** D-014 and gate F (`EVALUATION_PLAN.md` §11) set the prompt and method freeze for
  Oct 31, 23:59 ET (Nov 1, 03:59 UTC). No freeze commit existed at that time.
- **Last methodology commit before the deadline.** `1e33881` (D-034), committed
  2026-10-31 22:06 CDT, which is 23:06 ET, 53 minutes before the deadline.
- **This freeze.** Committed on 2026-11-01, after the deadline. Nothing is backdated: the commit
  carries its real time, and the manifest copies it. Commit times are self-asserted, so the
  freeze time is provable only once the manifest is anchored externally (§7).
- **What did not change between the deadline and the freeze** (checkable with
  `git diff 1e33881 <freeze> -- src/ fixtures/ targets/ docker/ experiments/2026-10-*`):
  - every file under `src/` that existed at `1e33881`;
  - fixtures, targets, images and every earlier experiment.

  The prompt fingerprint is `3da3aa34…`, the same as in the pilot (`db1f84f`) and A2
  (`aa1f4eb`) manifests. `planner.py` last changed on Oct 29 (`c927e5c`), in a target-dependent
  limit only, which the fingerprint does not cover. `methods.py` last changed on Oct 31
  (`3b912d3`, M3+arg).
- **What was added at the freeze, after the deadline.** All of it was written after every
  development result was known:
  - the analysis rules as code (§4, `src/mylonite/analysis.py`, `tests/test_analysis.py`);
  - the held-out configuration (`experiments/heldout-v1/config.json`);
  - the minimum held-out scope (§5, `HELDOUT_PROTOCOL.md`);
  - the amendment policy (`AMENDMENTS.md`);
  - the manifest tooling (`freeze/manifest.py`).
- **Gate F's pre-registered fallback is not taken.** Gate F says that if the freeze is missed,
  Muse's role is reduced to A4 (Muse ranks M3+ candidates) and that is frozen instead.
  - The owner decided on 2026-11-01: "Record the missed deadline as a protocol deviation and
    prepare an immediate freeze of the current approved methodology."
  - The fallback was written for a planner that was not ready to freeze. This planner's prompt
    fingerprint has been unchanged since Oct 28. That is the reason given, and it is the
    owner's decision, not a pre-registered branch.
- **Gate F's other condition, "held-out sealed", is also missed.** No held-out material exists.
  The held-out schedule is replaced by §5. Gate G3 (Nov 2, 12:00 ET) will be missed too.

## 2. What is frozen

The manifest pins every tracked file by SHA-256. The method-relevant parts:

| Component | Frozen value | Where |
|---|---|---|
| Model | `muse-spark-1.3` at `https://api.meta.ai/v1/chat/completions`, Standard mode. `json_schema` structured output with `strict: true`, `reasoning_effort: medium`. No temperature is sent (the API default; 1.0 per the pilot notes). No `store` field is sent: D-008 said "`store: false` if honored", and it was never sent in any run. Timeout 600 s. | `planner.py`, D-008 |
| Model retries | Up to 3 attempts on transport errors, HTTP 429 and 5xx, waiting 5 s then 15 s. Failed attempts count as model latency. | `experiments/2026-10-29-pilot/run_pilot.py` (`LiveModel`) |
| Cost cap | Strict: a call is refused if spend plus a $0.25 reserve would exceed the cap. Held-out cap: $30, which still needs the owner's approval. | `experiments/2026-10-28-a2-no-source/run_a2.py` (`StrictCap`), held-out config |
| Prompt | `planner-v2-2026-10-28`, fingerprint `3da3aa341994c85e64bf1e452a3e61070f8da4b37013dc2de08c9ca6e1c31157`. At most 3 experiments per call and 16 hint steps. `HYPOTHESIS_KINDS` is the author's prior (disclosed in plan §5). | `planner.py` |
| Model view and audit | Declared files only, comments and bare strings removed. `audit.assert_clean` runs before every call. | `planner.py`, `audit.py`, `tests/test_contamination.py` |
| Methods | M0, M1, M3+, M3+arg, M4. A2 is M4 with `include_source: false`. | `methods.py`, D-031, D-033 |
| Workload space | Setup ≤ 6 calls; 2–4 concurrent calls; a target may lower the maximum for every method. | `space.py`, D-029 |
| Harness | Proxy, scheduler, executor, oracle, RESP framing, sandbox. | `src/mylonite/` |
| Budgets per trial | `B_exec` 1,000 search executions, M3+ profiles and stress runs included; 900 method-seconds; `K` 50 schedules per workload; M4 and A2 at most 5 rounds. | held-out config |
| Stopping, per trial | The first verified violation; `B_exec`; the method-seconds cap; the method's plan exhausted (M3+ and M3+arg: frontier and every pair; M4 and A2: 5 rounds); an error, which ends that trial only. | `methods.run_trial` |
| Verification | 20 replays with an identical trace hash. Corrected variant: exhaustive up to 5,000 schedules, otherwise 5,000 depth-first plus 2,000 random ("bounded"). Up to 2 re-runs of an INCONCLUSIVE execution. Never charged to a method. | `methods.verify`, held-out config |
| Accounting | Method-seconds are wall-clock minus harness round trips and verification, with model latency included. Dollars are tokens at list price (input $1.25, cached $0.15, output $4.25 per 1M) plus execution seconds at $1.11 × 10⁻⁵ per second. Verification is reported separately. | `methods.Trial`, plan §2 |
| Seeds | 1–20 for every method on every held-out target. | held-out config |
| Analysis | §4. | `analysis.py` |
| Held-out construction | §5. | `HELDOUT_PROTOCOL.md` |
| Run validity and stop rules | §6. | here |

## 3. Target designations

- **D2 and D3 are development targets.** They are author-written fixtures used to build, tune
  and pilot the methods.
- **D1 (the OTel cart, #3824) is a development and feasibility target.** It fails every
  held-out criterion:
  - the defect and its fix (#3825) are public, and the author inspected both;
  - the harness was changed on it (D-025, D-029, D-030);
  - baselines have run on it at seeds 0–5.
- No result on D1, D2 or D3 supports a generalization or discovery claim. None is pooled with
  held-out results.
- On those targets M3+arg has no trials at seeds 1–5, so D-034 comparisons there use M3+ alone
  and say so.

## 4. Analysis rules (D-036; code in `src/mylonite/analysis.py`)

Development results were known when these rules were written. Each rule is either the standard
default or the choice less favorable to Muse. None was chosen by computing alternatives on
development data.

An independent review of the first draft found two rules that favored Muse:
- seconds and dollars were censored at different points for different methods;
- the break-even took Muse's overhead from its successful trials only.

Both were fixed before this freeze, and the review's counterexamples are now tests.
`tests/test_analysis.py` checks every rule against an independent computation or a
hand-computed value.

1. **Outcomes.** Each trial, on each metric (E₁, method-seconds and dollars to the first
   verified violation), has one of three outcomes:
   - **found**, at its cost;
   - **failed**, which covers three cases:
     - its own plan ran out, so it would never find the bug;
     - the time budget ran out. That is a failure within the budget every method shares
       (900 method-seconds);
     - a Muse trial errored;
   - **censored**: the execution budget ran out, so its cost to find in seconds or dollars is
     unknown, and larger than what it had spent.
2. **A common scale for each comparison.** τ is the smallest cost spent by any trial censored
   at the execution budget, in either of the two groups. Every cost above τ, and every
   non-finding, ranks as one tied failure.
   - A second review found the draft's version unsafe: it let a Muse trial stopped by the time
     budget set τ, which could truncate E₁ for everyone and turn a tie into "better".
   - For E₁, where trials are censored at `B_exec`, τ = `B_exec` and nothing changes.
   - For seconds and dollars, a baseline censored after 1,000 cheap executions stopped long
     before a Muse trial could. So a Muse success that cost more than that is not counted as
     better. On the pilot's D3 this turns the first draft's "M4 better than M1 on dollars" into
     no evidence either way.
   - Medians and success counts use each trial's own value, with failures at `B_exec` + 1 or
     infinity.
3. **Errored, missing and re-run trials.**
   - The crash rule re-runs a trial once, and only after an error. A Muse trial uses its first
     attempt, so an error is a failure and never a fresh draw. A baseline, whose seed fixes its
     search, uses its second attempt. Both are reported.
   - An errored baseline trial is left out and counted.
   - Every (target, method, seed) must be present, as a result or as `not_run` (for example, cut
     by the cost cap); otherwise the analysis refuses to run.
   - If more than 10% of a method's trials on a target error, that is flagged but never
     excluded: C6's rule stays the only exclusion.
4. **Test and ties.** Exact two-sided Wilcoxon–Mann–Whitney with mid-ranks: the share of all
   splits whose rank sum S satisfies |S − E| ≥ |s − E|. It is conditional on ties, with no
   approximation and no Monte Carlo.
   - Â₁₂ = P(Muse < baseline) + ½ P(=). Ties count one half, and values above 0.5 favor Muse.
5. **Pairing.** M4 and A2 have no seed, and each other method draws from its own seed stream.
   So every Muse comparison is between independent samples.
   - M3+ and M3+arg share a stream (`M3+:<seed>`) and are reported seed by seed, without a test.
   - The intersection–union rule is valid whatever the correlation between comparisons.
6. **Stronger baseline (D-034, approved and reaffirmed on 2026-11-01).** Muse is better than a
   group only if it is better than every member.
   - The group's p for "better" is the largest member p, and it is 1 unless every member's Â₁₂
     favors Muse.
   - "Worse" needs one member: the smallest p among those Muse loses to. This is deliberately
     liberal, against Muse.
   - **Confirmatory groups:**
     - **conventional** = {M0, M1, M3+, M3+arg}, the headline;
     - **systematic** = {M3+, M3+arg}, D-034's rule.
   - Secondary, and not claims on their own: M0 alone, M1 alone, and M4 against A2 (RQ2).
   - Every baseline's own results are always reported.
7. **Co-primary metrics stay separate.** E₁, seconds and dollars each get their own verdict, and
   they are never combined.
   - For each group, Holm runs across every tested held-out buggy target × metric cell (6 for 2
     targets), separately for "better" and "worse", at α = 0.05.
   - A cell where a member did not run is "not tested", and stays out of Holm.
8. **Wording.** Each cell is one of:
   - "better";
   - "worse";
   - "no significant difference", which is not a claim of equivalence;
   - "not tested".

   Where `EVALUATION_PLAN.md` says "tied", it means "no significant difference".
9. **Medians.** The median is the ⌈n/2⌉-th smallest value. With one censoring point it is the
   Kaplan–Meier median and always an observed value. It is "not reached" when more than half of
   the trials failed.
   - Intervals: percentile bootstrap, 10,000 resamples, with a fixed seed per series.
   - Success@10/30/100/300/1,000 is reported with Wilson 95% intervals, and not tested.
10. **Break-even, from every trial.**
    - Each trial's cost to its first verified violation is a line in the cost per execution c:
      E·c plus its other cost (method-seconds minus execution seconds; or model dollars, as
      compute-seconds at the nominal price).
    - Failed trials are infinite. A censored Muse trial is infinite. A censored baseline trial
      takes the lower bound (executions + 1)·c plus what it had spent, so a baseline is never
      made to look slower than it is.
    - The break-even c* is where Muse's median line falls below the baseline's and stays below.
      Medians of lines are piecewise linear, so c* is exact at the lines' crossing points.
    - Status is "always", "breaks_even" (with c*), "never" (Muse is not cheaper for large c), or
      "undetermined".
    - Headline: the least favorable to Muse over the group: "never", then "undetermined", then
      the largest c*.
    - The target's measured cost per execution, shared by every method, is reported beside it.
11. **Scope of claims.**
    - Verdicts come only from held-out buggy targets that C6 shows to be buggy.
    - On a negative control (a base), **any** VIOLATION verdict is a false positive. A base has
      no corrected variant, so no hit there can ever count as "verified". Each one is counted
      by where it came from:
      - scheduled executions;
      - stress runs;
      - serial profiles;
      - the corrected variant during a mutant witness's verification.

      Those that replayed 20/20 are also counted.
    - Development and held-out results are never pooled.

## 5. Minimum held-out scope (D-037; full procedure in `HELDOUT_PROTOCOL.md`)

- **Targets.** 2 previously unseen defects:
  - Each is one mechanical mutation of a different base service. The bases are written after
    this freeze, and the mutation site is chosen by a public randomness beacon published after
    the bases are committed and timestamped.
  - Each base is its mutant's corrected variant, and it is also run as a full **negative
    control**.
- **Trials.** 20 per method per target:
  - M0, M1, M3+, M3+arg, M4 and A2 on the mutants;
  - M0, M1, M3+, M3+arg and M4 on the controls.

  Model trials are capped by cost, and any trial not run is reported as such (held-out
  config).
- **Protocol.** Transparent sole developer, without independence. Wording for the submission:
  "Single developer. The two held-out defects were generated by mechanical mutation of base
  services written after the method freeze, at sites chosen with a public randomness beacon. No
  independent author was involved."
- **Deviations from plan §4.2 and D-020,** each disclosed wherever results appear:
  - 2 buggy targets instead of 6;
  - no weak-contract control and no equivalent mutant;
  - Python services with per-connection clients only;
  - **no guaranteed shallow stratum.** Both bases need a precondition, so the "at least a third
    shallow" rule, the cases where baselines are expected to win, may be unmet. The unguarded
    stratum is the nearest substitute;
  - **no style decoys.** This favors source-reading M4: a mutant may stand out by its style;
  - the mutation script and the held-out runner are written after the freeze (C1b), not before
    it as D-020 planned. The operators and the selection rules are fixed now;
  - the C2 external timestamp needs approval, so it may not happen. D-020 made it mandatory.

## 6. Run validity and stop rules (held-out)

- **Before any held-out trial:**
  - unit tests pass at the run commit, and the tree is clean;
  - `python3 freeze/manifest.py check` passes at the run commit. That requires:
    - the latest committed freeze version is the reference;
    - every file it lists matches, except narrative Markdown and the run's output directories;
    - no unexpected file has been added;
    - `AMENDMENTS.md` has only been appended to;
    - every version after v1.0 has its entry there;
  - the owner has approved the model cost cap.
- **Validity, for results to count:**
  - every model request passed the audit;
  - INCONCLUSIVE is at most 1% of each method's executions, and there are 0 soundness problems.
    A breach is flagged beside that target's verdicts, never excluded (§4, rule 3);
  - every hit is verified.
- **Stop at once, and report rather than patch:**
  - a contamination refusal;
  - a soundness problem;
  - any VIOLATION on a base, whether in a control trial or in a witness's corrected-variant
    check. This blocks every claim until explained;
  - repeated executor failures: 3 errored trials in a row, or a crash-rule re-run that fails
    with the same error;
  - the cost cap, which stops model trials only.

  After a stop, completed trials are kept and reported. Verdicts are computed only for targets
  whose conventional trials are all complete. Restarting after a fix follows `AMENDMENTS.md`
  class B, which restarts C5 from scratch.

## 7. External anchoring (proposed; nothing has been submitted)

- **What to anchor.** The SHA-256 of `freeze/v1.0/MANIFEST.json`. The manifest names the
  freeze commit, its tree, and the SHA-256 of every tracked file, so the anchor covers the
  whole frozen state.
  - The C1 manifest is not salted: nothing in it is secret, and the repository is meant to be
    published.
  - The C2 manifest of sealed bases is salted, as D-028 proposes.
- **Tool.** The OpenTimestamps client (`ots`), run in a disposable container rather than on the
  host (D-012). It is installed from PyPI with `--require-hashes` from a lock file written at
  install time; version and hashes are not fixed here. The only egress is to the calendars.
  - The file stays local. The client submits a digest derived from the file's SHA-256, and
    blinds it with a random nonce (the client's behavior, to be confirmed at use).
- **Steps,** each needing the owner's approval at the time:
  1. `python3 freeze/manifest.py verify freeze/v1.0/MANIFEST.json`, locally.
  2. `ots stamp freeze/v1.0/MANIFEST.json`. This writes `MANIFEST.json.ots`, with pending
     attestations from the public calendars.
  3. Commit the `.ots` file locally.
  4. A few hours later, `ots upgrade freeze/v1.0/MANIFEST.json.ots` adds the Bitcoin block
     attestation. Commit the result.
  5. `ots verify` checks it against Bitcoin block headers. That needs a node or a block-header
     source, to be settled at use. At publication anyone can repeat it.
- **What it proves.** The manifest, and so the frozen state, existed no later than the attested
  block's time.
  - It says nothing about anything before that, and nothing about the time between the commit
    and the stamp. So stamping early is what keeps the late freeze's gap small.
  - It must happen before C2, so that "methods frozen before any held-out base existed" is
    externally checkable.
- **Complement.** D-028's RFC 3161 TSAs give a signed time within seconds. That is useful at C2,
  where the drand round must come after the timestamp. It is a separate submission with its own
  approval.
- **A local commit alone is not an independently verified timestamp.**

## 8. What this freeze does not establish

- **Independence.** The author of the prompt, the methods and the analysis also writes the
  held-out bases.
- **Blindness to development data.** Every development result was seen before this freeze.
- **Blindness to the mutants is procedural.** The author could work out the mutated site from
  the beacon value and the frozen script without opening a file. Progress timing, such as how
  fast a Muse trial ends, could also hint at outcomes.
- **Model stability.** The API model behind `muse-spark-1.3` could change. Every response's
  reported model string is recorded; the held-out runner must compare it with the pilot's and
  report any difference (`HELDOUT_PROTOCOL.md`, C1b).
- **Provable times.** Commit times stay self-asserted until anchored (§7).

## 9. Audit before the freeze (2026-11-01)

What was checked, what was found, and what the freeze does about it.

| Area | Finding | Resolution |
|---|---|---|
| Prompt | Fingerprint `3da3aa34…` is identical to the pilot and A2 manifests. `HYPOTHESIS_KINDS` names D2's and D3's bug classes, which is the author's prior. | Frozen as is. The prior is disclosed (plan §5). |
| Model parameters | D-008 says "`store: false` if honored", but no run ever sent it. Temperature is not sent, so the API default applies. The retry rule lives in an experiment runner, not in `src/`. | Frozen as run. Disclosed in §2. The manifest pins the runner files. |
| Model drift | Each response's model string is recorded (the pilot's was `muse-spark-1.3`), but nothing compares it. | The held-out runner must compare it (C1b). |
| Evaluation plan §7 | Not stated: one- or two-sided tests; tie handling; whether "plan exhausted" and time-censored trials count as censored; errored trials; the Holm family when there are two co-primary metrics; even-n medians; break-even when a median is censored or the baselines tie. | Resolved in §4 and implemented in `analysis.py`. |
| Analysis code | No analysis script existed for held-out data. Earlier analyses were per-experiment scripts. | `analysis.py` and its tests are frozen now, before any held-out data. |
| Target selection | §4.2 asks for 6 buggy targets, 4 controls and 2 multiplexed clients. `HELDOUT_PROTOCOL.md` asked for 8 bases and a mutation script before C1. None of it exists, and its dates have passed. | The minimum scope (§5). The base specifications are fixed now. The mutation script is C1b tooling, which must exist before any base. |
| Operators | "Watch the wrong key" can never be exposed: the proxy runs `WATCH`…`EXEC` as a unit. A mutant that changes serial behavior is not a concurrency defect. | The operator is reduced to "remove `WATCH`". A serial-equivalence filter is added. |
| Baseline methods | M0 replaces the plan's replay with reproduction under control (D-031). M3+arg is implemented but has no trials. M2 (PCT), A1 and A4 do not exist. | M0, M1, M3+ and M3+arg run on held-out. M2, A1 and A4 are not part of v1.0, as the plan's "if time allows" provides. |
| Budgets | `B_exec` 1,000 was raised from 300 after an emulation on D3 (D-023, disclosed). 900 s; `K` 50; 5 rounds. | Frozen. |
| Stopping | Per-trial stopping is defined only in code (`run_trial` statuses). Run-level stop rules existed only for the pilot (READINESS §8). | Both are stated (§2, §6). |
| Verification | `inconclusive_reruns` was 0 for D2 and D3 and 2 for D1. | 2 for every held-out target. |
| Cost accounting | Prices are from D-008's smoke test. Compute uses a nominal rate. No held-out cap was set. | Frozen. A $30 cap is proposed and needs approval. |
| Secondary metrics | Oracle executions (§6, item 4) do not exist: the oracle checks invariants on each execution and has no serial reference runs. RQ5 drafting and explanation accuracy (items 10–11) have no code. | Reported as not applicable and not measured. No claim is made on them. |
| Paired seeds | M4 and A2 have no seed, and each other method has its own stream. Only M3+ and M3+arg are paired. | §4, rule 5. |
| Independent review (subagent, 2026-11-01, two passes) | **First pass:** 7 must-fix findings. Unequal censoring of seconds and dollars; a break-even from successes only; `verify` not checking the run commit; incomplete staging; amendment gaps (class C after C2, the primary version under class B, the C6 script); unvalidated analysis input; a negative-control check that could never fire. **Second pass:** 5 resolved and 2 partial, plus 3 new findings. A time-censored Muse trial truncated E₁; `check` had gaps in scope; false positives from stress, profiles and verification were missed. | All fixed before this commit (§4, `AMENDMENTS.md`, `HELDOUT_PROTOCOL.md`, `freeze/manifest.py check`), and the counterexamples are now tests. The disclosures are in §5 and §8. |
