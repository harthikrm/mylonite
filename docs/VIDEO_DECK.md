# Demo video deck and talk script

The 12 slides of the demo video: what each slide shows, and what to say over it. The narration
is the fact-checked narration in [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md), split by slide; the numbers
and their sources are there. About 2:50 at 145 words a minute. If a take runs past 3:00, drop
the slide 9 lines; the slide still shows them.

| # | Slide shows | Say |
|---|---|---|
| 1 | **Mylonite** · *Change the order. Reveal the fault.* · Team MetaMorphic | Mylonite uses Meta's Muse Spark to find concurrency bugs in services that share state in Redis or Valkey. |
| 2 | `award` handler, `fixtures/dev/d2_counter/service.py` lines 14–19; `r.get` (read) and `r.set` (write back) highlighted. Caption: development fixture, written by us; same bug class as OpenTelemetry Demo issue #3824 | This handler reads a balance, adds points, writes it back. Run two at once, and one award vanishes. |
| 3 | Muse's recorded first experiment (`concurrent`, `schedule_hint` GET GET SET SET, `expected_effect`). Reads the source · answers in strict-schema JSON · never runs code. Caption: recorded response, Oct 28 pilot, no live call, `muse-spark-1.3` | Muse reads the source and proposes experiments as strict-schema JSON: which requests to race, after what setup, and in what order their store commands run. Here it bets both reads come before both writes. Muse never runs code, and never decides what counts as a bug. |
| 4 | Muse's plan → service (Docker sandbox) → delay-only proxy → Valkey 9.0.4 → contract oracle (plain code) | This is our pilot, replayed from Muse's recorded answers, so it is free and repeatable. A delay-only proxy decides when each store command reaches Valkey. |
| 5 | Execution 1: expected 3, observed 2 · plain code flags it · 20 of 20 replays, identical trace hash · 6 of 6 orders pass on the fixed version. Caption: random search finds this easy fixture too (median 5 executions) | On the first execution, awards of 1 and 2 points leave a balance of 2, not 3. Plain code, not the model, flags the violation. Mylonite then replays the schedule 20 times with an identical trace, and runs all six orders on the fixed version: all pass. |
| 6 | Freeze → 2 new services, timestamped → public beacon picks the bugs → sealed → runs → reveal · 4 non-AI baselines, 20 trials each. Caption: freeze check passes (v1.2, 125 files); v1.0 frozen 5 hours late | Then we tried to prove ourselves wrong. We froze the prompt, budgets and analysis rules. Then a public randomness beacon picked one bug to inject into each of two new services, and the bugs stayed sealed until the results were committed. Muse faced four non-AI baselines, 20 trials each. |
| 7 | Median executions to the bug: Muse with the source 1 and 1; best non-AI method 764 and 97 | The result is mixed. Muse needed a median of one execution to find each bug. The best conventional method needed 764 and 97. |
| 8 | Muse 41.8 s and 59.9 s per find; systematic search 5.8–6.5 s and 1.0 s; Muse faster only above 0.055 s and 0.62 s per execution (measured ≈ 0.009 s) | But an execution takes about 9 milliseconds, while Muse's median find took 42 to 60 seconds. The systematic search took 1 to 6.5 seconds, so it was faster and cheaper. Muse would win on time only above 55 milliseconds per execution on one bug, and 620 on the other. |
| 9 | Without the source: not significantly better (401 vs 764; 137 vs 97, worse) · 200 control trials: 0 false alarms | Without the source, Muse was not significantly better. 200 control trials gave zero false alarms. |
| 10 | Hypothesis, and the limits: one developer; 2 held-out bugs; no decoys; same plan each trial; freeze 5 hours late; one post-observation restart; slow or remote targets not tested | Our hypothesis: Muse spots the one non-atomic counter update in each service; the no-source result supports that. Muse repeats nearly the same plan every trial, so this shows reliability on two bugs, not breadth. It could pay off where executions are slow; we haven't tested that. The full limits are linked from the README. |
| 11 | Built during the hackathon, and used, not built (as in VIDEO_SCRIPT.md) | Everything on the left, we built during the hackathon. On the right is what we used: Muse Spark through the Meta Model API, Valkey, Docker and open-source libraries. |
| 12 | `github.com/harthikrm/mylonite` · Apache-2.0 · Team MetaMorphic · AI-assistance and defensive-use small print | Mylonite is a defensive tool, run only in local sandboxes. Change the order, reveal the fault. The code, trial data and analysis are on GitHub. |

The slides themselves are kept outside the repository: only new Markdown files leave the method
freeze check (`freeze/manifest.py check`) passing.
