# Prior Art

Research date: 2026-10-27/28. **Evidence labels:**
**[P]** primary text read (paper, docs, or source); **[A]** abstract or official landing page only;
**[S]** secondary source, not verified against the primary; **[K]** known to the team but not
re-verified in Phase 0. Numbers are quoted only where a source was read. The dated trail of how
each was found is in `RESEARCH_LOG.md`.

## 1. The six questions

### 1.1 What has already been solved?

- **Controlled, replayable interleaving of threads in managed runtimes.** CHESS (C#/.NET, OSDI
  2008) [P]; Coyote (.NET, binary rewriting, JSON replay traces) [P]; Fray (JVM, OOPSLA 2025:
  random, PCT, POS, SURW, replay) [P]; Lincheck (JVM, model checking plus default sequential
  oracle plus minimization) [P]; Loom (Rust, DPOR, exhaustive with preemption bound) [P]; Shuttle
  (Rust, randomized and PCT; "not sound… but scales") [P]; gosim (Go, experimental) [P].
- **Exploration algorithms with guarantees.** PCT gives a per-run probability of at least
  1/(n·k^(d−1)) for depth-d bugs [P]. DPOR and optimal DPOR give complete exploration with
  provably minimal executions [P/A]. POS and SURW improve on PCT on standard suites [P, slides].
  RFF and PERIOD add greybox feedback [P].
- **Spec-free oracles by comparing with serial executions.** Line-Up (PLDI 2010) checks
  deterministic linearizability against serial runs with no written specification: 13 .NET
  classes, 7 real errors fixed [A]. Lincheck's default oracle runs the same structure
  sequentially [P].
- **History checkers.** Knossos (linearizability; its author is "not certain the algorithm is
  correct yet") [P]; Porcupine (Go, P-compositional WGL, 1,000–10,000× faster than Knossos on
  Jepsen data per its README, HTML visualizer) [P]; Elle (isolation anomalies from dependency
  cycles, hundreds of thousands of transactions in tens of seconds, deliberately incomplete) [P].
- **History format with indeterminacy.** Jepsen's `invoke/ok/fail/info` [P].
- **Memory-level data race detection.** ThreadSanitizer and the Go race detector: dynamic,
  happens-before, low false positives. Go's caught 10 of 20 reproduced non-blocking bugs within
  100 runs in Tu et al. [P].
- **Whole-system deterministic simulation**, if you can afford it. FoundationDB simulation and
  TigerBeetle's VOPR require all nondeterminism behind injectable interfaces [P]. Antithesis
  makes arbitrary containers deterministic with a hypervisor, but is commercial with no free
  tier [P].
- **LLM-chosen interleavings.** REINS (arXiv 2610.13421, Oct 2026) [P] is a research system that
  beats strong baselines and found real bugs. Fray's MCP server exposes `get_all_threads` /
  `run_thread` to an LLM [P, no published evaluation found].
- **LLM fixing a known race given a failing test.** Meta's own cookbook
  (`02_agent_patterns/01_agent_loop_basics`, `async_counter.py`) has Muse Spark fix an asyncio
  lost update in an agent loop with `pytest` as the oracle [P, read 2026-10-28]. Mylonite targets
  the step before: finding and proving the race when no failing test exists.

### 1.2 What remains difficult in practice?

1. **Choosing the workload.** PCT explicitly assumes "the bug-triggering input is given" [P].
   Fray needed hand-written drivers for its real-world bugs [P]. Only 8 of 47 JaConTeBe bugs were
   found by any automated test generator in a 2018 study [A]. ConCovUp (2026) uses LLM agents
   precisely because driver generation is open [A].
2. **Writing the oracle.** Porcupine and Knossos need a sequential model; Elle needs particular
   workload shapes and asks users to confirm anomalies by hand [P].
3. **State outside the process.** A client-side thread scheduler cannot control interleavings
   inside a database. Only hypervisor-level control (Antithesis) or simulation-first design
   (FoundationDB, TigerBeetle) controls both sides [P].
