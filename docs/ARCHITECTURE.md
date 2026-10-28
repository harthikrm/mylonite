# Architecture

Status: **Approved direction (2026-10-28, D-004 amended by D-018).** This specifies Option B from
`ARCHITECTURE_OPTIONS.md` with the Phase 0 review corrections. Items tagged **[UNVERIFIED]**
depend on behavior we have read about but not yet executed; each is checked by a named Phase 1
experiment.

## 1. One-paragraph summary

Mylonite tests a service that keeps shared state in Valkey/Redis. A small proxy sits between the
unmodified service and the store and decides when each data command reaches the store. It only
delays commands and never reorders commands within a connection. A harness sends a chosen set of
concurrent requests to the service, records what each request returned, and reads the final
state through the service's own API. A deterministic oracle checks the outcome against the
target's **owner-approved contract**: its expected-state invariants, and serial equivalence for
operations the contract declares atomic. A violation counts only once its recorded schedule
replays 20/20 in fresh environments. Muse Spark reads the service's source to draft the operation
catalog and candidate contract clauses for human approval. It proposes which requests to race,
with which arguments and setup, and explains verified traces. The model never writes code that
runs and never decides a verdict.

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
| C1 | Target spec + catalog loader | Loads a human-approved YAML: compose file reference with pinned image digests, store endpoint, operation catalog (name, transport, argument types, example values), observation operations, the **contract** (§6.1), allow-listed source globs. | Yes |
| C2 | Context builder | Reads only allow-listed source files, runs the secret deny-list and pattern scan, applies byte caps, and wraps the files as delimited untrusted data. | Yes |
| C3 | Muse planner | One structured-output call: hypotheses + experiments. | **No** (model) |
| C4 | Plan validator | JSON Schema check, catalog membership, argument type checks, clamps (≤ 6 setup, 2–4 concurrent ops, ≤ 16 hint steps), dedup against already-run workloads. | Yes |
| C5 | Strategies | Produce experiments: Stress, Random, PCT, Conflict-directed systematic, Muse, plus ablations. Common interface (§7). | Seeded |
| C6 | Executor | Runs **inside the sandbox network**. Resets state, runs setup sequentially, admits the concurrent round under the scheduler, runs observations, and collects a Jepsen-style history. Takes an experiment as JSON on stdin and writes size-capped JSON results to stdout. | Yes, given a schedule |
| C7 | Proxy + scheduler | Frames RESP, gates data commands, keeps per-connection order, chooses admissions and cross-connection order at decision points, records the trace, and runs the soundness checker (§5). | Yes, given a schedule |
| C8 | Serial-reference engine | Runs real-time-consistent serial orders for the contract's atomic groups, each twice (§6.3). | Yes |
| C9 | Oracle | Contract invariants plus serial equivalence on declared fields → `PASS`, `VIOLATION(clause)`, `OBSERVATION`, or `INCONCLUSIVE` (§6). | Yes |
| C10 | Replay verifier | Re-runs the recorded decision list 20 times from fresh resets and checks trace hashes. For targets with a corrected version, explores the same workload exhaustively on it (§6.4). | Yes |
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
  # At tag 3.1.0 the demo's .env says IMAGE_VERSION=3.0.0, so prebuilt images are not proven
  # to match this source. Proposed (PHASE0_REVIEW.md A6): build cart from source at the commit.
  cart: build-from-source@dedc0178918e260823323b8d95005a8cb924b007
  valkey: ghcr.io/valkey-io/valkey:9.0.4-alpine3.23   # per .env at tag 3.1.0 (9.1.2 is main)
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

Corrected on 2026-10-28 (`PHASE0_REVIEW.md` R1/R1b, accepted as D-018/A1). The Phase 0 version
allowed out-of-order execution within one connection; that is removed.

### 5.1 What is scheduled

- **Gated commands:** data commands on keys, for example `GET SET HGET HSET HDEL HINCRBY INCR
  INCRBY DECR DEL EXPIRE PEXPIRE SETNX GETSET LPUSH RPOP SADD SREM ZADD`.
