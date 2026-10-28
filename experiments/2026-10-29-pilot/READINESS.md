# Pilot readiness review (written 2026-10-28, before the pilot)

**Verdict: ready to run once the owner approves live model calls (cap $10) and the go
criteria in §8.A hold.** Nothing here is evidence about Muse's effectiveness. The pilot cannot
produce such evidence either: 5 trials per method, on development targets written by the people
who wrote the prompt and the baselines.

## 1. Source changes

| Area | Change | Why |
|---|---|---|
| `planner.py` | The request is built only from a declared view:<br>• catalog, domains, limits, observation;<br>• contract without provenance;<br>• `model_view` files under display names, with comments and every bare string statement removed (AST);<br>• allow-listed feedback.<br>Plus a target-independent command vocabulary, issue codes in feedback, defensive validation, merged argument domains, `ModelAPIError`. Prompt `planner-v2-2026-10-28`. | Closes the three tracer leaks; review findings #3, #4, #10 |
| `audit.py` (new) | Runs on every request:<br>• artifact shapes (schedule labels, digests, verdict words, result keys);<br>• labels, harness paths and fixture IDs, split out of identifiers;<br>• identifiers and lines found only in the corrected variant. | Second layer behind the noninterference tests |
| `space.py` (new) | One catalog × domains × limits space and one validator for every method | Equal search space (rule 7) |
| `methods.py` (new) | `Trial`: the only counter of executions, with the budget, method seconds and verification. M1, M3+ (greybox breadth-first, conflict-cycle pair filter, contract-directed priority) and M4 (≤ 5 rounds, own feedback only). | Equal budgets and accounting by construction (D-022, D-023) |
| `executor.py` | JSON-lines session mode; `profile`; store-state digest; setup calls that raise are recorded; proxy/store failures become INCONCLUSIVE; pass-through compares each call's result | Harness crash paths; M3+ needs profiles |
| `proxy.py`, `resp.py`, `scheduler.py` | Script key extraction; `WRITES`; unscheduled commands during a round become soundness problems; hint steps advance through an operation's earlier commands | Review findings #3, #7 |
| `sandbox.py` | Persistent `ExecutorSession`: same hardening, fails fast on exit, never reused after a timeout | Review finding #10 |
| `oracle.py` | `non_negative` state invariant | D3's contract |
| `fixtures/dev/d3_inventory/` (new) | 8-operation inventory service with a setup-dependent check-then-act; `EVAL` corrected variant; `DESIGN.md` | Step 2 of the request |
| `fixtures/dev/d2_counter/` | `model_view`; contract stated as a property; clause renamed | Same semantics |
| `experiments/2026-10-29-pilot/` | `config.json` (pre-registered); `run_pilot.py` | Step 4 of the request |
| `run_pilot.py` details | Manifest with commit, dirty list, SHA-256 of every source file, images and prompt fingerprint; full model I/O; incremental `trials.jsonl`; replay from recorded answers; retry rule; refuses dirty trees; censoring-aware summary | Step 4 of the request |
| `docs/HELDOUT_PROTOCOL.md` (new) | Sole-developer protocol (D-020, proposed) | Step 5 of the request |

## 2. Evidence

**Unit tests: 38/38 pass.** Run `python3 -m unittest tests/test_core.py tests/test_contamination.py`.

Contamination (`test_contamination.py`):
- **Noninterference.** Each perturbation leaves the request byte-for-byte unchanged, for D2 and
  D3:
  - the source moved under a revealing path;
  - the corrected variant replaced;
  - the target ID, modules and provenance renamed;
  - result files, raw runs and a README added;
  - comments and docstrings added to the shown source.
- **Only the declared files are opened.** The spy covers `io.open` and `open`.
- **Feedback** is unchanged when schedules, steps, digests and hashes are scrambled.
- **Sensitivity.** Source, domain, contract and A2 changes all change the request.
- **Detectors.** Each of the 12 fires on a planted positive. A label inside a string literal is
  caught. The real requests are clean.
- **Target independence.** The same system message and schema skeleton for D2 and D3, and no
  target vocabulary in the instructions.
- **Gate and model text.** A contaminated request is refused before any model call.
  Model-written text is not echoed back.

Core (`test_core.py`):
- framing, oracle, enumeration, hints, the validator and the planner schema;
- the shared space, `non_negative` and script keys;
- normalization and the pair filter;
- M3+ order;
- trial accounting: the budget is exact, the first verified violation is counted, and an
  unreliable replay is not verified;
- soundness.

