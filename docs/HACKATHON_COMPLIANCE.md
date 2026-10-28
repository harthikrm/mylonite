# Hackathon Compliance

Event: **Meta AI Developer Hackathon** (Global), theme *Push the Frontier*, track under
consideration: **Indie Developer**. Team: MetaMorphic. Project: Mylonite.

Sources were read on 2026-10-27. The rules say organizers "reserve the right to modify these
terms at any time", so **re-read the rules page on Nov 1 and on Nov 4 before submitting.**

How these were read: Meta's docs pages through an automated fetcher that returns a summary of
each page; the Cerebral Valley rules through plain HTTP GETs of the public HTML. Items marked
**(re-verify)** matter enough that a human should read the original page once.

## 1. Authoritative sources

| Source | URL | Status |
|---|---|---|
| Official Rules and Event Waiver (dated Oct 25, 2026) | https://cerebralvalley.ai/e/meta-ai-developer-hackathon/waiver | **Binding rules.** |
| Event page (Cerebral Valley) | https://cerebralvalley.ai/e/meta-ai-developer-hackathon | Schedule, model list. It still said the rules "will be published before" Oct 26 when read. |
| Meta event page | https://dev.meta.ai/events/global-hackathon | Links to the Cerebral Valley page. |
| Submission portal | https://cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit | Form fields not publicly visible. |
| Meta Model API Terms of Service (updated Oct 9, 2026) | https://dev.meta.ai/legal/terms-of-service | Applies to every API call. |
| Meta Acceptable Use Policy | https://dev.meta.ai/legal/acceptable-use-policy | Relevant to a testing tool (see §5). |
| Geographic Use Policy (updated Oct 12, 2026) | https://dev.meta.ai/legal/geographic-use-policy | Restricted territories. |
| Participant guide | Provided by the team (not a public URL we have read) | Source of the public-repo, video, new-contribution, and judging-stage rules in §4–§5. Recorded as **team-reported**; keep a copy with the team's records. |
| Hackathon Discord | https://cerebralvalley.ai/e/meta-ai-developer-hackathon/discord | Organizer Q&A for Q-H1. |
| Meta Model API cookbook | https://github.com/meta-models/meta-model-cookbook (MIT) | Read 2026-10-28; confirms the API usage patterns in §6. |

No Devpost page was found. Third-party listings exist but some show wrong times; ignore them.

## 2. Dates and deadline

- Building period (team plan): Oct 27 – Nov 4, 2026.
- **Submission deadline: Nov 4, 2026, 9:00 PM Eastern** (event page and Meta page).
  US daylight saving time ends Nov 1, so 9 PM ET on Nov 4 is EST = **02:00 UTC Nov 5**,
  which matches the due date in the event page data.
- The page data also contains a 6-hour grace-period setting. It is not in the rules.
  **Do not rely on it.** Our internal deadline is **Nov 4, 6:00 PM ET** (3-hour buffer).
- Judging Nov 4–8; finals Nov 9 (event page).

## 3. Eligibility and team

- Indie Developer track: open to individual builders and students, **teams of up to four**.
  The team Representative submits and must name every member. One track per participant and
  per project (rules).
- Participants must be 18+ and of the age of majority where they live. Excluded locations in the
  rules: Belarus, China, Russia, Ukraine, Syria, Crimea/Donetsk/Luhansk, Cuba, North Korea, Iran.
  Meta and Cerebral Valley staff are excluded (rules).
- Separately, the Model API's Geographic Use Policy restricts API use from certain territories
  (the list includes Pakistan, China/Hong Kong, Russia). **Every team member who calls the API
  must be in a permitted territory.** (re-verify against the policy page)
- Indie prizes: $400k pool (1st $150k, then $100k / $75k / $50k / $25k); bonus prizes up to $50k
  (rules).

## 4. Judging criteria (rules) and what each implies for Mylonite

