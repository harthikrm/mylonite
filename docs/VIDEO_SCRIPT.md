# Demo video script (draft, 3:00)

**Status: draft for the owner. Not recorded.** `[TODO]` marks what only the owner can fill in.
Every number is tied to a results file under "Sources".
- **Length:** the narration is about 405 words as spoken (numbers read out in full). That is
  2:48 at 145 words a minute, and 2:54 at 140.
- **Pace:** the time windows below assume 145 words a minute, and narration starts over the
  title card. If a take runs past 3:00, cut the A2 sentence at 1:28; the card shows it.
- **Fact-check:** an independent fact-check (an AI agent, not a person) found 24 problems in
  the first draft, 4 of them errors. All are corrected here.

**What the rules ask of the video** (`HACKATHON_COMPLIANCE.md` §4–§5, team-reported):
- three minutes;
- Muse's role unmistakable, and shown working, in the first 30 seconds;
- what we built named on screen, apart from what we used;
- a demo that holds up: replayable from recorded responses, with no live dependency on the
  model giving the same answer;
- said plainly: Mylonite is a defensive tool, and we did not test third-party live systems.

**Everything shown costs $0.** The demo replays the pilot's recorded Muse responses, and the
results come from committed files. No Muse call is made.

---

## Script

### 0:00–0:15 · The problem

**On screen:**
- Title card, 2 s: **Mylonite** · *Change the order. Reveal the fault.*
- Then `fixtures/dev/d2_counter/service.py`, lines 14–19: the `award` handler. Highlight
  line 16 (`r.get`) and line 18 (`r.set`).

> Mylonite uses Meta's Muse Spark to find concurrency bugs in services that share state in Redis
> or Valkey. This handler reads a balance, adds points, writes it back. Run two at once, and one
> award vanishes.

**Caption:** "Development fixture, written by us. The same bug class is in the OpenTelemetry
Demo's cart (issue #3824), still open when last checked on Nov 1."

### 0:15–0:35 · What Muse does

**On screen:** Muse's recorded answer from the pilot, its first experiment (command 3 under
"Recording"). Highlight `concurrent`, the four `schedule_hint` lines (GET, GET, SET, SET) and
`expected_effect`.

> Muse reads the source and proposes experiments as strict-schema JSON: which requests to race,
> after what setup, and in what order their store commands run. Here it bets both reads come
> before both writes. Muse never runs code, and never decides what counts as a bug.

**Captions:**
- from 0:15: "Recorded Muse response, from the Oct 28 pilot (no live call) · `muse-spark-1.3` ·
  Standard mode · `reasoning_effort` medium · the only model Mylonite calls";
- at about 0:28: "This experiment found the bug on execution 1 (next)."

### 0:35–1:06 · It runs

**On screen:**
1. The terminal, running the replay (command 2). Ten lines appear, each `verified e1=1`.
2. The first trial's witness (command 4). Highlight, in order:
   - `after: {'m1': 2, ...}` beside `"allowed_deltas": [3]`;
   - `trace hash matches: 20`;
   - `"mode": "exhaustive"` and `"PASS": 6`.

> This is our pilot, replayed from Muse's recorded answers, so it is free and repeatable. A
> delay-only proxy decides when each store command reaches Valkey. On the first execution, awards
> of 1 and 2 points leave a balance of 2, not 3. Plain code, not the model, flags the violation.
> Mylonite then replays the schedule 20 times with an identical trace, and runs all six orders on
> the fixed version: all pass.

**Captions:**
- while the replay runs: "Replay of the Oct 28 pilot: recorded Muse responses, $0 spent now.
  The model time and dollars printed are the original calls'."
- over the witness: "An easy fixture: random search finds this bug too, in a median of 5
  executions (0.06 s). The held-out bugs come next."

### 1:06–1:28 · How we tested it

**On screen:**
- `python3 freeze/manifest.py check` (command 5): "matches freeze v1.2 … 125 files checked".
  Caption: "v1.0 frozen Nov 1, 5 hours late; v1.2 adds a retry fix, made before the restart.
  Commit times are self-asserted."
