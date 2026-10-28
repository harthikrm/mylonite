# Architecture

Status: **Provisional (Phase 0).** This specifies Option B from `ARCHITECTURE_OPTIONS.md`. Items
tagged **[UNVERIFIED]** depend on behavior we have read about but not yet executed; each is
checked by a named Phase 1 experiment. Nothing is implemented.

## 1. One-paragraph summary

Mylonite tests a service that keeps shared state in Valkey/Redis. A small proxy sits between the
unmodified service and the store and decides when each data command reaches the store. It only
delays commands, never alters them. A harness sends a chosen set of concurrent requests to the
service, records what each request returned, and reads the final state through the service's own
API. A deterministic oracle compares that outcome with the outcomes of every serial order of the
same requests. If no serial order explains it, the run is a **non-serializable outcome**; the
recorded schedule is replayed in a fresh environment to confirm it. Muse Spark reads the
service's source and proposes which requests to race, with which arguments and setup, and later
explains a confirmed trace. The model never writes code that runs and never decides a verdict.

## 2. Scope

In scope (P0):
- Races mediated by an external key-value store speaking **RESP2** (Valkey, Redis): lost updates,
  check-then-act, non-atomic multi-key updates, unsafe locks built from store commands.
- Services in **any language**, unmodified, run in containers.
- A workload is a few sequential **setup** operations, then one **concurrent round** of 2–4
  operations, then **observation** operations.

Out of scope (stated so nobody over-claims):
- In-process memory races (data races, in-memory atomicity violations, deadlocks). Use TSan, the
  Go race detector, Fray, Shuttle, or Loom.
- Interleavings inside the store server beyond command order. Valkey executes commands one at a
  time, so command order is the whole store-level interleaving. That is **not** true of Postgres,
  which is why SQL is P2.
- Faults (crashes, partitions, timeouts). Jepsen and Antithesis cover these.
- Long histories with real-time ordering across rounds. Porcupine or Elle could be added later
  (see `PRIOR_ART.md`).

## 3. Components and trust boundaries

```
                     ┌──────────── host orchestrator (trusted, our code) ────────────┐
 target spec (YAML) ─►  Catalog loader ──► Strategy ◄───────── results/feedback ─────┐ │
 (human-reviewed)      │                    │  ▲                                     │ │
                       │   Context builder  │  │ PlannerOutput (validated)           │ │
 target source ───────►│  (allow-list, scan)│  │                                     │ │
                       │        │           ▼  │                                     │ │
                       │        └──► Muse planner ─► Plan validator                  │ │
                       │                    │                                        │ │
                       │                Experiment                                   │ │
                       │                    ▼                                        │ │
                       │   Executor ── reset / setup / concurrent round / observe    │ │
                       │      │  ▲ op results (gRPC/HTTP)                            │ │
                       └──────┼──┼─────────────────────────────────────────────────┼─┘
             requests (B3)    ▼  │                            trace + results      │
     ┌──────────── sandbox network (internal, no egress) ─────────────────────┐    │
     │  Service under test ──RESP──► Mylonite proxy + scheduler ──RESP──► Valkey│    │
     │  (unmodified image)              (decides command order)              │    │
     └────────────────────────────────────────────────────────────────────────┘    │
                                                                                    │
     Serial-reference engine ──► Oracle ──► Verdict ──► Replay verifier ──► Report ─┘
                                                     └► (P1) Minimizer, Explainer (Muse)
```