- **Blocks:** `MULTI…EXEC/DISCARD`, `WATCH…EXEC/DISCARD/UNWATCH`, and `EVAL/EVALSHA/FCALL` are
  each scheduled as one unit on their connection.
- **Pass-through:** connection and admin commands (`PING ECHO AUTH CLIENT INFO CONFIG CLUSTER
  SELECT COMMAND`) are never held *by policy*. They still wait behind any held command ahead of
  them on the same connection, because per-connection order is never broken.
- Connections that enter pub/sub mode switch to raw pass-through.
- RESP3 is framed and passed through. redis-py 8.1 negotiates RESP3 (`HELLO 3`) by default and
  fails instead of falling back when refused (observed 2026-10-28, D-019). RESP3 push frames are
  forwarded to the client and never treated as replies.
- Unknown commands are passed through and reported.
- Framing uses a small, framing-only RESP2/RESP3 parser that forwards the original bytes
  unchanged (`src/mylonite/resp.py`, unit-tested).

### 5.2 Ordering rules

1. Never drop, rewrite, duplicate, or invent commands.
2. **Per connection**, commands execute in arrival order and replies return in arrival order. The
   scheduler can only *delay* the head of a connection's queue.
3. **Across connections**, the scheduler chooses freely which connection's head executes next.
   TCP connections are independent, so network delay alone can produce any cross-connection
   order.
4. One gated command (or block) is in flight to the store at a time. Valkey executes commands
   one at a time, so store execution order equals decision order. Q-E7 checks this still holds
   with Valkey's I/O threads.
5. **Admission is a decision.** When each operation's request is issued is chosen by the
   scheduler and enumerated by `exhaustive`.

Consequence: every schedule the proxy produces is reachable by ordinary network delay, so a
violation is a real behavior. The converse does not hold. On a multiplexed client, where all
operations share one connection, reality can also produce orders that come from in-process thread
timing on that connection. The proxy cannot produce those. That is a **false-negative** risk, and
reports state it.

A **soundness checker** runs on every trace. It verifies that per-connection order was preserved,
that at most one gated command was in flight, and that nothing executed before it arrived. A trace
that fails is discarded and counted as a harness error.

### 5.3 Operation states, decision points, timeouts

Each operation of the concurrent round is in one of these states:
- `pending`: not yet admitted.
- `running`: admitted and computing inside the service, with no command queued at the proxy.
- `held`: has a gated command queued at the proxy.
- `reply-pending`: its command executed, but the reply is waiting behind an earlier command on
  the same connection. This only arises with pipelining inside one operation.
- `done`: returned `ok`, `fail`, or `info`.

A **decision point** occurs when no operation is `running`. The choices are:
1. admit a `pending` operation, or
2. execute the head command of a connection whose head belongs to a `held` operation.

After each decision the scheduler waits until no operation is `running` again.

**Attribution.** Each decision lets at most one operation run, so any new command belongs to that
operation. This holds on a shared connection too, because execution is strictly FIFO and the
executed head's reply is delivered immediately. Per-connection clients are also attributed by
connection, which acts as a cross-check.

**Timeouts.** If no operation is `running`, nothing can make progress without a decision. If an
operation stays `running` longer than `Δq`, the scheduler records a `forced` decision and
continues. The default `Δq` is measured on Day 1 (Q-E6). Forced decisions mark the execution
timing-dependent. Held commands are capped well below client timeouts. Admission has the same
timeout, so an operation blocked on an in-process lock cannot deadlock the run.

### 5.4 Multiplexed clients (the #3824 case) under the corrected rules

A and B are both `AddItem(u1, p1, 1)` on the cart's single shared connection.

| Decision | Connection queue after | Store effect |
|---|---|---|
| admit A | `[HGET_A]` | — |
| admit B | `[HGET_A, HGET_B]` | — |
| execute head `HGET_A` | `[HGET_B, HSET_A]` (A ran and sent HSET) | A reads q₀ |
| execute head `HGET_B` | `[HSET_A, HSET_B]` | B reads q₀: lost-update path |
| execute `HSET_A`, then A's `EXPIRE`, then `HSET_B`, … | — | final q₀+1, not q₀+2 |

