# A2 results: Muse without source (run 2026-10-28, 17:23–17:27 CDT)

Run `results/20261028-172308/`, at the pre-registration commit `aa1f4eb` with a clean tree.
Protocol: `PROTOCOL.md`. **Exploratory, development-only:** two author-written targets, 5
trials each.
- This is not an independent replication and not a held-out result.
- Nothing here shows that Muse outperforms any baseline.
- The M1, M3+ and source-visible M4 rows are the pilot's trials at `db1f84f`, not re-run.
- The pilot's results directory is unchanged (V5).

## 1. Validity (PROTOCOL.md §5): all pass

The checker was written before the run. It was confirmed to catch a planted fault for every
criterion; a single INCONCLUSIVE execution correctly stays under the 1% threshold, and three are
caught. Full output: `results/20261028-172308/validity.txt`.

| | Result |
|---|---|
| V1 | 13/13 requests carry no source (`a2_audit.check`) and are clean under `audit.findings`; recorded calls = logged calls |
| V2 | 0 errors; 0 INCONCLUSIVE in 263 executions; 0 soundness problems |
| V3 | Every corrected-variant schedule PASS in all 10 verifications |
| V4 | 10/10 hits replay 20/20 with one hash; corrected variant exhaustive |
| V5 | No file under `src/`, `fixtures/`, `docker/`, `tests/` differs from the pilot run; the pilot directory is unchanged since `ecf37d9`; every condition equals the pilot's except `include_source` and the cap |
| V6 | $0.2667 of the $5 cap; 10/10 trials; clean manifest at `aa1f4eb` |

No stop condition occurred.

**Replay check.** Replaying from the recorded answers, in a clean worktree at `aa1f4eb`,
reproduced all 10 trials on status, E₁, executions, witness hash, decisions, workload,
counters, model seconds and dollars. That includes the three round-2 requests, so the feedback
rebuilt from the replayed executions was byte-identical.

## 2. Comparison (development targets; Wilson 95% intervals in brackets)

E₁ is the number of executions until the first verified violation. Censored trials count as
1,001. Method seconds include model latency, as pre-registered.

| Target | Method | Verified | E₁ per seed 1–5 | Median E₁ | Success@100 | @300 | Median method s | Model $ per trial (median) | Model calls |
|---|---|---|---|---|---|---|---|---|---|
| D2 | M1 | 5/5 [0.57, 1] | 9, 5, 7, 5, 1 | 5 | 5/5 | 5/5 | 0.058 | — | 0 |
| D2 | M3+ | 5/5 [0.57, 1] | 8 ×5 | 8 | 5/5 | 5/5 | 0.047 | — | 0 |
| D2 | M4 (source) | 5/5 [0.57, 1] | 1 ×5 | 1 | 5/5 | 5/5 | 14.15 | $0.0146 | 1 ×5 |
| D2 | **A2 (no source)** | 5/5 [0.57, 1] | 1 ×5 | 1 | 5/5 | 5/5 | 16.34 | $0.0169 | 1 ×5 |
| D3 | M1 | 0/5 [0, 0.43] | censored ×5 | 1,001 | 0/5 | 0/5 | 6.80 | — | 0 |
| D3 | M3+ | 5/5 [0.57, 1] | 211, 246, 211, 211, 775 | 211 | 0/5 [0, 0.43] | 4/5 | 1.66 | — | 0 |
| D3 | M4 (source) | 5/5 [0.57, 1] | 1 ×5 | 1 | 5/5 [0.57, 1] | 5/5 | 12.59 | $0.0162 | 1 ×5 |
| D3 | **A2 (no source)** | 5/5 [0.57, 1] | 1, 1, 114, 71, 71 | 71 | 4/5 [0.38, 0.96] | 5/5 | 30.95 | $0.0367 | 1, 1, 2, 2, 2 |

Baseline compute is about $0.00002 per trial at the nominal price. Model tokens over the 5 D3 trials:

| | Prompt | Completion | Reasoning | Cost |
|---|---|---|---|---|
| A2 | 16,227 | 39,218 | 32,483 | $0.18 |
| M4 | 11,510 | 16,811 | 12,348 | $0.08 |

Without the source, Muse reasoned about 2.6× longer per D3 trial.

## 3. Predictions and pre-registered rules

| Pre-registered | Outcome |
|---|---|
| D2: A2 verified 5/5, median E₁ ≤ 2 | **Held**: 5/5 at E₁ = 1 |
| D3: A2 Success@100 ≥ 4/5 | **Held, at the boundary**: 4/5. Seed 3 needed 114 |
| Round-1 hints name commands Muse cannot know, so some steps advance | **Held** on D3 (every round-1 hint advanced steps). On D2, Muse guessed `GET`/`SET` correctly every time |
| R1, source not needed for M4's D3 result (A2 Success@100 ≥ 4/5) | **R1 applies** by the rule as written. The mechanism below qualifies it: the source did matter, in a specific and measurable way |

## 4. What Muse's first-execution hits depend on (item 6)

Every D3 trial's E₁ splits exactly into two parts:
- executions spent on experiments that could not violate (by D3's design, given their setup
  outcomes);
