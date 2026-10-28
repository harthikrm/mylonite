# Architecture Options

Status: **Phase 0 proposal, awaiting team approval.** Nothing here is implemented.

This document compares the realistic ways to build Mylonite in eight days and recommends one.
The recommended design is specified in `ARCHITECTURE.md`; decisions are logged in `DECISIONS.md`.

## 1. Constraints that shape every option

From the research (details and links in `PRIOR_ART.md` and `RESEARCH_LOG.md`):

1. **Interleaving search is largely solved for small bugs.** Most real concurrency bugs involve
   ≤ 2 threads and ≤ 4 ordered accesses (Lu et al., ASPLOS 2008). On SCTBench, naive controlled
   random scheduling found 43 of 49 bugs in total; a single seed found 27 within its first 2
   schedules and 32 within 10 (Thomson et al., TOPC 2016). PCT,
   POS, RFF, and SURW push further. An LLM picking interleavings competes against this.
2. **Choosing the workload is not solved.** PCT explicitly assumes the bug-triggering input is
   given. Learned input selection helped in Snowcat (SOSP 2023); LLM driver generation helped
   in ConCovUp (2026). This is the most plausible place for model guidance to win.
3. **LLM-chosen interleavings already exist.** REINS (arXiv 2610.13421, Oct 2026) uses an LLM
   agent to turn bug hypotheses into constraints on event orders and variable states for a
   controlled C/C++ thread scheduler. It reports 48/52 vs 47 for the best baseline on
   SCTBench+ConVul and 769 vs 731 bugs on RaceBench (each tool run once, per the full paper),
   plus six previously unknown real-world bugs, three confirmed by developers (abstract). Its
   abstract does not describe the LLM choosing inputs or workloads. Fray (JVM) ships an MCP
   server that lets an LLM choose every scheduling step. Re-doing either for another language is
   not differentiated.
4. **Application-level races through a shared store are invisible to memory-level tools.** A lost
   update across two HTTP/gRPC requests that each do `HGET` then `HSET` has no data race in any
   process; ThreadSanitizer and the Go race detector cannot see it. ACIDRain (SIGMOD 2017) found
   22 such attacks in 12 deployed e-commerce apps; 8 of 22 needed a manual 200 ms proxy delay to
   reproduce, and its analysis reported 4 non-triggerable candidates.
5. **A real, unfixed instance exists**: OpenTelemetry Demo #3824. The C# cart service
   does `HGET → mutate → HSET` on Valkey with no atomicity, on `main` and tag `3.1.0`.
6. **Model facts** (Meta docs): `muse-spark-1.3` supports JSON-schema-constrained output
   (non-recursive, depth ≤ 10); `seed` is deprecated and only best-effort; temperature is tuned for
   1.0; `tool_choice` is `auto` only. Model output is not reproducible, so every result must be
   reproducible from recorded artifacts, not by asking the model again.
7. **Local environment**: macOS, Docker 29.5.3, Python 3.14, Node 26. No Go or Java toolchain.

## 2. Option A: In-process deterministic scheduler for Python targets

**Idea.** Shuttle/Coyote-style controlled testing for Python. Each logical operation runs in its own
thread or task; instrumented points (store-client calls, `threading.Lock`, `asyncio` awaits)
block until a central scheduler picks that operation. Exact attribution, exact replay.

| Aspect | Assessment |
|---|---|
| Components | Op runner, instrumented store client and lock wrappers (monkeypatched), scheduler, serial-reference oracle, Muse planner, replay files. |
| Data flow | Planner → validated workload → runner spawns ops → each yield point asks the scheduler → trace → oracle. |
| Model vs deterministic | Model picks workloads and hints only; everything else is deterministic Python. |
| Technology | Python 3 only. No containers needed for fixtures. |
| Complexity | Low to moderate. The hard part is unmodeled blocking (I/O, C extensions, third-party locks), which hangs the scheduler. |
| Security | Targets run in-process with the harness, so the sandbox must wrap the whole harness. |
| Failure modes | Hangs on uninstrumented blocking; monkeypatching misses; GIL-level races out of scope. |
| Difficulty | ~2 days to a reliable core. |
| Benefits | Strongest determinism; very fast (thousands of executions per minute); easiest to debug. |
| Drawbacks | **Python only.** Cannot run the real #3824 code (C#), so the real-world bug would have to be hand-ported into a Python "bug kernel" (a GoKer-style practice, but weaker evidence). Little new relative to Shuttle/Coyote/Fray/REINS. |

## 3. Option B: Delay-only command scheduler at the data-store wire boundary (recommended)

**Idea.** Put a small proxy between the unmodified service and its data store (Valkey/Redis,
protocol RESP2 first). The proxy holds data commands and decides **when** each one reaches the
store. The service can be written in any language and runs unmodified in a container. A harness
issues the concurrent requests, observes results through the service's own API, and checks them
against the serial-equivalence oracle.

**Why "delay-only" matters.** The proxy never invents, drops, or rewrites commands. It only
delays, while keeping each connection's replies in order. Every schedule it produces could
therefore happen in production through ordinary network or scheduling delay. A violation found
this way is a real possible behavior, not an artifact of the instrumentation. This is the
systematic version of the manual 200 ms delay proxy ACIDRain used.