The serial order comes from a different admission choice: admit A, then execute all of A's
commands, then admit B. No reordering within the connection is needed for either outcome.

### 5.5 Scheduling policies (same interface for all strategies)

| Policy | Behavior at a decision point |
|---|---|
| `passthrough` | No gating. Used for setup, observation, serial runs, and the Stress baseline, which runs in record mode. |
| `fifo` | Admit everything first, then execute in arrival order. |
| `random(seed)` | Uniform over the available choices. |
| `pct(seed, d)` | PCT priorities with d−1 change points. |
| `exhaustive` | Depth-first enumeration of every decision sequence, admissions included. P1: sleep-set reduction for adjacent commands on different keys, applied identically to every method. |
| `hint(steps) → exhaustive` | Follow the model's suggested order where it is a legal choice, then enumerate the rest. Hint adherence is recorded. |
| `replay(decisions)` | Follow a recorded decision list exactly; fail loudly on divergence. |

### 5.6 Trace record (JSON Lines) [provisional]

```json
{"seq": 17, "event": "exec", "op": 1, "conn": 3, "cmd": "HSET", "key_hash": "9f2c…",
 "args_digest": "sha256:…", "reply_digest": "sha256:…",
 "decision": {"kind": "chosen", "choices": ["admit:2", "exec:conn3"], "policy": "random"}}
```

Keys and values are hashed or truncated in traces and reports. Raw values exist only in run
directories, which are git-ignored. The trace hash covers decisions, attributions, commands, and
digests, and excludes timestamps.

## 6. Oracle

Corrected on 2026-10-28 (`PHASE0_REVIEW.md` R2–R4, accepted as D-018/A2). The Phase 0 version
imposed serializability on every target and treated errors as "no effect". Both are removed.

### 6.1 The contract comes first

Every target spec carries a `contract` block. The owner approves it, and each clause cites its
source: API documentation, a docstring, an issue, or, for our fixtures, our own specification.

```yaml
contract:
  source: "fixture spec: 'every successful increment is counted' (fixtures/dev/d2_counter)"
  observed_fields: [counter]            # only these are compared
  invariants:                           # primary oracle: the expected-state check
    - id: no_lost_increment
      kind: counter_conserved           # final == initial + sum(amount of ok increments)
      key: counter
      op: increment
      amount_arg: by
  atomic_groups: []                     # operations that must be serializable together
  allowed_anomalies: []                 # e.g. last_writer_wins on a field
  status_semantics:                     # which non-OK statuses mean "no effect"
    increment: { no_effect: [] }        # empty → every error is `info`
```

Invariants use a fixed set of kinds, interpreted by our code, with no expressions. The initial
kinds are `counter_conserved`, `sum_conserved` (over several keys), `non_negative`,
`at_most(n)` (for quotas and stock), `member_preserved` (an added item is in the final
collection), and `state_machine` (allowed transitions). New kinds are added as code with tests,
never from model text.

Muse may **draft** clauses with citations to source lines (§8.1). A human approves or edits every
clause before it is used; drafts are never used unapproved.

### 6.2 History semantics

Each operation is recorded as `invoke` followed by `ok`, `fail`, or `info`. **Any non-OK status
is `info`** (it may or may not have taken effect) unless the contract's `status_semantics`
declares it `no_effect` for that operation. This matters for the cart, which turns every
exception into `FailedPrecondition`, even after a write succeeded.

### 6.3 Checks

1. **Invariants** are evaluated on the observation over the `ok` operations. For `info`
   operations, the check passes if *some* subset of them having taken effect satisfies it.
2. **Serial equivalence**, for `atomic_groups` only, on `observed_fields` only. The observed
   values are compared with every serial order of the group's `ok` operations, plus each subset
   of its `info` operations.
   - Only orders consistent with real-time order count: if X returned before Y was invoked, X
     comes first.
   - Serial runs go through the proxy in pass-through from a fresh reset, are cached per
     workload, and their cost is reported separately and identically for every method.
