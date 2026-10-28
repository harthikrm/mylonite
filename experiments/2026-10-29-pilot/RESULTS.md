# Pilot results (run 2026-10-28, 16:50–16:54 CDT)

Run `results/20261028-165020/`, at commit `db1f84f` with a clean tree, using `config.json` as
pre-registered. The criteria applied here are the ones fixed in `READINESS.md` §8 before the run.
`check_validity.py` was written after the run, to those criteria. It reads the raw run directory
and was checked against a planted fault for each criterion; all were caught.

**This is a development pilot on two author-written targets, with 5 trials per method. It shows
that the harness works and gives the owner a continue/re-scope signal. It is not evidence that
Muse outperforms any baseline, and no such claim is made.**

## Validity (§8.B): all pass

Full output: `results/20261028-165020/validity.txt`.

| Criterion | Result |
|---|---|
| B1 every model request clean | 10/10 requests clean, under the runtime gate and again under an independent re-run of `audit.findings` |
| B2 no errors, INCONCLUSIVE ≤ 1%, no soundness problems | 0 errors; 0 INCONCLUSIVE in 6,731 executions and profiles; 0 soundness problems |
| B3 corrected variant | Every schedule PASS in all 25 verifications |
| B4 every hit verified | 25/25 verified trials replay 20/20 with one hash. Corrected variant mode: exhaustive in all 25 |
| B5 D2 sanity | M1 5/5, M3+ 5/5 |
| B6 spend, completeness, manifest | $0.1516 of $10; 30/30 trials recorded; dirty list empty; commit `db1f84f` |
| Accounting | Logged executions and profiles match each trial's count; no trial over B_exec or 900 method seconds |

No §8.C stop condition occurred. The run was watched live for soundness problems,
INCONCLUSIVE executions and corrected-variant failures.

## Results

E₁ is the number of executions until the first verified violation. Censored trials count as
1,001 in the median (§7). Method seconds include model latency, profiling and harness overhead;
verification is not charged (D-022).

| Target | Method | Verified | E₁ per seed 1–5 | Median E₁ | Success @100 / @300 / @1000 | Median method s [range] | Dollars, 5 trials |
|---|---|---|---|---|---|---|---|
| D2 | M1 | 5/5 | 9, 5, 7, 5, 1 | 5 | 5 / 5 / 5 | 0.058 [0.006, 0.077] | $0.000003 |
| D2 | M3+ | 5/5 | 8, 8, 8, 8, 8 | 8 | 5 / 5 / 5 | 0.047 [0.043, 0.066] | $0.000003 |
| D2 | M4 | 5/5 | 1, 1, 1, 1, 1 | 1 | 5 / 5 / 5 | 14.15 [10.45, 14.88] | $0.0708 |
| D3 | M1 | 0/5 | censored ×5 | 1,001 | 0 / 0 / 0 | 6.80 [6.66, 9.02] | $0.0004 |
| D3 | M3+ | 5/5 | 211, 246, 211, 211, 775 | 211 | 0 / 4 / 5 | 1.66 [1.24, 6.91] | $0.0001 |
| D3 | M4 | 5/5 | 1, 1, 1, 1, 1 | 1 | 5 / 5 / 5 | 12.59 [11.08, 13.84] | $0.0808 |

Model calls:
- 10 calls in all, one per M4 trial. Every trial hit in round 1, so no feedback round ran.
- No retries. Every call finished with `stop`.
- 30/30 proposed experiments were valid.
- 18,590 prompt tokens (8,757 of them cached), 32,468 completion tokens. Median latency 12.6 s.
- Recorded dollars match the token counts × config prices for every call.
- The request was byte-identical across the 5 trials of each target (one SHA-256 per target). The
  M4 trials are therefore 5 samples, at temperature 1.0, of one fixed input.

## Interpretation, by the pre-registered rules (§8.D)

**No statement that M4 outperforms anything comes from this pilot** (§8.D, first rule).

**D2: the prediction was half wrong.** §8.D predicted a tie on executions and M4 losing on cost:
- Executions: not a tie. M4 needed 1 in every trial, against medians of 5 (M1) and 8 (M3+).
- Cost: M4 lost, as predicted. It used about 240× M1's and 300× M3+'s median method seconds,
  and $0.014 per trial against about $0.000001.
- In time, the baselines' extra 4–7 executions are worth 30–50 ms.

**D3, M1: the prediction held.** M1 was censored in 5/5, as predicted (≈ 0.08% within 300; it was
not reached within 1,000 either).

**D3, M4 against M3+: both pre-registered clauses fire. The rule has no precedence for this case.**
- *Continue*: M4's Success@1000 (5) ≥ M3+'s (5), **and** M4's median E₁ (1) ≤ M3+'s (211). **Holds.**
- *Re-scope or re-frame*:
  - its first part, M4's Success@1000 < M3+'s, does not hold;
  - its second part holds. M4 wins only on executions. It loses on both cost measures: a median
    of 12.59 against 1.66 method seconds (7.6×), and $0.016 against about $0.00003 per trial. And
    M3+ succeeded in 5/5, which meets the ≥ 4/5 condition.
