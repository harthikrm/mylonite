# The Problem

## 1. The failure in one sentence

Each request handler is correct on its own, but two requests that run at the same time
read the same shared state, compute independently, and write back. The result is an outcome
that no one-at-a-time order of those requests could produce.

No exception is thrown, nothing is logged, and no test fails. Tests run requests one at a time,
and memory-level race detectors see no data race, because the "shared memory" is a key in
Redis/Valkey or a row in a database, reached over a socket.

## 2. Concrete failure modes in scope

| Pattern | Store-level shape | User-visible effect |
|---|---|---|
| **Lost update** | `GET`/`HGET` → compute → `SET`/`HSET` on the same key | An increment, cart item, or profile change disappears. |
| **Check-then-act** | Read a guard (stock, quota, coupon used, balance) → write in a separate step | Overselling, a coupon redeemed twice, quota exceeded, negative balance. |
| **Destructive overwrite** | An unconditional write (e.g. "reset to empty") interleaves with a read-modify-write | Data written between the read and the reset is silently discarded. |
| **Non-atomic multi-key update** | Debit key A, then credit key B, in separate commands | Totals not conserved; readers see money missing in between, or forever if a step is lost. |
| **Unsafe lock built from store commands** | `SETNX` lock released with a plain `DEL`, or `GET`-then-`SET` locking | Two holders in the critical section. |
| **Invalid state transition** | Guarded transition (`PAID → SHIPPED`) races another (`PAID → CANCELLED`) | An order both shipped and cancelled. |

These map onto the classic categories: Lu et al. (ASPLOS 2008) found 97% of non-deadlock
concurrency bugs are atomicity or order violations, and 96% involve at most two threads. The
store-mediated versions are what ACIDRain (SIGMOD 2017) found in deployed e-commerce software.
Sources: `PRIOR_ART.md` §2.4.

Out of scope for now: in-process data races, deadlocks, crash and partition faults, SQL isolation
anomalies inside the database engine. `ARCHITECTURE.md` §2 says why.

## 3. A real instance: OpenTelemetry Demo #3824

Source: https://github.com/open-telemetry/opentelemetry-demo/issues/3824 (opened 2026-08-10, open,
unlabeled, no maintainer response). Code read at tag `3.1.0` (`dedc0178…`) and `main`
(`8f640ded…`, 2026-10-27) via the GitHub API. **Not executed yet.**

The demo's cart service (C#, .NET 10, ASP.NET Core gRPC, StackExchange.Redis; Valkey
`9.0.4-alpine3.23` per the `.env` at tag `3.1.0`, 9.1.2 on `main`) stores each user's cart as one serialized protobuf blob in a Valkey hash field. In
`src/cart/src/cartstore/ValkeyCartStore.cs` at `3.1.0`:

- `AddItemAsync` does `HashGetAsync(userId, "cart")` (line 140), parses the blob, adds the item or
  increments its quantity in memory, then writes the whole blob back with `HashSetAsync`
  (line 165), then `KeyExpireAsync` (line 166). There is no `WATCH/MULTI`, Lua script, or version
  check. The `_locker` only guards connection setup.
- `EmptyCartAsync` overwrites the field with an empty cart unconditionally (line 187).
- The checkout service (Go) reads the cart in `PlaceOrder`, charges the card, ships, and only then
  calls `EmptyCart`.

Two failures follow:
- **Scenario A (lost update).** Two concurrent `AddItem(user, product, 1)` calls both read
  quantity 0 and both write quantity 1. Any serial order gives 2.
- **Scenario B (destructive overwrite).** An `AddItem` that lands between checkout's `GetCart` and
  `EmptyCart` is neither in the placed order nor in the cart afterwards. In every serial order
  the item ends up in one or the other.

Status: fix PR #3825, which added optimistic concurrency, was closed as stale on 2026-09-17
without being merged. PR #3988 re-enabled cart tests against an in-memory store with no
concurrency test. The racy code is present in releases 3.0.0 and 3.1.0 and on `main`. The
issue's grpcurl reproduction uses port 5070, but the demo's `.env` sets `CART_PORT=7070`, and
the cart registers no gRPC reflection service. The published commands need adjusting before they
run. Details: `RESEARCH_LOG.md` 2026-10-27.