- Then a timeline card: **freeze** → **2 new services, timestamped** → **public beacon picks
  the bugs** → **sealed** → **runs** → **reveal**.
- Then a list: **4 non-AI baselines:** stress, random search, systematic search, and an
  argument-aware systematic search · **20 trials each**.

> Then we tried to prove ourselves wrong. We froze the prompt, budgets and analysis rules. Then a
> public randomness beacon picked one bug to inject into each of two new services, and the bugs
> stayed sealed until the results were committed. Muse faced four non-AI baselines, 20 trials
> each.

### 1:28–2:09 · The result

**On screen:**
- The analysis output (command 6): 13 lines. Highlight, in order:
  - in line 1, `'control_trials': 200` and `'total': 0`;
  - `e1 better`;
  - then `seconds worse` and `dollars worse`.
- Then the results card:

  | | `alpha_m` | `beta_m` |
  |---|---|---|
  | Muse with the source: median executions to the bug | **1** | **1** |
  | Best non-AI method | 764 | 97 |
  | Muse without the source | 401 (not significant) | 137 |
  | Muse: median seconds per find | 41.8 | 59.9 |
  | Systematic search: median seconds | 5.8–6.5 | 1.0 |
  | Muse would be faster only if one execution took more than | 0.055 s | 0.62 s |

  Footer: "One execution measured ≈ 0.009 s. Without the source, Muse was not significantly
  better on `alpha_m` (it found the bug in 13 of 20 trials, against 17), and worse on `beta_m`.
  200 control trials: 0 false alarms."

> The result is mixed. Muse needed a median of one execution to find each bug. The best
> conventional method needed 764 and 97. But an execution takes about 9 milliseconds, while
> Muse's median find took 42 to 60 seconds. The systematic search took 1 to 6.5 seconds, so it
> was faster and cheaper. Muse would win on time only above 55 milliseconds per execution on one
> bug, and 620 on the other. Without the source, Muse was not significantly better. 200 control
> trials gave zero false alarms.

### 2:09–2:33 · What it means, and the limits

**On screen:** a card with the limits:
- one developer; 2 held-out bugs, both lost updates;
- no decoy edits: each bug was the only non-atomic counter update in its file, which favors
  Muse;
- Muse repeats nearly the same plan, so 20 trials measure reliability on one bug, not breadth;
- the method freeze was 5 hours late;
- one restart after a harness defect, under a pre-registered rule. It is post-observation,
  and it supplies 60 `beta_m` trials and all 200 controls;
- slow or remote targets not tested.

> Our hypothesis: Muse spots the one non-atomic counter update in each service; the no-source
> result supports that. Muse repeats nearly the same plan every trial, so this shows reliability
> on two bugs, not breadth. It could pay off where executions are slow; we haven't tested that.
> The full limits are linked from the README.

### 2:33–2:47 · Built, and used

**On screen:** two columns.

| Built during the hackathon (from Oct 28) | Used, not built |
|---|---|
| Delay-only proxy and scheduler (RESP2, RESP3) | Muse Spark, through the Meta Model API |
| Contract oracle | Valkey 9.0.4 |
| Sandboxed executor | Docker; Python and .NET images |
| Muse planner client and contamination audit | `redis`, `grpcio`, `typing-extensions` |
| 4 non-AI baselines and the no-source ablation | OpenTelemetry Demo (not vendored) |
| Pre-registered analysis; freeze manifests; recorded-model replay | drand, FreeTSA, OpenTimestamps |
| Held-out tooling: mutation, runner, ground truth | Claude Code, the AI assistant that wrote most of the code |
| 2 development fixtures; 2 held-out base services | |

> Everything on the left, we built during the hackathon. On the right is what we used: Muse Spark
> through the Meta Model API, Valkey, Docker and open-source libraries.

### 2:47–3:00 · Close

