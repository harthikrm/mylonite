"""Freeze manifest (docs/FREEZE.md): build it from a commit, or verify one.

  python3 freeze/manifest.py write <commit> <version> <out.json>
  python3 freeze/manifest.py verify <manifest.json>
  python3 freeze/manifest.py check [<commit>]

Everything comes from git objects at the commit, never from the working tree: the commit and
tree ids, the SHA-256 of every tracked file, and the prompt fingerprint and test result,
computed in a temporary export of that commit with ``python3 -I`` (nothing from the working tree
can be imported). ``verify`` rebuilds the manifest from the commit it names and compares every
field. ``check`` is what a held-out run calls first, at the run commit (default HEAD):
- the latest manifest version committed there (freeze/v*/MANIFEST.json) is the reference; its
  commit must be an ancestor, and a version after v1.0 must be named in docs/AMENDMENTS.md;
- docs/AMENDMENTS.md must extend, unchanged, the one at the manifest's commit (append-only);
- every file the manifest lists must hash the same, except narrative Markdown (anything but the
  three rule documents) and the run's own output directories;
- no file may be added, except narrative Markdown, the run's output directories, and new
  experiment directories (experiments/<a directory the manifest does not have>/).
A change needs a new manifest version, with its entry in docs/AMENDMENTS.md. Standard library
only.
"""

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCOPE = {  # which frozen component each file belongs to; every tracked file is hashed anyway
    "methods and harness": ("src/",),
    "model wrapper and cost cap": ("experiments/2026-10-29-pilot/run_pilot.py",
                                   "experiments/2026-10-28-a2-no-source/run_a2.py"),
    "held-out configuration": ("experiments/heldout-v1/",),
    "evaluation rules": ("docs/FREEZE.md", "docs/EVALUATION_PLAN.md", "docs/AMENDMENTS.md",
                         "src/mylonite/analysis.py"),
    "held-out construction procedure": ("docs/HELDOUT_PROTOCOL.md",),
    "decisions": ("docs/DECISIONS.md",),
    "tests": ("tests/",),
    "images": ("docker/",),
    "development targets": ("fixtures/", "targets/"),
    "manifest tool": ("freeze/manifest.py",),
}
RULE_DOCS = ("docs/FREEZE.md", "docs/EVALUATION_PLAN.md", "docs/HELDOUT_PROTOCOL.md")
AMENDMENTS = "docs/AMENDMENTS.md"  # append-only, checked as a prefix
OUTPUTS = ("experiments/heldout-v1/sealed/", "experiments/heldout-v1/results/", "freeze/v")

PROBE = """import json, sys
sys.path.insert(0, sys.argv[1])
from mylonite import methods, planner
print(json.dumps({"version": planner.PROMPT_VERSION, "fingerprint": planner.prompt_fingerprint(),
                  "model": planner.MODEL, "base_url": planner.BASE_URL,
                  "max_experiments": planner.MAX_EXPERIMENTS, "max_hint": planner.MAX_HINT,
                  "hypothesis_kinds": planner.HYPOTHESIS_KINDS, "methods": sorted(methods.METHODS)}))
"""


def git(*args, binary=False):
    out = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, check=True)
    return out.stdout if binary else out.stdout.decode().strip()


def tracked(commit):
    """{path: SHA-256} of every file in the commit."""
    paths = [p for p in git("ls-tree", "-r", "-z", "--name-only", commit, binary=True)
             .decode().split("\0") if p]
    return {p: hashlib.sha256(git("show", f"{commit}:{p}", binary=True)).hexdigest() for p in paths}


def narrative(path):
    return path.endswith(".md") and path not in RULE_DOCS


def must_match(path):
    """A file the manifest lists whose change would need a new version."""
    return path != AMENDMENTS and not narrative(path) and not path.startswith(OUTPUTS)


def must_not_appear(path, then):
    """A file the manifest does not list, outside the places where new files are expected."""
    experiments = {p.split("/")[1] for p in then if p.startswith("experiments/")}
    new_experiment = path.startswith("experiments/") and path.split("/")[1] not in experiments
    return not (narrative(path) or path.startswith(OUTPUTS) or new_experiment)


def version_key(version):
    return tuple(int(x) for x in version.lstrip("v").split("."))


def check(commit):
    """Problems with running at ``commit`` under its latest freeze version, or []."""
    names = [p for p in tracked(commit) if p.startswith("freeze/v") and p.endswith("/MANIFEST.json")]
    if not names:
        return None, ["no committed freeze manifest"]
    manifests = [json.loads(git("show", f"{commit}:{p}")) for p in names]
    recorded = max(manifests, key=lambda m: version_key(m["version"]))
    problems = []
    if subprocess.run(["git", "-C", str(REPO), "merge-base", "--is-ancestor", recorded["commit"],
                       commit]).returncode:
        problems.append(f"freeze commit {recorded['commit']} is not an ancestor")
    log_now = git("show", f"{commit}:{AMENDMENTS}", binary=True)
    log_then = git("show", f"{recorded['commit']}:{AMENDMENTS}", binary=True)
    if not log_now.startswith(log_then):
        problems.append(f"{AMENDMENTS} was edited, not appended to")
    if recorded["version"] != "v1.0" and recorded["version"].encode() not in log_now:
        problems.append(f"{recorded['version']} has no entry in {AMENDMENTS}")
    now, then = tracked(commit), recorded["files_sha256"]
    problems += [f"changed or removed: {p}" for p in sorted(then)
                 if must_match(p) and now.get(p) != then[p]]
    problems += [f"added: {p}" for p in sorted(set(now) - set(then)) if must_not_appear(p, then)]
    return recorded, problems


