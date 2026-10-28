# D3: product inventory (development fixture, setup-dependent)

Written 2026-10-28, before any search method (M1, M3+, M4) ran on D3. The model never sees this
file: the planner reads only the files listed under `model_view` in `target.json`, and
`tests/test_contamination.py` checks that adding or changing anything else leaves the request
byte-for-byte unchanged.

## Service

Eight operations over two SKUs (`s1`, `s2`) and quantities `1, 2, 3`:
- Lifecycle: `create`, `restock`, `publish`, `unpublish`, `retire`.
- Sale: `purchase`.
- Reads: `stock`, `status`.

The product state machine is `draft → live → draft`, and `draft → retired`.

| Operation | Precondition (else it raises, with no effect) | Effect |
|---|---|---|
| `create(sku)` | product does not exist | `HSETNX product:{sku} status draft` |
| `restock(sku, qty)` | exists, not retired | `INCRBY stock:{sku} qty` |
| `publish(sku)` | status `draft`, stock > 0 | status `live` |
| `unpublish(sku)` | status `live` | status `draft` |
| `retire(sku)` | exists, not `live` | status `retired` |
| `purchase(sku, qty)` | status `live`, stock ≥ qty | `DECRBY stock qty`, `INCRBY sold qty` |

**Contract (owner statement):** a product's stock, as returned by `stock(sku)`, is never
negative. The clause is `stock_non_negative` (kind `non_negative`) over the observation
`stock(sku)` for each SKU.
- Every rejected call raises before writing, so all errors are declared `no_effect`.
- No serial execution can violate the contract: only `purchase` decrements, and it checks first.
  This is checked in `experiments/2026-10-28-d3-fixture/` on 150 random serial workloads per
  variant.

## Failure mechanism

`purchase` reads the stock (`GET`), compares it with `qty`, and only then decrements (`DECRBY`).
Two purchases of the same live product can both read the old stock before either decrements.
Both checks pass and both decrements apply: with stock 1, two `purchase(s1, 1)` leave stock −1.

**Necessary state:** the product must exist, have stock, and be `live`. That takes three
specific calls in order: `create(s)`, `restock(s, q)`, `publish(s)`. Then the round needs two
concurrent purchases of `s` with each `qty ≤ q` and the two summing to more than `q`.
- From any state missing one of these steps, every schedule of the same two purchases passes.
  The fixture validation checks this for 0, 1 and 2 of the 3 setup calls.
- The steps can also happen inside the concurrent round (for example `publish` concurrent with
  two purchases). That is still a state that has to be reached first.

**Corrected variant (`service_fixed.py`):** `purchase` is one server-side script (`EVAL`) that
checks and decrements atomically. Every other operation is imported unchanged from `service.py`.

## Why this is a different mechanism from D2

| | D2 (loyalty points) | D3 (inventory) |
|---|---|---|
| Pattern | Lost update: read-modify-write of one counter (`GET` → `SET` of a value computed from a stale read) | Check-then-act (atomicity violation): a guard evaluated on a state that is stale when the action runs (`GET` → compare → `DECRBY`) |
| Writes | One write is overwritten and lost | No write is lost; every `DECRBY` applies atomically |
| Would D2's fix help? | It is the fix: an atomic `INCRBY` | No. D3 already uses atomic `INCRBY`/`DECRBY`. The guard and the action must be atomic together (script or transaction) |
| Oracle | History-based: final = initial + Σ successful awards (`counter_conserved`) | State-based: stock ≥ 0 (`non_negative`); it holds whatever the history |
| Reachable from the empty store? | Yes: any two concurrent `award`s on one member | No: needs `create`, `restock`, `publish` first, then two purchases with the right quantities |
| Catalog | 2 operations, 6 calls | 8 operations, 24 calls, with distractors (`unpublish`, `retire`, reads) |
| Also present, but outside the contract | — | Lifecycle check-then-act races (for example `retire` ∥ `publish` can both succeed). They break no declared clause, so they must **not** be reported. This tests that the oracle respects the owner's contract (Risk C) |

## What D3 is for, and what it cannot show

- **For:** the pilot's first look at whether reaching a precondition favors a method that reads
  code (M4) over random (M1) and greybox (M3+) search. It also checks that the harness handles
  setup calls that raise, state-based clauses, and a script-based corrected variant.
- **Cannot show:** generalization. The author of D3 also wrote the planner prompt and knows the
  bug. D3 is a development target. Effectiveness claims come only from the held-out set
  (`docs/HELDOUT_PROTOCOL.md`).
- **Possible bias toward M4:** the identifiers (`purchase`, `stock`, `publish`) are descriptive,
  and the pattern is a textbook one. The held-out composition rules (neutral identifiers,
  mechanical injection) address this. D3 does not.