**Sandbox checks (real executor, Valkey 9.0.4):**
- **D3 fixture validation** (`experiments/2026-10-28-d3-fixture/`), run twice, with identical
  results the second time on the final code:
  - egress blocked;
  - pass-through: 0/50 mismatches;
  - serial runs: 150/150 PASS on each variant;
  - author's witness: replay 20/20 with one hash, 120 of 192 schedules violating;
  - every setup step necessary;
  - corrected variant 6/6, 6/6 and 90/90 PASS.
- **Harness smoke runs** (not pilot data; M4 used a stub that proposes random valid
  experiments):
  - D2: M1, M3+ and M4 all verified, at E₁ = 9, 8 and 3;
  - D3 at a budget of 30: all censored, as intended;
  - 0 INCONCLUSIVE executions;
  - a replayed M4 trial reproduced its witness hash, decisions and E₁ exactly.

**Not yet exercised:**
- a live model call with the v2 request;
- M3+ on D3 in the real executor (emulated only, by the reviewer);
- a real unscheduled command reaching the new soundness check;
- a corrected-variant check in bounded mode.

## 3. Equivalence across methods

| | M1 | M3+ | M4 |
|---|---|---|---|
| Operations, values, limits | `space.py` | same | same: schema enums plus the same validator |
| Correctness condition | Contract oracle on every execution | same | same; the model also reads the contract |
| Executions | ≤ 1,000, each counted by `Trial` | same; profiling is charged | same |
| Time | ≤ 900 method seconds | same | same; model latency (and retries) charged |
| Per-workload schedules | 1 (a new workload each time) | ≤ 50 per pair | ≤ 50 per experiment (hint + depth-first) |
| Information | catalog, contract | plus its own profiles and **store-state digests** (greybox) | plus the normalized source and feedback on its own experiments |
| Verification | `methods.verify` | same | same |
| Seed | workload and schedule draws | call and pair order only | none usable (temperature 1.0) |

M3+ sees store-state digests that M4 never sees. Rule 2 forbids only the reverse, so this
favors the baseline.

## 4. Independent review and disposition

A fresh agent was given the code, not my conclusions. Its emulation reproduced the D3 numbers
exactly.

| # | Finding | Disposition |
|---|---|---|
| 1 | Blocker: breadth-first M3+ is censored on D3 at 300 executions (20/20 seeds in emulation; hand count agrees) | **Fixed:** contract-directed pair priority (D-023, a disclosed post-emulation change that strengthens the baseline). **Fixed:** B_exec = 1,000, with Success@100/300/1,000 |
| 2 | One error ends the whole pilot | **Fixed:** any error ends only its trial; incremental `trials.jsonl`; retry rule |
| 3 | Hint steps silently skipped | **Fixed:** steps advance through earlier commands; the prompt states the rule; tested |
| 4 | The audit trips on the model's own text | **Fixed:** issue codes only; tested |
| 5 | Pre-registration not committed | **Fixed** by this commit; the runner refuses dirty trees |
| 6 | Median ignores censoring | **Fixed:** budget + 1 for censored trials; Success@b |
| 7 | Proxy blind spots: first key only, unscheduled commands, `WATCH` | Unscheduled commands **fixed** (soundness problem). First key and `WATCH`: **open, before the freeze** (protocol) |
| 8 | Read spy too narrow; weak fingerprint; author prior in hypothesis kinds; prompt wording | **Fixed:** spy and wording. Fingerprint: the freeze pins every `src/` hash. Prior: **disclosed** (§5 of the plan) |
| 9 | Protocol: backdating, C6 labeling, shaping bases against M3+, mutant style, sealed mount, blindness | **Addressed** in `HELDOUT_PROTOCOL.md`. External timestamp now mandatory; it needs a public action |
| 10 | Minor: domain collisions, replay crash and latency, session reuse, harness errors in setup | **Fixed** |

## 5. What every pilot run records

`runs/pilot-<ts>/` holds everything; `results/<ts>/` holds the curated copy, which is committed:
- **manifest:**
  - git commit and dirty list (must be empty);
  - SHA-256 of every file under `src/`, `fixtures/`, `docker/` and `tests/`, plus the config
    and the runner;
  - host and executor Python versions, and the redis-py version;
  - executor image ID and Valkey digest;
  - prompt version and fingerprint;
  - full config and arguments;
  - start and finish times;
- **per trial:** status, E₁, executions, method seconds, harness overhead, verification time,
  model seconds and calls, tokens (prompt, cached, completion, reasoning), model and compute
  dollars, counters, the witness (workload, decisions, trace hash, pre/post, violations), and
  the verification;
- **every execution, profile, verification, validation and model call** (git-ignored raw);
- **every model request and full response, and failed attempts**, in `model_calls.jsonl`. They
  are committed, which is what makes replay possible.

