"""Ablation A2's payload checks: a no-source request must carry no source, directly or indirectly.

``check(body, target, repo_root)`` returns (problems, attribution):
- problems: a source block, a line of either variant's source, or an identifier shared with
  either variant's source that no permitted channel explains. Any problem means the request must
  not be sent.
- attribution: every identifier the request shares with either variant's source, with the
  permitted channels it reaches the model through: prompt (target-independent text), catalog,
  contract, schema, request fields, and feedback on the model's own experiments. Identifiers that
  arrive through the catalog or contract are interface facts, not code, but they are listed so a
  reader can judge what remains.

This sits beside ``audit.assert_clean``, which still runs on every request. That gate treats the
buggy source as shown, which is not true under A2, so it cannot see source leakage.

Run as a script, it writes payload_audit.json: the round-1 A2 request for each pilot target, its
checks, and a byte comparison with the pilot's recorded source-visible request.
"""

import copy
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / "src"))

from mylonite import audit, planner  # noqa: E402

PROMPT_TEXT = planner.SYSTEM + planner.USER_TEMPLATE + planner.NO_SOURCE + planner.FEEDBACK_HEADER
PILOT_CALLS = REPO / "experiments/2026-10-29-pilot/results/20261028-165020/model_calls.jsonl"
SOURCE_BLOCK = re.compile(re.escape(planner.SOURCE_HEADER) + r"<untrusted_source.*</untrusted_source>\n\n",
                          re.S)


def source_texts(target, repo_root):
    """Normalized model views of both variants: the declared files and the corrected module."""
    texts = [text for _, text in planner.source_view(target, repo_root)]
    fixed = target["variants"].get("fixed")
    if fixed:
        texts.append(planner.model_view_source(audit.module_file(repo_root, fixed).read_text()))
    return texts


def body_text(body):
    fields = copy.deepcopy({k: v for k, v in body.items() if k != "messages"})
    return "\n".join(m["content"] for m in body["messages"]) + "\n" + json.dumps(fields, sort_keys=True)


def feedback_text(user):
    if planner.FEEDBACK_HEADER not in user:
        return ""
    return user.split(planner.FEEDBACK_HEADER, 1)[1].rsplit("\n\nPropose up to", 1)[0]


def channels(body, target):
    fields = copy.deepcopy({k: v for k, v in body.items() if k != "messages"})
    fields.get("response_format", {}).get("json_schema", {}).pop("schema", None)
    return {"prompt": PROMPT_TEXT,
            "catalog": json.dumps(planner.catalog_view(target), sort_keys=True),
            "contract": json.dumps(planner.contract_view(target), sort_keys=True),
            "schema": json.dumps(planner.plan_schema(target), sort_keys=True),
            "request fields": json.dumps(fields, sort_keys=True),
            "feedback": feedback_text(audit.target_dependent_text(body))}


def check(body, target, repo_root):
    text = body_text(body)
    problems = []
    if "<untrusted_source" in text or planner.SOURCE_HEADER in text:
        problems.append({"check": "source block"})
    if planner.NO_SOURCE not in text:
        problems.append({"check": "no-source marker missing"})
    sources = source_texts(target, repo_root)
    lines = {line.strip() for s in sources for line in s.splitlines() if len(line.strip()) >= 12}
    problems += [{"check": "source line", "match": line} for line in sorted(lines) if line in text]
    channel_ids = {name: audit.identifiers(t) for name, t in channels(body, target).items()}
    shared = set().union(*map(audit.identifiers, sources)) & audit.identifiers(text)
    attribution = {i: sorted(n for n, ids in channel_ids.items() if i in ids) for i in sorted(shared)}
    problems += [{"check": "unexplained source identifier", "match": i}
                 for i, found_in in attribution.items() if not found_in]
    return problems, attribution


def without_source(body):
    """The pilot's source-visible request with its source block replaced by the no-source marker."""
    out = copy.deepcopy(body)
    user = next(m for m in out["messages"] if m["role"] == "user")
    user["content"], n = SOURCE_BLOCK.subn(planner.NO_SOURCE, user["content"])
    assert n == 1, "expected exactly one source block"
    return out


def canonical(body):
    return json.dumps(body, sort_keys=True)


def main():
    pilot_requests = {}
    for line in PILOT_CALLS.read_text().splitlines():
        entry = json.loads(line)
        pilot_requests.setdefault(entry["trial"].split("/")[0], entry["request"])
    config = json.loads((HERE / "config.json").read_text())
    report = {}
    for path in config["targets"]:
        target = json.loads((REPO / path).read_text())
        a2 = planner.build_request(target, REPO, (), False, config["A2"]["reasoning_effort"])
        m4 = planner.build_request(target, REPO, (), True, config["A2"]["reasoning_effort"])
        problems, attribution = check(a2, target, REPO)
        report[target["target"]] = {
            "sha256": hashlib.sha256(canonical(a2).encode()).hexdigest(),
            "equals_pilot_recorded_request_minus_source":
                canonical(a2) == canonical(without_source(pilot_requests[target["target"]])),
            "equals_current_m4_request_minus_source": canonical(a2) == canonical(without_source(m4)),
            "chars": {"a2_user_message": len(audit.target_dependent_text(a2)),
                      "m4_user_message": len(audit.target_dependent_text(m4))},
            "audit_findings": audit.findings(a2, target, REPO),
            "a2_check_problems": problems,
            "source_identifiers_reaching_the_model": attribution,
            "user_message": audit.target_dependent_text(a2)}
    (HERE / "payload_audit.json").write_text(json.dumps(report, indent=1) + "\n")
    ok = all(r["equals_pilot_recorded_request_minus_source"] and r["equals_current_m4_request_minus_source"]
             and not r["audit_findings"] and not r["a2_check_problems"] for r in report.values())
    for name, r in report.items():
        print(name, {k: r[k] for k in ("sha256", "equals_pilot_recorded_request_minus_source",
                                       "equals_current_m4_request_minus_source", "chars")})
        print("   shared with source:", r["source_identifiers_reaching_the_model"])
    print("CLEAN" if ok else "NOT CLEAN")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