| # | Component | Responsibility | Deterministic? |
|---|---|---|---|
| C1 | Target spec + catalog loader | Loads a human-reviewed YAML: compose file reference with pinned image digests, store endpoint, operation catalog (name, transport, argument types, example values), observation operations, volatile-field masks, allow-listed source globs. | Yes |
| C2 | Context builder | Reads only allow-listed source files, runs the secret deny-list and pattern scan, applies byte caps, and wraps the files as delimited untrusted data. | Yes |
| C3 | Muse planner | One structured-output call: hypotheses + experiments. | **No** (model) |
| C4 | Plan validator | JSON Schema check, catalog membership, argument type checks, clamps (≤ 6 setup, 2–4 concurrent ops, ≤ 16 hint steps), dedup against already-run workloads. | Yes |
| C5 | Strategies | Produce experiments: Stress, Random, PCT, Conflict-directed systematic, Muse, plus ablations. Common interface (§7). | Seeded |
| C6 | Executor | Resets state, runs setup sequentially, launches the concurrent round, runs observations, and collects a Jepsen-style history. | Yes, given a schedule |
| C7 | Proxy + scheduler | Parses RESP, gates data commands, chooses execution order at decision points, records the trace (§5). | Yes, given a schedule |
| C8 | Serial-reference engine | Runs every serial order of the operations that succeeded, each twice, to get the allowed outcome set and detect volatile fields (§6). | Yes |
| C9 | Oracle | Masked comparison → `PASS`, `VIOLATION`, or `INCONCLUSIVE` (§6). | Yes |
| C10 | Replay verifier | Re-runs the recorded schedule N times in fresh state; reports reproduction rate and trace-hash agreement. For benchmark targets, also runs it on the fixed variant. | Yes |
| C11 | Minimizer (P1) | Delta-debugs setup ops, concurrent ops, argument values, and non-default scheduling decisions; every candidate re-verified. | Yes |
| C12 | Explainer (P1) | Muse explains a *verified* counterexample with code references; a checker confirms each reference exists. | **No**, output labeled unverified |
| C13 | Reporter | JSON results; static HTML timeline with every untrusted string escaped. | Yes |
| C14 | Evaluation harness | Runs strategies × targets × trials under fixed budgets; writes results; runs the pre-registered analysis. | Seeded |

## 4. Target spec and operation catalog

The catalog is the only vocabulary the model can use. It is written or generated by humans
(from `.proto` or OpenAPI files), reviewed, and versioned. Example for the OTel cart (provisional):

```yaml
target: otel-demo-cart
revision: { repo: open-telemetry/opentelemetry-demo, tag: "3.1.0",
            commit: dedc0178918e260823323b8d95005a8cb924b007 }
images:                       # pinned by digest at Phase 1 Day 1  [UNVERIFIED digests]
  cart: ghcr.io/open-telemetry/demo:3.1.0-cart
  valkey: ghcr.io/valkey-io/valkey:9.1.2-alpine3.24
store: { protocol: resp2, upstream: valkey-cart:6379 }
source_allow: ["src/cart/src/**/*.cs", "pb/demo.proto"]
operations:
  AddItem:   { transport: grpc, method: oteldemo.CartService/AddItem,
               args: { user_id: user, product_id: product, quantity: { int: [1, 5] } } }
  GetCart:   { transport: grpc, method: oteldemo.CartService/GetCart,  args: { user_id: user } }
  EmptyCart: { transport: grpc, method: oteldemo.CartService/EmptyCart, args: { user_id: user } }
domains:                      # same pools for every strategy, including Muse
  user: [u1, u2]
  product: [OLJCESPC7Z, 66VCHSJNUP, 1YMWWN1N4O]   # from the demo's product catalog [UNVERIFIED]
observe: [ { op: GetCart, for_each: user } ]
volatile_masks: []
```

## 5. Proxy and scheduler semantics

### 5.1 What is scheduled

- **Gated (scheduled) commands:** data commands on keys, for example `GET SET HGET HSET HDEL
  HINCRBY INCR INCRBY DECR DEL EXPIRE PEXPIRE SETNX GETSET LPUSH RPOP SADD SREM ZADD`.
  `MULTI…EXEC` and `EVAL/EVALSHA/FCALL` are scheduled as **one atomic unit**. `WATCH` is
  scheduled.
- **Pass-through (not scheduled):** connection and admin traffic (`PING ECHO HELLO AUTH CLIENT
  INFO CONFIG CLUSTER SELECT COMMAND`), and any connection that enters pub/sub mode. Pass-through
  commands are recorded in the trace but never held.
- Unknown commands are passed through and reported. They are never silently scheduled.

### 5.2 Delay-only rule (soundness)

1. The proxy never drops, rewrites, duplicates, or invents commands.
2. Replies on each client connection are delivered in the order the commands arrived on that
   connection. RESP requires this.
3. Commands from the same operation keep their order.
4. Exactly one gated command is in flight to the store at a time. Because Valkey executes
   commands one at a time, the store's execution order is the proxy's decision order.

Under these rules every schedule the proxy produces is one that ordinary network delay could
produce. A violation found this way is a reachable behavior of the real system.

### 5.3 Decision points and quiescence

The executor admits the concurrent operations one at a time. It invokes the next one only after
the previous has either reached its first gated command (held at the proxy) or returned. This
gives each command an owner. After that:

