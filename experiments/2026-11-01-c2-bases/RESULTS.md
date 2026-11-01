# Base safety check before C2: results

Run 2026-11-01 at 19:02 UTC (14:02 ET), at `0e06212`, the pre-registration commit
(`PROTOCOL.md`), on freeze v1.1. Raw counts: `results/20261101-190214.json`. No model calls, no
mutant, no round named. The sealed root is outside the repository.

**Result: pass for both bases** (pre-registered rule: zero VIOLATION and zero soundness
problems). Coverage was complete: every stage ran in full, well inside the 60-minute limit.

| | α (seat reservations) | β (job leases) |
|---|---|---|
| Setups (the empty one plus the M3+ frontier) | 6 | 7 |
| Pairs explored depth-first | 1,992 of 1,992, all exhausted (none reached the 2,000-schedule cap) | 1,470 of 1,470, all exhausted |
| Groups of 3–4, each under 5 random schedules | 1,000 | 1,000 |
| Stress workloads | 1,000 | 1,000 |
| Executions | 20,384 | 20,994 |
| PASS | 20,384 | 20,994 |
| VIOLATION | 0 | 0 |
| INCONCLUSIVE | 0 | 0 |
| Soundness problems | 0 | 0 |
| Harness errors | 0 | 0 |
| Forced decisions | 0 | 0 |
| Time | 225 s | 237 s |

**What this does and does not show.**
- FACT: no violation of either contract, in any exhausted pair from these setups, in any sampled
  group or in any stress run.
- **Limit:** the frontier is small (5 and 6 setups that are not empty). So the exhaustive pairs
  cover few states, and deeper states are covered only by the samples. This is evidence for the
  correctness argument in the sealed design notes. It is not proof.
- The positive control before the run (`PROTOCOL.md` §5) shows that the check can flag a
  check-then-act race. It does not show that every kind of defect would be found.

## After the run: the review, and a docstring revision

**Review.** An independent reviewer read both bases and the design notes. It did not run them,
and it built no mutants.
- **No must-fix defect.** The reviewer reported high confidence that neither unmutated base can
  end a round with a negative counter. It tried:
  - every write to each counter;
  - every exception path;
  - WATCH and MULTI blocks under the proxy and in pass-through;
  - the interleavings listed in its report.
- `status_semantics` is truthful in every case it checked, and spec compliance holds:
  - op counts: α 8, β 8;
  - lifecycle and distractor ops are present;
  - precondition depth: α 2, β 1;
  - determinism, and gated commands only.
- **Should-fix, all done before C2:**
  1. **Docstring claims.** Two were false under concurrency:
     - α: "while it is on sale". A reservation that started before `close_sales` can still
       finish after it.
     - β: "a paused queue leases nothing". A lease that started before `pause` can still finish.
     - β also said "one batch per queue"; the code allows one per worker and queue.
     The docstrings now say what the code does. **Only docstrings changed.** The executable code
     is byte-identical: the model view has the same SHA-256 before and after, and the hashes are
     kept in the sealed notes. So this safety run applies to the revised bases unchanged.
  2. **Disclosures, now in the sealed design notes:**
     - those uncontracted interleavings;
     - each base sits at exactly 3 live sites in a stratum because of one style choice: β's
       pause check before `lease`'s WATCH, and α's existence checks inside the WATCH of
       `withdraw_seats` and `move_seats`;
     - the dead site.
  3. **Binding of the design notes.** The notes, including the author's expectation that each
     base's O3 site cannot violate its contract, are not covered by the C2 commitment, which
     hashes only `heldout/`. Their SHA-256 is recorded here instead, before C2:
     `private/design.md` = `6f591cfaee35e43fabefe27c2a8a0a445a21c2f916d7c71441a8b50a30f0aeee`.
- **A harness residual (hypothesis, low likelihood, every target).**
  - FACT: redis-py 8.1.0 in the executor image retries a command up to 10 times on a timeout,
    and `socket_timeout` is 5 s, as in D2 and D3. This was checked in the image with no network.
  - So a command the proxy held for more than 5 s could run twice.
  - FACT: 0 forced decisions in the 41,378 executions above, and rounds take milliseconds.
  - It is disclosed and not changed: a fix to frozen code would be class B. On a base it would
    stop C5 through the stop rule, so it would not be silent.

**The frozen C2 checks, re-run on the revised sources** (`heldout.py check-bases`): both pass.
- serial: 150/150 PASS;
- nondeterministic: 0; pass-through mismatches: 0; audit findings: 0;
- all 13 sites are serially equivalent;
- live sites: α 3 guarded and 3 unguarded, β 3 and 3, with kinds O1, O2 and O3;
- the one dead site is α `O1:reserve:83`, as in the first run, where it was line 82.

The first run's report is kept in the sealed private directory.