**On screen:**
- `github.com/harthikrm/mylonite` · Apache-2.0
- Team MetaMorphic: `[TODO: names]`
- Small print:
  - "Most of the code and documents were written by an AI coding assistant (Claude Code),
    under the developer's direction, including the held-out services. Muse is the only model
    Mylonite calls."
  - "A defensive tool, tested on our own code and on open-source code (the OpenTelemetry Demo),
    in local sandboxes. Never run against live third-party systems."

> Mylonite is a defensive tool, run only in local sandboxes. Change the order, reveal the fault.
> The code, trial data and analysis are on GitHub.

---

## Recording

**Set up before recording** (not on camera):
- **Rehearse in one clone, record in another.** Each clone allows one take of the replay. The
  replay refuses to run on a modified tree, and it leaves its own results folder behind. The
  rehearsal also pulls the Valkey image, which would otherwise slow the first take on camera.
  - Use two folder names, for example `mylonite-rehearse` and `mylonite-rec` (command 1 takes
    the name).
  - Run one replay at a time. Every replay uses the same sandbox name, and starting one removes
    the other's Valkey.
  - Before a retake, re-clone. Or reset the clone: preview with
    `git clean -nd experiments/2026-10-29-pilot/results/`, then run
    `git clean -fd experiments/2026-10-29-pilot/results/` (it removes only untracked folders
    there) and `git checkout -- experiments/heldout-v1-analysis/inputs.json`.
  - If the replay prints "refusing a non-smoke run on a dirty tree: commit first", reset or
    re-clone. Don't commit anything from the recording clone.
- **No key in the recording shell.** Run `unset MODEL_API_KEY` first. A fresh clone has no
  `.env`, but with a key exported, dropping `--replay-model` from command 2 would make 10 live
  Muse calls.
- **First time on a machine:** Docker Desktop must be running. The build pulls the Python base
  image, and the first replay silently pulls Valkey (about 64 MB). Rehearsing does both.
- **A terminal at least 120 columns wide.** The first line of command 6 is 223 characters,
  and it holds two highlighted values. Plan those highlights around the wrap.
- **Order matters.** Run the replay (command 2) before the analysis (command 6). The analysis
  rewrites `inputs.json`, and the replay then refuses. The freeze check (command 5) passes in
  any order.
- **Use Python 3.14.** The pilot was recorded on 3.14.5, and the replay was checked only on
  3.14.5. It refuses any request that differs from the recording, and the source view is built
  with Python's `ast` module, so another version may make it refuse.
- A plain prompt and a large font. In zsh, `PROMPT='$ '` hides the path.
- Don't show:
  - `.env`, or any command that reads it;
  - the sealed held-out folder (`heldout-sealed-v1`), or the held-out base and mutant source:
    publishing them is still the owner's decision;
  - the git-ignored `runs/` folder.

**1. Clone and build** (off camera):

```bash
git clone https://github.com/harthikrm/mylonite.git mylonite-rec && cd mylonite-rec
```

```bash
docker build -t mylonite-exec:dev -f docker/executor.Dockerfile docker
```

**2. The replay** (on camera, 0:35). Muse's 10 pilot trials, answered from the recorded
responses. `sed` keeps the 10 trial lines and drops the 62-line summary that follows them.
- Checked on 2026-11-03 in fresh clones at `e3e5c80`, and on 2026-11-04 from a fresh clone of
  the public repository at `31a0bb5`: 3.4–4 s, 10 of 10 `verified e1=1`. These checks are not
  recorded in the repository; the committed record is the 30-trial replay in
  `experiments/2026-11-03-pilot-replay/`.
- The results match the original pilot on status, E₁, executions, witness and counters.
  Tokens and model dollars are copied from the recording, so they match by construction. This
  checks the harness, not Muse: no new answer is sampled.
- `method_s` is the recorded model latency plus this run's execution time, so it differs from
  the original by a few milliseconds.

```bash
python3 experiments/2026-10-29-pilot/run_pilot.py --methods M4 --replay-model experiments/2026-10-29-pilot/results/20261028-165020/model_calls.jsonl | sed -n 1,10p
```

**3. Muse's recorded answer** (0:15). Its first experiment, unchanged, one key per line:

