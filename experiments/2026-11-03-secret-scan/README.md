# Full-history secret scan (2026-11-03)

This is the pre-publication check from `HACKATHON_COMPLIANCE.md` §7: "Final secret scan of the
full Git history, not only the working tree". **Nothing was pushed, and no remote exists.**

## Method

No secret-scanning tool was installed, and installing one needs a download, so `scan.py` is a
standard-library scanner.

```bash
python3 -I experiments/2026-11-03-secret-scan/scan.py . .env
```

- **Scope:** every object in the object database at `d0b7241`: 313 blobs, 216 trees and 49
  commits, including 39 unreachable objects that a push would not send.
  - Contents of files, including files deleted later.
  - Commit and tag messages, and tree entry names.
- **The real Meta Model API key** is read from the git-ignored `.env` and never printed. The scan
  looks for:
  - the full key;
  - its first, middle and last 16 characters;
  - its base64 form, alone and as a `Bearer` header.
- **Other patterns:**
  - Meta `LLM_` keys, AWS, GitHub, OpenAI/Anthropic-style, Stripe live, Slack and Google API keys;
  - private-key blocks, JWTs, `Bearer` values, URLs with credentials;
  - values assigned to names containing key, secret, token or password.

  Hits are printed redacted: the first 4 characters and the length.
- **Positive control:** a scratch repository with a planted fake key, a fake AWS key and a
  base64 `Bearer` header, the leaking file deleted in a later commit. The scanner found:
  - the key and its fragments in the deleted file;
  - a fragment in a commit message;
  - the base64 header;
  - the AWS, `Bearer` and `LLM_` patterns.

## Findings

| Check | Result |
|---|---|
| The real API key, its fragments and encodings, in any object | **0 hits** |
| 11 of the 12 secret patterns | **0 hits** |
| "Assigned secret" pattern | 3 hits, all `self.tokens = collections.Counter()` in `src/mylonite/methods.py`: false positives |
| Paths ever committed that look sensitive (`.env`, keys, credentials, `.netrc` and others) | only `.env.example`, which has never held a value in any version |
| Files tracked under `runs/` (raw logs) or `targets/checkouts/` (third-party source) | none |
| Sealed held-out source (lines from the bases or the mutants) | none |
| `Authorization` or API-key fields in committed model logs | none. The word appears only in `planner.py`, which builds the header from a variable |

`report_d0b7241.json` is the scanner's output.

## For the owner to decide before publishing (not secrets)

- **Commit identity:**
  - All 43 commits carry the author and committer `Harthik Mallichetty <hrmallichetty@gmail.com>`.
    Pushing makes that email public.
  - Changing it means rewriting history. That would change every commit id the freeze
    manifests, amendments, results and decisions cite, so it would break the provenance chain.
  - Recommendation: keep it.
- **Local paths:** `/Users/harthikmallichetty/...` appears 25 times in 5 files:
  - `docs/DECISIONS.md`, `docs/OPEN_QUESTIONS.md` and `docs/PHASE0_REVIEW.md` (the repository
    location);
  - two security-checklist records under `experiments/*/results/pre_run/` (Docker mount sources).

  This is the same name as the author. Removing it from history would also need a rewrite.
- **Third-party emails:** two FreeTSA operator addresses appear inside FreeTSA's signed timestamp
  response (`experiments/heldout-v1/sealed/c2_timestamps/c2_commitment.json.tsr`). They are part
  of FreeTSA's certificate and are public.
- **A second opinion:** a maintained scanner such as gitleaks could check again. It needs the
  owner's approval to download.
