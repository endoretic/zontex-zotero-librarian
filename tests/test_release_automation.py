from __future__ import annotations

import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


RELEASE_POLICY = load_module("release_policy", "scripts/release_policy.py")
BUMP_VERSION = load_module("bump_version", "scripts/bump_version.py")
BUILD_RELEASE = load_module("build_release", "scripts/build_release.py")
SYNC_UPSTREAM = load_module("sync_upstream", "scripts/sync_upstream.py")
RELEASE_UPDATER = load_module(
    "release_updater", "plugins/zontex/scripts/update_release.py"
)


class ReleaseAutomationTests(unittest.TestCase):
    def test_upstream_state_uses_a_real_tree_sha(self) -> None:
        state = json.loads((ROOT / "upstream.json").read_text(encoding="utf-8"))
        self.assertRegex(state["pinnedCommit"], r"^[0-9a-f]{40}$")

    def test_upstream_copy_does_not_inherit_executable_mode(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            source = root / "source.py"
            target = root / "target.py"
            source.write_text("new\n", encoding="utf-8")
            target.write_text("old\n", encoding="utf-8")
            if os.name != "nt":
                source.chmod(0o755)
                target.chmod(0o644)

            SYNC_UPSTREAM.copy_vendored_file(source, target)

            self.assertEqual(target.read_text(encoding="utf-8"), "new\n")
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o644)

    def test_zontex_identity_is_consistent_across_manifests(self) -> None:
        marketplace = json.loads(
            (ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8")
        )
        plugin = json.loads(
            (ROOT / "plugins/zontex/.codex-plugin/plugin.json").read_text(
                encoding="utf-8"
            )
        )
        source = json.loads(
            (ROOT / "plugins/zontex/.codex-plugin/release-source.json").read_text(
                encoding="utf-8"
            )
        )
        companion = json.loads(
            (ROOT / "companion/zontex-bridge/manifest.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(marketplace["name"], "zontex-zotero-librarian")
        self.assertEqual(marketplace["interface"]["displayName"], "Zontex")
        self.assertEqual(marketplace["plugins"][0]["name"], "zontex")
        self.assertEqual(marketplace["plugins"][0]["source"]["path"], "./plugins/zontex")
        self.assertEqual(plugin["name"], "zontex")
        self.assertEqual(plugin["interface"]["displayName"], "Zontex")
        self.assertEqual(source["marketplace"], "zontex-zotero-librarian")
        self.assertEqual(companion["name"], "Zontex Bridge")
        self.assertEqual(
            companion["applications"]["zotero"]["id"],
            "zontex-bridge@endoretic.github.io",
        )
        self.assertEqual(BUILD_RELEASE.PLUGIN, ROOT / "plugins/zontex")
        self.assertEqual(BUILD_RELEASE.ADDON, ROOT / "companion/zontex-bridge")

    def test_plugin_and_companion_manifests_share_stable_version(self) -> None:
        plugin = json.loads(
            (ROOT / "plugins/zontex/.codex-plugin/plugin.json").read_text(
                encoding="utf-8"
            )
        )
        companion = json.loads(
            (ROOT / "companion/zontex-bridge/manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(plugin["version"], companion["version"])
        self.assertRegex(plugin["version"], r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

    def test_repository_and_plugin_use_gplv3_with_upstream_notice(self) -> None:
        plugin = json.loads(
            (ROOT / "plugins/zontex/.codex-plugin/plugin.json").read_text(
                encoding="utf-8"
            )
        )
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertEqual(plugin["license"], "GPL-3.0-only")
        self.assertIn("GNU GENERAL PUBLIC LICENSE", license_text)
        self.assertIn("Version 3, 29 June 2007", license_text)
        self.assertIn("OpenAI Zotero plugin", notices)
        self.assertIn("MIT License", notices)

    def test_functional_paths_request_a_patch_release(self) -> None:
        policy = RELEASE_POLICY.classify(
            [
                "README.md",
                "companion/zontex-bridge/bootstrap.js",
                "plugins/zontex/scripts/zontex.py",
            ]
        )
        self.assertEqual(policy.release_kind, "patch")
        self.assertEqual(
            policy.functional_files,
            [
                "companion/zontex-bridge/bootstrap.js",
                "plugins/zontex/scripts/zontex.py",
            ],
        )
        self.assertEqual(policy.nonfunctional_files, ["README.md"])

    def test_nonfunctional_paths_do_not_request_a_release(self) -> None:
        policy = RELEASE_POLICY.classify(
            [
                ".github/workflows/release.yml",
                "README.md",
                "plugins/zontex/assets/flower_a.png",
            ]
        )
        self.assertEqual(policy.release_kind, "none")

    def test_paired_manifest_change_requests_an_explicit_version_release(self) -> None:
        policy = RELEASE_POLICY.classify(
            [
                "plugins/zontex/.codex-plugin/plugin.json",
                "companion/zontex-bridge/manifest.json",
            ]
        )
        self.assertEqual(policy.release_kind, "patch")
        self.assertTrue(policy.explicit_version)

    def test_single_manifest_change_is_not_an_explicit_version_release(self) -> None:
        policy = RELEASE_POLICY.classify(
            ["plugins/zontex/.codex-plugin/plugin.json"]
        )
        self.assertEqual(policy.release_kind, "patch")
        self.assertFalse(policy.explicit_version)

    def test_initial_push_uses_git_diff_tree_root(self) -> None:
        completed = Mock(stdout="plugins/zontex/scripts/update_release.py\n")
        with patch.object(RELEASE_POLICY.subprocess, "run", return_value=completed) as run:
            changed = RELEASE_POLICY.git_changed_files(RELEASE_POLICY.ZERO_SHA, "HEAD", False)
        self.assertEqual(changed, ["plugins/zontex/scripts/update_release.py"])
        self.assertIn("--root", run.call_args.args[0])

    def test_patch_versions_are_incremented_without_changing_major_or_minor(self) -> None:
        self.assertEqual(BUMP_VERSION.next_patch("0.1.0"), "0.1.1")
        self.assertEqual(BUMP_VERSION.next_patch("3.14.99"), "3.14.100")
        with self.assertRaises(ValueError):
            BUMP_VERSION.next_patch("0.1.0-dev")

    def test_github_repository_values_are_normalized_for_release_metadata(self) -> None:
        self.assertEqual(
            BUILD_RELEASE.normalize_repository("https://github.com/example/zontex.git"),
            "example/zontex",
        )
        with self.assertRaises(ValueError):
            BUILD_RELEASE.normalize_repository("example/not a repository")

    def test_local_build_preserves_bridge_update_url(self) -> None:
        manifest = {
            "applications": {
                "zotero": {
                    "id": "bridge@example.test",
                    "update_url": "https://example.test/updates.json",
                }
            }
        }
        built = BUILD_RELEASE.release_addon_manifest(manifest, None)
        self.assertEqual(
            built["applications"]["zotero"]["update_url"],
            "https://example.test/updates.json",
        )
        self.assertIsNot(built, manifest)

    def test_install_guide_requires_manual_xpi_handoff_and_cleanup(self) -> None:
        guide = BUILD_RELEASE.plugin_install_guide("0.1.0", "example/project")
        self.assertIn("one manual Zotero action", guide)
        self.assertIn("zontexBridge.available: true", guide)
        self.assertIn("Keep this stable marketplace directory", guide)

    def test_bridge_reports_runtime_manifest_version(self) -> None:
        bootstrap = (ROOT / "companion/zontex-bridge/bootstrap.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("bridgeVersion = data && data.version", bootstrap)
        self.assertIn("version: bridgeVersion", bootstrap)
        self.assertNotIn('version: "0.1.0"', bootstrap)

    def test_codex_plugin_exposes_and_guards_experimental_annotations(self) -> None:
        plugin = json.loads(
            (ROOT / "plugins/zontex/.codex-plugin/plugin.json").read_text(
                encoding="utf-8"
            )
        )
        skill = (ROOT / "plugins/zontex/skills/zontex/SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("PDF annotations", plugin["interface"]["shortDescription"])
        self.assertTrue(
            any(
                "highlight or underline" in prompt
                for prompt in plugin["interface"]["defaultPrompt"]
            )
        )
        self.assertIn("zontexBridge.compatibility.warnings", skill)
        self.assertIn("reader.capabilities.annotation.warnings", skill)
        self.assertIn("Active PDF annotation is experimental", skill)
        self.assertIn("never send annotations to Trash", skill)
        self.assertIn("注释删除后无法恢复", skill)

    def test_release_updater_rejects_nonstable_versions_and_unsafe_archives(self) -> None:
        self.assertEqual(RELEASE_UPDATER.version_key("1.2.3"), (1, 2, 3))
        with self.assertRaises(RELEASE_UPDATER.UpdateError):
            RELEASE_UPDATER.version_key("1.2.3-dev")
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as zip_file:
            zip_file.writestr("../outside.txt", "unsafe")
        with self.assertRaises(RELEASE_UPDATER.UpdateError):
            RELEASE_UPDATER.safe_extract(archive.getvalue(), ROOT / "never-created-test-target")


if __name__ == "__main__":
    unittest.main()
