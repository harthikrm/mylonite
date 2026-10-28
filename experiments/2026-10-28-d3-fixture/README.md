# Experiment 2026-10-28: D3 fixture validation (no search method run)

**Question.** Is D3 what `fixtures/dev/d3_inventory/DESIGN.md` says it is? Specifically: is the
contract serially valid, is the failure real and reproducible, is the setup necessary, and does
the corrected variant pass?

**No search method ran.** The witness was **constructed by the fixture's author**, who knows
the bug. It is not a search result and says nothing about how hard D3 is for any method. M1,
M3+ and M4 first run on D3 in the pilot.

Command: `python3 experiments/2026-10-28-d3-fixture/validate.py` (sandboxed, about 1 minute).
`--prediction-only` recomputes the prediction without Docker. Raw numbers are in
`results.json`.

## Results (run 2026-10-28)

| Check | Result |
|---|---|
| Egress from the sandbox | Blocked: TCP 1.1.1.1:443 and DNS for pypi.org both fail |
| Pass-through changes nothing (each call's result or error, and the final observation) | 0 mismatches in 50 paired runs |
| Contract is serially valid | 150 random workloads run serially: buggy 150/150 PASS, corrected 150/150 PASS |
| Author's witness: setup `create(s1)`, `restock(s1,1)`, `publish(s1)`; concurrent `purchase(s1,1)` ∥ `purchase(s1,1)` | Stock 1 → **−1** (`stock_non_negative` violated); hint followed 6/6 |
| Replay | **20/20**, one trace hash, identical to the witness |
| Same workload, exhaustive (buggy) | 192 schedules, exhausted; **120 violate**; first at schedule 6 |
| Same workload, 500 random schedules | 154 violate (30.8%) |
| Setup necessity: same two purchases after the first 0, 1 or 2 setup calls | 6/6, 6/6 and 6/6 schedules PASS (exhausted) |
| Corrected variant (`EVAL`), exhaustive | Witness 6/6 PASS; stock 3 with two `purchase(2)` 6/6 PASS; stock 2 with three `purchase(1)` 90/90 PASS |

## Prediction for M1, written before any method ran on D3

- M1 draws each workload as in `space.random_workload`: 0–6 setup calls, 2–4 concurrent calls,
  each operation uniform, each argument uniform.
- Exact probability that a workload can reach the failure: **8.6 × 10⁻⁶**. This uses an
  abstract serial model of the setup; calls inside the concurrent round that change the state are
  ignored. A Monte Carlo cross-check found 1 hit in 200,000 samples, consistent with that value.
- Times the witness's violating-schedule fraction (0.308), that gives **≈ 2.6 × 10⁻⁶ per
  execution**:
  - P(M1 finds it within 300 executions) ≈ 0.08%;
  - expected executions ≈ 380,000.
- **Expectation: M1 is censored in every pilot trial on D3.** If it is not, either the
  approximation is wrong (concurrent enabling calls) or something else is, and that gets
  investigated before any conclusion.
- **Consequence for the pilot:** on D3, beating M1 shows nothing. Any method that reaches the
  precondition beats it. The informative comparison on D3 is **M4 vs M3+**.