**Judging stages (participant guide, team-reported):** (1) baseline viability and Meta model
usage; (2) scored evaluation under the official rubric; (3) final judging of the top five
projects per track. Stage 1 is a gate. Muse's role must be unmistakable and functional in the
first 30 seconds of the video and in the README's first screen, whatever the comparison
results turn out to be. The numerical weights below come from the Official Rules page;
re-verify them against the complete rubric before relying on them.

| Criterion | Weight | What the rules emphasize | Mylonite implication |
|---|---|---|---|
| Impact | 30% | Includes "whether it fits one of the problem statements". | The problem statements were **not found** in the public rules. Open question Q-H1. Our framing: reliability of software that handles money/state under concurrency. |
| Use of Meta AI Tooling | 25% | Going beyond a basic integration; surfacing unexpected capabilities. | Muse must do real work: reading code in any language, choosing workloads with valid preconditions, proposing invariants that we then validate, and explaining verified traces with checked line references. A chat wrapper would score poorly. |
| Technical Depth & Execution | 20% | — | Deterministic schedule control, a spec-free oracle, measured comparison against baselines. |
| Demo | 25% | Whether it "holds up live", and the quality of the demo video. | The demo must be replayable from a recorded seed and pinned target revision, with no live dependency on the model producing the same output (the model is non-deterministic; see §6). |

## 5. Rules that constrain what we build

**Meta model use.** Participants "build with Meta AI products, including Muse Spark, Glimmer,
SAM 3, and any other Meta AI products identified on the Event page" (rules). The event page lists
the Muse Spark series, Muse Wonder, Muse Image, SAM 3.1 via the Model API, the open-weight models,
and Muse Code. There is no explicit "must be primary" rule; the 25% tooling criterion is the
incentive. Our own requirement is stricter: Meta models are the only LLMs in Mylonite's runtime.

**Original work and pre-existing code.** The Submission must be "original work product", solely
owned, and non-infringing. Third-party technical help is allowed if the parts remain our own work.
Open source may be used "provided applicable open source licenses are followed and the Submission
enhances or builds upon the underlying open source product" (rules). No explicit rule about code
written before the building period or about AI coding assistants was found.
Our boundary, to be safe:
- Everything in this repository is created on or after Oct 27, 2026 (first commit date is the
  evidence).
- Third-party projects we test (OpenTelemetry Demo, Apache-2.0) are **not vendored**; they are
  referenced by URL and pinned commit and pulled into a sandbox at test time.
- Any reused library is listed with its license in the README before submission.
- Use of AI coding assistants is disclosed in the README.

**Licensing grant.** We keep ownership, but grant the organizers a perpetual, irrevocable,
worldwide, royalty-free, non-exclusive license to the Submission "for any purpose", and shared
materials are not confidential (rules). Do not include anything we cannot license that way.

**Public repository: required** (participant guide, team-reported; the public Official Rules
text does not state it). Plan: keep the repository local until the team approves, then publish
before submission with a license (Apache-2.0 proposed, `DECISIONS.md` D-016), after a secret
scan of the full history. Creating the remote and pushing require explicit team approval.

**Demo video: three minutes, required** (participant guide, team-reported). Format details are
still unknown (Q-H3).

**New contributions must be identified** (participant guide, team-reported). The submitted work
must clearly demonstrate new functionality built during the hackathon, and the demo must say
what is new. Plan: a README section "Built during the hackathon" listing our components,
separate from "Used, not built": OpenTelemetry Demo, Valkey, the OpenAI-compatible SDK, and any
other library. The video names both on screen.

**Discouraged categories** (participant guide, team-reported): generic RAG tools, basic
chatbots, and other overused categories. Mylonite is neither, but the pitch must not
present Muse as a chat front-end.

**Acceptable Use Policy.** The AUP prohibits using the service to "identify, scan for, or exploit
vulnerabilities in any system… without proper authorization" and building offensive cyber
tooling. Mylonite is a defensive tool for testing code you own or are authorized to test, in
local disposable sandboxes. Our targets are open-source code run on our own machines. The README
and pitch must say this plainly; we must not demo against third-party live systems.