- The clauses were meant to be exclusive, and they are not. That is a defect in the
  pre-registration, recorded here rather than resolved after the fact. Under §8.D's last line,
  the owner decides.
- Facts that bear on the decision:
  - The re-scope clause describes this exact pattern, which `READINESS.md` §6 risk 1 predicted
    before the run.
  - Where M4 does lead, it leads at small budgets: Success@100 5/5 against M3+'s 0/5, and @300
    5/5 against 4/5.
  - Break-even on method seconds: at M3+'s measured 7.7 ms per execution, M4's median 12.6 s per
    trial equals about 1,600 M3+ executions. On D3, M3+ needed 211–775.
  - Break-even on dollars, at the nominal compute price: about 190,000 executions.

## What explains M4's E₁ = 1 (observations, not claims)

- **Muse read the bug out of the source.** All five D3 plans:
  - named a single `check_then_act` hypothesis;
  - cited the same two lines of the shown `service.py`, the stock check and the decrement;
  - proposed the full three-step precondition (`create`, `restock`, `publish`) and two
    concurrent `purchase` calls.
  On D2, all five plans named `lost_update` at the read and the write.
- **The search side of M4 was barely exercised.** Each trial's first execution of its first
  experiment violated, so the following were never run live:
  - depth-first schedules beyond the hint;
  - feedback rounds;
  - the second and third experiments.
- **This pilot cannot separate reading code from planning.** Every M4 trial ran with
  `include_source: true`. The A2 ablation (no source) was not part of the pilot.
- **D3 is a textbook check-then-act written by the same author as the prompt and the baselines**
  (`READINESS.md` §6 risk 4). Muse may recognize the pattern rather than infer it.
- **The hint-advance rule mattered live.** In 3 of the 5 D3 trials, Muse's hint omitted
  `purchase`'s first command, the status read. The rule ran that command first and then followed
  the hinted steps: 2 steps advanced, 4 followed, 0 skipped, 0 forced decisions. Before review
  fix #3, those hint steps would have been skipped silently.

## M3+ observations

- **The emulation was confirmed.** 4/5 seeds found D3 within 300 executions (211–246), and the
  emulation predicted 16/20 at 161–285. The seed only orders calls and pairs. On D2, the contract
  priority puts the same pair first for every seed, hence E₁ = 8 throughout.
- **Seed 5 (E₁ = 775) shows the known argument-blindness limit** (`READINESS.md` §6 risk 5):
  - Pair priority allows one pair per operation signature and ignores argument values.
  - At the published state (stock 3), seed 5's one prioritized `purchase ∥ purchase` pair was
    `purchase(1) ∥ purchase(2)`. Its total equals the stock, so it cannot go negative.
  - The violating `purchase(3) ∥ purchase(1)` was deferred behind 18 other pairs. It ran at
    executions 770–775 and violated on its 6th schedule.
  - Seed 1 picked `purchase(3) ∥ purchase(1)` first and found it at 211.
  - Making the priority argument-aware would strengthen the baseline. It would also be a baseline
    change made after seeing pilot results, so it is an owner decision and must be disclosed if
    made.

## Newly exercised, and still not exercised

Exercised for the first time:
- the live API with the v2 request: 10/10 calls, strict schema, 67-value command enum;
- M3+ on D3 in the real executor;
- hint advance on live model output.

Still not exercised:
- a real unscheduled command reaching the soundness check;
- a corrected-variant check in bounded mode (all 25 were exhaustive);
- M4 feedback rounds and depth-first schedules on live output;
- the retry path.

Also observed: D2/M1 hits cost up to 30 s of verification (2,520 corrected-variant schedules).
Verification is not charged to any method, by design.

## Reproduction

Check out `db1f84f` into a clean tree, copy `results/20261028-165020/model_calls.jsonl` out of
this commit, and run `python3 experiments/2026-10-29-pilot/run_pilot.py --replay-model <that
file>`. M1 and M3+ are seeded. M4 replays the recorded answers, with no API call.

**Done once, on 2026-10-28 (16:59 CDT), from a temporary worktree at `db1f84f`:**
- all 30 trials matched the original on status, E₁, executions, witness trace hash, schedule
  decisions, workload and counters;
- recorded model latency and dollars matched too.

Only host timing differs. The raw run
(`runs/pilot-20261028-165020/`, 12 MB, git-ignored) holds every execution, profile and
verification. To re-check validity, run `check_validity.py runs/pilot-20261028-165020 --commit
db1f84f41682a9114d67fed9abe1197e887c4947`.
