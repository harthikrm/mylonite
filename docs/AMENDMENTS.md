# Amendments to the method freeze

Policy accepted with freeze v1.0 (D-038). This file is append-only: entries are never edited or
removed. A wrong entry is corrected by a later entry.

## Policy

**Versions.** The current version is `v1.0` (`docs/FREEZE.md`, `freeze/v1.0/MANIFEST.json`).
- An amendment of class A or B makes `v1.n+1`, with a new manifest.
- An amendment of class C makes `v2.0`, with a new freeze document, a new manifest and a new
  anchor.
- A held-out run starts only if `freeze/manifest.py check` passes against the latest manifest.
  So every change to a checked file needs a version, and every version needs an entry here.

Every result names the version it ran under.

**Held-out milestones** (`HELDOUT_PROTOCOL.md`):
- C1 is the freeze;
- C1b is tooling;
- C2 is the bases, committed and timestamped;
- C3 is the beacon;
- C4 is generation;
- C5 is evaluation;
- C6 is ground truth and reveal.

"Held-out outcomes have been observed" from the moment any of these happens:
- a held-out trial result, beyond progress counts, is seen by anyone;
- a generated mutant is opened;
- the C5 results commit exists.

**Classes.**

| Class | What | When it is allowed | What it requires |
|---|---|---|---|
| **A: implementation** | Tooling that carries out a frozen procedure and cannot change any method's choices or any analysis rule. Examples: the mutation script for the frozen operators; the held-out runner; manifest tooling; reporting. | Before C2 only. After C2, a change to such tooling is class B or C. | Tests. If `src/` changes, the pilot regression must be identical event for event. A note on which frozen text it implements. |
| **B: security or correctness fix** | A defect in the harness, sandbox, verification or accounting code that makes a result wrong or a run unsafe. Also analysis code that does not do what the frozen text (`FREEZE.md` §4) says. Changing that text is class C. | At any time. | A dated entry covering the defect, its evidence, the fix and its commit. A **validity assessment**: which recorded results the defect could have affected, and how (re-run the pilot regression and any recorded held-out trials from their logs where possible). **The remedy:** affected trials are re-run for **every** method, and both versions are reported. Before held-out outcomes are observed, the fixed version is primary. After they are observed, the original stays primary and the re-run is labeled post-observation, so the author never chooses between them after seeing results. **During C5, any fix stops C5, and C5 restarts from scratch** under the new version (the original C5 rule). Investigating why it stopped counts as observing outcomes. So **the aborted run stays primary** for every trial it completed, and the restart is reported beside it, labeled post-observation. |
| **C: methodological change** | Anything else: the prompt or schema, model parameters, method logic, budgets, verification thresholds, analysis rules, target-selection or construction rules. | **Before C2:** as a new freeze version, with the old version and its reason kept. **After C2, before any held-out outcome:** only with new bases. The author has seen the bases, so a change could be fitted to them. C2 and everything after it are redone after the new freeze, and the abandoned bases are reported. **After held-out outcomes have been observed:** never for that held-out set. A changed method needs a new held-out set built after the new freeze. Results under the old version are reported as they are. | A new freeze document, a new manifest and a new anchor. A statement of whether development results motivated the change. |

**Never allowed:**
- Changing a method, the prompt, a parameter, or an analysis rule after observing held-out
  outcomes in order to change any method's result.
- Re-running a trial except under the crash rule or a class B remedy.
- Dropping a target, trial or run from a report.
- Editing a recorded result.

**Not amendments, but recorded.** Each of these is logged in the results with its effect, and
none of them changes the frozen version:
- the API changing the model behind `muse-spark-1.3`, detected through the recorded model
  string;
- price changes;
- infrastructure failures that end trials under the crash rule.

**Entry format:**
- ID (`AM-001`, …);
- date and time (ET);
- class and new version;
- what changed (files, commits);
- why;
- which held-out milestone it came after;
- the validity assessment;
- evidence;
- the owner's approval, quoted;
- the new manifest's hash and anchor, if any.

## Log

### AM-001: C1b held-out tooling (class A, freeze v1.1)

- **When.** 2026-11-01, ET. After C1 (freeze v1.0, `da3ca57`) and before C2: no held-out base,
  mutant or contract exists.
- **Approval.** The owner, 2026-11-01: "Yes, build C1b". This answered "Go ahead with the
  minimum held-out evaluation under the $30 cap?". Model spend still needs `--approved-cap 30`
  at C5. Each external submission (anchor, C2 timestamp, beacon fetch) still needs its own
  approval.
- **What changed.**
  - `src/mylonite/sandbox.py`: an optional `target_root`, mounted read-only at `/app/heldout`.
    This is the configurable target root the protocol names. It is None by default.
  - `tests/test_sandbox.py`: one test.
  - New: `experiments/heldout-v1/heldout.py`, `run_heldout.py`, `c6_extended.py` and
    `tests/test_heldout.py`.
  - `docs/HELDOUT_PROTOCOL.md`: "C1b as built".
- **Why.** This implements C1b of the minimum scope (`FREEZE.md` §5, `HELDOUT_PROTOCOL.md`).
- **How the frozen text was implemented.** Each choice is disclosed in `HELDOUT_PROTOCOL.md`.
  None changes a method, the prompt, a budget, verification or an analysis rule.
  - **O4 and O6 are not implemented,** recorded before C2 as the protocol requires:
    - O4 would need a Lua-to-Python translation;
    - O6 is never serially equivalent.
  - **The O2 rewrite also removes the retry loop,** which could no longer retry.
  - **O3 excludes pipelines with an explicit `multi()`.** With one, redis-py would still send
    MULTI/EXEC.
  - **C2's minimums count live sites:** serially equivalent and changing the command stream.
  - **The C4 filter stays the frozen one** (serial equivalence). It is run at C2 for every site
    and bound by the C2 commitment, so C4 is deterministic.
  - **The beacon's randomness** must be SHA-256 of its signature. C6 compares the committed
    response with drand's public record.
- **Validity assessment.**
  - The sandbox change adds a mount only when `target_root` is set.
  - Pilot regression after the change: 30/30 trials and all 6,766 events identical
    (`runs/d1gate-regression-20261101-034950/`).
  - The prompt fingerprint is unchanged.
  - No held-out outcome exists, so none can be affected.
- **Evidence.**
  - 123 tests pass (2 skipped).
  - Toy smokes and two rehearsals in scratch clones, listed in `HELDOUT_PROTOCOL.md` (not data).
  - An independent review made two passes. It found 5 must-fix defects, the most serious being
    a forged C4 record that could choose the site. All are fixed and covered by tests.
- **New manifest.** `freeze/v1.1/MANIFEST.json`, committed next. Its SHA-256 is appended below.
