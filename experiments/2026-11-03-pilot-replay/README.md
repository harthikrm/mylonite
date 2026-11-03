# Pilot replay at the current code (2026-11-03)

**No model calls. $0 in API credits.** This checks that the published reproduction command works
at the current code, and records the outcome.

## What was run

- **Commit:** `cc37224`, the README rewrite, under freeze v1.2. It ran in a clean, temporary
  worktree; the manifest's `git_dirty` list is empty.
- **When:** 2026-11-03, 23:10:42–23:13:13 UTC, about 2.5 minutes. Docker was used, with the
  existing `mylonite-exec:dev` image.
- **The command:**

  ```bash
  python3 experiments/2026-10-29-pilot/run_pilot.py --replay-model experiments/2026-10-29-pilot/results/20261028-165020/model_calls.jsonl
  ```

  It runs all 30 pilot trials (D2 and D3; M1, M3+ and M4; seeds 1–5). Muse's 10 calls are
  answered from the pilot's recorded responses. The recorded-model class refuses any request
  that differs from the recorded one.
- **The output** was written in the worktree under `experiments/2026-10-29-pilot/results/`. It
  was copied here, to `results/20261103-171042/`, so that the pilot's own directory stays as
  frozen.

## Result

`compare.py` compares the replay with the original pilot (`20261028-165020`) trial by trial.
Output: `comparison.json`.

| Compared field | Trials that differ |
|---|---|
| status | 0 of 30 |
| E₁ | 0 |
| executions | 0 |
| witness: workload, schedule decisions and trace hash | 0 |
| counters | 0 |
| model calls, model dollars and tokens | 0 |
| unverified violations | 0 |

```bash
python3 experiments/2026-11-03-pilot-replay/compare.py experiments/2026-10-29-pilot/results/20261028-165020/trials.json experiments/2026-11-03-pilot-replay/results/20261103-171042/trials.json
```

**Not compared:** method, execution and overhead seconds. Real time is not seeded.

**Earlier replays:**
- the pilot's own, at `db1f84f` (`experiments/2026-10-29-pilot/RESULTS.md`);
- the event-level regressions after AM-002, in which 30/30 trials and 6,766 events were
  identical. Their raw logs are in the git-ignored `runs/`.

**A record lost first:** the same replay was run once before, at `f0bd6eb`, with the same
result. Its output was deleted along with its temporary worktree before it was recorded. This
re-run replaces it.
