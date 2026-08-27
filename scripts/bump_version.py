#!/usr/bin/env python3
"""Bump the paired Codex plugin and Zotero Bridge patch version together."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_MANIFEST = ROOT / "plugins" / "zontex" / ".codex-plugin" / "plugin.json"
ADDON_MANIFEST = ROOT / "companion" / "zontex-bridge" / "manifest.json"
PATCH_VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def next_patch(version: str) -> str:
    match = PATCH_VERSION.fullmatch(version)
    if not match:
        raise ValueError(f"Expected a stable MAJOR.MINOR.PATCH version, got {version!r}")
    major, minor, patch = (int(part) for part in match.groups())
    return f"{major}.{minor}.{patch + 1}"


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bump paired plugin and companion patch versions")
    parser.add_argument("kind", choices=["patch"])
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()

    plugin = read_json(PLUGIN_MANIFEST)
    addon = read_json(ADDON_MANIFEST)
    old_version = str(plugin.get("version", ""))
    if old_version != str(addon.get("version", "")):
        raise SystemExit("Plugin and companion versions must match before bumping")
    new_version = next_patch(old_version)
    plugin["version"] = new_version
    addon["version"] = new_version
    write_json(PLUGIN_MANIFEST, plugin)
    write_json(ADDON_MANIFEST, addon)

    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as stream:
            stream.write(f"old_version={old_version}\nnew_version={new_version}\n")
    print(json.dumps({"old_version": old_version, "new_version": new_version}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
