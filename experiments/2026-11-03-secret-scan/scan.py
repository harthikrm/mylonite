"""Full-history secret scan of a git repository. Standard library only; run with python3 -I.

  scan.py <repo> <env file>

Scans every object in the object database (reachable or not): blobs, commit and tag messages,
tree entry names. Never prints a secret: hits are shown as pattern name, object, paths, and a
redacted preview (first 4 characters and the length).
"""

import base64
import collections
import json
import re
import subprocess
import sys

repo, env_path = sys.argv[1], sys.argv[2]


def git(*args, data=None):
    return subprocess.run(["git", "-C", repo, *args], input=data, capture_output=True, check=True).stdout


key = None
for line in open(env_path, encoding="utf-8"):
    if line.startswith("MODEL_API_KEY="):
        key = line.split("=", 1)[1].strip().strip('"').strip("'")
if not key or len(key) < 20:
    sys.exit("no usable MODEL_API_KEY in the env file")

# The key, its two ends and middle, and encodings a leak could take.
needles = {"key: full": key.encode(), "key: first 16": key[:16].encode(), "key: last 16": key[-16:].encode(),
           "key: middle 16": key[len(key) // 2 - 8: len(key) // 2 + 8].encode(),
           "key: base64": base64.b64encode(key.encode()).rstrip(b"="),
           "key: base64 Bearer": base64.b64encode(f"Bearer {key}".encode())[:-4]}

PATTERNS = {
    "Meta Model API key (LLM_...)": rb"LLM_[A-Za-z0-9_\-]{16,}",
    "AWS access key": rb"\b(AKIA|ASIA)[0-9A-Z]{16}\b",
    "GitHub token": rb"\b(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})",
    "OpenAI/Anthropic-style key": rb"\bsk-(ant-)?[A-Za-z0-9_\-]{20,}",
    "Stripe live key": rb"\b[rs]k_live_[A-Za-z0-9]{16,}",
    "Slack token": rb"\bxox[abposr]-[A-Za-z0-9\-]{10,}",
    "Google API key": rb"\bAIza[0-9A-Za-z_\-]{35}",
    "private key block": rb"-----BEGIN ([A-Z ]+ )?PRIVATE KEY-----",
    "JWT": rb"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}",
    "Bearer token value": rb"Bearer\s+(?!\$|<|\{|\.\.\.|\*|REDACTED|xxx)[A-Za-z0-9_\-\.=]{16,}",
    "assigned secret": rb"(?i)\b[A-Z0-9_]*(api[_-]?key|secret|token|passw(or)?d)[A-Z0-9_]*\s*[:=]\s*[\"']?(?![\"']?\s*$)(?!\$\{|<|your|xxx|changeme|example|None|null|\"\"|'')[A-Za-z0-9_\-\.\/+=]{12,}",
    "URL with credentials": rb"[a-z][a-z0-9+\-.]*://[^\s/:@\"']+:[^\s/@\"']{6,}@",
}
COMPILED = {name: re.compile(p) for name, p in PATTERNS.items()}

# object id -> paths, from every reachable commit's trees
paths = collections.defaultdict(set)
for line in git("rev-list", "--all", "--objects").decode().splitlines():
    oid, _, path = line.partition(" ")
    if path:
        paths[oid].add(path)
reachable = {l.split(" ")[0] for l in git("rev-list", "--all", "--objects").decode().splitlines()}

objects = [l.split() for l in git("cat-file", "--batch-all-objects", "--batch-check").decode().splitlines()]
key_hits, pattern_hits, counts = [], collections.defaultdict(list), collections.Counter()
for oid, kind, size in objects:
    counts[kind] += 1
    if kind == "tree":
        data = git("ls-tree", oid)  # entry names only matter here
    else:
        data = git("cat-file", "-p", oid) if kind in ("commit", "tag") else git("cat-file", "blob", oid)
    for name, needle in needles.items():
        if needle in data:
            key_hits.append({"needle": name, "object": oid, "kind": kind, "paths": sorted(paths.get(oid, [])),
                             "reachable": oid in reachable})
    for name, rx in COMPILED.items():
        for m in rx.finditer(data):
            s = m.group(0)
            pattern_hits[name].append({"object": oid[:10], "kind": kind, "reachable": oid in reachable,
                                       "paths": sorted(paths.get(oid, []))[:3],
                                       "preview": s[:4].decode(errors="replace") + f"…({len(s)} chars)"})

print(json.dumps({"objects": dict(counts), "reachable_objects": len(reachable),
                  "key_needles_checked": list(needles), "key_hits": key_hits,
                  "pattern_hits": {k: {"count": len(v), "distinct_objects": len({h['object'] for h in v}),
                                       "examples": v[:6]} for k, v in pattern_hits.items()},
                  "patterns_with_no_hits": [k for k in PATTERNS if k not in pattern_hits]}, indent=1))
