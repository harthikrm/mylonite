# Held-out evaluation v1: results

Minimum scope (D-037): 2 held-out mutants, each with its base as a negative control, and 20 trials
per method per target. Frozen analysis (`docs/FREEZE.md` §4, `src/mylonite/analysis.py`), freeze
v1.2. Single developer; no independent author was involved.

## Provenance

| Step | Commit | What |
|---|---|---|
| C2 | `50fe826` | Bases committed; round R = 6605131 named; FreeTSA timestamp `9d09957` |
| C4 | `76264cf` | Mutants generated from round 6605131; nobody opened them before C6 |
| C5 run 1 | `f82681e` | Stopped by the crash rule on a harness defect (D-043); primary for the trials it completed |
| AM-002, v1.2 | `e19d818`, `3bb8957` | The model client's transport errors reach the frozen retry rule (class B) |
| C5 run 2 | `8e249c3` | Restart from scratch under v1.2, complete, no stop (D-044); post-observation |
| C6 | `0cf4fb6` | Both mutants shown buggy by C5's own verified witnesses; nothing excluded |
| Driver | `cac2654` | `analyze_heldout.py`, committed before its first run |

- **Beacon at C6.** Round 6605131 was fetched again from api.drand.sh (byte-identical to the C3
  fetch) and from drand.cloudflare.com. Round, randomness, signature and previous signature all
  equal the committed response. The BLS signature has not been verified here.
- **The mutants (revealed at C6).** Both use operator O1: an atomic update becomes a read, a
  computation and a write.
  - `alpha_m`: `reserve`, line 80. `HINCRBY` becomes `HGET` + `HSET`, at a guarded site (inside
    a branch that depends on a store read).
  - `beta_m`: `discard`, line 79. `DECRBY` becomes `GET` + `SET`, at an unguarded site.
- **Spend:** $25.01 of model calls over both C5 runs ($4.58 and $20.44), under the $30 cap.

## How the two C5 runs combine

`AMENDMENTS.md` class B: the aborted run stays primary for every trial it completed, and the
restart is reported beside it, labeled post-observation.
- **Primary:** run 1 for `alpha_m` (120 trials) and for 60 `beta_m` trials; run 2 for the other
  60 `beta_m` trials and all 200 control trials.
- Two run-1 trials ended in a model-client error: `beta_m` M4 seed 8 and A2 seed 10. Under
  `FREEZE.md` §4 rule 3, a Muse trial uses its first attempt and an error is a failure. So both
  count as failures in the primary analysis. This is the reading less favorable to Muse.
- **Sensitivity analyses:** run 2 alone, and the primary with A2 seed 10 taken from run 2 (the
  reading D-044 first gave).

## Confirmatory results (primary)

Holm-adjusted p-values, across the 6 cells of each group, separately for "better" and "worse".
Every `beta_m` cell includes 60 post-observation trials (seeds 11–20, from run 2), and so do the
negative controls. Run 2 alone gives the same verdicts (see Sensitivity).
"Conventional" is {M0, M1, M3+, M3+arg}; Muse is better than a group only if it is better than
every member. "Systematic" ({M3+, M3+arg}) gives the same verdict as conventional in every cell.

| Muse condition | Metric | `alpha_m` | `beta_m` |
|---|---|---|---|
| **M4** (with source) | E₁ (executions to the first verified violation) | **better**, p = 8.7e-11 | **better**, p = 2.0e-5 |
| | method-seconds | **worse**, p = 1.0e-7 | **worse**, p = 8.7e-11 |
| | dollars | **worse**, p = 1.0e-7 | **worse**, p = 8.7e-11 |
| **A2** (no source) | E₁ | no significant difference, p = 0.84 | **worse**, p = 0.015 |
| | method-seconds | **worse**, p = 1.0e-7 | **worse**, p = 8.7e-11 |
| | dollars | **worse**, p = 1.0e-7 | **worse**, p = 8.7e-11 |

**Negative controls:** 200 trials on the two bases (M0, M1, M3+, M3+arg and M4, 20 each). There
were 0 VIOLATION verdicts from scheduled executions, stress runs, serial profiles, or the
corrected variant during witness verification, and 0 control hits that replayed.

