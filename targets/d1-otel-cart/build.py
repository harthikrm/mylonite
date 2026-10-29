"""Build the two D1 cart images from the pinned checkout (ARCHITECTURE.md §9).

- buggy: tag 3.1.0 (dedc0178), unmodified.
- fixed: the same tree with src/cart/src/cartstore/ValkeyCartStore.cs taken from the head of
  PR #3825 (060ee206). That PR was written against this exact file (blob 1f4b9037), so nothing
  else changes.

The checkout is fetched beforehand into targets/checkouts/ (git-ignored); this script only reads
it with git and never runs anything from it on the host. Writes a manifest with the commits,
the SHA-256 of every file in each build context, and the resulting image IDs.

Usage: build.py <checkout> <manifest.json>
"""

import hashlib
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TAG_COMMIT = "dedc0178918e260823323b8d95005a8cb924b007"
FIX_COMMIT = "060ee20677b4383f28277069b68d99e234b64dcb"
STORE = "src/cart/src/cartstore/ValkeyCartStore.cs"
IMAGES = {"buggy": "mylonite-d1-cart:buggy-dedc0178", "fixed": "mylonite-d1-cart:fixed-pr3825-060ee206"}


def git(checkout, *args):
    return subprocess.run(["git", "-C", str(checkout), *args], capture_output=True, check=True).stdout


def context(checkout, variant, into):
    with tarfile.open(fileobj=io.BytesIO(git(checkout, "archive", TAG_COMMIT, "src/cart", "pb"))) as tar:
        tar.extractall(into, filter="data")
    if variant == "fixed":
        (into / STORE).write_bytes(git(checkout, "show", f"{FIX_COMMIT}:{STORE}"))
    return {str(p.relative_to(into)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(into.rglob("*")) if p.is_file()}


def main():
    checkout, manifest_path = Path(sys.argv[1]), Path(sys.argv[2])
    assert git(checkout, "rev-parse", "HEAD").decode().strip() == TAG_COMMIT
    assert git(checkout, "rev-parse", FIX_COMMIT).decode().strip() == FIX_COMMIT
    manifest = {"tag_commit": TAG_COMMIT, "fix_commit": FIX_COMMIT,
                "dockerfile_sha256": hashlib.sha256((HERE / "Dockerfile").read_bytes()).hexdigest(),
                "variants": {}}
    for variant, image in IMAGES.items():
        with tempfile.TemporaryDirectory() as tmp:
            files = context(checkout, variant, Path(tmp))
            build = subprocess.run(["docker", "build", "-q", "-t", image, "-f", str(HERE / "Dockerfile"), tmp],
                                   capture_output=True, text=True)
            if build.returncode != 0:
                sys.exit(f"{variant}: docker build failed:\n{build.stderr[-4000:]}")
        image_id = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", image],
                                  capture_output=True, text=True, check=True).stdout.strip()
        manifest["variants"][variant] = {"image": image, "image_id": image_id,
                                         "store_sha256": files[STORE], "context_files": files}
        print(variant, image, image_id, "store", files[STORE][:16])
    manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
