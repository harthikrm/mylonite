# Roadmap: Oct 27 – Nov 4, 2026

Status: **Approved order (2026-10-28, `PHASE0_REVIEW.md` A4).** This follows the team handoff:
the tracer bullet comes first, the value question is answered early, and the real defect plus its
corrected version precede the kill gate.

Hard deadline: **Nov 4, 9:00 PM ET** (= Nov 5 02:00 UTC; DST ends Nov 1).
Internal submission target: **Nov 4, 6:00 PM ET.**
Fixed event: **Oct 28, 12–1 PM ET, "Agents 102: Best Practices for Verifiable Agents".**

## 1. Priorities

**P0: must work.**
1. A controlled, replayable concurrency failure checked by an independent contract oracle, first
   on a fixture (Oct 28), then on the real OTel cart built from source (#3824, Oct 30).
2. The corrected version passes under exhaustive exploration of the same workload (fixture's
   `INCR` variant; the #3825-patched cart).
3. Muse-guided experiment selection compared with random and conflict-directed systematic search
   under equal budgets.
4. Muse drafting of catalog and contract clauses, with human approval (RQ5).
5. Evidence: results files behind every claim; a pre-registered held-out evaluation.

**P1, in order:** counterexample minimization; static HTML timeline; Muse explanation with
reference checking; R1 (#3824 scenario B); evaluation report charts; optional methods (M2, A1,
A4).

**P2:** Postgres and other protocols, CI integration, distributed fault injection,
Porcupine/Elle oracles, a hosted service.

## 2. Workstreams

W1 execution core (proxy, scheduler, executor, oracle, replay); W2 model (client, schemas,
planner, drafting, validator, context builder); W3 targets and benchmark (fixtures, OTel build,
sealed held-out set); W4 evaluation and story (accounting, analysis, demo, submission).
**Team roster and owners: still needed (A10).** Whoever writes prompts must not author the
held-out set.

## 3. Day-by-day plan

| Day | Work | Gate |
|---|---|---|
| **Wed Oct 28** | **Tracer bullet on D2:** RESP proxy with corrected ordering rules, scheduler (admission + cross-connection choice), executor in the sandbox network, contract oracle, replay; exhaustive and random search; one Muse planner call (key from the owner's local `.env`); `INCR` corrected variant explored exhaustively; costs and timings recorded. Attend Agents 102. | T0 |
| **Thu Oct 29** | D3 precondition fixture; M3+ (profiling + greybox setup search); Muse feedback loop (M4) and A2; **pilot value checkpoint** (§9 of the evaluation plan). Start the OTel cart build from source at `dedc0178` in a builder container. Search for real Redis race fixes for the held-out set (Q-E3). | P1: owner decision on scope and claim |
| **Fri Oct 30** | **External defect:** #3824 scenario A on the real cart through the proxy (multiplexed client); build the #3825-patched cart and explore the same workload exhaustively; Muse `draft_spec` for the cart (RQ5); memorization probe. D4 (Node, multiplexed). | **K (kill gate)** |
| **Sat Oct 31** | Calibrate budgets from the pilot; freeze the prompt and schemas (hash); seal the held-out set (hash); freeze the pre-registration; run controls, including the weak-contract control. | F |
| **Sun Nov 1** | Held-out evaluation: M0, M1, M3+, M4, A2 × 20 trials; verification of every violation. Re-read the rules (DST ends). | — |
| **Mon Nov 2** | Pre-registered analysis; results written honestly; P1 items if time allows (minimizer, timeline, explanation). Open the submission form and copy its required fields. | G3 (12:00 ET) |
| **Tue Nov 3** | README results and a "Built during the hackathon" section; security checklist audit; record the 3-minute video. **Code freeze 23:59 ET.** | — |
| **Wed Nov 4** | Final video; full-history secret scan; publish the repository **with owner approval**; **submit by 18:00 ET**; buffer to 21:00. | — |

## 4. Three-minute demo outline (target)

| Time | Beat |
|---|---|
| 0:00–0:25 | What Muse does in Mylonite, said plainly: drafts the contract, chooses experiments, explains verified traces. Then the problem: two "add to cart" requests on the real OTel Demo, and an item vanishes. |
| 0:25–1:05 | Muse-drafted contract clause (human-approved) → experiment → proxy timeline `HGET A, HGET B, HSET A, HSET B` → contract violation → replay 20/20. |
| 1:05–1:30 | The #3825-patched cart passes exhaustive exploration of the same workload: the unmerged fix, checked. |
| 1:30–2:20 | Evidence chart on held-out bugs: executions and cost to the first verified failure, for each method, including where Muse did not help. |
| 2:20–2:45 | Soundness and safety: per-connection order kept, the model never runs code, verdicts come from the contract oracle. |
| 2:45–3:00 | What is new in this hackathon vs. what we used; next steps. |

## 5. Risk register

| Risk | Likelihood | Impact | Mitigation / fallback | Cutoff |
|---|---|---|---|---|
| Proxy control on the multiplexed C# client fails | Medium | High | Fallback A for fixtures; D1 by stress with a measured rate | Oct 30 EOD |
| OTel cart build from source fails or needs many services | Medium | Medium | Published 3.0.0 image (same race logic, diff verified) with the caveat stated | Oct 29 EOD |
| Muse adds no measurable search value | Medium-High | Medium | Reported honestly; RQ5 and verified reproduction carry the Meta-model role | Pilot, Oct 29 |
| Model API key or credits not ready | Unknown | High | Owner creates the key Oct 28; spend alert (Q-M7) | Oct 28 |
| Held-out set not ready | Medium | High | Sealed-seed mutation script | Oct 31 |
| Harness false positive found late | Low | Critical | Controls in every batch; soundness checker on every trace | Any time |
| Rules change or hidden form fields | Low | Medium | Re-read Nov 1 and Nov 4; open the form Nov 2 | Nov 2 |
| A team member in a restricted API territory | Unknown | High | Confirm Oct 28 (Q-H5) | Oct 28 |
