# Base safety check before C2 (pre-registered 2026-11-01, before the run)

Author-side. **Not one of the frozen C2 checks** (`docs/HELDOUT_PROTOCOL.md`), and it changes
none of them. It runs at the commit that adds this file, on freeze v1.1 (`d9361b4`, manifest
`94d56be`). This is a new experiment directory, which `freeze/manifest.py check` allows without
a new version.

**No model calls, no method trials, no mutant.** At this point no mutant exists, and the C4
round is not named. The check runs only on the two unmutated bases in the sealed root, which
stays outside the repository.

## 1. Why

The frozen C2 checks are serial: 150 random serial workloads, determinism, pass-through, the
audit, and serial equivalence of each site's mutant. None of them runs a base under
concurrency. In C5, a single VIOLATION on a base is a false positive: it stops the run and blocks
every claim (`docs/FREEZE.md` §6). This check looks for a concurrency violation of each base's
own contract **before** the bases are committed, while fixing one is still allowed.

Each base was argued correct against its contract when it was written. That argument is kept
with the sealed material (`<sealed root>/private/design.md`), and the review checks it. This
check is evidence for the argument, not proof.

## 2. What runs (`base_safety.py`)

For each base, in the sandbox, with the frozen executor and oracle, in this order:

1. **Pairs.** From the empty setup and every setup on the base's M3+ frontier
   (`heldout.frontier`, the rule C6 uses), every unordered pair of catalog calls that:
   - share a value of a key argument, meaning an argument whose domain is the observation's;
   - and are not the observation's read.

   Each pair is explored depth-first until exhausted, or for at most 2,000 schedules.
   - Calls on different key values touch disjoint keys, so they cannot interact.
   - A read changes nothing, so a pair containing one behaves like the other call alone.
2. **Groups.** 1,000 workloads of 3 or 4 such calls on one key value, after a setup drawn from
   the same list, each under 5 random schedules (seeded).
3. **Stress.** 1,000 workloads of M1's draw, each run once without the scheduler.

Limit: 60 minutes per base. Stages run in order until the limit; anything not reached is
reported as not reached.

## 3. Outputs

- `results/<UTC timestamp>.json`: counts only. Per base: executions, verdicts, soundness
  problems, harness errors, forced decisions, frontier size, coverage of each stage, and time.
- Any record that is not a clean PASS is written to `<sealed root>/private/base_safety/`, with
  its workload and decisions. That file stays sealed.

## 4. Decision rule, fixed before the run

- **Pass:** zero VIOLATION and zero soundness problems in everything that ran. Coverage is
  reported beside it, and is not a pass condition.
- **A VIOLATION or a soundness problem on a base:** the base has a defect, or the harness does.
  The base is fixed, or the cause is found, and the whole check is re-run. The failed run's
  results file is kept and reported.
- Harness errors and INCONCLUSIVE verdicts are counted and reported. They are not passes.

## 5. Before this commit (not data)

The script was run only in a scratch clone, on toy material that is not a base:
- A correct toy ledger: 11,214 executions, nothing flagged.
- **A positive control:** a toy withdrawal that checks the balance, then decrements it. This is a
  check-then-act race.
  - The check flagged 32 VIOLATIONs out of 548 executions, in pairs and groups, and exited 1.
  - Two earlier toy mutants were not flagged. Neither can violate `non_negative`: one changes an
    operation the contract does not observe, and one loses an update with a computed `SET`.
- Groups and stress were exercised on a copy with smaller counts.

The real bases had passed the frozen C2 checks (`heldout.py check-bases`) before this commit.
That run is serial and is not this check.

## 6. Limits

- Pairs from the frontier cover setups that M3+'s rule reaches, not every reachable state.
- Groups and stress are samples.
- Passing does not prove a base correct. The correctness argument does that, and the review
  checks it.