- the schedule index of the hit within the hitting experiment.

| Trial | E₁ | Executions on experiments that could not violate | Hit's schedule index | Round of hit | Round-1 setup order |
|---|---|---|---|---|---|
| M4/1–5 (source) | 1 each | 0 | 1 (hint) | 1 | 5/5 correct |
| A2/1 | 1 | 0 | 1 (hint) | 1 | correct |
| A2/2 | 1 | 0 | 1 (hint) | 1 | correct |
| A2/3 | 114 | 107 | 7 (6th depth-first) | 2 | `publish` before `restock` |
| A2/4 | 71 | 64 | 7 (6th depth-first) | 2 | `publish` before `restock` |
| A2/5 | 71 | 64 | 7 (6th depth-first) | 2 | `publish` before `restock` |

Observations:
- **Without source, Muse still found the bug class and the target operation.**
  - All 5 A2 trials hypothesized `check_then_act` on `purchase`, with no code references.
  - 14 of the 15 round-1 experiments Muse proposed on D3 used purchase quantities that each fit
    the restocked stock and together exceed it. The 15th used `purchase(3)` twice against a stock
    of 2, which can never pass the stock check.
  - On these targets that information is in the interface: operation names, the contract's
    statement, and its error semantics.
- **What the source added was the precondition order.**
  - With the source, 5/5 first experiments ran `create`, `restock`, `publish`. Without it, 2/5 did.
  - The other 3 ran `publish` before `restock`. `publish` refuses an empty product, so every
    round-1 experiment in those trials ran against an unpublished product and could not violate.
  - The contract lists `InsufficientStock` among `publish`'s errors, but in those 3 trials Muse did
    not act on that until it saw it happen.
- **Execution feedback repaired the plan in one round, 3/3.** Round 2 received
  `publish → InsufficientStock` in its setup outcomes, and every round-2 first experiment had the
  correct order.
- **Interpretation:**
  - M4's E₁ = 1 on D3 depends on the source for the setup order. It does not depend on the source
    for the bug.
  - Without the source, Muse plus feedback reached Success@300 5/5 and a median of 71, against
    M3+'s 211.
  - This is n = 5 on one author-written target whose API names its domain plainly. A2 cannot say
    how much of the bug-class inference comes from those names (an A3-style renaming would; not run).

## 5. Schedule selection without source (item 6)

- **Hint hits.** Among all 10 Muse hits on D3, the hint schedule produced the hit in 7: all 5
  source-visible trials and A2/1–2.
- **Hint misses.** In the 3 round-2 A2 hits, the hint schedule passed and depth-first search found
  the violation at its 6th schedule. That is exactly the base index measured for this workload
  structure before the pilot (`experiments/2026-10-28-d3-fixture/`: first depth-first violation at
  6, 120 of 192 schedules violate).
- **Why those hints missed.** The round-2 hints were `HGET@0 HGET@1`. The feedback showed only the
  commands that ran before each purchase failed, so Muse had never seen `GET` or `DECRBY` for
  `purchase`.
- **Without source, a hint is only as good as the command sequence Muse can infer.** Round-1
  guesses (`GET@0 GET@1 …`) worked when the workload could violate (2/2). Truncated feedback led
  to a useless hint (0/3).
- **The hint is worth about 5 executions per hit here** (schedule 1 against 6): small next to the
  64–107 executions a wrong setup order cost.
- **This agrees with the plan's pre-registered expectation** of "little effect" from hints (§10):
  - on D3, the workload, meaning the setup order and quantities, decides E₁;
  - on D2, the depth-first base index is 2, so the hint saves at most 1 execution.

## 6. M3+'s argument-blindness and a proposed variant (item 7)

Mechanism, from `methods.pair_priority` and D3's domains (`m3arg_estimate.py`, no executions):
- **The stock is fixed by the seed.** Novelty ignores argument values, so the first successful
  `restock` in a seed's shuffled order fixes the stock S of the state M3+ builds (uniform over
  1, 2, 3).
- **One purchase pair stands for all quantities.** Every `purchase(q)` with q ≤ S has the same
  command signature, so one unordered pair represents all quantity combinations. That
  representative is uniform over them.
- **The chance of the blind spot is 2/9 per seed:**
  - at S = 1, 0;
  - at S = 2, 1/3 (`purchase(1) ∥ purchase(1)` fits);
  - at S = 3, 1/3 (`(1,1)` and `(1,2)` fit).
  - The pilot saw 1 in 5: seed 5 picked `purchase(1) ∥ purchase(2)` at S = 3, and the violating
    pair waited behind 18 deferred pairs.

**Emulator fidelity.** The emulator replays M3+ over the pilot's recorded profiles and
explorations, and matched every profile call and exploration in order:
- with `methods.run_m3plus`;
- with the variant's code with its change switched off.

Both reproduce E₁ exactly (211, 246, 211, 211, 775). All 30 recorded explorations agree with
D3's design rule for which pairs can violate.

