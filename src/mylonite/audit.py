"""Contamination audit of the complete model-visible context (EVALUATION_PLAN.md rules 4–6).

``assert_clean`` runs on every request body before it is sent, and in the tests. It looks for
three kinds of contamination:
1. search artifacts, anywhere in the body: schedule labels, digests, verdict words, result keys;
2. labels, in the target-dependent text: words that mark the target as a test case or a variant,
   paths of the harness, fixture IDs (identifiers are split into words first);
3. answer overlap, in the target-dependent text: any identifier or line that exists only in the
   corrected variant.
These are content checks. The information flow itself (nothing outside the declared view can
change the request) is tested separately in tests/test_contamination.py.
"""

import json
import re
from pathlib import Path

from . import planner
from .resp import HINT_VOCABULARY

DECISION = re.compile(r"\b(?:admit|exec):\d+\b")
DIGEST = re.compile(r"\b[0-9a-f]{16,}\b")
VERDICT = re.compile(r"\b(?:VIOLATION|INCONCLUSIVE)\b")
RESULT_KEY = re.compile(r'"(?:decisions|steps|trace|trace_hash|verdict|violations|witness)"\s*:')
HARNESS_PATH = re.compile(r"\b(?:fixtures|experiments|runs|heldout|held_out|docs)/"
                          r"|/(?:Users|home|private|tmp|var)/")
FIXTURE_ID = re.compile(r"\b[DR]\d+\b|\bd\d+[_-]")
LABELS = frozenset({
    "bug", "bugs", "buggy", "fix", "fixed", "fixes", "fixture", "fixtures", "mutant", "mutants",
    "mutation", "mutated", "seeded", "inject", "injected", "planted", "corrected", "variant",
    "variants", "vulnerable", "vulnerability", "race", "races", "racy", "toctou", "oversell",
    "oversold", "witness", "heldout", "benchmark", "intentional", "deliberate", "broken",
})


class ContaminationError(Exception):
    def __init__(self, findings):
        super().__init__(f"{len(findings)} contamination finding(s): {findings[:5]}")
        self.findings = findings


def words(text):
    """Split into lowercase words, including inside snake_case and camelCase identifiers."""
    out = []
    for token in re.findall(r"[A-Za-z]+", text):
        out += [w.lower() for w in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])", token)]
    return out


def identifiers(text):
    return {t.lower() for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text)}


def module_file(repo_root, module):
    return Path(repo_root) / (module.replace(".", "/") + ".py")


def answer_material(target, repo_root):
    """Identifiers and lines found only in the corrected variant's model view. Identifiers that
    are shown anyway (source, display names, the target-independent scaffold) are excluded."""
    fixed_module = target["variants"].get("fixed")
    if not fixed_module:
        return set(), set()
    fixed = planner.model_view_source(module_file(repo_root, fixed_module).read_text())
    shown = "\n".join(f"{name}\n{text}" for name, text in planner.source_view(target, repo_root))
    shown += "\n" + target_dependent_text(planner.scaffold()) + planner.SYSTEM
    shown_lines = {line.strip() for line in shown.splitlines()}
    only_lines = {line.strip() for line in fixed.splitlines()
                  if line.strip() not in shown_lines and len(line.strip()) >= 12}
    only_ids = {t for t in identifiers(fixed) - identifiers(shown)
                if "_" in t or t.upper() in HINT_VOCABULARY}  # code-like names, not prose words
    return only_ids, only_lines


def target_dependent_text(body):
    """The user message. The system message and schema skeleton are target-independent; that is
    tested by comparing them across targets."""
    return "\n".join(m["content"] for m in body["messages"] if m["role"] != "system")


def findings(body, target, repo_root):
    full = json.dumps(body, sort_keys=True)
    text = target_dependent_text(body)
    found = []
    both = full + "\n" + text  # the user message is escaped inside ``full``; scan it raw too
    for name, pattern, where in (("decision label", DECISION, both), ("digest", DIGEST, both),
                                 ("verdict word", VERDICT, both), ("result key", RESULT_KEY, both),
                                 ("harness path", HARNESS_PATH, text),
                                 ("fixture id", FIXTURE_ID, text)):
        found += [{"detector": name, "match": m.group()} for m in pattern.finditer(where)]
    found = [dict(t) for t in sorted({tuple(sorted(f.items())) for f in found})]
    found += [{"detector": "label word", "match": w} for w in sorted(set(words(text)) & LABELS)]
    for forbidden in (target.get("target"), *target["variants"].values()):
        if forbidden and forbidden in full:
            found.append({"detector": "target identity", "match": forbidden})
    only_ids, only_lines = answer_material(target, repo_root)
    found += [{"detector": "fix-only identifier", "match": t}
              for t in sorted(only_ids & identifiers(text))]
    found += [{"detector": "fix-only line", "match": line}
              for line in sorted(only_lines) if line in text]
    return found


def assert_clean(body, target, repo_root):
    found = findings(body, target, repo_root)
    if found:
        raise ContaminationError(found)