## Per method

Verified trials out of 20; median E₁ with its 95% bootstrap interval (1001 means "not reached":
more than half failed); and medians of method-seconds and dollars to the first verified
violation (failures are infinite).

| Target | Method | Verified | Median E₁ [95% CI] | Median seconds | Median dollars |
|---|---|---|---|---|---|
| `alpha_m` | M0 | 0 | not reached | not reached | not reached |
| | M1 | 0 | not reached | not reached | not reached |
| | M3+ | 17 | 764 [546, 856] | 6.5 | < $0.001 |
| | M3+arg | 17 | 764 [546, 856] | 5.8 | < $0.001 |
| | **M4** | **20** | **1 [1, 1]** | 41.8 | $0.033 |
| | A2 | 13 | 401 [254, not reached] | 159.5 | $0.124 |
| `beta_m` | M0 | 20 | 205 [131, 300] | 2.0 | < $0.001 |
| | M1 | 18 | 292 [131, 582] | 3.9 | < $0.001 |
| | M3+ | 20 | 97 [82, 127] | 1.0 | < $0.001 |
| | M3+arg | 20 | 97 [82, 127] | 1.0 | < $0.001 |
| | **M4** | **19** | **1 [1, 1]** | 59.9 | $0.047 |
| | A2 | 19 | 137 [137, 201] | 68.1 | $0.072 |

- M4 made 1 model call in every `alpha_m` trial, and 1–2 in every completed `beta_m` trial.
  Its one `beta_m` failure is run 1's errored seed 8. A2 used 2–5 calls.
- M3+ and M3+arg have the same E₁ on all 20 seeds of both targets: M3+arg never exhausted
  M3+'s frontier.

## Break-even: when M4 would pay off

One execution costs about 9 ms on both mutants (median 0.0090 s and 0.0091 s). M4 spends far
fewer executions but adds model latency and model dollars. The frozen break-even gives the cost
per execution above which Muse's median cost to the first verified violation is below every
conventional method's.

| Condition | Unit | `alpha_m` | `beta_m` |
|---|---|---|---|
| M4 | seconds per execution | 0.055 s (6× the measured cost) | 0.62 s (68×) |
| M4 | compute-seconds per execution, for dollars | 3.9 | 44 |
| A2 | seconds per execution | 0.43 s | never: A2 needs more executions than M3+, so it is not cheaper however costly an execution is |
| A2 | compute-seconds per execution, for dollars | 30.5 | never |

## Secondary results (not claims on their own)

- **Against M0 and M1 alone:** M4 is better on E₁ on both targets. On `alpha_m`, seconds and
  dollars show no significant difference, because M0 and M1 never found the bug: under the
  frozen τ rule, every M4 success that cost more than their censoring point ranks as a tie with
  their failures. On `beta_m`, M4 is worse on seconds and dollars than each.
- **M4 against A2 (does reading the source help? RQ2):** M4 is better on E₁ on both targets
  (Holm p = 8.7e-11 and 5.3e-7). It is also better on seconds and dollars on `alpha_m`; on
  `beta_m` those two show no significant difference (p = 0.22 and 0.11).

## Sensitivity

- **Run 2 alone** (complete, single version, post-observation): every confirmatory verdict is
  the same as in the primary. Two secondary cells change: M4 against A2 on `beta_m` becomes
  "better" on seconds and dollars. Run 2 has no errored trial, so M4 finds `beta_m` in 20 of 20.
- **A2 seed 10 from run 2:** every verdict is the same as in the primary.
- **Run to run** (descriptive; trials both runs completed): the seeded methods M1, M3+ and M3+arg
  gave the same status and the same E₁ on every such trial. M0 is stress, timing-dependent, and
  its E₁ differed on every `beta_m` trial. The Muse conditions vary too: M4 had the same E₁ in
  27 of 29 trials both runs verified.

## What this does and does not show

