# Roadmap: Oct 27 – Nov 4, 2026

Status: **Proposed.** Phase 1 starts only after the team approves the architecture
(`ARCHITECTURE.md`) and the evaluation design (`EVALUATION_PLAN.md`).

Hard deadline: **Nov 4, 9:00 PM ET** (= Nov 5 02:00 UTC; DST ends Nov 1).
Internal submission target: **Nov 4, 6:00 PM ET.**

## 1. Priorities

**P0: must work.** Nothing in P1 or P2 starts until every P0 item has passed its gate.
1. One real concurrency failure, reproduced on demand: OTel #3824 scenario A on the unmodified
   cart image.
2. Controlled experiment execution: proxy, scheduler, executor, replay files.
3. Muse-guided test selection: planner, validator, feedback loop.
4. Independent correctness verification: serial-equivalence oracle plus replay verification.
5. Evidence-backed result: a results file per run; every README claim links to one.
6. Basic comparison with deterministic testing: M0–M3 against M4 on the dev set and the held-out
   set.

**P1: strong enhancements**, in this order:
1. Counterexample minimization.
2. Visual execution timeline (static HTML).
3. Muse explanation with reference checking.
4. A second real-world defect (R1: #3824 scenario B, or R2).
5. Automated evaluation report (charts from results files).
6. Ablations A1–A4 beyond the minimum.

**P2: future work, not started in this hackathon.** Postgres wire protocol; broad protocol
support; CI integration; distributed fault injection; Porcupine/Elle oracles for long histories;
multi-tenant hosted service.

## 2. Workstreams

The team size is not yet confirmed (the Indie track allows ≤ 4). The plan is written as four
workstreams; one person can own several, but **W3's held-out authoring must not be done by
whoever writes prompts** (`EVALUATION_PLAN.md` §4.2).

- **W1 Execution core:** proxy, scheduler, executor, oracle, replay.
- **W2 Model:** Meta API client, schemas, planner, validator, context builder, explainer.
- **W3 Targets and benchmark:** OTel target spec and Compose; dev fixtures; sealed held-out set.
- **W4 Evaluation and story:** strategies' budget accounting, results format, analysis script,
  report, demo, video, submission.

## 3. Day-by-day plan

Each day ends with a 15-minute check: gate status, decisions recorded in `DECISIONS.md`,
observations in `RESEARCH_LOG.md`.

### Day 0: Tue Oct 27 (done)
Phase 0: research, architecture, threat model, evaluation plan, repository. **Team approval
needed before Day 1 work.**

### Day 1: Wed Oct 28: spikes
| WS | Task | Done when |
|---|---|---|
| W2 | Create Model API team key; load $150 credits; confirm payment-method requirement; record terms. Smoke test: `muse-spark-1.3` with a strict `json_schema` planner schema on a fixture prompt, 10 calls; record validity, latency, tokens, and whether nullable types, `$ref`, `minItems`, and `store: false` are accepted. | Smoke-test numbers recorded. |
| W1 | Experiment `experiments/2026-10-28-resp-proxy/`: asyncio RESP2 proxy in pass-through mode in front of Valkey in Docker; framing for all reply types; pub/sub pass-through. | D2 serial runs identical with and without proxy over 50 runs. |
| W3 | Write D2 (Python, lost update). Pull pinned OTel `3.1.0` cart and Valkey images (pin digests). Try starting cart without flagd and the collector; if it fails, add them. **Run inside the sandbox network only.** | Cart answers `GetCart` through a published localhost port. |
| W4 | Results-file schema; Jepsen-style history format; skeleton of the analysis script (Wilson, bootstrap, Mann–Whitney, Â₁₂). | Script runs on synthetic data. |
**Gate G0** (`EVALUATION_PLAN.md` §10).

### Day 2: Thu Oct 29: control and the real bug
| WS | Task | Done when |
|---|---|---|
| W1 | Scheduler with decision points, quiescence, `fifo/random/pct/exhaustive/replay`; replay files; serial-reference engine; oracle with volatile masking and `ok/fail/info` handling. | D2 forced schedule 20/20, identical trace hashes; D5 correct variant 0 violations. |
| W1+W3 | **#3824 scenario A on the real cart through the proxy.** Multiplexed-connection handling (§5.4). | Verified violation, ≥ 19/20 replays. |
| W3 | D3 (check-then-act) and D4 (Node + ioredis, multiplexed). | Both run under the proxy. |
| W2 | Catalog → schema generator; plan validator with clamps; context builder with deny-list and secret scan (canary test). | Validator rejects a hand-written malicious plan set. |
**Gate G1.** **Cutoff:** if multiplexed control is not working by **Oct 29, 20:00 ET**, switch
D1 to barrier mode (hold reads of a key until N reads have arrived). If the proxy fails on D2
as well, switch to **Fallback A** and record the decision.

### Day 3: Fri Oct 30: strategies and the planner
| WS | Task | Done when |
|---|---|---|
| W1 | Strategies M0–M3, including M3's profiling and conflict enumeration; budget accounting (profiling and serial runs counted). | All four run on D1–D4 with results files. |
| W2 | Muse planner v1 with feedback loop and recorded I/O; M4 strategy. | M4 runs end-to-end on D2. |
| W3 | Held-out authoring starts **if** its author is not the prompt author; otherwise wait for the prompt freeze. Composition rules are fixed in `EVALUATION_PLAN.md` §4.2. | — |
| W4 | Security checklist items that gate third-party execution (`THREAT_MODEL.md` §8). | Checklist items ticked with commits. |

### Day 4: Sat Oct 31: dev-set runs and prompt freeze
| WS | Task | Done when |
|---|---|---|
| All | Full dev-set runs M0–M4; calibrate `B_exec`; fix harness bugs; iterate prompts **on dev targets only**. | Dev results file. |
| W2 | Prompt and schema freeze at **23:59 ET**; commit their SHA-256 values. | Hash in `DECISIONS.md`. |
| W3 | Seal the held-out archive; commit its SHA-256. | Hash committed. |
**Gate G2.**

### Day 5: Sun Nov 1: held-out evaluation
| WS | Task | Done when |
|---|---|---|
| W4 | Run M0–M4 on the held-out set with planned trials (Muse 10, others 20); then A1–A4 on a subset if budget allows. | Raw results complete. |
| W1 | Replay-verify every violation 20×; fixed-variant checks. | Verification table. |
| W2 | P1: explanation call + reference checker, on dev targets only. | — |
| W4 | Re-read hackathon rules (DST ends today). | Noted in `HACKATHON_COMPLIANCE.md`. |
**Kill check at 12:00 ET** (at least one verified violation end-to-end).

### Day 6: Mon Nov 2: analysis and P1
| WS | Task | Done when |
|---|---|---|
| W4 | Run the pre-registered analysis; write results honestly; decide the narrative (§9 of the evaluation plan). | `results/published/` committed. |
| W1 | P1: minimizer; static HTML timeline. | — |
| W3 | P1: R1 (#3824 scenario B) attempt, **time-boxed to 4 hours**. | Either verified or recorded as not done. |
| W4 | Open the submission form; list required fields. | Fields copied into the checklist. |
**Gate G3 at 12:00 ET.**

### Day 7: Tue Nov 3: demo and documentation
| WS | Task | Done when |
|---|---|---|
| W4 | Demo script (3:00), dry run on a clean checkout, record the video; README results section with links to results files. | Video draft. |
| All | Security checklist audit; secret scan of full history; license list. | Checklist complete. |
| All | **Code freeze 23:59 ET.** After this, only documentation and video changes. | — |

### Day 8: Wed Nov 4: submit
| Time (ET) | Task |
|---|---|
| Morning | Final video edit; re-read rules; final README. |
| 15:00 | With team approval: publish repository, after the final secret scan. |
| **18:00** | **Submit.** |
| 18:00–21:00 | Buffer only. No new work. |

## 4. Three-minute demo outline (target)

| Time | Beat |
|---|---|
| 0:00–0:20 | Problem: two "add to cart" requests on the real OpenTelemetry Demo; one item vanishes. Tests pass; TSan sees nothing. |
| 0:20–0:50 | Mylonite reads the C# cart; Muse proposes the hypothesis and the experiment. On screen: the plan JSON, validated. |
| 0:50–1:30 | Proxy timeline: `HGET A`, `HGET B`, `HSET A`, `HSET B`. Observed quantity 1 vs serial outcomes {2}. Replay 20/20. |
| 1:30–2:15 | Evidence chart: executions to first verified failure, M0–M4, on held-out bugs, with intervals. Including where Muse did not help. |
| 2:15–2:45 | Safety and soundness: delay-only proxy, model never runs code, verdicts from the oracle. |
| 2:45–3:00 | What's next. |

## 5. Risk register

| Risk | Likelihood | Impact | Mitigation / fallback | Cutoff |
|---|---|---|---|---|
| Multiplexed-client control on the C# cart fails | Medium | High | Barrier mode for D1; Fallback A for fixtures | Oct 29 20:00 ET |
| OTel cart image needs flagd/collector/other services to start | Medium | Medium | Add them (≈ 4 containers, ~655 MB limits per compose) | Oct 28 EOD |
| Meta API structured output rejects our schema features | Medium | Medium | Flatten; drop nullable unions; inline everything | Oct 28 EOD |
| Model output too slow or costly for 10 trials × 14 targets | Medium | Medium | Lower reasoning effort; fewer calls per trial; A4 mode | Oct 31 |
| Held-out set not ready by Nov 1 | Medium | High | Mutation script on dev-style correct services with sealed seed | Oct 31 EOD |
| Harness false positive found late | Low | Critical | Correct controls run in every batch; claims blocked until fixed | Any time |
| Credits exhausted | Low-Med | High | Usage tracked per call; budget plan in `EVALUATION_PLAN.md` §11 | Daily check |
| Rules change or hidden requirements (repo, video) | Low | Medium | Re-read Nov 1 and Nov 4; open the form Nov 2 | Nov 2 |
| Team member in a restricted territory for the API | Unknown | High | Confirm on Day 1 (Q-H5) | Oct 28 |

## 6. Dependencies

```
G0 (API smoke test, proxy pass-through)
  └─► G1 (scheduler + oracle + #3824 reproduced) ──► strategies M0–M3 ─┐
          └─► planner v1 (M4) ─────────────────────────────────────────┼─► dev runs ─► prompt freeze (G2)
held-out authoring (independent) ──► sealed hash ───────────────────────┘                   └─► held-out runs ─► analysis (G3) ─► demo ─► submit
```