- A **decision point** occurs when the system is quiescent: every live operation has a held gated
  command or has returned. The scheduler then picks one held command to execute.
- If quiescence is not reached within `Δq` (default 50 ms **[UNVERIFIED value]**), the scheduler
  decides anyway and records a `forced` decision. Executions with forced decisions are flagged
  timing-dependent, and their replay rate is reported separately.
- Holding time per command is capped well below client timeouts (StackExchange.Redis defaults to
  seconds **[UNVERIFIED]**), so held commands never trigger client-side failure paths.

### 5.4 Multiplexed clients (the #3824 case)

StackExchange.Redis and ioredis send all of a process's commands over one connection. Rule 2
then means a held command at the head of that connection delays replies to everything behind it.
The scheduler handles this by separating **execution order** (free across operations) from
**reply delivery** (FIFO per connection). Example for two concurrent `AddItem(u1, …)` calls,
A arriving first:

| Step | Decision | Store effect |
|---|---|---|
| 1 | execute `HGET u1 cart` (A); deliver A's reply | A reads q₀ |
| 2 | A sends `HSET` (now behind B's `HGET` on the connection) | — |
| 3 | execute `HGET u1 cart` (B) before A's `HSET` | B reads q₀: lost-update path |
| 4 | execute A's `HSET`, then B's `HSET`; deliver replies in arrival order | final q₀+1, not q₀+2 |

Attribution after step 1 uses admission order plus command content. When two operations send
byte-identical commands, they are interchangeable for the store, so either labeling is valid.
Whether this is robust on the real cart is **the** Phase 1 Day-2 experiment (gate G1).

### 5.5 Scheduling policies (same interface for all strategies)

| Policy | Behavior at a decision point |
|---|---|
| `passthrough` | No gating (used for setup, observation, serial runs, and the Stress baseline). |
| `fifo` | Oldest held command first. |
| `random(seed)` | Uniform over held commands. |
| `pct(seed, d)` | PCT priorities with d−1 change points over the estimated step count. |
| `exhaustive(prefix)` | Depth-first enumeration of all decision sequences (small workloads only). |
| `hint(steps) → exhaustive` | Follow the model's suggested order where it matches held commands, then enumerate the rest. Hint adherence is recorded. |
| `replay(decisions)` | Follow a recorded decision list exactly; fail loudly on divergence. |

### 5.6 Trace record (JSON Lines) [provisional]

```json
{"seq": 17, "t_ns": 123456789, "event": "exec", "op": 1, "conn": 3,
 "cmd": "HSET", "key_hash": "9f2c…", "args_digest": "sha256:…",
 "reply_digest": "sha256:…", "decision": {"kind": "chosen", "among": [0, 1], "policy": "pct"}}
```

Keys and values are hashed or truncated in traces and reports. Raw values exist only in run
directories, which are git-ignored.

## 6. Oracle

### 6.1 History semantics (adopted from Jepsen)

Each operation is recorded as `invoke` then one of `ok`, `fail`, or `info`:
- `ok`: completed, with a result.
- `fail`: the service returned a definite error. **A failed operation must have no effect.**
- `info`: indeterminate (timeout, transport error). It may or may not have taken effect.

### 6.2 Serial-equivalence check (spec-free)

Given the setup state, the set `S` of `ok` operations, and the set `I` of `info` operations:

1. For every subset `I' ⊆ I` and every permutation of `S ∪ I'` (|S ∪ I'| ≤ 4, so ≤ 24
   permutations per subset), run the operations **serially** through the proxy in pass-through
   mode from a fresh reset with the same setup. Record each operation's result and the
   observation.
2. Run every serial permutation **twice**. Fields that differ between two identical serial runs
   are volatile (IDs, timestamps). Mask them, together with any `volatile_masks` from the target
   spec. If a serial run is non-deterministic outside masked fields, the result is
   `INCONCLUSIVE`.
3. The concurrent run **passes** if its masked outcome (results of the `ok` operations plus the
   observation) equals some serial outcome. Otherwise it is a **VIOLATION: non-serializable
   outcome**.

All operations in a round are invoked before any returns, so their intervals overlap and any
serial order is a legal linearization. Serializability and linearizability coincide here, and
no sequential model has to be written (the idea behind Line-Up and Lincheck's default oracle).

### 6.3 What a violation does and does not mean

A violation proves the service produced an outcome that **no serial order of the same requests
produces**. It does not by itself prove the API promised serializability. For #3824, the outcome
"two successful `AddItem(+1)` calls leave quantity 1" is a user-visible lost item, which the issue
reports as a bug. Reports therefore say "non-serializable outcome", and the human decides
whether the contract was violated. Only replay-confirmed violations are labeled `verified`.

### 6.4 Model-proposed invariants (P1)

The model may propose invariants from a fixed template grammar (no code), for example
`non_negative(path)`, `equals(path, const)`, `sum_equals(paths, const)`, `count_equals(path, n)`.
An invariant is accepted only if it holds on **every** serial execution of the workload, which
automatically rejects invariants the model invented incorrectly. Violations of accepted
invariants are still labeled `candidate` until a human confirms them.

## 7. Strategy interface

```python
class Strategy(Protocol):                       # provisional
    name: str
    def next_experiment(self, state: SearchState) -> Experiment | None: ...
    def observe(self, result: ExperimentResult) -> None: ...

@dataclass(frozen=True)
class Experiment:
    workload: Workload            # setup: list[OpCall]; concurrent: list[OpCall] (2..4)
    policy: SchedulePolicy        # one of §5.5
    max_schedules: int            # executions this experiment may consume
```

Every strategy uses the same catalog, value domains, executor, oracle, and budget accounting.
Only workload choice and policy differ. This is what makes the comparison in
`EVALUATION_PLAN.md` attributable.

## 8. Meta model integration

### 8.1 Calls

| Call | When | Input | Output | Verified by |
|---|---|---|---|---|
| `plan` | Start of a Muse trial, then after each batch of results | System rules; catalog; value domains; allow-listed source as delimited untrusted data; structured feedback from previous experiments | `PlannerOutput`: ≤ 5 hypotheses, ≤ 4 experiments | Plan validator (C4); then execution and the oracle |
| `explain` (P1) | After a violation is verified and minimized | Minimized trace (digests + command names + operation labels), serial outcomes vs observed, source | `Explanation`: summary, ordered steps with `{path, line}` references, root-cause kind, fix direction | Reference checker: file exists, line is in range, line is inside the operation's handler. Output labeled "model explanation" |
| `invariants` (P1) | Optional | Catalog, source, serial outcomes | Template invariants | Must hold on all serial runs (§6.4) |

### 8.2 Model configuration (provisional, checked in the Day-1 smoke test)

- Model `muse-spark-1.3`, Standard mode (not Contributor). Base URL `https://api.meta.ai/v1`,
  key from the host `MODEL_API_KEY` environment variable.
- Structured output with `strict: true` via the Responses API `text.format` or Chat Completions
  `response_format: {type: "json_schema"}`. Both are documented; the smoke test picks one.
- `reasoning_effort: medium` by default; `low` and `high` as a cost ablation.
- Temperature left at the documented default (1.0). `seed` is not relied on (deprecated,
  best-effort).
- `store: false` on the Responses API **[UNVERIFIED that the field is honored]**.
- Streaming or background mode for long calls (the docs warn of 504s on long non-streaming
  requests).

### 8.3 Schema design rules (from Meta's documented limits)

- Root is a plain object with `additionalProperties: false` and every property `required`.
  Optional values are represented as nullable types **[UNVERIFIED that `["string","null"]` is
  accepted]**.
- No recursion and nesting ≤ 10. Traces and graphs are sent as flat lists with integer ids.
- The schema is **generated from the catalog** for each target: `op` is an `enum` of catalog
  operation names, and `args` is an object holding the union of all argument names, each
  nullable. Per-operation argument checks happen in the validator.
- `$ref` is avoided (inlined) until verified.

Provisional `PlannerOutput` for the cart catalog (abridged):

```json
{
  "type": "object", "additionalProperties": false,
  "required": ["hypotheses", "experiments"],
  "properties": {
    "hypotheses": { "type": "array", "items": {
      "type": "object", "additionalProperties": false,
      "required": ["id", "kind", "state_key_pattern", "operations", "code_refs", "rationale"],
      "properties": {
        "id": { "type": "string" },
        "kind": { "enum": ["lost_update", "check_then_act", "atomicity_violation",
                           "order_violation", "stale_read", "other"] },
        "state_key_pattern": { "type": "string" },
        "operations": { "type": "array", "items": { "enum": ["AddItem", "GetCart", "EmptyCart"] } },
        "code_refs": { "type": "array", "items": {
          "type": "object", "additionalProperties": false, "required": ["path", "line"],
          "properties": { "path": { "type": "string" }, "line": { "type": "integer" } } } },
        "rationale": { "type": "string" } } } },
    "experiments": { "type": "array", "items": {
      "type": "object", "additionalProperties": false,
      "required": ["hypothesis_id", "setup", "concurrent", "schedule_hint", "expected_effect"],
      "properties": {
        "hypothesis_id": { "type": "string" },
        "setup":      { "type": "array", "items": { "$comment": "OpCall, inlined" } },
        "concurrent": { "type": "array", "items": { "$comment": "OpCall, inlined" } },
        "schedule_hint": { "type": "array", "items": {
          "type": "object", "additionalProperties": false, "required": ["op_index", "command"],
          "properties": { "op_index": { "type": "integer" },
                          "command": { "enum": ["GET", "SET", "HGET", "HSET", "EXPIRE", "PEXPIRE", "OTHER"] } } } },
        "expected_effect": { "type": "string" } } } }
  }
}
```

`OpCall` = `{ "op": enum(catalog), "args": { "user_id": string|null, "product_id": string|null,
"quantity": integer|null } }`. Length limits (`maxItems`, `maxLength`) are enforced locally
whether or not the API honors them.

### 8.4 Prompt-injection posture

Source code is placed in clearly delimited blocks and described as untrusted data. That wording
is a quality measure, **not a security control**. Security comes from the output side: the model
can only emit a validated choice among catalog operations, and nothing it emits reaches a shell,
path, image name, or verdict (`THREAT_MODEL.md`, T1–T3, T13).

### 8.5 Record and replay of model I/O

Every request and response is logged to the run directory with the prompt-template hash, model
ID, parameters, token counts, and latency. A Muse trial can be re-executed from its recorded
plans without calling the API. The demo uses this as a fallback when the API is unavailable, and
says so on screen.

## 9. Execution environment

- Docker Compose project per target on an `internal: true` network: service, proxy, store.
  The harness reaches the service through one published port bound to `127.0.0.1`.
- Hardened flags from `THREAT_MODEL.md` §6 on every container that tolerates them.
- Reset between executions: `FLUSHALL` sent to Valkey on a proxy-owned admin connection, then
  the target's warm-up (the cart writes a test key on first connect). Services must not cache
  state across requests. A per-target check runs a serial workload twice and compares outcomes.
- Images pinned by digest; Compose files live in `targets/`; third-party source is fetched by
  pinned commit into `targets/checkouts/` (git-ignored) only when the model needs to read it.

## 10. Planned repository layout (Phase 1+)

| Path | Contents | Rule |
|---|---|---|
| `docs/` | Phase 0 documents, updated as decisions change | Documentation only |
| `schemas/` | JSON Schemas: planner, explanation, trace, replay, results | Versioned with the prompt |
| `src/mylonite/` | proxy, scheduler, executor, oracle, strategies, planner, report | Application code |
| `targets/` | Target specs and Compose files; never vendored third-party source | Reviewed config |
| `fixtures/dev/` | Development fixture services (ours) | Used for tuning |
| `experiments/` | Throwaway spikes, each with a dated README and a result line | Never imported by `src/` |
| `eval/` | Evaluation configs and the pre-registered analysis script | Frozen before held-out runs |
| `results/published/` | Curated results committed deliberately | Raw runs stay git-ignored |

Held-out benchmark services are **not** stored in this repository until the held-out evaluation
finishes. Their hash is committed beforehand (see `EVALUATION_PLAN.md` §5).

## 11. Known weaknesses of this design

1. Determinism is empirical. Forced decisions and multiplexed-connection attribution can make
   replays diverge. We measure and report this rather than assume it.
2. The serial-reference cost grows with `|S|!`. The ≤ 4 concurrent-operation cap keeps it at ≤ 24
   serial runs per subset, and results are cached per workload.
3. Observation through the service API can hide store-level anomalies the API does not expose.
   A raw store snapshot is a P1 addition.
4. The catalog is human-made. A wrong catalog can make every strategy miss a bug equally. This
   does not bias the comparison, but it limits recall.
5. Services with internal background work (timers, consumers) can break quiescence detection.
   Such targets are out of scope for P0.
