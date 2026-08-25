#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "zotero-modified"
STATE_FILE = ROOT / "upstream.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync the vendored files from OpenAI's Zotero plugin")
    parser.add_argument("upstream", type=Path, help="Path to the upstream plugins/zotero directory")
    parser.add_argument("--commit", default="unknown")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()

    upstream = args.upstream.resolve()
    manifest = read_json(upstream / ".codex-plugin" / "plugin.json")
    state = read_json(STATE_FILE)
    old_version = str(state.get("pinnedVersion", ""))
    old_commit = str(state.get("pinnedCommit", ""))
    new_version = str(manifest["version"])

    copies = {
        upstream / "skills" / "zotero" / "scripts" / "zotero.py": PLUGIN / "scripts" / "zotero.py",
        upstream / "skills" / "zotero" / "references" / "local-api-routes.md": (
            PLUGIN / "skills" / "zotero-modified" / "references" / "upstream-local-api-routes.md"
        ),
        upstream / "assets" / "icon.png": PLUGIN / "assets" / "icon.png",
    }
    for source, target in copies.items():
        if not source.is_file():
            raise SystemExit(f"Missing upstream file: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    version_changed = new_version != old_version
    source_changed = args.commit != old_commit
    if version_changed or source_changed:
        state.update({"pinnedVersion": new_version, "pinnedCommit": args.commit})
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    values = {
        "upstream_version": new_version,
        "upstream_sha_short": args.commit[:12],
        "version_changed": str(version_changed).lower(),
        "source_changed": str(source_changed).lower(),
    }
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as stream:
            for key, value in values.items():
                stream.write(f"{key}={value}\n")
    print(json.dumps(values, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