Why this matters as an example:
- It is a well-known, widely deployed reference application, and the bug sat unfixed for 2.5
  months after a complete report and fix.
- The existing tests cannot catch it: they use an in-memory store and run requests one at a time.
- The service is C#. A tool that only controls Python, Go, or JVM threads cannot touch it
  unmodified.
- Reproduction is "intermittent" by the reporter's own account, which is exactly the gap
  between knowing a bug exists and proving it.

What it is **not**: a discovery. It is public, with root cause and fix, and may be in the model's
training data. We use it as the development target and the demo's real-world anchor, and make
no discovery claim (`EVALUATION_PLAN.md` §5).

## 4. Who has this problem

**Primary user: a backend engineer on a team whose services keep shared state in Redis/Valkey.**
Carts, sessions, rate limiters, inventory and reservation counters, feature quotas, idempotency
keys, leaderboards, and job locks are typical. They usually learn about a race from a customer
complaint or a data-reconciliation discrepancy, not from a test.

Secondary users:
- A reviewer of a pull request that touches shared state ("does this fix actually close the
  race?"). Re-running a recorded counterexample against the fix answers that.
- An SRE investigating "impossible" data, who needs a deterministic reproduction to hand to a
  developer.
- Maintainers of open-source reference applications, like the OTel demo, who receive race
  reports they cannot easily confirm.

Intended workflow (target for Phase 1, simplified):
1. Describe the service once: a Compose file plus a target spec listing its operations. This is
   generated from `.proto` or OpenAPI files where possible and reviewed by a human.
2. Run Mylonite locally. It brings up the service against a fresh Valkey behind the proxy.
3. Get back either "no non-serializable outcome found within budget X" with the coverage
   achieved, or a **verified counterexample**: the requests, the store command order, the
   observed outcome vs every serial outcome, a replay file, and a model-written explanation
   labeled as such.
4. Fix the code and re-run the replay file. It becomes a regression test.

## 5. Why it is expensive

We have **no measured cost data** of our own; claims here are qualitative and sourced.
- **Bugs are silent and hard to reproduce.** CHESS found 21 bugs that had never surfaced in months
  of stress testing. PCT's per-run detection probability for a Pbzip2 bug was 0.701 against 0 for
  stress across a million runs. Engineers lose time on bugs they cannot reproduce. (`PRIOR_ART.md`
  §2.1)
- **They touch money and inventory.** ACIDRain verified 22 concurrency attacks in 12 e-commerce
  applications deployed on more than 2M sites. The specific attack types (e.g., overspending
  gift cards or reusing vouchers) are recalled by the team [K] and were not re-verified in
  Phase 0.
- **Store-mediated races escape existing tools.** TSan and `-race` cannot see them, and unit tests
  run one request at a time. Load tests show symptoms without a reproducible cause or an oracle.
- **Fixes are hard to validate.** Without a deterministic counterexample, a proposed fix like
  #3825 is reviewed on reading alone. #3825 was closed as stale with its substance never
  discussed.

What would make the economic case convincing, and is not yet established: frequency data for
store-mediated races in production incident reports, and time-to-reproduce figures from real
teams. Both are open questions (`OPEN_QUESTIONS.md` Q-P1, Q-P2).

## 6. What a solution must do (requirements derived from the above)

1. Work on **unmodified services in any language**, because the shared state is outside the
   process.
2. **Prove** a failure, not suspect one: an outcome no serial order produces, reproduced on
   replay.
3. Need **no written specification**. Teams do not have one.
4. Produce a **minimal, replayable counterexample** usable as a regression test.
5. Choose **which requests to race** without a human enumerating them. This is where model
   guidance might matter, and it has to be measured against a non-LLM baseline before it is
   claimed.
6. Be **safe** to run on untrusted code (`THREAT_MODEL.md`).
