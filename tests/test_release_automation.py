from __future__ import annotations

import importlib.util
import io
import sys
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
RELEASE_UPDATER = load_module(
    "release_updater", "plugins/zotero-modified/scripts/update_release.py"
)


class ReleaseAutomationTests(unittest.TestCase):
    def test_functional_paths_request_a_patch_release(self) -> None:
        policy = RELEASE_POLICY.classify(
            [
                "README.md",
                "companion/zotero-modified-bridge/bootstrap.js",
                "plugins/zotero-modified/scripts/zotero_modified.py",
            ]
        )
        self.assertEqual(policy.release_kind, "patch")
        self.assertEqual(
            policy.functional_files,
            [
                "companion/zotero-modified-bridge/bootstrap.js",
                "plugins/zotero-modified/scripts/zotero_modified.py",
            ],
        )
        self.assertEqual(policy.nonfunctional_files, ["README.md"])

    def test_nonfunctional_paths_do_not_request_a_release(self) -> None:
        policy = RELEASE_POLICY.classify(
            [
                ".github/workflows/release.yml",
                "README.md",
                "plugins/zotero-modified/assets/flower_a.png",
            ]
        )
        self.assertEqual(policy.release_kind, "none")

    def test_initial_push_uses_git_diff_tree_root(self) -> None:
        completed = Mock(stdout="plugins/zotero-modified/scripts/update_release.py\n")
        with patch.object(RELEASE_POLICY.subprocess, "run", return_value=completed) as run:
            changed = RELEASE_POLICY.git_changed_files(RELEASE_POLICY.ZERO_SHA, "HEAD", False)
        self.assertEqual(changed, ["plugins/zotero-modified/scripts/update_release.py"])
        self.assertIn("--root", run.call_args.args[0])

    def test_patch_versions_are_incremented_without_changing_major_or_minor(self) -> None:
        self.assertEqual(BUMP_VERSION.next_patch("0.1.0"), "0.1.1")
        self.assertEqual(BUMP_VERSION.next_patch("3.14.99"), "3.14.100")
        with self.assertRaises(ValueError):
            BUMP_VERSION.next_patch("0.1.0-dev")

    def test_github_repository_values_are_normalized_for_release_metadata(self) -> None:
        self.assertEqual(
            BUILD_RELEASE.normalize_repository("https://github.com/example/zotero-modified.git"),
            "example/zotero-modified",
        )
        with self.assertRaises(ValueError):
            BUILD_RELEASE.normalize_repository("example/not a repository")

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
