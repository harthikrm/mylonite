# Harness diagnostics before pre-registration (2026-10-29)

Development evidence for D-030, not experiment data. `stall.py`, one bring-up per file, real cart.

| File | Code | What it shows |
|---|---|---|
| `d1stall-before-*.json` | `20f1666`, clean `src/` (the gate's proxy) | Fixed build, 1,200 cycled schedules of the gate's 2-operation workloads: 17 inconclusive, all `unattributed WATCH` and a forced decision. Buggy: 195 violations, 0 inconclusive |
| `d1stall-lazy-*.json` | the D-030 attribution fix, with the other changes of this pre-registration, uncommitted | The same 1,200: 0 inconclusive, 0 unstable schedules. Buggy unchanged (195) |
| `d1stall-lazy2-*.json` | the same, with the random part added to `stall.py` | Random D1 workloads under random schedules: fixed 1 inconclusive in 4,000 (a cart pause over Δq, 2 forced decisions), buggy 0 in 4,000 |

The `before` file records `src_dirty: false`. The `lazy` files record `src_dirty: true`: they ran
the fix before it was committed. The fix is in the pre-registration commit.