**Proposed: `M3+arg`** (new method ID, post-pilot development, `DECISIONS.md` D-024, Proposed):
- **What it is:** identical to M3+ until the frontier is exhausted. Then, before the other deferred
  pairs, it explores the pairs M3+ deferred only because they differ from an explored
  representative in argument values.
- **What it guarantees:** on any run where M3+ hits before its frontier is exhausted, the two are
  the same.

| | Seed 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| M3+ (pilot, measured) | 211 | 246 | 211 | 211 | 775 |
| **M3+arg (estimate; every reached pair had a recorded cost)** | 211 | 246 | 211 | 211 | **555** |
| M3+arg-immediate (estimate; alternative, rejected) | 281–296 | 281–296 | 281–311 | 281–296 | 531 |

- **The alternative** explores variants right after their representative at every state. It also
  expands harmless variants at earlier states, so it makes the typical case worse. It was rejected
  for that reason.
- **M3+arg is weakly better on these data,** but modestly so: it removes about 220 executions from
  the bad seed and does not change the comparison with Muse on executions.
- **What it does not fix:** M3+ still builds one state per behavior, so it never tries other
  restock quantities. The `M3+` baseline itself is not changed.

## 7. Recommendation (item 8): **re-scope**, not stop, not continue as planned

| Dimension | What the pilot and A2 show (development targets, n = 5) |
|---|---|
| Bug discovery | M3+, M4 and A2 each verified both bugs in 5/5. M1 never found D3. Muse found no bug a baseline missed |
| Execution efficiency | Muse needs far fewer executions. On D3, M4's median is 1, A2's 71, M3+'s 211. Success@100: M4 5/5, A2 4/5, M3+ 0/5. On D2 the margin is 1 against 5–8, worth about 40 ms |
| Wall-clock (method s) | Muse loses on every target: D3 medians are 12.6 s (M4) and 30.9 s (A2) against 1.7 s (M3+). At M3+'s measured 7.7 ms per execution, M4 ties M3+ on D3 only when an execution takes about 60 ms, and A2 at about 215 ms |
| Cost | Muse loses: $0.016 (M4) and $0.037 (A2) per D3 trial, against about $0.00002. At the nominal compute price, M4 ties only when an execution takes about 7 s, and A2 at about 24 s |
| Methodological validity | Strong on mechanics: every hit verified, 0 false positives, both runs replay exactly, payloads audited, code identical across runs. Weak on generality: one author wrote D3, the prompt and the baselines; D3 is a textbook pattern with self-describing names; `HYPOTHESIS_KINDS` carries the author's prior; n = 5 |

Why not each option:
- **Not continue as planned.** RQ3 asks whether the advantage survives latency and cost. On these
  targets it does not, by a wide and structural margin: executions cost milliseconds and a model
  call costs 10–30 s. More trials of the same kind will not change that.
- **Not stop.** The execution-efficiency signal is consistent across both targets and both Muse
  variants. A2 shows it is not only code reading: from the interface alone plus its own execution
  feedback, every A2 trial on D3 needed fewer executions than every M3+ trial (at most 114,
  against at least 211).

**Re-scope**, concretely:
1. **State RQ1's efficiency claim on the pre-registered executions metric, and report the
   wall-clock and dollar break-even per target.** Measured here: about 60 ms per execution for M4
   on D3. Do not present execution savings as time or cost savings unless the break-even is
   crossed.
2. **Measure the per-execution cost on D1, the real cart, early** (kill gate K, Oct 30). If a real
   service's execution takes more than about 60–200 ms, the wall-clock comparison becomes
   live. That is a measurable prediction, not a claim.
3. **Keep A2 required on held-out targets**, as the plan already says. Ask the owner whether to add
   an interface-obfuscation (A3-style) ablation, since A2 shows the interface carries most of the
   signal. Any such run needs separate approval.
4. **Decide D-024:** whether `M3+arg` joins M3+ as an additional, disclosed baseline before the
   freeze.

The owner decides (§8.D of the pilot's READINESS). This recommendation does not change any
pre-registered rule.

## 8. Limitations

- Two development targets written by the author of the prompt and the baselines; 5 trials;
  temperature 1.0.
- A2 ran about 30 minutes after the pilot with the same model ID; model-side drift cannot be
  excluded.
- "Could not violate" relies on D3's documented design. It was checked against all 30 recorded M3+
  explorations, and on A2's unviolable experiments every executed schedule passed.
- The M3+arg numbers are emulated estimates from recorded data, not runs.

## 9. Reproduction

- **Validity:** `check_validity.py results/20261028-172308 --commit aa1f4eb76089926fda29c98d29d217488659c96b`.
  The curated directory includes `executions.jsonl`, so this needs no raw data.
- **Replay:** check out `aa1f4eb` into a clean tree, copy `results/20261028-172308/model_calls.jsonl`
  out, and run `run_a2.py --replay-model <that file>`.
- **Analysis:** `analyze.py runs/a2-20261028-172308 runs/pilot-20261028-165020`. The raw pilot
  log is git-ignored; its derived numbers are in `analysis.json`.
- **M3+ estimate:** `m3arg_estimate.py` reads the committed extract `m3_d3_record.json`.