```bash
python3 -c "import json; r=json.loads(open('experiments/2026-10-29-pilot/results/20261028-165020/model_calls.jsonl').readline()); e=json.loads(r['response']['choices'][0]['message']['content'])['experiments'][0]; print(r['model'], r['trial'], 'round', r['round']); [print(k+':', json.dumps(e[k])) for k in ('setup', 'concurrent', 'expected_effect')]; print('schedule_hint:'); [print('  ', json.dumps(s)) for s in e['schedule_hint']]"
```

**4. The witness from the replay just run** (0:50). The first line prints the file it read. It
must be the new folder, not `20261028-165020`: if the replay did not run, this falls back to
the original pilot's first trial, which is a random-search trial.

```bash
python3 -c "import json,glob; p=sorted(glob.glob('experiments/2026-10-29-pilot/results/2026*/trials.json'))[-1]; t=json.load(open(p))[0]; w=t['witness']; v=t['verification']; print(p); print(t['target'], t['method'], 'seed', t['seed'], t['status'], 'e1 =', t['e1_executions']); print('schedule:', w['decisions']); print('before:', w['pre'], 'after:', w['post']); print('violation:', json.dumps(w['violations'])); print('replays:', v['replays'], 'violations:', v['replay_violations'], 'trace hash matches:', v['replay_hash_matches']); print('fixed version:', json.dumps(v['corrected']))"
```

**5. The freeze check** (1:06):

```bash
python3 freeze/manifest.py check
```

**6. The held-out verdicts** (1:28). About 3.5 s, from the committed trial files. It prints a
false-positive summary line, then M4's 12 confirmatory verdicts:

```bash
python3 experiments/heldout-v1-analysis/analyze_heldout.py | sed -n 1,13p
```

**Captions and cards:** keep each card on screen for at least 4 seconds.

## Sources

| Claim | Source |
|---|---|
| The `award` handler and its fix | `fixtures/dev/d2_counter/service.py`, `service_fixed.py` |
| Muse's experiment, the witness, 20/20 replays, 6/6 corrected schedules | `experiments/2026-10-29-pilot/results/20261028-165020/` (`model_calls.jsonl`, `trials.json`, trial `d2-loyalty-points/M4/1`) |
| Random search on D2: median 5 executions, 0.06 s | same `trials.json` (M1, seeds 1–5) |
| The replay is identical at the current code | `experiments/2026-11-03-pilot-replay/` (all 30 trials, at `cc37224`); the M4-only checks above (at `e3e5c80` and `31a0bb5`; not recorded in the repository) |
| Model and settings | `src/mylonite/planner.py`; `docs/FREEZE.md` |
| Freeze, its lateness, v1.2, beacon, sealing, restart | `docs/FREEZE.md`; `docs/AMENDMENTS.md` AM-002; `docs/DECISIONS.md` D-041 to D-045 |
| Medians (1, 764, 97, 401, 137), seconds (41.8, 59.9, 5.8–6.5, 1.0), break-even (0.055 s, 0.62 s), ≈ 0.009 s, 0 false alarms in 200 | `experiments/heldout-v1-analysis/RESULTS.md`, `report_primary.json` |
| Verdicts (E₁ better; seconds and dollars worse; A2 no better) | same |
| Same plan each trial; no decoys; only non-atomic counter update | `experiments/heldout-v1-analysis/RESULTS.md`; `docs/SUBMISSION.md`, "What we learned" and "Limitations" |
| Built and used; AI assistance | `docs/SUBMISSION.md`, "What we built", "Built with" and "Limitations" |
| OpenTelemetry #3824, open on Nov 1 | `experiments/2026-11-01-d1-recheck/RESULTS.md` |

## Open for the owner

- Team names, and the track. "One developer", on the limits card, must match the team list.
- The video format and upload site are not known yet (`OPEN_QUESTIONS.md` Q-H3).
- A live Muse call on camera would show latency honestly, but it spends API credits, and the
  answer can differ from the recording. Not planned without approval.
