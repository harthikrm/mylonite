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
- **Manifest.** `freeze/v1.1/MANIFEST.json`, SHA-256
  `771075b905e9bb398b4de8daef18d3696e50ecc50d89891e0a5d18e74be3ef18`, for commit `d9361b4`
  (154 files; 123 tests pass, 2 skipped). It is not anchored externally.
- **Disclosure about this log.** Adding AM-001 replaced the placeholder line "None yet." rather
  than appending below it. That is the only non-append change to this file. From v1.1 on,
  `freeze/manifest.py check` enforces appends against the v1.1 text.

### AM-002: model-response errors reach the retry rule (class B, freeze v1.2)

- **When.** 2026-11-02, ET. During C5: after run 1 stopped (D-043) and its results were
  committed and then examined to find the cause. So held-out outcomes have been observed.
- **Approval.** The owner, 2026-11-02: "Yes, fix and restart". This answered "Apply the fix and
  restart C5?", which named AM-002, freeze v1.2 and a restart with `--approved-cap 30`.
- **The defect.**
  - `planner.call_muse` turned only `URLError`, `TimeoutError` and JSON errors into a
    retryable `ModelAPIError`.
  - Python's `urllib` wraps an `OSError` as `URLError` only while it sends the request. A
    connection reset or close while waiting for the response, or while reading it, arrives
    bare: `ConnectionResetError`, `RemoteDisconnected` or `IncompleteRead`.
  - So the frozen rule, up to 3 attempts on transport errors (`run_pilot.LiveModel`, and the
    held-out config's notes), never applied to these errors. The trial ended in error, and the
    failed attempt was not logged.
  - **The same escape, found by the review:**
    - a body that is not UTF-8 (`UnicodeDecodeError`);
    - a body that is JSON but not an object (`AttributeError`).

    The frozen code already treats an undecodable body (`JSONDecodeError`) as a transport
    error.
- **Evidence.**
  - C5 run 1 (`f82681e`) has 3 records ending in `ConnectionResetError: [Errno 54]`. Each one
    had a model request in flight: time the logged calls and executions do not account for,
    and no `failed_attempt` entry anywhere in the run (D-043).
  - `tests/test_transport.py`: a local server fails the request at each phase, over a real
    socket on 127.0.0.1.
    - Against the old `call_muse`: 8 errors. The reset before the response raises the run's
      exact `ConnectionResetError: [Errno 54]`.
    - With the fix: all 6 tests pass, and 30 repeated runs all passed.
- **What changed.**
  - `src/mylonite/planner.py`, `call_muse`:
    - `OSError`, `http.client.HTTPException` and `UnicodeDecodeError` are retryable transport
      errors. `URLError` and `TimeoutError`, which are subclasses of `OSError`, already were;
    - a JSON body that is not an object is one too;
    - an HTTP error whose body cannot be read keeps its status.
    - `ValueError` is deliberately not caught. The one `putheader` raises for an invalid
      header value quotes the Authorization header, so it would put the key into a trial's
      status.
  - `tests/test_transport.py`, new: 6 tests. They cover:
    - each failure phase, with its exception type;
    - a timeout while reading;
    - 429 still retried, and 400 still not;
    - a 503 with an unreadable body;
    - `LiveModel` retrying a reset after 5 s.
  - Nothing else. The prompt, the schema, the parameters and the retry rule itself are
    unchanged.
- **Review.** An independent reviewer reported no must-fix defect. It ran about 30 failure
  scenarios on 127.0.0.1, including TLS truncation and resets, chunked-body errors and malformed
  status lines.
  - With the fix, every scenario became a retryable `ModelAPIError` with no status. HTTP
    errors keep their status.
  - For connection refused, TLS handshake and certificate failures, timeouts, `JSONDecodeError`
    and 429/500/401, the messages are byte-identical to before.
  - The key appeared in no message.
  - Its should-fix items are done: the two escapes above, and the test gaps (exception types,
    the server's read loop, server-thread errors, more cases).
- **Validity assessment.**
  - **The changed lines run only when a call raises, or when the body is not a JSON object.**
    A successful call, and every error the old code already wrapped, behave as before.
  - **Pilot, D1 and the A2 ablation:** no recorded run has such an error, so none is affected.
  - **Pilot regression after the change:** 30/30 trials and all 6,766 events are identical,
    on the first version of the fix and on the final one
    (`runs/d1gate-regression-20261102-113604/`, `-114315/`). It replays recorded answers, so it does not
    exercise `call_muse` itself. It shows that nothing else changed.
  - **The prompt fingerprint is unchanged:** `3da3aa34…`. 129 tests pass, 2 skipped.
  - **C5 run 1, affected:**
    - `beta_m` M4 seed 8, attempt 1. The analysis uses Muse's first attempt, so this counts as
      an M4 failure that a retry might have avoided;
    - `beta_m` A2 seed 10, both attempts;
    - through the stop, every `not_run` trial: 60 on `beta_m`, and all 200 controls.

    No answer was received for the failed requests, so they cannot be replayed from the logs.
  - **C5 run 1, unaffected:** every other trial received every answer it requested, and so
    never ran the changed code.
  - **The crash rule is slightly coarser.** Every model transport failure is now named
    `ModelAPIError`, as HTTP errors already were. So two different model failures in a row,
    each after 3 attempts, now count as "the same exception type" and stop the run.
- **Remedy (class B, during C5).**
  - C5 restarts from scratch under v1.2, with the same sealed targets, seeds and config.
  - Run 1 stays primary for every trial it completed. The restart is reported beside it,
    labeled post-observation.
  - For trials run 1 did not complete, the restart is the only data, also labeled
    post-observation.
- **Disclosures** (none changes a method):
  - **`OSError` is broad.** A local failure, such as too many open files or
    `http.client.InvalidURL`, is also retried. It is still bounded at 3 attempts and 20 s of
    waits, and then the trial ends in error.
  - **Unbilled failures.** A request that fails after the API processed it may have been
    billed. No usage comes back, so the cap's tally does not count it. This was true before,
    for 5xx errors.
  - **Not changed, pre-existing:**
    - `load_api_key` does not strip the key. A key with a trailing newline would fail every
      call in `putheader`. Run 1's 143 successful calls show the current key has none.
    - An `HTTPError` is not closed explicitly.
- **New manifest.** `freeze/v1.2/MANIFEST.json`, committed next. Its SHA-256 is appended below.