- **Shown, on these two mutants:** M4 needs fewer executions to find the bug than every
  conventional baseline, and that holds against the strongest one, which is what the plan
  requires. With executions as cheap as they are here, that does not make it faster or cheaper:
  it is worse on both time and dollars.
- **Shown:** reading the source is what makes the difference in executions. Without it (A2),
  Muse is not better than the conventional group on any metric.
- **Not shown:** that this generalizes. There are 2 mutants, both from the same operator (a lost
  update), in small Python services written by the same developer who ran the evaluation.
- **The small p-values measure repeatability on these targets, not breadth.**
  - M4's trials are near-replicates. 35 of its 39 verified trials found the bug at execution 1,
    each with one model call.
  - Every round-1 prompt is the same 3,078 tokens, and in 13 of 20 `alpha_m` trials the
    provider served 3,057 of them from its prompt cache. 19 of 20 `alpha_m` witnesses in run 1
    use the same workload.
  - So p ≈ 1e-11 says M4 reliably repeats one good plan on each target. It does not say M4
    would win on a different defect.
  - Together, these suggest that M4's advantage in executions comes from reading the mutated
    line, which is a hypothesis rather than something measured: both mutants are O1, there are
    no decoys, and A2 is not better than M3+.
- **Disclosed deviations that favor M4** (`HELDOUT_PROTOCOL.md`, minimum scope):
  - **There are no style decoys,** and the mutation stands out to a source reader. In each
    mutant, the mutated lines are the only read-then-write of a counter outside a `WATCH`
    transaction. Every other update of that counter uses `HINCRBY`, `INCRBY` or `DECRBY`, or a
    `WATCH`/`MULTI` transaction (read from the sources after C6).
  - No guaranteed shallow stratum, which is where baselines were expected to win.
- **Found at the reveal, not disclosed before:** the generator rewrites the whole mutant file
  through `ast.unparse`, so quote style, line wrapping and blank lines differ from the
  hand-written base. Within a mutant the style is uniform, so the mutated line does not stand
  out by style. But a reader who saw both files could tell the mutant from the base. No method
  sees both in one trial.
- **Other limits:**
  - The analysis driver was written after outcomes were observed. It makes no rule of its own,
    and it was committed before its first run.
  - The prompt cache is shared across trials, so Muse's dollar cost depends on trial order. The
    dollar verdict is "worse" either way.
  - 26 of A2's 32 verified witnesses had only the bounded check on the corrected variant, against
    1 of M4's. This is the frozen rule: the check is exhaustive only up to its cap.
  - 9 M4 trials on the controls ran past the 900 method-second budget, the longest to 1,098 s.
    The budget is checked before each model round and each execution (`methods.py:93`, `:343`),
    so a model call already in flight runs to its end. This affects controls only.

## Independent review

An independent reviewer recomputed the results without importing `analysis.py`, using a
different exact algorithm for the Mann–Whitney test. All of these reproduced exactly:
- the 12 verified counts and medians;
- all 48 comparisons (p, Â₁₂ and τ);
- the 24 confirmatory verdicts with their Holm values;
- all 32 break-evens;
- both sensitivity variants.

The reviewer found nothing that must change. It found two places where the frozen code differs
from the frozen text. Neither changes any result here, and neither is fixed: a fix after
observation would be a class B amendment.
- `analysis.cost_lines` gives a baseline stopped by the time budget a finite lower bound.
  `FREEZE.md` §4 rules 1 and 10 call it failed, which is infinite. This favors the baseline. No
  baseline trial on either mutant hit the time budget.
- `analysis.false_positives` scans only the records the analysis selected. Rule 11 counts every
  VIOLATION. A scan of all 882 records in both runs finds 0 corrected-variant VIOLATIONs, and the
  200 control records have none from any source.

Under the reviewer's other readings of the combination:
- with A2 seed 10, or both errored Muse trials, taken from run 2, no confirmatory verdict changes;
- counting M4 seed 8's re-run instead of its first attempt, which breaks rule 3, would turn the
  secondary "M4 against A2, `beta_m`, dollars" into "better".
  - Run 2 is post-observation.
  - The manifests for v1.0–v1.2 are not anchored externally (OTS awaits approval).