## 6. Meta Model API facts that affect compliance and design

| Fact | Source | Consequence |
|---|---|---|
| Model IDs: `muse-spark-1.3` ("recommended for new work"), `muse-spark-1.2`, `muse-spark-1.1`, `muse-wonder-1.0` (preview), Contributor variants `muse-spark-1.3-contributor`, `muse-spark-1.2-contributor`. 1,048,576-token context; text output. | https://dev.meta.ai/docs/models | Default model: `muse-spark-1.3` Standard. Muse Wonder only as an ablation if budget allows. |
| Base URL `https://api.meta.ai/v1`; `Authorization: Bearer $MODEL_API_KEY`; keys start `LLM_`, per team, shared rate limits. | https://dev.meta.ai/docs/overview, https://dev.meta.ai/docs/authentication | Key only in the host environment variable `MODEL_API_KEY`; `.env` is git-ignored. |
| Endpoints: `/v1/responses` (recommended), `/v1/chat/completions` (OpenAI-compatible), `/v1/messages` (Anthropic-compatible). No Meta-branded SDK; docs use the OpenAI SDK, Anthropic SDK, or LiteLLM. | https://dev.meta.ai/docs/protocols, https://dev.meta.ai/docs/sdks | Use the OpenAI Python SDK against Meta's base URL, or plain HTTPS. No other provider is configured. |
| Structured output: `response_format: {type: "json_schema", json_schema: {name, schema, strict}}` (Chat Completions) / `text.format` (Responses; sending `response_format` there returns 400). Decoding is constrained, so output is "guaranteed to conform", and `strict: false` currently behaves the same. Strict mode: root must be a plain object (no top-level `anyOf`/`oneOf`/`allOf`/`enum`/`not`); `allOf`/`oneOf` banned anywhere; **`anyOf` allowed below the root**; every object `additionalProperties: false`; `required` lists every key. `$ref`/`$defs` usable if non-recursive (≤ 200,000 nodes after inlining). Limits: depth 10, 5,000 properties, 120,000 schema-string characters, 1,000 enum values. `minItems`/`maxItems`/`maxLength`/`pattern` not mentioned. | https://dev.meta.ai/docs/structured-output (re-read 2026-10-28); cookbook `01_api_fundamentals/04_structured_output.ipynb` | Planner schemas: flat lists with id references; nullable fields as `anyOf` with `null` below the root; enforce length limits locally. |
| Prompt caching is automatic on identical leading tokens; `usage.prompt_tokens_details.cached_tokens` reports hits; an optional stable `prompt_cache_key` raises hit rates. | Cookbook `01_api_fundamentals/05_prompt_caching.ipynb` | Put rules, catalog, and source first and the per-call feedback last. |
| Tool calling supported, but `tool_choice` only `"auto"` on Chat Completions/Responses; tool `strict` "does not guarantee" argument validity. | https://dev.meta.ai/docs/tool-calling | Use structured output, not tool calls, for planner actions. |
| `seed` deprecated and best-effort; temperature default 1.0 and the model "is tuned to run at the default"; reasoning cannot be disabled (`reasoning_effort`: minimal…max). | https://dev.meta.ai/docs/protocols/chat-completions, https://dev.meta.ai/docs/reasoning | Model output is not reproducible. Every result we report must be reproducible from the **recorded plan**, not by re-querying the model. Repeat model-guided trials to measure variance. |
| Pricing per 1M tokens (cached input / input / output): Spark Standard $0.15 / $1.25 / $4.25; Spark Contributor $0.002 / $0.10 / $0.20; Wonder $0.20 / $4.00 / $20.00. Rate limits per team: Spark Standard and Wonder 3,000 RPM / 4M TPM; Contributor 150 RPM / 3M TPM. Reasoning tokens are billed as output. | https://dev.meta.ai/docs/pricing-rate-limits, https://dev.meta.ai/docs/reasoning | Track tokens per call; report cost per verified bug. |
| Hackathon credit: $150 of Model API credit, valid for a 10-day window (confirmed by the team as received). A payment method is required before any request. Credit terms PDF returned 403. | Rules; https://dev.meta.ai/help/accounts-and-login/sign-up | Budget below. Whether credits cover Wonder/Contributor is unknown (Q-H4). |
| Other credits (team-reported): $200 Claude API credit tied to the team's existing Claude setup (may carry project restrictions); Modal, Baseten, Fireworks possible, subject to approval. | Team | Claude assists development. It is **not** part of Mylonite's runtime and not a planner baseline unless the team decides otherwise and the rules allow it (`DECISIONS.md` D-008). |
| Standard mode: content "not used to train Meta models". Contributor mode: may be used for training; the ToS forbids submitting confidential code to Contributor. Responses API `store` defaults to true, no retention period stated; Zero Data Retention by sales request only; AUP-flagged content may be kept up to 2 years. | https://dev.meta.ai/docs/models, https://dev.meta.ai/legal/terms-of-service, https://dev.meta.ai/docs/protocols/responses, https://dev.meta.ai/help/policies-and-privacy/zero-data-retention | Use **Standard** mode. Set `store: false` on the Responses API if supported (verify). Send only open-source target code. |
| ToS: you own inputs and outputs; you warrant IP rights to what you submit; no using outputs to train competing models; 18+. | https://dev.meta.ai/legal/terms-of-service | Compatible with our plan (no training). |

