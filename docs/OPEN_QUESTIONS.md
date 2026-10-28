# Open Questions

Questions that must be answered before or during Phase 1. Each has a **needed-by** date and a
way to answer it. "Blocking" means Phase 1 work that depends on it cannot start or finish.

## Team decisions (blocking Phase 1 start)

| ID | Question | Needed by | How to answer |
|---|---|---|---|
| Q-T1 | Do we approve Option B (wire-level, delay-only proxy) and the evaluation design as pre-registered? | Oct 28 AM | Team review of `ARCHITECTURE.md` and `EVALUATION_PLAN.md`. |
| Q-T2 | Who is on the team (≤ 4 for Indie), and who owns W1–W4? Who authors the held-out set? It must not be the prompt author. | Oct 28 AM | Team. Solo fallback: sealed-seed mutation script. |
| Q-T3 | Is `/Users/harthikmallichetty/Desktop/MetaMorphic/mylonite` the right location? | Oct 28 | Team. Moving the folder is harmless before a remote exists. |
| Q-T4 | Indie track confirmed? | Before submission | Team. |
| Q-T5 | License for publication (Apache-2.0 proposed) and when to create the public remote. | Nov 3 | Team (D-016). |

## Hackathon and compliance

| ID | Question | Needed by | How to answer |
|---|---|---|---|
| Q-H1 | What are the "problem statements" referenced by the Impact criterion (30%)? Does Mylonite fit one? | Oct 29 | Re-read the event page; ask organizers in the event channel. |
| Q-H2 | Is a public repository required, and by when? | Nov 2 | Submission form (open it Nov 2) or organizers. |
| Q-H3 | Required demo video length and format? | Nov 2 | Submission form or organizers. Planning for ≤ 3:00. |
| Q-H4 | Do the $150 credits cover Muse Wonder and Contributor mode? Is a payment method still required? | Oct 28 | Credit terms (the PDF returned 403); try in the console. |
| Q-H5 | Is every team member who will call the API in a permitted territory? | Oct 28 | Each member checks the Geographic Use Policy. |
| Q-H6 | Is the 6-hour grace period in the event page data real? | Never rely on it | Ignore; submit by 6 PM ET. |

## Model API behavior (gate G0)

| ID | Question | How to answer |
|---|---|---|
| Q-M1 | Does strict `json_schema` accept nullable types, `$ref`, `minItems`/`maxItems`, `maxLength`? | Day-1 smoke test with variants. |
| Q-M2 | Is `store: false` honored on the Responses API? | Smoke test plus docs re-read. |
| Q-M3 | Real token counts and latency for a planner call with ~30k tokens of C# source, at `reasoning_effort` low/medium/high. | Smoke test; then re-estimate the budget. |
| Q-M4 | How does prompt caching work (automatic prefix caching?), and what prefix structure maximizes cache hits? | Docs and smoke test (cached-token counts in usage). |
| Q-M5 | What is `muse-spark-1.3`'s training cutoff? It determines whether #3824 (Aug 2026) could be memorized. | Docs; if unknown, assume it could be. |
| Q-M6 | Maximum output tokens for `muse-spark-1.3`? | Docs or an error probe. |

## Technical feasibility (gates G0–G1)

| ID | Question | How to answer |
|---|---|---|
| Q-E1 | Does the OTel cart image start and serve `AddItem`/`GetCart` without flagd and the collector? | Day-1 run in the sandbox network. |
| Q-E2 | Can execution order be controlled on StackExchange.Redis's multiplexed connection (`ARCHITECTURE.md` §5.4)? What is the replay rate? | Day-2 experiment. |
| Q-E3 | Is there a second real-world, store-mediated race in an open-source service, ideally reported after the model's training cutoff (R2)? | Day 1–2 GitHub search: "lost update", "race", with HGET/HSET, GET/SET, INCR, and WATCH. |
| Q-E4 | Does the cart (or any target) open extra connections or send background commands that break quiescence detection? | Trace inspection on Day 2. |
| Q-E5 | Do Python 3.14 wheels exist for every dependency we need (grpcio in particular)? | `pip download` dry run in a container on Day 1. Fallback: harness in a pinned Python 3.12 container. |
| Q-E6 | Right default quiescence window `Δq` and hold cap relative to client timeouts? | Measure on D2, D4, and the cart. |
| Q-E7 | Valkey 9 I/O threads: is command execution still strictly serialized, as §5.2 assumes? | Valkey docs; observe with one-in-flight gating. |

## Research validity

| ID | Question | How to answer |
|---|---|---|
| Q-R1 | Does any existing tool already schedule RESP (or SQL) commands systematically between a service and its store, with a serial-equivalence oracle? Phase 0 found none, but the search was not exhaustive. | A focused search on Day 1 (GitHub, arXiv, "Redis proxy concurrency testing", "deterministic Redis", "ACIDRain follow-up"). Update `PRIOR_ART.md`. |
| Q-R2 | What exactly does REINS do with workload and input selection, versus schedules? Does its evaluation include service-level or I/O-bound targets? | A team member reads https://arxiv.org/html/2610.13421 in full. |
| Q-R3 | Is `B_exec = 300` sensible? | Calibrate on the dev set before freezing (G2). |
| Q-R4 | Can M3's argument sampling reach deep operations, such as checkout with valid payment data? | Dev-set runs; this decides how hard M3 is to beat. |
| Q-R5 | Are SURW/POS worth adding when exhaustive enumeration is feasible for our workload sizes? | Only if dev runs show workloads with > ~1,000 interleavings. |

## Product

| ID | Question | How to answer |
|---|---|---|
| Q-P1 | How often do store-mediated races appear in public incident reports or postmortems? | Background reading; not blocking. |
| Q-P2 | How long do teams take to reproduce such bugs today? | Talk to 2–3 backend engineers if time allows; not blocking. |
| Q-P3 | Would a backend engineer write the target spec, or does it have to be generated? | Ask the same engineers; P2 design input. |
