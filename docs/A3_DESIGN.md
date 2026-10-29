# A3: interface obfuscation (design only)

Status: **design approved by the owner on 2026-10-28; not implemented and not run** (D-027).
Running it needs a separate approval, with a cost cap.

## Question

A2 removed the source and Muse still named D3's bug class in 5 of 5 trials, from the interface
alone: `purchase`, `stock`, `restock`, `InsufficientStock` (`experiments/2026-10-28-a2-no-source/RESULTS.md`).
A3 asks how much of Muse's workload selection comes from **descriptive names** rather than from
structure: the catalog's shape, the value domains, the contract's clause kinds, and the store
commands each operation issues.

## Conditions

| ID | Muse sees | Purpose |
|---|---|---|
| M4 | original names, source | Reference (already run in the pilot) |
| A2 | original names, no source | Reference (already run) |
| A3 | renamed names, renamed source | How much do names help when code is available? |
| A3-ns | renamed names, no source | Structure only: the floor for an informed planner |

Targets: D2 and D3, 5 seeds each, as exploratory as A2. Not D1: its operation names are the
public gRPC API (`oteldemo.CartService/AddItem`). Renaming them would mean changing the service
or its proto, and the bug is public anyway (`EVALUATION_PLAN.md` §5).

## The renaming

One bijection `R` per target, **computed by code from the target spec**, with no human choice.
It is order-preserving: within each class, names are numbered in the sorted order of the
originals, so anything that enumerates names in sorted order behaves identically.

| Class | Example (D3) | Renamed to | Where it is applied |
|---|---|---|---|
| Operation names | `purchase`, `restock` | `op1` … `opN` | catalog, observation, contract clauses, status semantics, source, feedback |
| Argument names | `sku`, `qty` | `a1` … `aM` | catalog, contract clauses, source, feedback |
| String domain values | `s1`, `s2` | `v1` … | catalog domains, source literals, feedback |
| Error names | `InsufficientStock`, `Unavailable` | `e1` … `eK` | status semantics, source, feedback outcomes |
| Store key prefixes | `"stock:"`, `"status:"` | `"k1:"` … | source string literals (declared per target in the spec) |
| Other source identifiers | `current`, `remaining` | `n1` … (by first occurrence) | source only |

**Not renamed:**
- **Numbers.** Quantities stay as they are: their arithmetic (two purchases that together exceed
  the stock) is part of the behavior under test.
- **Store commands** (`GET`, `DECRBY`, `EVAL`). They are the protocol every method observes, and
  the hint vocabulary.
- **Language keywords and builtins**, and the store client's method names (`r.get`, `r.decrby`).
  They map one-to-one onto store commands.
- **The contract's clause kinds** (`non_negative`, `counter_conserved`). They are the correctness
  requirement itself.
- **The target-independent scaffold**, including `HYPOTHESIS_KINDS`. It is already identical
  across targets and tested to be (`tests/test_contamination.py`).

**The contract's prose statement** cannot be renamed mechanically without leaving hints ("stock"
in prose). A3 replaces it with a sentence generated from the clauses by a fixed template per
kind, for example `non_negative`: "every value returned by op7(a1) is at least 0". No
human-written text reaches the model.

**The source** is renamed token by token after the existing normalization (comments and bare
strings already removed), so the view stays a consistent program. Only the model's view is
renamed. The service that runs is the original.

## Correctness requirements stay identical

- Muse's plan, written in renamed names, is translated back with `R⁻¹` by code **before**
  validation. A name outside `R`'s range is invalid, exactly like a misspelled operation today.
- Executions, the oracle, replay and verification therefore see only original names. The
  verdict semantics, budgets and per-experiment cap are unchanged.
- Feedback is built from the original results and then renamed with `R`. Its fields stay
  the same.
- The A3 validity checker asserts that every executed workload is in the original space and
  that every verdict comes from the unchanged oracle.

## No method gets privileged information

- **M1, M3+ and M3+arg never use names semantically.** They enumerate the catalog and react to
  store commands and state digests. Because `R` is order-preserving, they behave identically on
  the renamed and the original spec.
  - This is checked, not assumed: run each baseline once on both specs and compare every event,
    as the D1 gate's regression check does. A difference blocks A3.
  - The baselines then need no new trials. Their pilot results stand for both conditions.
- **`R` is public and mechanical,** and is not shown to the model. The system message and schema
  skeleton stay target-independent.
- **An A3 audit** extends the A2 identifier attribution:
  - no identifier from `R`'s domain (three characters or more) may appear anywhere in the
    request;
  - every remaining identifier must be explained by the scaffold, the renamed catalog or
    contract, the schema, store commands, or language and library names.
- **A noninterference test** consistently changes the original names throughout the spec and the
  source (for example `purchase` → `buy`, `stock` → `level`). The A3 request must stay
  byte-identical, which shows that names cannot reach the model.

## What A3 still leaves visible (stated in advance)

- **Structure in the source.** The command pattern (`GET`, compare, `DECRBY`) still shows a
  check-then-act shape. That is intended: A3 separates names from structure.
- **The author's prior** in `HYPOTHESIS_KINDS`, as for every condition.
- **Numeric domains.** For example, a stock that is restocked and then purchased.

## Predictions (to pre-register before any run)

- **A3 vs M4.** The round-1 rate of experiments that can violate by design falls. E₁ rises but
  stays below M3+'s on D3.
- **A3-ns.** E₁ is close to A2's or worse.
- **Controls.** No false positives in any condition, since the oracle is unchanged.

## Cost and work

- **Cost.** About A2's per trial: A2 cost $0.27 for 10 trials. A cap of **$1.50** for 2
  conditions × 2 targets × 5 seeds.
- **Work.** Renamer, translation back, A3 audit, noninterference and baseline-invariance tests:
  about half a day.
- **Not started.** It needs the owner's approval to implement and run.
