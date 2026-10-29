# THREAT_MODEL.md §8 for running the third-party cart without a model (2026-10-29)

**Scope.** What must hold before D1 runs again: third-party code (the OTel cart, built from
source) executes in the sandbox, and **no model is called**. The items that only matter when a
model is called stay open for any Muse run on third-party code. Recorded as D-032.

**Evidence.**
- `sandbox_check.py`, run at the pre-registration commit. Its report is copied to
  `results/<ts>/pre_run/`.
- `tests/test_sandbox.py`.
- The commands quoted below.

**The gate ran the cart on 2026-10-28 before this record existed**, against the threat model's
own rule. Nothing found here shows that run was unsafe, but the order was wrong.

| # | Item (abridged) | Status for this run | Evidence |
|---|---|---|---|
| 1 | Planner output validated against a strict schema | **N/A here** (no model). Built for M4 (pilot) | `tests/test_core.py` `PlannerSchemaTest`, `ValidatorRobustnessTest` |
| 2 | Operation names and argument values checked against the catalog | **Met** for every method | `space.workload_problems`; V4 checks every executed workload |
| 3 | No `eval`, `exec` or dynamic import in the oracle path | **Met** | `grep` over `src/`: the one dynamic import is `executor.Context`, which loads the adapter module named in the reviewed target spec, never model text |
| 4 | No model text to a shell, subprocess argument, path, image, SQL or address | **N/A here**. The subprocess calls are `docker` argument lists (no shell), built from code constants and the reviewed target spec | `grep` over `src/` |
| 5 | Static, reviewed flag set, asserted by a unit test | **Met** (test added today) | `tests/test_sandbox.py` |
| 6 | No egress, shown by an in-sandbox probe that must fail | **Met** | Every executor start (`egress_probe`); fixture `filesystem.egress_tcp` |
| 7 | Non-root, read-only root filesystem, all capabilities dropped | **Met** for Valkey, the executor and both carts, as Docker applied them | `inspection.pass` |
| 8 | CPU, memory, pids, tmpfs and wall-clock limits; fork-bomb and infinite-loop fixtures contained | **Met for containment.** Partly met for "recorded as inconclusive". See the note below | `containment` |
| 9 | No host mounts except a read-only target copy; Docker socket and `$HOME` never mounted | **Met with a deviation.** The carts and Valkey have no mounts. The executor has two read-only binds, our own `src/` and `fixtures/` (not the target, not `$HOME`, not `.env`) | `inspection.containers.*.mounts` |
| 10 | API key never in logs, reports, prompts or the sandbox environment (canary test) | **Met for the sandbox:** a canary `MODEL_API_KEY` set in the host process reached no container's environment or logs. Prompts: N/A here | `inspection.pass.canary_absent` |
| 11 | Deny-list and secret scan before every API call; planted canary blocked | **N/A here.** Built for M4 | `tests/test_contamination.py` |
| 12 | Meta API data-use and retention terms recorded | **Met** (Phase 0) | `docs/HACKATHON_COMPLIANCE.md` |
| 13 | Dependencies pinned with hashes; base images by digest | **Partly met.** Python: hash-locked. Base images and Valkey: by digest. **Open: the cart's NuGet packages are pinned by version only** (upstream has no lock file) | `docker/requirements-d1.lock`, `targets/d1-otel-cart/Dockerfile` |
| 14 | Result parser rejects oversized and non-schema input | **Partly met.** Size cap of 64 MiB per response line. A line that is not JSON raises, which ends that trial with `error:`. No schema check on executor results | `sandbox.MAX_RESULT_BYTES`, `ExecutorSession` |
| 15 | Results leave only through size-capped stdout; no writable host mounts | **Met** | Items 9 and 14 |
| 16 | Docker Desktop file sharing restricted; `.env` and `$HOME` never mounted | **`.env` and `$HOME` are never mounted:** met, checked on every container. **Open: file sharing is at Docker Desktop's default** (`/Users` and others), so a container *could* be given `/Users` by a flag. No code path does that, and item 5's test pins the flags. Restricting it is a Docker Desktop setting: the owner's call | `settings-store.json` has no `FilesharingDirectories` key |
| 17 | Compose lint | **N/A.** Compose is not used. The launcher is code with a pinned flag set (item 5) | `sandbox.py` |
| 18 | Proxy soundness checker on every trace; failures counted | **Met** | `scheduler.soundness_problems`; V8 |
| 19 | Third-party images built from source at a pinned commit, network only at build time | **Met** | `../2026-10-28-d1-gate/build.json` |
| 20 | Report renderer escapes untrusted strings | **N/A.** No renderer exists yet. Results are JSON and Markdown written by us | — |
| 21 | Findings labeled `verified` or `candidate` | **Met.** Trial status `verified`; unverified violations are listed separately | `trials.json` |
| 22 | Per-session caps on model calls, tokens, wall-clock | **N/A here** (no model). Wall-clock: the 900 method-seconds cap per trial, and a 300 s request timeout per executor call | `config.json`, `ExecutorSession` |
| 23 | Held-out material outside the prompt loop | **N/A here** | `docs/HELDOUT_PROTOCOL.md` |
| 24 | Pre-commit secret check passes; `.env` ignored | **Partly met.** `.env` is ignored and has never been committed (`git log --all -- .env` is empty). **Open: there is no pre-commit hook.** Each commit's diff is reviewed by hand | `.gitignore` |

## Note on item 8: what is and is not shown

**Contained** (`sandbox_check-*.json`, `containment`). Each fixture ran with the cart's exact
flags: 160 MB, 1 CPU, pids 256, read-only root, a 32 MB noexec `/tmp`, user 1654, the internal
network.
- **Fork bomb:** stopped at 256 processes and 1 CPU. Valkey kept answering `PING` throughout,
  and the host killed it in seconds.
- **Busy loop:** capped at 1 CPU, and killed.
- **Memory hog:** OOM-killed at the limit (exit 137).
- **`/tmp`:** full at 32 MB.
- **Root filesystem:** read-only; writes are refused.
- **Scripts in `/tmp`** could not be executed.

**Not shown:** that a service that hangs or dies during a round ends as an INCONCLUSIVE
execution rather than a failed trial. By the code:
- a hung gRPC call ends at its 30 s deadline as a harness failure, so the execution is
  INCONCLUSIVE;
- a hung observation raises `Unreachable`, so the trial ends with `error:`, which is reported and
  never dropped;
- a hung executor ends at the 300 s request timeout, and the session is not reused.

This bounds every hang, but it is not the item's "recorded as inconclusive" in every case, and no
fixture exercises it end to end.
