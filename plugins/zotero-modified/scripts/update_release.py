#!/usr/bin/env python3
"""Check and safely stage updates from a Zotero Modified GitHub release feed."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PLUGIN_MANIFEST = ROOT / "plugins" / "zotero-modified" / ".codex-plugin" / "plugin.json"
RELEASE_SOURCE = ROOT / "plugins" / "zotero-modified" / ".codex-plugin" / "release-source.json"
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
USER_AGENT = "Zotero-Modified-for-Codex/1.0"


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class UpdatePlan:
    state: str
    installed_version: str
    latest_version: str
    repository: str
    release_page: str
    published_at: str | None
    bundle_url: str | None
    checksums_url: str | None
    marketplace: str


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise UpdateError(f"Could not read {path}: {error}") from error


def normalize_repository(value: str | None) -> str | None:
    if value is None:
        return None
    repository = value.strip().removesuffix("/")
    if repository.startswith("https://github.com/"):
        repository = repository.removeprefix("https://github.com/").removesuffix(".git")
    if not REPOSITORY_PATTERN.fullmatch(repository):
        raise UpdateError(
            "Expected GitHub repository in OWNER/REPOSITORY form, "
            f"got {value!r}"
        )
    return repository


def version_key(version: str) -> tuple[int, int, int]:
    match = VERSION_PATTERN.fullmatch(version)
    if not match:
        raise UpdateError(f"Expected a stable MAJOR.MINOR.PATCH version, got {version!r}")
    return tuple(int(part) for part in match.groups())


def read_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except urllib.error.URLError as error:
        raise UpdateError(f"Could not download {url}: {error}") from error


def read_remote_json(url: str) -> dict:
    try:
        return json.loads(read_bytes(url).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UpdateError(f"Expected JSON from {url}: {error}") from error


def asset_url(release: dict, name: str) -> str:
    for asset in release.get("assets", []):
        if asset.get("name") == name and isinstance(asset.get("browser_download_url"), str):
            return asset["browser_download_url"]
    raise UpdateError(f"Release is missing required asset {name!r}")


def installed_configuration(repository_override: str | None) -> tuple[str, str, str]:
    plugin = read_json(PLUGIN_MANIFEST)
    source = read_json(RELEASE_SOURCE)
    installed_version = str(plugin.get("version", ""))
    version_key(installed_version)
    repository = normalize_repository(repository_override or source.get("githubRepository"))
    if not repository:
        raise UpdateError(
            "No GitHub release feed is configured. Install a published ZIP release, or pass "
            "--repository OWNER/REPOSITORY while testing a development checkout."
        )
    marketplace = str(source.get("marketplace", "zotero-modified-private"))
    return installed_version, repository, marketplace


def build_update_plan(repository_override: str | None = None) -> UpdatePlan:
    installed_version, repository, marketplace = installed_configuration(repository_override)
    release = read_remote_json(f"https://api.github.com/repos/{repository}/releases/latest")
    latest_version = str(release.get("tag_name", "")).removeprefix("v")
    version_key(latest_version)
    release_page = str(release.get("html_url", f"https://github.com/{repository}/releases/latest"))
    if version_key(latest_version) <= version_key(installed_version):
        return UpdatePlan(
            state="up_to_date",
            installed_version=installed_version,
            latest_version=latest_version,
            repository=repository,
            release_page=release_page,
            published_at=release.get("published_at"),
            bundle_url=None,
            checksums_url=None,
            marketplace=marketplace,
        )
    bundle_name = f"zotero-modified-{latest_version}.zip"
    return UpdatePlan(
        state="update_available",
        installed_version=installed_version,
        latest_version=latest_version,
        repository=repository,
        release_page=release_page,
        published_at=release.get("published_at"),
        bundle_url=asset_url(release, bundle_name),
        checksums_url=asset_url(release, "checksums.json"),
        marketplace=marketplace,
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def expected_checksum(checksums: dict, file_name: str) -> str:
    for artifact in checksums.get("artifacts", []):
        if artifact.get("file") == file_name and isinstance(artifact.get("sha256"), str):
            return artifact["sha256"].lower()
    raise UpdateError(f"checksums.json does not contain a SHA-256 for {file_name!r}")


def safe_extract(archive_bytes: bytes, target: Path) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            invalid_member = archive.testzip()
            if invalid_member:
                raise UpdateError(f"Downloaded ZIP is corrupt at {invalid_member!r}")
            root = target.resolve()
            for member in archive.infolist():
                member_target = (target / member.filename).resolve()
                try:
                    member_target.relative_to(root)
                except ValueError as error:
                    raise UpdateError(f"Unsafe ZIP member {member.filename!r}") from error
            archive.extractall(target)
    except zipfile.BadZipFile as error:
        raise UpdateError(f"Downloaded bundle is not a valid ZIP: {error}") from error


def verify_staging_directory(staging: Path, plan: UpdatePlan) -> None:
    marketplace = staging / ".agents" / "plugins" / "marketplace.json"
    manifest = staging / "plugins" / "zotero-modified" / ".codex-plugin" / "plugin.json"
    source = staging / "plugins" / "zotero-modified" / ".codex-plugin" / "release-source.json"
    if not marketplace.is_file() or not manifest.is_file() or not source.is_file():
        raise UpdateError("Downloaded bundle is missing the expected local marketplace structure")
    if str(read_json(manifest).get("version", "")) != plan.latest_version:
        raise UpdateError("Downloaded bundle version does not match the GitHub release tag")
    if normalize_repository(read_json(source).get("githubRepository")) != plan.repository:
        raise UpdateError("Downloaded bundle points to a different GitHub release feed")


def updater_script() -> str:
    return r'''param(
  [Parameter(Mandatory=$true)][string]$Root,
  [Parameter(Mandatory=$true)][string]$Staging,
  [Parameter(Mandatory=$true)][string]$Backup,
  [Parameter(Mandatory=$true)][string]$Log,
  [Parameter(Mandatory=$true)][string]$Marketplace,
  [Parameter(Mandatory=$true)][bool]$ReinstallCodex
)
$ErrorActionPreference = 'Stop'
Start-Sleep -Seconds 3
try {
  if (-not (Test-Path -LiteralPath $Staging)) { throw "Staging folder was not found: $Staging" }
  if (-not (Test-Path -LiteralPath $Root)) { throw "Installed marketplace folder was not found: $Root" }
  if (Test-Path -LiteralPath $Backup) { throw "Backup target already exists: $Backup" }
  Move-Item -LiteralPath $Root -Destination $Backup
  try {
    Move-Item -LiteralPath $Staging -Destination $Root
  } catch {
    Move-Item -LiteralPath $Backup -Destination $Root
    throw
  }
  $result = [ordered]@{
    state = 'updated'
    updatedAt = (Get-Date).ToUniversalTime().ToString('o')
    root = $Root
    backup = $Backup
    codexReload = 'not-requested'
  }
  if ($ReinstallCodex) {
    $codex = Get-Command codex -ErrorAction SilentlyContinue
    if ($null -eq $codex) {
      $result.codexReload = 'codex-command-not-found'
    } else {
      try {
        & $codex.Source plugin add ("zotero-modified@" + $Marketplace) *>> $Log
        $result.codexReload = 'requested'
      } catch {
        $result.codexReload = 'failed-see-log'
      }
    }
  }
  $result | ConvertTo-Json -Compress | Set-Content -LiteralPath $Log -Encoding UTF8
} catch {
  [ordered]@{
    state = 'failed'
    failedAt = (Get-Date).ToUniversalTime().ToString('o')
    error = $_.Exception.Message
    root = $Root
    staging = $Staging
  } | ConvertTo-Json -Compress | Set-Content -LiteralPath $Log -Encoding UTF8
  exit 1
}'''


def schedule_apply(staging: Path, plan: UpdatePlan, reinstall_codex: bool) -> dict:
    timestamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    backup = ROOT.with_name(f"{ROOT.name}.backup-{plan.installed_version}-{timestamp}")
    log = ROOT.parent / f".{ROOT.name}.update-{timestamp}.json"
    helper = Path(tempfile.gettempdir()) / f"zotero-modified-update-{uuid.uuid4().hex}.ps1"
    helper.write_text(updater_script(), encoding="utf-8")
    flags = 0
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags |= subprocess.DETACHED_PROCESS
    try:
        process = subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(helper),
                str(ROOT),
                str(staging),
                str(backup),
                str(log),
                plan.marketplace,
                str(bool(reinstall_codex)).lower(),
            ],
            creationflags=flags,
            close_fds=True,
        )
    except OSError as error:
        raise UpdateError(f"Could not start the Windows update helper: {error}") from error
    return {
        "state": "update_scheduled",
        "latest_version": plan.latest_version,
        "process_id": process.pid,
        "backup": str(backup),
        "log": str(log),
        "reinstall_codex": reinstall_codex,
        "next_step": "Wait for the helper to finish, then start a new Codex task.",
    }


def apply_update(plan: UpdatePlan, reinstall_codex: bool) -> dict:
    if plan.state == "up_to_date":
        return asdict(plan)
    if (ROOT / ".git").exists():
        raise UpdateError(
            "This is a Git checkout, so the release updater will not replace it. Use `git pull --ff-only` "
            "after resolving any local changes, then reinstall the Codex plugin from its marketplace."
        )
    if not plan.bundle_url or not plan.checksums_url:
        raise UpdateError("Update plan is incomplete")
    checksums = read_remote_json(plan.checksums_url)
    bundle_name = f"zotero-modified-{plan.latest_version}.zip"
    bundle = read_bytes(plan.bundle_url)
    expected = expected_checksum(checksums, bundle_name)
    observed = sha256_bytes(bundle)
    if observed != expected:
        raise UpdateError(
            f"SHA-256 mismatch for {bundle_name}: expected {expected}, received {observed}"
        )
    staging = ROOT.parent / f".{ROOT.name}.staging-{plan.latest_version}-{uuid.uuid4().hex[:8]}"
    staging.mkdir(parents=False, exist_ok=False)
    try:
        safe_extract(bundle, staging)
        verify_staging_directory(staging, plan)
        return schedule_apply(staging, plan, reinstall_codex)
    except Exception:
        # Preserve the staged files for inspection if extraction succeeded but validation failed.
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Check or stage Zotero Modified release updates")
    parser.add_argument("--repository", help="Override the configured GitHub OWNER/REPOSITORY")
    parser.add_argument("--apply", action="store_true", help="Download, verify, and schedule the update")
    parser.add_argument("--yes", action="store_true", help="Confirm replacing a release ZIP installation")
    parser.add_argument(
        "--reinstall-codex",
        action="store_true",
        help="Ask the helper to run `codex plugin add` after the files are replaced",
    )
    args = parser.parse_args()
    if args.yes and not args.apply:
        parser.error("--yes is only valid with --apply")
    if args.apply and not args.yes:
        parser.error("Refusing to replace an installed release bundle without --yes")
    try:
        plan = build_update_plan(args.repository)
        result = apply_update(plan, args.reinstall_codex) if args.apply else asdict(plan)
    except UpdateError as error:
        print(json.dumps({"state": "error", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
