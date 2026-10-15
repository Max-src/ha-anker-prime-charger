#!/usr/bin/env python3
"""Build and check the release zip that HACS installs.

hacs.json has "zip_release": true, so HACS downloads
https://github.com/<owner>/<repo>/releases/download/<tag>/anker_prime_charger.zip
and extracts it straight into config/custom_components/anker_prime_charger/.
The zip therefore holds the CONTENTS of custom_components/anker_prime_charger
at its root. HACS's "Downloads" figure is that asset's download count.

Used by .github/workflows/release.yaml and for local checks (same commands):

    python scripts/release-zip.py [--ref REF] [--tag vX.Y.Z] [--output FILE]

The zip is made with `git archive` from the tracked files at REF only (no
__pycache__, login cache or other local files). On any failed check the zip is
deleted and the exit code is non-zero. Standard library only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import zipfile

DOMAIN = "anker_prime_charger"
SOURCE = f"custom_components/{DOMAIN}"
# Must match hacs.json "filename": HACS looks for an asset with this name
ZIP_NAME = f"{DOMAIN}.zip"
REQUIRED_AT_ROOT = ("manifest.json", "__init__.py")


class CheckError(Exception):
    """A check on the zip failed."""


def git(*args: str, cwd: Path) -> str:
    """Run git and return its output."""
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def build(repo: Path, ref: str, output: Path) -> None:
    """Write the zip of the integration folder's tracked files at ref."""
    # autocrlf=false: the zip gets the committed (LF) line endings on any OS
    git(
        "-c",
        "core.autocrlf=false",
        "archive",
        "--format=zip",
        f"--output={output}",
        f"{ref}:{SOURCE}",
        cwd=repo,
    )


def check(repo: Path, ref: str, output: Path, tag: str | None) -> list[str]:
    """Check the zip against the tracked files, the manifest and the tag; return its files."""
    tracked = sorted(
        name.removeprefix(f"{SOURCE}/")
        for name in git(
            "ls-tree", "-r", "--name-only", ref, "--", f"{SOURCE}/", cwd=repo
        ).splitlines()
    )
    if not tracked:
        raise CheckError(f"{SOURCE} has no tracked files at {ref}")

    with zipfile.ZipFile(output) as archive:
        if (bad := archive.testzip()) is not None:
            raise CheckError(f"corrupt entry in the zip: {bad}")
        files = sorted(n for n in archive.namelist() if not n.endswith("/"))
        manifest = (
            json.loads(archive.read("manifest.json"))
            if "manifest.json" in files
            else None
        )

    if files != tracked:
        extra = sorted(set(files) - set(tracked))
        missing = sorted(set(tracked) - set(files))
        raise CheckError(
            f"zip differs from the tracked files: extra={extra} missing={missing}"
        )
    for name in REQUIRED_AT_ROOT:
        if name not in files:
            raise CheckError(f"{name} is not at the root of the zip")
    if cached := [n for n in files if "__pycache__/" in n or n.endswith(".pyc")]:
        raise CheckError(f"compiled Python files in the zip: {cached}")

    if manifest.get("domain") != DOMAIN:
        raise CheckError(
            f"manifest domain is {manifest.get('domain')!r}, expected {DOMAIN!r}"
        )
    if tag is not None:
        if not tag.startswith("v"):
            raise CheckError(f"tag {tag!r} must be v<version> (e.g. v1.2.3)")
        if manifest.get("version") != tag[1:]:
            raise CheckError(
                f"manifest version {manifest.get('version')!r} does not match tag {tag!r}"
            )

    # Once the ref's hacs.json opts in, its filename must be this zip's name
    hacs = json.loads(git("show", f"{ref}:hacs.json", cwd=repo))
    if hacs.get("zip_release") and hacs.get("filename") != ZIP_NAME:
        raise CheckError(
            f"hacs.json filename is {hacs.get('filename')!r}, expected {ZIP_NAME!r}"
        )
    return files


def main() -> int:
    """Build and check the zip; delete it and return 1 on any failure."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--ref", default="HEAD", help="commit or tag to package (default: HEAD)"
    )
    parser.add_argument("--tag", help="release tag; the manifest version must match it")
    parser.add_argument(
        "--output", default=ZIP_NAME, help=f"zip to write (default: {ZIP_NAME})"
    )
    args = parser.parse_args()

    repo = Path(git("rev-parse", "--show-toplevel", cwd=Path.cwd()).strip())
    output = Path(args.output).resolve()
    output.unlink(missing_ok=True)
    try:
        build(repo, args.ref, output)
        files = check(repo, args.ref, output, args.tag)
    except (CheckError, subprocess.CalledProcessError, KeyError, ValueError) as err:
        output.unlink(missing_ok=True)
        detail = (
            err.stderr.strip()
            if isinstance(err, subprocess.CalledProcessError)
            else err
        )
        print(f"release-zip: FAILED: {detail}", file=sys.stderr)
        return 1

    print(
        f"release-zip: OK {output.name} ({output.stat().st_size} bytes, {len(files)} files)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