**Budget estimate (provisional).** One planner call ≈ 30k input tokens (source excerpts and
catalog) + 6k output tokens including reasoning ≈ $0.0375 + $0.0255 ≈ **$0.063** on Spark
Standard. A naive evaluation of 12 targets × 20 trials × up to 10 planner calls = 2,400 calls ≈
**$151**, i.e. the entire $150 credit. The evaluation is therefore sized at ≤ 5 calls per trial under an owner-approved cap of
≈ $100 in total, including ablations, development, and the demo (`EVALUATION_PLAN.md` §12). Further savings: cache the static prompt prefix (cached input is
~8× cheaper). Recompute after measuring real token counts on Oct 28.

## 7. Submission checklist

Content
- [ ] Public repository URL (required), published after team approval and a full-history
      secret scan.
- [ ] README: what Mylonite does, the hypothesis, results with confidence intervals, how to
      reproduce the demo, known limitations, licenses of dependencies, AI-assistant disclosure.
- [ ] README section "Built during the hackathon" vs "Used, not built".
- [ ] Demo video, 3:00 (required), naming the new contributions on screen and showing Muse's
      role in the first 30 seconds, a verified result, and the baseline comparison.
- [ ] Clear statement of which Meta models are used and how (model IDs, mode, what they decide).
- [ ] All team members named (≤ 4) by the Representative; each confirms eligibility.
- [ ] Track selected: Indie Developer (pending team confirmation).

Integrity
- [ ] Final secret scan of the full Git history, not only the working tree.
- [ ] No vendored third-party code; pinned third-party revisions listed.
- [ ] Every claim in the README links to a results file produced by the evaluation harness.
- [ ] Negative or mixed results reported as such.

Logistics
- [ ] Rules page re-read on Nov 1 and Nov 4 for changes.
- [ ] Submission form opened early (by Nov 2) to see required fields.
- [ ] Submit by **6:00 PM ET Nov 4** (internal), hard deadline 9:00 PM ET.

## 8. Open compliance questions

Tracked in `OPEN_QUESTIONS.md` as Q-H1 … Q-H6: the problem statements behind the Impact
criterion; the public-repository deadline (required per the participant guide); demo video
format; whether credits cover Muse Wonder; API territory eligibility; and the grace period.
Useful event: **Oct 28, 12–1 PM ET, "Agents 102: Best Practices for Verifiable Agents"**
(team-reported). It bears directly on D-003 and D-007; attend and record takeaways in
`RESEARCH_LOG.md`.
