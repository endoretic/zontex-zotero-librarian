#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "zotero-modified"
ADDON = ROOT / "companion" / "zotero-modified-bridge"
MARKETPLACE = ROOT / ".agents" / "plugins" / "marketplace.json"
DIST = ROOT / "dist"
RELEASE_SOURCE = PLUGIN / ".codex-plugin" / "release-source.json"
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_zip_text(archive: zipfile.ZipFile, name: str, text: str) -> None:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, text)


def zip_tree(source: Path, target: Path, replacements: dict[Path, str] | None = None) -> None:
    replacements = replacements or {}
    with zipfile.ZipFile(
        target,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=False,
    ) as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            relative = path.relative_to(source)
            replacement = replacements.get(relative)
            if replacement is None:
                archive.write(path, relative.as_posix())
            else:
                write_zip_text(archive, relative.as_posix(), replacement)


def normalize_repository(value: str | None) -> str | None:
    if value is None:
        return None
    repository = value.strip().removesuffix("/")
    if repository.startswith("https://github.com/"):
        repository = repository.removeprefix("https://github.com/").removesuffix(".git")
    if not REPOSITORY_PATTERN.fullmatch(repository):
        raise ValueError(
            "Expected GitHub repository in OWNER/REPOSITORY form, "
            f"got {value!r}"
        )
    return repository


def plugin_install_guide(version: str, repository: str | None) -> str:
    automatic_update = (
        "The installed Bridge checks this release feed through Zotero's native add-on updater. "
        "For the Codex package, use `@Zotero Modified check for updates` periodically; review "
        "the JSON preview, then explicitly approve the update."
        if repository
        else "For a local build, Bridge update behavior follows its source manifest. GitHub "
        "Actions generates the release metadata used by published builds."
    )
    return f"""# Zotero Modified {version}: local installation

This ZIP is a self-contained local Codex marketplace bundle. Keep this directory intact after
extracting it: `.agents/plugins/marketplace.json` refers to `plugins/zotero-modified`.

## Install

1. Extract this ZIP to a stable local directory.
2. In Codex, add that extracted directory as a local marketplace, then install
   `zotero-modified` from `zotero-modified-private`.
3. First use requires one manual Zotero action: install the matching
   `zotero-modified-bridge-{version}.xpi` through Zotero's Plugins/Add-ons Manager and restart
   Zotero. Codex must remind you of this step, but cannot silently confirm it for you. The Bridge
   requires Zotero 10.x.
4. Start a new Codex task and run `@Zotero Modified status` before requesting writes.
5. Only after `status` reports `modifiedBridge.available: true`, remove installation artifacts
   that Codex downloaded or copied: the release ZIP, XPI installer copy, checksum/release-note
   copies, and scratch extraction/staging directories. Keep this stable marketplace directory,
   Git checkouts, backups, Zotero profile files, and unrelated user files.

## Updates

{automatic_update}

## Uninstall

Remove **Zotero Modified** from Codex's Plugins view. In Zotero's Add-ons Manager, remove
**Zotero Modified Bridge**, then restart Zotero. You may remove the extracted marketplace folder
only after the Codex plugin has been removed.
"""


def release_source_config(repository: str | None) -> str:
    source = read_json(RELEASE_SOURCE)
    source["githubRepository"] = repository
    return json.dumps(source, ensure_ascii=False, indent=2) + "\n"


