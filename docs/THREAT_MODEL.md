# Threat Model

Status: **Phase 0 draft.** Nothing described here is implemented yet. Every control below is a
requirement for Phase 1, and the [security acceptance checklist](#security-acceptance-checklist)
at the end is the gate for running any third-party code.

> **Updated 2026-10-28 (`PHASE0_REVIEW.md` R10, approved as A7).**
> - The executor, proxy, and oracle run as a container **inside** the target's internal network.
> - The host orchestrator, the only process with internet access and the API key, talks to it
>   only through stdin/stdout (B4).
> - No published ports. Compose files are linted.
> - Docker Desktop file sharing is restricted, and `.env` is never mounted.
> - Checklist items added in §8.

## 1. What Mylonite does that is dangerous

Mylonite reads source code it did not write, sends parts of it to a remote model, receives
model output, and executes the target program under many schedules. Each of those four steps
crosses a trust boundary. The design principle that makes the rest of this document tractable:

> **The model chooses; it never writes code that runs, and it never decides what is true.**
> Model output is data (a JSON document validated against a strict schema and an allow-list of
> operations defined by humans). Execution is done by deterministic code we wrote. Verdicts come
> from a deterministic oracle.

If a later phase relaxes this (for example, model-generated harness code), this threat model
must be revised first.

## 2. Assets

| Asset | Where it lives | Why it matters |
|---|---|---|
| Developer workstation (macOS laptop) | Host | Holds everything below; compromise is total. |
| Meta Model API key | Host environment variable only | Billable; tied to a team member's account. |
| GitHub session (`gh` is logged in on the host) | `~/.config/gh`, keychain | Push access to team repositories. |
| SSH keys, cloud credentials, browser sessions | `~/.ssh`, `~/.aws`, keychain, etc. | Lateral movement beyond the project. |
| Docker daemon | Docker Desktop VM | Root-equivalent inside the VM; can mount host paths that are shared with the VM. |
| Target source code | Sandbox checkout | Open-source for the hackathon, but the design must not assume that. |
| Evaluation integrity | Results files, held-out bug set | The project's central claim depends on it; contamination or tampering silently invalidates it. |
| Judges' and users' trust in reported bugs | Reports, demo | A false bug report presented as verified is a credibility failure. |

## 3. Adversaries and untrusted inputs

1. **Malicious or compromised target repository.** Comments, docstrings, README files, test
   fixtures, build scripts, `setup.py`/`postinstall` hooks, Makefiles, Dockerfiles, and
   dependency manifests may be hostile.
2. **Prompt injection carried by any text the model reads**: source code, logs, error messages,
   stack traces, operation results, and prior experiment output (feedback loops re-inject
   target-controlled text).
3. **The model itself** as an unreliable component: hallucinated operations, out-of-range
   arguments, invented invariants, overconfident explanations, schema-violating output.
4. **Supply chain**: Python/Node packages, container base images, and the target's own
   dependencies.
5. **Accidental misuse by us**: pointing Mylonite at a real database, leaking a key into a
   commit, running a target on the host "just once" to debug.

Out of scope for the hackathon: a network attacker between us and the Meta API (TLS is assumed),
and nation-state VM escapes.

## 4. Trust boundaries

```
 ┌──────────────────────────── Host (trusted, must stay clean) ─────────────────────────────┐
 │  Orchestrator (our code)  ── holds META API key, budgets, sandbox policy (static config)   │
 │      │  B1: context builder (allow-listed files, secret scan, size caps) ─────────────┐    │
 │      │                                                                               ▼    │
 │      │                                                          Meta Model API (remote) │
 │      │  B2: model output ◄── strict JSON Schema + operation allow-list + clamps ◄──────┘    │
 │      ▼                                                                                    │
 │  B3: sandbox launcher (docker run with fixed flags; no model-controlled fields)           │
 └──────┬───────────────────────────────────────────────────────────────────────────────────┘
        ▼
 ┌──────────── Sandbox (untrusted: target code + our harness + scheduler) ─────────────┐
 │  no network egress · read-only root · non-root · caps dropped · pids/mem/cpu/time caps │
 │  writes only to tmpfs · emits a trace file through a size-capped output channel (B4)  │
 └────────────────────────────────────────────────────────────────────────────────────────┘
        ▼ B4: trace/result parser (schema-validated, size-capped, never eval/pickle)
   Oracle (our code, host) → Report renderer (B5: HTML-escapes every string)
```

| Boundary | Crossing | Control |
|---|---|---|
| B1 Host → Meta API | Source excerpts, operation catalog, experiment feedback | File allow-list, deny-list for secret-bearing paths, secret-pattern scan, byte cap, open-source targets only during the hackathon. |
| B2 Meta API → Host | Plans, hypotheses, invariant proposals, explanations | JSON Schema validation (reject, at most one repair retry), operation names must exist in the human-written adapter registry, argument values validated per operation and clamped to caps, invariants restricted to a fixed template grammar (no code), free text treated as display-only. |
| B3 Host → Sandbox | Launch parameters, target checkout | Static, version-controlled sandbox policy; the model cannot set image, mounts, flags, network, limits, or commands. |
| B4 Sandbox → Host | Traces, operation results, final state | Size-capped files, schema-validated JSON lines, no deserialization of code objects. |
| B5 Results → Human | Report, timeline visualization | All target- and model-originated strings escaped; reports say which claims are oracle-verified and which are model commentary. |

## 5. Abuse cases and mitigations

Each row: threat → mitigation → residual risk. "P1" marks mitigations that must exist before
Phase 1 runs any third-party code; "Later" marks hardening we will document but not build.

| # | Threat | Mitigation | Residual risk |
|---|---|---|---|
| T1 | **Prompt injection through source/docs** (e.g., a comment instructing the model to call a tool, exfiltrate the key, or report "no bugs"). | Model has no tools with side effects; its only output is schema-validated data choosing among allow-listed operations. The key is never in the prompt. The oracle, not the model, decides verdicts. (P1) | Injection can still *bias which experiments run* (reducing effectiveness) or *mislead the explanation text*. Explanations are labeled as unverified commentary. |
| T2 | **Arbitrary shell execution** requested by model output. | No code path turns model text into a command, path, image name, or file write. Allow-listed operations map to hand-written adapter functions. (P1) | Bugs in our own adapters. Mitigated by review and keeping adapters small. |
| T3 | **Malicious generated test code.** | Out of scope by design: Phase 1 does not execute model-generated code. Any future change requires a revised threat model and sandbox review. | — |
| T4 | **Secrets exposure to the API** (target `.env`, keys in source, our own key). | Context builder sends only allow-listed source extensions from the target subtree; denies `.env*`, `*.pem`, `*.key`, `secrets*`, `credentials*`, CI configs; regex scan for common key formats with hard fail; byte cap per request. Our API key lives only in the host process environment, never in a sandbox, never logged. (P1) | Novel secret formats; proprietary code sent to a third-party API. Only open-source targets during the hackathon. Use **Standard** mode (inputs not used for training); never Contributor mode, whose terms forbid confidential code. The Responses API stores responses by default with no stated retention period, so set `store: false` where supported (see `HACKATHON_COMPLIANCE.md` §6). |
| T5 | **Secrets exposure to the sandbox** (host env vars, `~/.config/gh`, Docker socket). | Sandbox launched with an empty environment allow-list, no host mounts except a read-only copy of the target source, never `/var/run/docker.sock`, never `$HOME`. (P1) | None identified beyond VM escape (T8). |
| T6 | **Unauthorized network access** (exfiltration, downloading payloads, hitting real services). | `--network none` for single-process targets; for multi-container targets, a Compose network with `internal: true` (no egress). Dependencies baked at image-build time from lock files, not fetched at test time. (P1) | Build stage needs network; a malicious dependency can act at build time. Mitigated by pinned versions/hashes and building only reviewed targets. |
| T7 | **Host filesystem access** by target code. | Target never runs on the host. Container root filesystem `--read-only`, writable `tmpfs` with size cap, non-root UID, `--cap-drop ALL`, `--security-opt no-new-privileges`. (P1) | Docker Desktop file sharing exposes configured host paths to the VM; we will restrict shared paths to the project directory. |
| T8 | **Container escape / sandbox limits.** | Containers on Docker Desktop run in a Linux VM, which adds a boundary between target and macOS host. No `--privileged`, no added capabilities, no device mounts, seccomp default profile kept. | Kernel/VM escape is possible in principle. Stronger isolation (gVisor, Firecracker, a dedicated throwaway VM) is **Later** and not available out-of-the-box on Docker Desktop for macOS. Accepted for curated open-source targets only. |
| T9 | **Resource exhaustion, fork bombs, infinite loops, livelock under a schedule.** | `--pids-limit`, `--memory`, `--memory-swap` equal to memory, `--cpus`, tmpfs size cap, per-execution wall-clock timeout enforced by the host (kill + remove), global run budget, cap on operations per workload and steps per schedule. A timeout is recorded as *inconclusive*, never as a bug. (P1) | Disk filled by Docker image layers/logs; mitigated by log size limits and cleanup. |
| T10 | **Dependency supply-chain attack** (our tooling or target deps). | Minimal dependencies; pinned versions with hashes in lock files; base images pinned by digest; no `curl | sh`; review every new dependency in `DECISIONS.md`. (P1) | Compromise of a pinned upstream before pinning. Accepted. |
| T11 | **Malicious repository setup scripts** (`postinstall`, `setup.py`, Makefile targets). | Never run target install/build steps on the host. Builds happen inside a container from a reviewed Dockerfile we control. Phase 0 runs no third-party code at all. (P1) | Same as T6 build-time risk. |
| T12 | **Destructive test operations** (an operation that drops tables or deletes files). | Operations are hand-written adapters per target; the model can only select and parameterize them. Every run starts from a fresh, disposable, synthetic-data state. (P1) | An adapter author mistake. Review required. |
| T13 | **Model output influencing security policy** (e.g., output that raises timeouts, adds mounts, enables network). | Sandbox policy is static configuration in the repository; the planner schema has no fields that map to policy. Numeric fields in plans are clamped to fixed caps by our code. (P1) | — |
| T14 | **Accidental execution against a production database.** | The store client in the harness only accepts endpoints created by the sandbox launcher (container-internal hostnames). No connection strings are read from the environment or from the target's config. Synthetic data only. (P1) | A human bypassing the harness. Documented as forbidden. |
| T15 | **Untrusted output parsed unsafely** (pickle, YAML tags, eval of traces). | JSON only, schema-validated, size-capped, `json.loads` with no object hooks that instantiate classes. (P1) | — |
| T16 | **XSS / content injection in the report or timeline** from target strings or model text. | Escape all strings; no `innerHTML` with untrusted data; static report without remote scripts. (P1 for visualization) | — |
| T17 | **Evaluation tampering or contamination** (model sees held-out bugs; developers tune prompts on held-out set; comments in held-out code reveal the bug). | Held-out bugs generated after the prompt freeze, stored outside the development loop, comments stripped and identifiers neutralized, hash of the frozen prompt recorded with every result. See `EVALUATION_PLAN.md`. | Human confirmation bias; mitigated by pre-registered metrics and reporting all runs. |
| T18 | **Over-claiming**: reporting a model-suggested issue as a verified bug. | Report schema distinguishes `verified` (oracle violation reproduced on replay N/N times) from `candidate` (anything else). Demo shows only verified results. | — |
| T19 | **Cost exhaustion of the Meta API** (runaway loop). | Per-session call cap, token cap, and wall-clock cap enforced by the orchestrator; no recursive agent loops. (P1) | — |

## 6. Sandbox technology choice

| Option | Isolation | Fit for us | Decision |
|---|---|---|---|
| Restricted subprocess on the macOS host (`ulimit`, `sandbox-exec`) | Weak; `sandbox-exec` is deprecated and shares the user's file permissions. | Easy but exposes `$HOME`, keychain, `gh` session. | **Rejected** for any third-party code. Acceptable only for our own synthetic fixtures during scheduler development. |
| Docker Desktop container with hardened flags | Linux VM boundary + namespaces + cgroups. | Docker 29.5.3 is installed; supports every limit we need; reproducible images. | **Proposed default.** |
| gVisor / Kata / Firecracker | Stronger (user-space kernel or microVM). | Not supported out-of-the-box on Docker Desktop for macOS; setup cost competes with the 8-day budget. | **Later.** |
| Disposable cloud VM | Strong separation from the laptop. | Adds cost and ops; useful if we ever run unvetted repositories. | **Later**, required before accepting arbitrary user repositories. |

Baseline `docker run` flags for a single-process target (provisional; verified in Phase 1):

```
--network none --read-only --tmpfs /tmp:rw,size=64m,noexec
--user 65534:65534 --cap-drop ALL --security-opt no-new-privileges
--pids-limit 256 --memory 1g --memory-swap 1g --cpus 1
--env-file /dev/null   # plus an explicit allow-list of non-secret variables
```

For multi-container targets (Valkey/Redis, Postgres), the same flags apply to every service, and
the Compose network is declared `internal: true`. Any flag an image cannot tolerate is an
exception recorded in `DECISIONS.md` with the reason. The executor container joins the same
internal network and is driven over stdin/stdout (`ARCHITECTURE.md` §9).

## 7. Phase 0 posture

During Phase 0 we executed **no third-party code**: no clones, builds, installs, or container
runs. Research used read-only web and GitHub API access.

## 8. Security acceptance checklist

A Phase 1 build may run third-party code only when every item is checked and recorded in
`DECISIONS.md` with the commit that satisfied it.

Status (2026-10-29): recorded for **no-model** runs of the D1 cart in D-032
(`experiments/2026-10-29-d1-baselines/SECURITY_CHECK.md`), with its open items. Not yet recorded
for model runs on third-party code.

- [ ] Planner output is validated against a JSON Schema with `additionalProperties: false`;
      invalid output is rejected (one repair retry max) and logged, never partially executed.
- [ ] Operation names in plans are checked against the adapter registry; argument values are
      validated per operation and clamped to configured caps.
- [ ] Invariants proposed by the model use only the fixed template grammar; no `eval`, `exec`,
      or dynamic import anywhere in the oracle path. (`grep` gate in CI or pre-commit.)
- [ ] No code path passes model text to a shell, subprocess argument, file path, image name,
      SQL string, or network address.
- [ ] Sandbox launcher uses a static, reviewed flag set (§6); unit test asserts the flags.
- [ ] Sandbox has no network egress (verified by an in-sandbox probe that must fail).
- [ ] Sandbox runs as non-root with a read-only root filesystem and all capabilities dropped.
- [ ] CPU, memory, pids, tmpfs size, and wall-clock limits are set and a fork-bomb fixture and an
      infinite-loop fixture are both contained (killed, recorded as inconclusive).
- [ ] No host mounts except the read-only target copy; Docker socket and `$HOME` never mounted.
- [ ] Meta API key read only from the host environment; never written to logs, traces, reports,
      prompts, or the sandbox environment (test with a canary key value).
- [ ] Context builder deny-list and secret scan run before every API call; a planted canary
      secret in a fixture is blocked.
- [ ] Meta API data-use and retention terms read and recorded in `HACKATHON_COMPLIANCE.md`.
- [ ] Dependencies pinned with hashes; base images pinned by digest.
- [ ] Trace/result parser rejects oversized input and non-schema JSON.
- [ ] Executor results leave the sandbox only through size-capped stdout; no writable host
      mounts.
- [ ] Docker Desktop file sharing restricted to what the build needs; `.env` and `$HOME` never
      mounted (checked with `docker inspect` on every container).
- [ ] Compose lint rejects `privileged`, `network_mode: host`, `cap_add`, `docker.sock`,
      `ports:` on sandbox networks, and writable bind mounts.
- [ ] Proxy soundness checker runs on every trace; failures are counted, never ignored.
- [ ] Third-party images are built from source at a pinned commit in a builder container
      (network only at build time), or are upstream infrastructure images pinned by digest.
- [ ] Report renderer escapes all untrusted strings (test with an HTML/script payload fixture).
- [ ] Reports label each finding `verified` or `candidate`; only `verified` appear in the demo.
- [ ] Per-session caps on model calls, tokens, and wall-clock are enforced.
- [ ] Held-out evaluation material is stored outside the prompt-development loop (see
      `EVALUATION_PLAN.md`), and the frozen prompt hash is recorded with each result.
- [ ] `git` pre-commit secret check (pattern scan) passes; `.env` is ignored.

## 9. Residual risks we accept for the hackathon

1. Docker Desktop's VM is the strongest boundary we have; a VM escape would reach the laptop.
   Accepted only because targets are curated open-source projects.
2. Prompt injection can degrade search effectiveness and explanation accuracy. It cannot cause
   execution or verdict changes under the design above.
3. Build-time dependency fetching requires network access; we rely on pinning and review.
4. Source excerpts of open-source targets are sent to the Meta API under its terms.