4. **Application-level races through a store.** These have no data race in any process, so TSan
   and `-race` are blind to them (Regehr's "race condition vs data race" example [P]). ACIDRain
   found 22 verified attacks in 12 e-commerce apps deployed on more than 2M sites. It had to
   reproduce them by hand, 8 needed an added 200 ms proxy delay, and 4 flagged candidates were not
   triggerable [P]. Feral Concurrency Control found validations used 13.6× more often than
   transactions in 67 Rails apps [S].
5. **Environment nondeterminism.** `synctest` does not control goroutine interleaving or treat
   mutexes and I/O as durably blocking [P]. Lincheck rejects socket I/O [P]. FoundationDB forbids
   threads in workloads [P].
6. **Python.** No mature controlled scheduler. Free-threading guidance offers only stress tools
   and calls such tests "inherently flaky" [P].

### 1.3 Which methods are realistically usable in eight days?

| Method | Usable? | Why |
|---|---|---|
| Random, PCT, exhaustive policies on our own executor | **Yes** | Under a day each; they are our baselines. |
| Serial-equivalence oracle (Line-Up idea) | **Yes** | Small; our workloads have ≤ 4 concurrent operations. |
| Jepsen history semantics | **Yes** | A convention, not a dependency. |
| Delay-injecting proxy (ACIDRain-style, made systematic) | **Yes, main risk** | One process. RESP2 is simple; multiplexed clients are the hard part. |
| Porcupine as a second oracle | Maybe (P1) | Requires installing Go and writing models in Go. |
| Elle via elle-cli | Not for P0 | Requires a JVM and Elle-shaped workloads. |
| Fray, Lincheck, Coyote, Loom, Shuttle | No | Wrong runtime for our target; no JVM, .NET SDK, or Rust toolchain needed so far. |
| Antithesis | No | No free access [P]. |
| rr | No | Linux only with performance counters; not on our Macs [P]. |
| Agent frameworks (NVIDIA OO-Agents) | Ideas only | Alpha v0.0.x, Python 3.12–3.13, runs model-written code by default [P]. |

### 1.4 Where could model-guided reasoning produce a measurable improvement?

Each item is a **hypothesis**, tested in `EVALUATION_PLAN.md`.
- **H-W (workload selection):** picking which operations to race, with which arguments, and
  which setup satisfies semantic preconditions (an active coupon, stock exactly 1, an order in
  state `PAID`, a valid payment card). This is the gap PCT leaves open. Learned input selection
  helped in Snowcat (1.4–2.6× better chance of picking bug-exposing inputs) [A]; LLM drivers
  doubled access-pair coverage in ConCovUp [A].
- **H-X (cross-language reading):** the service can be C#, Go, Node, or Python. The model reads it
  without a per-language analyzer. Our baseline counters this with language-agnostic dynamic
  profiling at the proxy.
- **H-E (explanation):** mapping a verified command trace back to source lines. Useful, but only
  measurable through reference checking, so it is a secondary claim.
- **H-I (invariant proposals, P1):** filtered by "must hold on every serial execution", which turns
  the model's known tendency to invent properties into a checkable proposal.

### 1.5 What would make Mylonite technically differentiated?

Differentiating hypotheses. None is a claim until the evaluation runs.
1. **The target is service-level, store-mediated races in unmodified services in any language.**
   Memory-level tools cannot see them. ACIDRain found them but reproduced by hand. We found no
   tool that systematically schedules RESP commands between a service and its store. The search
   was not exhaustive; see `OPEN_QUESTIONS.md` Q-R1. Toxiproxy-style latency proxies [K] add
   delays but do not choose orders or check outcomes.
2. **Delay-only soundness.** Every schedule we produce is reachable by network delay alone, so a
   violation is a real behavior and not an instrumentation artifact.
3. **No written specification.** Serial-equivalence on observed API outcomes, with automatic
   volatile-field masking and Jepsen `fail`/`info` semantics.
4. **The model chooses workloads, not interleavings.** This is the opposite emphasis from REINS
   and Fray-MCP. It targets the open problem rather than the saturated one.
5. **Evidence discipline.** Repeated trials, cost accounting, a conflict-directed non-LLM baseline,
   held-out bugs. REINS ran each tool once with no variance [P]; ChatAFL and Fuzz4All did not
   analyze contamination [P].

### 1.6 Where might conventional deterministic methods outperform the AI system?

- **Shallow bugs.** In Thomson et al., random scheduling found 27 bugs within its first 2
  schedules [P]. For the 2-operation, 3-command workloads typical of store races, exhaustive
  enumeration costs fewer executions than one model call costs in seconds.
- **Small APIs.** The OTel cart has 3 operations. Random pairs collide on a user with probability
  ~½ given a 2-user domain, and any two `AddItem` calls on the same user trigger #3824.
- **Guarantees.** PCT, POS, and SURW give probability bounds or uniformity; a model gives none.
- **Reliability and cost.** LLM answers vary across runs, with high false-positive rates in
  vulnerability detection (Ullah et al., S&P 2024 [A]; IRIS false discovery rate 84.82% [A]).
  REINS used up to 153M input tokens on one target [P].
- **Conflict detection itself.** A dynamic read/write-set profile at the proxy finds "two
  operations write the same key" with no model at all. This is our M3 baseline, and it may match
  the model on every target whose bug is reachable with sampled arguments.

## 2. Source-by-source notes

### 2.1 Systematic and randomized concurrency testing

| Work | Key facts | Relevance |
|---|---|---|
| Iterative context bounding (PLDI 2007) [P] https://www.cs.columbia.edu/~junfeng/08fa-e6998/sched/readings/context-bounding.pdf | 9 new bugs; each needed ≤ 2 preemptions. | Small bounds suffice. |
| CHESS (OSDI 2008) [P] https://static.usenix.org/events/osdi08/tech/full_papers/musuvathi/musuvathi_html/index.html | 27 bugs (25 new); 21 never seen in months of stress. | Controlled beats stress. |
| PCT (ASPLOS 2010) [P] https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/paper-83.pdf | Bound 1/(n·k^(d−1)); Pbzip2 per-run 0.701 vs 0 for stress. Assumes input is given. | Baseline M2; motivates H-W. |
| DPOR (POPL 2005) [A] https://dblp.org/rec/conf/popl/FlanaganG05.html; Optimal DPOR (POPL 2014) [P] https://user.it.uu.se/~parosha/publications/papers/popl2014.pdf | Complete search with reduction; optimal variant explores the minimal number of executions. | P1 reduction for `exhaustive`. |
| POS (CAV 2018) [P] https://www.cs.columbia.edu/~junfeng/papers/pos-cav18.pdf | 2.6× faster than random walk and PCT on SCTBench. | Optional policy. |
| SURW (ASPLOS 2025) [P, slides] https://zhaohuanqdcn.github.io/assets/files/asplos25-slides.pdf | SCTBench 34.90/37 vs PCT 30.75, random walk 19.90. Budget not confirmed. | State of the art for schedules. |
| Thomson, Donaldson, Betts (TOPC 2016) [P] https://www.doc.ic.ac.uk/~afd/papers/2016/TOPC.pdf | Random 43/49 bugs; 27 within 2 schedules; 18 programs buggy in > 50% of random schedules. Use controlled random as a baseline. | The reason M1 exists. |
| RFF (ASPLOS 2024) [P] https://www.comp.nus.edu.sg/~gregory/papers/asplos24.pdf | 46.1/49 vs PERIOD 44.6, PCT ~37; 20 trials, Mann–Whitney. | Methodology model. |
| PERIOD (ICSE 2022) [P] https://wcventure.github.io/pdf/ICSE2022_PERIOD.pdf | 10/10 CVE programs. | — |
| QL (OOPSLA 2020) [A]; Snowcat (SOSP 2023) [A] https://research.google/pubs/snowcat-efficient-kernel-concurrency-testing-using-a-learned-coverage-predictor/ | Learned schedulers and input selection. Snowcat: 1.4–2.6× better input picking. | Closest learned-input precedent. |
| Krace, MUZZ, Conzzer [A] | Kernel and userspace concurrency fuzzing. | Context only. |

### 2.2 Tools

| Tool | Facts | Use for us |
|---|---|---|
| Jepsen https://github.com/jepsen-io/jepsen [P] | Generator/nemesis/checker; no thread-level control; needs JVM 21+, SSH nodes; Docker "unsupported". v0.3.15 (Oct 2026). | Adopt the history semantics only. |
| Knossos https://github.com/jepsen-io/knossos [P] | Linearizability; returns `:unknown` on timeouts. | No. |
| Elle https://github.com/jepsen-io/elle, elle-cli https://github.com/ligurio/elle-cli [P] | Isolation checking from JSON or EDN histories; requires a JVM. | P2, for SQL targets. |
| Porcupine https://github.com/anishathalye/porcupine [P] | Go, MIT, v1.3.1; `Partition/Init/Step/Equal`; HTML visualizer; no first-class `info`; no maintained Python port. | P1 second oracle and timeline inspiration. |
| Antithesis https://antithesis.com/docs/ [P] | Deterministic hypervisor; always/sometimes/reachable assertions; Test Composer; no free version. | Vocabulary only. |
| FoundationDB https://apple.github.io/foundationdb/testing.html, TigerBeetle VOPR [P] | Simulation-first design. | Pattern only. |
| Lincheck https://github.com/JetBrains/lincheck [P] | Default oracle is the sequential run of the same structure; minimization on by default; rejects socket I/O. | Ideas: oracle and minimization. |
| Fray https://github.com/cmu-pasta/fray [P] | JVM; random/PCT/POS/SURW/FEST; random found 46/53 vs JPF 27, rr 26; POS led on several sets; MCP server for LLM-driven stepping. | Prior art for LLM scheduling; reference implementations of policies. |
| Coyote https://microsoft.github.io/coyote/ [P] | .NET binary rewriting; last NuGet release Mar 2024. | Could control the C# cart in-process, but that would mean rebuilding the image and is .NET-only. Not chosen. |
| Loom, Shuttle [P] | Rust exhaustive vs randomized; Shuttle's stated trade-off favors randomized at scale. | Design argument for M1/M2. |
| Go race detector, `testing/synctest` [P] | TSan-based; `synctest` GA in Go 1.25, controls time, not interleaving. | Out of scope (memory races). |
| Python: blanket, interleave-test [P] | Scripted primitives; immature sys.monitoring scheduler (1★). | Confirms there is no mature Python option (relevant to Fallback A). |
| rr [P] | Linux only; chaos mode is randomized. | No. |
| ThreadSanitizer [P] | Data races only; 5–15× slowdown. | Cannot see store-mediated races. |
| Toxiproxy [K] | TCP proxy that injects latency and faults. | Shows proxies are an accepted test tool; it does not schedule or check. |

### 2.3 Oracles and theory

| Work | Facts |
|---|---|
| Linearizability, Herlihy & Wing (TOPLAS 1990) [A] https://www.cs.columbia.edu/~wing/publications/HerlihyWing90.pdf | Locality: a system is linearizable iff each object is. |
| Line-Up (PLDI 2010) [A] https://microsoft.com/en-us/research/wp-content/uploads/2016/02/pldi015-burckhardt.pdf | Serial-execution oracle without a specification. Our oracle is this idea applied to service APIs. |
| WGL / Lowe (CCPE 2017) [A] https://www.cs.ox.ac.uk/people/gavin.lowe/LinearizabiltyTesting/paper.pdf | Checking is NP-complete; caching variants. |
| P-compositionality (FORTE 2015) [A] https://arxiv.org/abs/1504.00204 | Partition by key; ≥ 10× faster. |
| Elle (PVLDB 2020) [P] https://arxiv.org/pdf/2003.10554 | Found lost updates in TiDB, among others. |
| MonkeyDB (OOPSLA 2021) [A] https://arxiv.org/abs/2103.02830 | Mock store returning weak-isolation reads. Different lever: it changes what reads return, while we change command order against a real store. |
| IsoDiff (PVLDB 2020) [A] https://par.nsf.gov/servlets/purl/10227054 | Debugging RC/SI anomalies in applications. |

### 2.4 Real-world bug characteristics and benchmarks

| Study | Facts |
|---|---|
| Lu et al. (ASPLOS 2008) [P] https://www.cs.columbia.edu/~junfeng/08fa-e6998/sched/readings/concurrency-bugs.pdf | 105 bugs; 97% of non-deadlock bugs are atomicity or order violations; 96% involve ≤ 2 threads; ~92% need ≤ 4 ordered accesses; 34% involve multiple variables. |
| Tu et al., Go (ASPLOS 2019) [P] https://songlh.github.io/paper/go-study.pdf | 171 bugs; built-in deadlock detector caught 2/21; race detector caught 10/20. |
| GoBench (CGO 2021) [A] | GoReal 82, GoKer 103 kernels (vendored in the Go tree). Public, so contamination-prone. |
| TaxDC (ASPLOS 2016) [A]; percentages [S] | 104 distributed concurrency bugs. |
| JaConTeBe (ASE 2015) [A] | 47 Java bugs. |
| ACIDRain (SIGMOD 2017) [P] https://static.aminer.org/pdf/20170130/pdfs/sigmod/aw7mzkroxdfsqbiab0mhpkt4zoepg3cd.pdf | 12 apps, 22 verified attacks; serial-impossibility check; manual reproduction; 200 ms proxy delay for 8. |
| Feral Concurrency Control (SIGMOD 2015) [S] https://blog.acolyer.org/2015/09/04/feral-concurrency-control-an-empirical-investigation-of-modern-application-integrity/ | 67 Rails apps; application-level validations dominate transactions. |
| OpenTelemetry Demo #3824 [P] https://github.com/open-telemetry/opentelemetry-demo/issues/3824 | Open, unlabeled; fix PR #3825 closed as stale; racy code on `main` and tag `3.1.0`. Details in `PROBLEM.md` §3. |

### 2.5 LLMs, testing, and concurrency

| Work | Facts | Lesson for us |
|---|---|---|
| **REINS** (arXiv 2610.13421; Zhang, Pasareanu, Yang; submitted 9 Oct 2026; abstract re-checked 2026-10-28) [P] https://arxiv.org/html/2610.13421 | LLM agent (Claude Sonnet 4.6) → event-order and state constraints for a controlled C/C++ scheduler; test entries and inputs are given, not chosen. Six previously unknown real-world bugs, three confirmed by developers (abstract). SCTBench+ConVul 48/52 vs RFF 47, SURW 46, PCT-3 44. RaceBench 769 vs SURW 731. Single run per tool; up to 153M input tokens per target; admits possible training-data exposure. | Closest prior work. We differ in level (service vs thread), what the model chooses (workload vs interleaving), and evaluation rigor. **The team should read it in full** (Q-R2). |
| Fray MCP https://github.com/cmu-pasta/fray/blob/main/docs/mcp.md [P] | LLM can drive each scheduling step. | LLM-as-scheduler is not novel. |
| ConCovUp (arXiv 2605.09573) [A] | LLM agents generate concurrency test drivers; access-pair coverage 36.6% → 68.1%. | Supports H-W. |
| Petri-net-guided Rust tests (arXiv 2607.21530) [A] | LLM writes tests; Loom or a scheduler explores. | Same division of labor as ours, different level. |
| Chen et al. 2023 [A] https://arxiv.org/abs/2308.07505; Internetware 2026 [A] | LLMs "cannot compete" with race tools on detail; hallucinations differ from tool false alarms. | Keep the model out of verdicts. |
| ChatAFL (NDSS 2024) [P]; Fuzz4All (ICSE 2024) [P]; KernelGPT (ASPLOS 2025) [A]; TitanFuzz (ISSTA 2023) [A] | Repeated trials, effect sizes, sanitizer oracles; little or no contamination analysis. | Copy their statistics; add contamination controls. |
| Ullah et al. (S&P 2024) [A] https://arxiv.org/abs/2312.12575; IRIS (ICLR 2025) [A] https://arxiv.org/html/2405.17238v3 | Non-deterministic answers; FDR 84.82% even with CodeQL. | Model output is a proposal, never a finding. |
| Contamination: Defects4J memorization [A] https://arxiv.org/abs/2411.13323; SWE-bench file-path recall ~76% without repository access [A] https://arxiv.org/abs/2506.12286 | Famous bugs are memorized. | D1 (#3824) is dev only; held-out bugs are new code. |
| Klees et al., evaluating fuzz testing [A] https://arxiv.org/abs/1808.09700 | Every one of 32 evaluations examined had problems. | Pre-register; repeat trials; report all. |

### 2.6 Agent frameworks

**NVIDIA Object-Oriented Agents (NOOA)** https://github.com/NVIDIA-NeMo/labs-OO-Agents [P].
Agents are Python classes. Fields are state, methods are capabilities, and methods with a `...`
body are implemented by an LLM strategy (`PredictStrategy`, `CodeActStrategy` (default),
`DecideStrategy`). Return types are validated with retry. Apache-2.0, alpha v0.0.10 (Sep 2026),
Python 3.12–3.13, built on LiteLLM; the README requires an OS-level sandbox for code-executing
agents. **It has no connection to OTel #3824** (code and issue search found none). Ideas we
adopt: "types validate values; Python validates the world", one LLM task per method, typed
outputs with validation retry, and deterministic proof-of-concept verification as in its
CyberGym example. We do not depend on it: it is alpha, its Python range excludes our installed
3.14, and its default strategy runs model-written code.

## 3. Competitors, from a user's point of view

| Alternative | What a team gets | Why they might still want Mylonite |
|---|---|---|
| Load tests (k6, Locust) with assertions [K] | Real concurrency, no control, ad-hoc oracle | Not reproducible; needs a hand-written invariant. |
| Jepsen | Rigorous histories and checkers for databases | Heavy (JVM, SSH nodes); aimed at the database itself, not the application on top of it. |
| Antithesis | Deterministic whole-system exploration | Commercial and sales-gated; still needs workloads and assertions. |
| JVM, .NET, Rust controlled testers | In-process determinism | Only one language each; blind to state in an external store. |
| TSan, `-race` | Memory races | Blind to store-mediated races by construction. |
| Static review or an LLM reading code | Cheap suspicion | Unverified; high false discovery rates. |