def zip_marketplace_bundle(target: Path, version: str, repository: str | None) -> None:
    replacement_path = RELEASE_SOURCE.relative_to(PLUGIN)
    with zipfile.ZipFile(
        target,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=False,
    ) as archive:
        archive.write(MARKETPLACE, ".agents/plugins/marketplace.json")
        write_zip_text(archive, "INSTALL.md", plugin_install_guide(version, repository))
        for path in sorted(PLUGIN.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            relative = path.relative_to(PLUGIN)
            archive_path = (Path("plugins") / "zotero-modified" / relative).as_posix()
            if relative == replacement_path:
                write_zip_text(archive, archive_path, release_source_config(repository))
            else:
                archive.write(path, archive_path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def github_url(repository: str, path: str) -> str:
    return f"https://github.com/{repository}/{path.lstrip('/')}"


def updates_manifest(repository: str, version: str, addon_manifest: dict, xpi: Path) -> dict:
    zotero = addon_manifest["applications"]["zotero"]
    addon_id = zotero["id"]
    return {
        "addons": {
            addon_id: {
                "updates": [
                    {
                        "version": version,
                        "update_link": github_url(
                            repository,
                            f"releases/download/v{version}/{xpi.name}",
                        ),
                        "update_hash": f"sha256:{sha256(xpi)}",
                        "applications": {
                            "zotero": {
                                "strict_min_version": zotero["strict_min_version"],
                                "strict_max_version": zotero["strict_max_version"],
                            }
                        },
                    }
                ]
            }
        }
    }


def release_addon_manifest(addon_manifest: dict, repository: str | None) -> dict:
    result = json.loads(json.dumps(addon_manifest))
    if repository:
        result["applications"]["zotero"]["update_url"] = github_url(
            repository, "releases/latest/download/updates.json"
        )
    return result


def release_notes(version: str, artifacts: list[Path], repository: str | None) -> str:
    checksums = {path.name: sha256(path) for path in artifacts}
    artifact_rows = "\n".join(
        f"| `{path.name}` | `{checksums[path.name]}` |" for path in artifacts
    )
    if repository:
        update_note = f"""## Updates

- **Zotero Modified Bridge:** Zotero checks
  `{github_url(repository, 'releases/latest/download/updates.json')}` through its native
  add-on updater. In Zotero's Plugins window, keep **Update Add-ons Automatically** enabled;
  a manual check is also available from its gear menu.
- **Zotero Modified for Codex:** ask `@Zotero Modified` to check for updates. It previews the
  version and verifies the release SHA-256 before an explicitly approved update. The updater
  keeps a timestamped backup, attempts to reinstall the Codex plugin, and requires a new task.
"""
    else:
        update_note = """## Updates

This local build was made without a GitHub repository identifier, so it does not include a
release feed. GitHub Actions supplies the update feed for published releases.
"""
    return f"""# Zotero Modified {version}

## Compatibility

- **Codex:** Codex Desktop with local marketplace support.
- **Zotero Modified Bridge:** Zotero **10.0–10.x**.
- **Version pairing:** install the ZIP and XPI with the exact same release version.

## Release assets and SHA-256

| Asset | SHA-256 |
| --- | --- |
{artifact_rows}

`SHA256SUMS.txt` and `checksums.json` contain the same artifact hashes in machine- and
shell-friendly forms.

{update_note}

## Install

1. Download both the ZIP and XPI from this release, then verify their SHA-256 values.
2. Extract `zotero-modified-{version}.zip` to a stable local folder. Do not move only its
   `plugins` subfolder: the included `.agents/plugins/marketplace.json` is required.
3. In Codex, add the extracted folder as a local marketplace and install
   `zotero-modified@zotero-modified-private`.
4. Complete the required one-time manual step in Zotero's Plugins/Add-ons Manager: choose
   **Install Add-on From File…**, select `zotero-modified-bridge-{version}.xpi`, and restart
   Zotero. Codex must remind the user of this step rather than silently bypassing it.
5. Open a new Codex task and run `@Zotero Modified status` before allowing writes.
6. After `status` reports `modifiedBridge.available: true`, remove only installer artifacts
   downloaded or copied for this installation: the release ZIP, XPI installer copy,
   checksum/release-note copies, and scratch extraction/staging directories. Keep the stable
   marketplace directory, Git checkouts, backups, Zotero profile files, and unrelated user files.

## Uninstall

Remove **Zotero Modified** in Codex's Plugins view. Remove **Zotero Modified Bridge** in
Zotero's Add-ons Manager and restart Zotero. Remove the extracted marketplace directory only after
the Codex plugin has been removed.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Codex plugin and Zotero companion XPI")
    parser.add_argument("--clean", action="store_true", help="Remove the existing dist directory")
    parser.add_argument(
        "--github-repository",
        help="Publish update metadata for this GitHub OWNER/REPOSITORY release feed",
    )
    args = parser.parse_args()

    try:
        repository = normalize_repository(args.github_repository)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    plugin_manifest = read_json(PLUGIN / ".codex-plugin" / "plugin.json")
    addon_manifest = read_json(ADDON / "manifest.json")
    plugin_version = str(plugin_manifest.get("version", ""))
    companion_version = str(addon_manifest.get("version", ""))
    if plugin_version != companion_version:
        raise SystemExit(
            "Plugin and companion versions must match: "
            f"plugin={plugin_version!r}, companion={companion_version!r}"
        )
    if not RELEASE_SOURCE.is_file():
        raise SystemExit(f"Missing release source descriptor: {RELEASE_SOURCE}")
    version = plugin_version

    if args.clean and DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True, exist_ok=True)

    bundle = DIST / f"zotero-modified-{version}.zip"
    xpi = DIST / f"zotero-modified-bridge-{version}.xpi"
    if not MARKETPLACE.is_file():
        raise SystemExit(f"Missing local marketplace descriptor: {MARKETPLACE}")
    zip_marketplace_bundle(bundle, version, repository)

    addon_for_release = release_addon_manifest(addon_manifest, repository)
    zip_tree(
        ADDON,
        xpi,
        {Path("manifest.json"): json.dumps(addon_for_release, ensure_ascii=False, indent=2) + "\n"},
    )

    artifacts = [bundle, xpi]
    manifest = {
        "version": version,
        "githubRepository": repository,
        "artifacts": [
            {"file": path.name, "sha256": sha256(path), "bytes": path.stat().st_size}
            for path in artifacts
        ],
    }
    (DIST / "checksums.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (DIST / "SHA256SUMS.txt").write_text(
        "".join(f"{item['sha256']}  {item['file']}\n" for item in manifest["artifacts"]),
        encoding="utf-8",
    )
    if repository:
        (DIST / "updates.json").write_text(
            json.dumps(updates_manifest(repository, version, addon_manifest, xpi), indent=2) + "\n",
            encoding="utf-8",
        )
    (DIST / "RELEASE_NOTES.md").write_text(
        release_notes(version, artifacts, repository), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