To reproduce: check out the manifest's commit, then run
`run_pilot.py --replay-model results/<ts>/model_calls.jsonl`. The executions are deterministic
given the model answers; the model itself cannot be re-sampled.

## 6. Unresolved risks, most serious first

1. **The cost metric is structurally hard for M4 on these targets.** An execution costs about
   6 ms and a model call about 10 s. M4 can win on wall-clock only where baselines need on the
   order of 1,500 executions per model call, or fail outright. Expect M4 to lose on cost on D2
   and probably on D3, whatever happens on executions.
2. **The live API is untested with the v2 request**: a 67-value command enum, nullable unions,
   and longer prompts with feedback. The first M4 trial acts as the preflight. If it fails, the
   trial ends in `error`, so the pilot is invalid under §8.B2.
3. **M3+ on D3 has only been emulated.** The real executor may differ.
4. **Author conflict.** The same authors wrote D3, M3+, the prompt and the tests, and D3 is a
   textbook pattern Muse may have memorized. Development only; no claims.
5. **M3+ limits:**
   - pairs only;
   - novelty ignores argument values (one state per new behavior);
   - conflicts use the first key only.

   These may make M3+ weaker than a best-effort baseline on held-out targets. They are to be
   fixed or disclosed before the freeze.
6. **Small n and temperature 1.0.** Five trials per method give coarse signals only.
7. **The time cap binds only M4.** That is by design: baseline compute is cheap. Recorded.
8. **The held-out protocol is unapproved.** Its pre-freeze work (mutation script, `WATCH`
   gating or dropping operator 2, multi-key conflicts, sealed-root mount, external timestamp) is
   due Oct 30–31, which is a schedule risk.

## 7. Expected cost and time

- **M4:** at most 5 calls × 10 trials = 50 calls. From the tracer, about $0.013 per call and
  more with feedback. Expect **about $0.5–1.5**, under the $10 cap the runner enforces.
- **M1 and M3+:** up to 1,000 executions × about 7 ms per trial, plus verification (an M1 hit on
  D2 can need up to 2,520 corrected-variant schedules, about 15 s).
- **Total wall-clock:** about 15–30 minutes, mostly model latency.

## 8. Pass/fail criteria (fixed before the run)

**A. Go: all must hold before starting.**
1. 38/38 unit tests pass at the commit to be run.
2. The working tree is clean and the manifest commit is HEAD. The runner refuses otherwise.
3. `config.json` is unchanged since this review's commit.
4. The owner has approved live model calls up to $10.

**B. Validity: all must hold for the pilot to count. Otherwise, fix, re-run everything, and
report both runs.**
1. Every M4 request passed the audit. The runner enforces this, and a refusal shows as an
   `error` status.
2. No trial ends in `error`. INCONCLUSIVE ≤ 1% of executions per method. 0 soundness problems.
3. 0 violations on any corrected-variant run. Any violation there is a false positive and
   blocks every conclusion until explained.
4. Every reported hit is verified (replay 20/20 and the corrected check), with its mode recorded.
5. D2 sanity: M1 and M3+ are verified in 5/5 trials. Otherwise suspect the harness.
6. Model spend ≤ $10 (enforced). All 30 trials are recorded and the manifest's dirty list is
   empty.

**C. Stop the run at once if:** a contamination refusal, a soundness problem, a corrected-variant
violation, or repeated executor failures appears. Then report it rather than patching mid-run.

**D. Interpretation, decided now.**
- No statement that M4 outperforms anything comes from the pilot.
- D2: expect a tie on executions and M4 losing on cost. Anything else gets reported as such.
- D3, with M1 predicted censored in 5/5:
  - If M1 succeeds, the prediction was wrong: investigate before any conclusion.
- D3, M4 vs M3+ (the owner's continue / re-scope signal):
  - **Continue as planned** if M4's Success@1000 ≥ M3+'s **and** M4's censored median E₁ ≤ M3+'s.
  - **Re-scope or re-frame** (§9 of the plan: for example Muse ranking M3+ candidates, spec
    drafting, or the verified-reproduction tooling) if M4's Success@1000 < M3+'s, or if M4 wins
    only on executions while losing on both cost measures **and** M3+ succeeds in ≥ 4/5.
  - **Anything in between** is reported as inconclusive at pilot scale. The owner decides.
- Success@100 and Success@300 are reported for every method alongside @1000.

## 9. Decisions needed from the owner

1. Approve running the pilot with live Muse calls (cap $10).
2. D-020, the held-out protocol, including two choices:
   - moving the method freeze to Oct 31 12:00 ET;
   - the Python-only injection scope.
3. Whether the protocol's external timestamp may be a GitHub push or an OpenTimestamps
   submission. Both are public actions.
