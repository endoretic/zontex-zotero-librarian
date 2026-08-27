#!/usr/bin/env python3
"""Classify a change set for the Zontex release workflow."""
from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


FUNCTIONAL_PREFIXES = (
    "plugins/zontex/scripts/",
    "plugins/zontex/skills/",
)
FUNCTIONAL_FILES = {
    "companion/zontex-bridge/bootstrap.js",
    "scripts/build_release.py",
    "scripts/release_policy.py",
}
ZERO_SHA = "0" * 40


@dataclass(frozen=True)
class ReleasePolicy:
    release_kind: str
    changed_files: list[str]
    functional_files: list[str]
    nonfunctional_files: list[str]


def is_functional(path: str) -> bool:
    return path in FUNCTIONAL_FILES or path.startswith(FUNCTIONAL_PREFIXES)


def classify(paths: list[str], force_patch: bool = False) -> ReleasePolicy:
    changed_files = sorted({path.replace("\\", "/") for path in paths if path})
    functional_files = [path for path in changed_files if is_functional(path)]
    if force_patch:
        functional_files.append("manual release request")
    nonfunctional_files = [path for path in changed_files if path not in functional_files]
    return ReleasePolicy(
        release_kind="patch" if functional_files else "none",
        changed_files=changed_files,
        functional_files=functional_files,
        nonfunctional_files=nonfunctional_files,
    )


def git_changed_files(base: str | None, head: str, working_tree: bool) -> list[str]:
    if working_tree:
        command = ["git", "diff", "--name-only"]
    elif not base or base == ZERO_SHA:
        command = [
            "git",
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-only",
            "-r",
            head,
        ]
    else:
        command = ["git", "diff", "--name-only", base, head]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return result.stdout.splitlines()


def write_github_output(path: Path, policy: ReleasePolicy) -> None:
    values = {
        "release_kind": policy.release_kind,
        "changed": str(bool(policy.changed_files)).lower(),
        "functional_files": ", ".join(policy.functional_files),
        "nonfunctional_files": ", ".join(policy.nonfunctional_files),
    }
    with path.open("a", encoding="utf-8") as stream:
        for key, value in values.items():
            stream.write(f"{key}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify a change set for release automation")
    parser.add_argument("--base", help="Base Git revision for a committed diff")
    parser.add_argument("--head", default="HEAD", help="Head Git revision for a committed diff")
    parser.add_argument("--working-tree", action="store_true", help="Inspect uncommitted changes")
    parser.add_argument("--force-patch", action="store_true", help="Request a patch release explicitly")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()

    if args.working_tree and args.base:
        parser.error("--working-tree and --base cannot be used together")
    policy = classify(
        git_changed_files(args.base, args.head, args.working_tree), args.force_patch
    )
    if args.github_output:
        write_github_output(args.github_output, policy)
    print(json.dumps(asdict(policy), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