| Aspect | Assessment |
|---|---|
| Components | Target spec + operation catalog; RESP proxy with scheduler; executor (reset, setup, concurrent round, observe); serial-reference engine and oracle; strategies (stress, random, PCT, conflict-directed systematic, Muse); replay/verifier; reports. |
| Data flow | Strategy → experiment → executor drives the service's API; the service's store commands flow through the proxy, which consults the scheduler → trace + op results + final observation → oracle → verdict → replay verification. |
| Model vs deterministic | Model: hypotheses, workload (operations and arguments, including setup to satisfy preconditions), schedule hints, explanation. Deterministic: catalog, proxy, scheduler, oracle, replay, minimization, budgets, sandbox. |
| Technology | Python 3 asyncio for proxy, scheduler and harness; Docker Compose for target + Valkey on an internal network; OpenAI-compatible SDK or plain HTTPS to the Meta Model API. |
| Complexity | Moderate. One extra process. Protocol subtleties: per-connection reply order, multiplexed clients (StackExchange.Redis, ioredis), `MULTI/EXEC` and `EVAL` blocks, pub/sub connections, heartbeats. |
| Security | Target runs in a hardened container with no egress. The model never produces code. See `THREAT_MODEL.md`. |
| Failure modes | Attribution errors on multiplexed connections; quiescence timeouts make some decisions timing-dependent (measured, not hidden); client timeouts if commands are held too long; unsupported commands (passed through unscheduled and reported). |
| Difficulty | ~2–3 days to reliable control on one real service. Main technical risk; it has a hard cutoff and a fallback (`ROADMAP.md`). |
| Benefits | Runs the **real, unmodified #3824 code**. Language-agnostic for the service. Targets a bug class memory-level tools miss. A clear story: "We control the order in which the cart's writes reach Valkey." Same mechanism for every benchmark target. |
| Drawbacks | Scope is limited to races mediated by an external store. In-memory races (for example OTel #3989 in the C++ currency service) are out of scope. Determinism is empirical and must be reported as a reproduction rate. SQL (Postgres wire protocol) is much harder and is P2. |

## 4. Option C: Agentic investigator that writes and runs its own tests

**Idea.** The model reads the repository, writes harness and test code, runs it in a sandbox,
reads the output, and iterates (CodeAct / SWE-agent / NVIDIA OO-Agents style).

| Aspect | Assessment |
|---|---|
| Components | Agent loop, code-execution sandbox, file/tool interface, result parser. |
| Data flow | Model → code → sandbox → output → model, repeatedly. |
| Model vs deterministic | Model is in the execution path and effectively becomes the oracle for whether a test "found" something. |
| Technology | Any agent framework, or a hand-rolled loop. NOOA is alpha (v0.0.x), Python 3.12–3.13 only, and runs model-written code by default. |
| Complexity | Low to start, high to make trustworthy. |
| Security | Worst of the three: model-written code runs; prompt injection from target source can steer what gets executed. Requires a stronger sandbox than Docker Desktop offers by default. |
| Failure modes | Hallucinated "bugs" (LLM static bug finding has high false discovery rates, e.g. IRIS 84.82%); unbounded loops and cost (REINS used up to 153M input tokens on one target); non-reproducible runs. |
| Difficulty | A flashy demo in 2 days; a defensible evaluation is unlikely in 8. |
| Benefits | Most general; most impressive-looking demo. |
| Drawbacks | Hard to compare fairly with baselines, because the model also changes the harness. Violates our rule that the model never writes code that runs and never decides what is true. |

## 5. Option D (considered): Muse as a scenario generator for an existing executor

Use Lincheck or Fray (JVM) as the controlled executor and let Muse replace its random scenario
generator. Those executors are mature, and the comparison would be clean. **Rejected for P0**:
the JVM is not installed, the bug class is in-memory data structures (crowded: Lincheck, Fray, JPF,
REINS-style approaches), and it cannot reach the real-world service bug we have. It remains a good
Phase-2 extension if store-mediated races prove too narrow.

## 6. Comparison

| Criterion | A in-process | **B wire-boundary** | C agentic |
|---|---|---|---|
| Runs the real #3824 code unmodified | No (port needed) | **Yes** | Yes |
| Determinism of replay | Exact | Empirical, measured | Poor |
| Verdict independent of the model | Yes | **Yes** | No |
| Model executes code | No | **No** | Yes |
| Fair comparison with baselines | Yes | **Yes** | Hard |
| Differentiation from prior art | Low | **Moderate-high** (service-level, store-mediated, any language, workload selection) | Low-moderate |
| Fits 8 days | Yes | Yes, with a cutoff | Demo yes, evidence no |
| Judge clarity in 3 minutes | Medium | **High** | High but fragile |

## 7. Recommendation

**Adopt Option B**, with one piece of Option A held in reserve:

- Core: delay-only RESP command scheduler at the store boundary; services under test run
  unmodified in containers; spec-free serial-equivalence oracle; Muse chooses workloads.
- Fallback (triggered only by the Day-2 gate in `ROADMAP.md`): if wire-level control is not
  reliable, swap the proxy for an in-process gated client in Python fixture services. The
  scheduler, oracle, strategies, and evaluation harness stay the same; #3824 is then reproduced
  by uncontrolled stress with a measured reproduction rate.
- Harness/tool language: **Python 3**. It is installed, asyncio fits a proxy, and the team avoids a
  toolchain install on Day 1.
- First protocol: **RESP2 (Valkey/Redis)**. It is simple to parse, #3824 uses it, and Redis-backed
  read-modify-write is a common real pattern. Postgres is P2.
- First real target: **OpenTelemetry Demo cart service, pinned to tag `3.1.0`**
  (`dedc0178918e260823323b8d95005a8cb924b007`), scenario A (concurrent `AddItem` lost update).
  Scenario B (`PlaceOrder` vs `AddItem`) is P1 because it needs about 12 containers.

What this recommendation does **not** claim: that Muse explores interleavings better than PCT or
exhaustive search. On the small workloads this bug class produces, exhaustive enumeration of
interleavings is cheap, and we will use it. The model's measurable job is choosing which
operations, with which arguments and setup, to race. That claim is tested against a strong
non-LLM baseline (conflict-directed systematic search; see `EVALUATION_PLAN.md`).