3. Fields that differ between two identical serial runs trigger a **warning** that the contract's
   `observed_fields` may include a volatile field. They are never silently masked.

**Verdicts:**
- `PASS`.
- `VIOLATION(clause)`: a named contract clause failed.
- `OBSERVATION`: the outcome matches no serial order, but no clause covers it. Reported, never
  called a bug.
- `INCONCLUSIVE`: timeouts, harness errors, or soundness-check failures.

### 6.4 Verified

A `VIOLATION` is **verified** when both hold:
- Its decision list replays **20 out of 20** times from fresh resets with identical trace hashes.
  Anything less is reported as "reproducible k/20".
- If the target has a corrected version, the **same workload explored exhaustively** on the
  corrected version produces no `VIOLATION`. Decision lists are not reused across code versions,
  because they diverge.

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
| `draft_spec` | Once per new target, before any search | Allow-listed source, proto/OpenAPI files | Draft operation catalog, setup recipes, and contract clauses (§6.1 kinds only), each citing `{path, line}` | Reference checker; **human approval of every clause**; clauses must hold on all serial runs. Metric: fraction accepted unchanged. |

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

- Root is a plain object (no top-level `anyOf`/`oneOf`/`allOf`/`enum`/`not`), every object has
  `additionalProperties: false`, and `required` lists every key. `allOf`/`oneOf` are banned
  everywhere; `anyOf` is allowed below the root, so optional values are written as
  `anyOf: [{...}, {"type": "null"}]`. (Verified in the docs 2026-10-28; nullable form still to be
  exercised in the smoke test.)
- No recursion and nesting ≤ 10. Traces and graphs are sent as flat lists with integer ids.
- The schema is **generated from the catalog** for each target: `op` is an `enum` of catalog
  operation names, the hint `command` enum is generated from the commands observed for that
  target, and `args` is an object holding the union of all argument names, each nullable.
  Per-operation argument checks happen in the validator.
- Non-recursive `$ref`/`$defs` are allowed (≤ 200,000 nodes after inlining).
  `minItems`/`maxItems`/`maxLength`/`pattern` are not documented, so they are enforced locally.
- Responses API: `text.format`; Chat Completions: `response_format`. Sending `response_format`
  to the Responses API returns 400.

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

- One `internal: true` network per target holding the service, the store, and the **executor
  container**, which runs the proxy, scheduler, executor, and oracle. Nothing on that network has
  egress or a published port.
- The host orchestrator is the only process with internet access and the API key. It starts the
  executor with `docker run -i`, writes the experiment JSON to its stdin, and reads size-capped
  JSON results from its stdout. Our source is mounted read-only; nothing else from the host is
  mounted.
- Hardened flags from `THREAT_MODEL.md` §6 on every container. A Compose lint rejects
  `privileged`, `network_mode: host`, `cap_add`, `docker.sock`, and writable bind mounts.
  Any per-image exception is recorded in `DECISIONS.md`.
- Images are built from source at the pinned commit in a builder container (network at build
  time only), or pulled by digest for upstream infrastructure images such as Valkey.
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

1. Determinism is empirical. Forced decisions can make replays diverge. We measure and report
   this rather than assume it.
2. Multiplexed clients make some real schedules unreachable (§5.2), so false negatives are
   possible. False positives from the control mechanism are excluded by the ordering rules and the
   soundness checker.
3. The serial-reference cost grows with `|S|!`. The ≤ 4 concurrent-operation cap keeps it at ≤ 24
   serial runs per subset, and results are cached per workload.
4. Contracts are human-approved. A missing clause means a real anomaly is reported only as an
   `OBSERVATION`; a wrong clause would mislabel designed behavior. Weak-contract controls exist to
   catch the second case.
5. Observation through the service API can hide store-level anomalies the API does not expose.
   A raw store snapshot is a P1 addition.
6. The catalog is human-made. A wrong catalog can make every strategy miss a bug equally. This
   does not bias the comparison, but it limits recall.
7. Services with internal background work (timers, consumers) can break quiescence detection.
   Such targets are out of scope for P0.