def build(commit, version):
    commit = git("rev-parse", f"{commit}^{{commit}}")
    files = tracked(commit)
    with tempfile.TemporaryDirectory() as tmp:
        archive = git("archive", "--format=tar", commit, binary=True)
        subprocess.run(["tar", "-x", "-C", tmp], input=archive, check=True)
        probe = subprocess.run([sys.executable, "-I", "-c", PROBE, str(Path(tmp) / "src")],
                               capture_output=True, text=True, check=True, cwd=tmp)
        try:
            tests = subprocess.run([sys.executable, "-I", "-m", "unittest", "discover", "-s", "tests"],
                                   capture_output=True, text=True, cwd=tmp, timeout=900)
        except subprocess.TimeoutExpired:
            tests = subprocess.CompletedProcess([], -1, "", "TIMEOUT after 900 s")
        config = json.loads((Path(tmp) / "experiments/heldout-v1/config.json").read_text())
    lines = tests.stderr.strip().splitlines()
    planner = json.loads(probe.stdout)
    return {
        "manifest": "Mylonite method freeze (docs/FREEZE.md)",
        "version": version,
        "commit": commit,
        "tree": git("rev-parse", f"{commit}^{{tree}}"),
        "commit_time": git("show", "-s", "--format=%cI", commit),
        "commit_subject": git("show", "-s", "--format=%s", commit),
        "prompt": {k: v for k, v in planner.items() if k != "methods"},
        "methods": planner["methods"],
        "heldout_config": config,
        "tests": {"command": "python3 -I -m unittest discover -s tests (in an export of the commit)",
                  "python": sys.version.split()[0],
                  "exit_code": tests.returncode,  # durations vary from run to run, so are dropped
                  "summary": [l.split(" in ")[0] for l in lines if l.startswith(("Ran ", "OK", "FAILED"))]},
        "scope": {name: sorted(p for p in files if p.startswith(prefixes))
                  for name, prefixes in SCOPE.items()},
        "files_sha256": files,
        "verify_with": "python3 freeze/manifest.py verify <this file>",
    }


def dump(manifest):
    return json.dumps(manifest, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main():
    if len(sys.argv) == 5 and sys.argv[1] == "write":
        out = Path(sys.argv[4])
        out.parent.mkdir(parents=True, exist_ok=True)
        manifest = build(sys.argv[2], sys.argv[3])
        out.write_text(dump(manifest))
        print(f"{out}: sha256 {hashlib.sha256(out.read_bytes()).hexdigest()}; commit "
              f"{manifest['commit']}; {len(manifest['files_sha256'])} files; tests "
              f"{' '.join(manifest['tests']['summary'])}")
    elif len(sys.argv) == 3 and sys.argv[1] == "verify":
        path = Path(sys.argv[2])
        recorded = json.loads(path.read_text())
        rebuilt = build(recorded["commit"], recorded["version"])
        diffs = [k for k in sorted(set(recorded) | set(rebuilt))
                 if k != "tests" and recorded.get(k) != rebuilt.get(k)]
        canonical = dump(recorded) == path.read_text()
        print(f"{path}: sha256 {hashlib.sha256(path.read_bytes()).hexdigest()}")
        print(f"commit {recorded['commit']} ({recorded['commit_time']}), "
              f"{len(recorded['files_sha256'])} files")
        if diffs or not canonical:
            sys.exit(f"MISMATCH: {', '.join(diffs) or 'not in canonical form'}")
        if recorded["tests"] != rebuilt["tests"]:  # depends on the machine (skips, Python version)
            print(f"note: tests here {rebuilt['tests']['summary']} (Python "
                  f"{rebuilt['tests']['python']}); recorded {recorded['tests']['summary']} (Python "
                  f"{recorded['tests']['python']})")
        print("verified: every hash, the prompt fingerprint and the held-out config match the commit")
    elif len(sys.argv) in (2, 3) and sys.argv[1] == "check":
        commit = git("rev-parse", f"{sys.argv[2] if len(sys.argv) == 3 else 'HEAD'}^{{commit}}")
        recorded, problems = check(commit)
        if problems:
            sys.exit(f"{commit}: refused under freeze "
                     f"{recorded['version'] if recorded else '(none)'}:\n  " + "\n  ".join(problems))
        print(f"{commit}: matches freeze {recorded['version']} ({recorded['commit']}); "
              f"{sum(map(must_match, recorded['files_sha256']))} files checked")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
