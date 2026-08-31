from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "zontex.py"
SPEC = importlib.util.spec_from_file_location("zontex_metadata_test", SCRIPT)
assert SPEC and SPEC.loader
zontex = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = zontex
SPEC.loader.exec_module(zontex)


def item(*, tags: list[str], extra: str = "", version: int = 4) -> dict:
    return {
        "key": "ITEM0001",
        "version": version,
        "itemType": "journalArticle",
        "title": "Example",
        "tags": [{"tag": tag} for tag in tags],
        "extra": extra,
    }


class MetadataProfileTests(unittest.TestCase):
    def test_profile_uses_nine_stable_colors_and_identifier_first(self):
        profile = zontex.load_metadata_profile()
        self.assertEqual(len(profile["palette"]), 9)
        self.assertEqual([row["position"] for row in profile["palette"]], list(range(9)))
        self.assertEqual(profile["identifierPolicy"]["mode"], "identifier-first")
        self.assertFalse(profile["identifierPolicy"]["crossValidate"])

    def test_audit_distinguishes_status_choices_from_multiple_assignments(self):
        profile = zontex.load_metadata_profile()
        problems = zontex.metadata_violations(
            item(
                tags=[
                    "/To Read",
                    "/Reading",
                    "/Done",
                    "Role/Core",
                    "#Topic/Example",
                ],
                extra="rate: 5",
            ),
            profile,
        )
        self.assertIn("multiple-statuses", problems)
        self.assertNotIn("primary-role-count", problems)

    def test_metadata_patch_preserves_unmanaged_tags_and_manual_status(self):
        profile = zontex.load_metadata_profile()
        data = item(
            tags=["/Reading", "Legacy", "Role/Context", "#Topic/Old"],
            extra="Citation Key: Example\nrate: 2",
        )
        patch = zontex.make_metadata_patch(
            data,
            {
                "key": "ITEM0001",
                "primaryRole": "Role/Method",
                "secondary": ["Signal/Validation"],
                "topics": ["#Topic/New"],
                "rating": 4,
            },
            profile,
        )
        names = {tag["tag"] for tag in patch["tags"]}
        self.assertEqual(
            names,
            {"/Reading", "Legacy", "Role/Method", "Signal/Validation", "#Topic/New"},
        )
        self.assertEqual(patch["extra"], "Citation Key: Example\nrate: 4")

    def test_rating_replaces_malformed_managed_line(self):
        self.assertEqual(
            zontex.update_extra_rating("Citation Key: Example\nrate: unknown", 3),
            "Citation Key: Example\nrate: 3",
        )

    def test_metadata_proposal_requires_the_reviewed_item_version(self):
        with self.assertRaises(SystemExit):
            zontex.validate_metadata_proposal(
                {"key": "ITEM0001", "rating": 3},
                zontex.load_metadata_profile(),
                0,
            )

    @mock.patch.object(zontex, "commit_item_patches")
    @mock.patch.object(zontex, "select_items")
    @mock.patch.object(zontex, "bridge_statuses")
    def test_set_status_does_not_write_only_to_reorder_tags(
        self, bridge_statuses, select_items, commit_item_patches
    ):
        bridge_statuses.return_value = [{"name": "/Reading"}]
        select_items.return_value = [item(tags=["/Reading", "Legacy"])]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            zontex.cmd_set_status(argparse.Namespace(name="/Reading", yes=True))
        result = json.loads(output.getvalue())
        self.assertEqual(result["changedCount"], 0)
        self.assertEqual(result["unchangedCount"], 1)
        commit_item_patches.assert_not_called()

    def test_palette_change_rejects_tenth_color_and_out_of_range_position(self):
        existing = {
            f"Tag {index}": {"name": f"Tag {index}", "position": index}
            for index in range(9)
        }
        with self.assertRaises(SystemExit):
            zontex.validate_colored_tag_change(existing, "Tenth", 0)
        zontex.validate_colored_tag_change(existing, "Tag 0", 1)
        with self.assertRaises(SystemExit):
            zontex.validate_colored_tag_change(existing, "Tag 0", 9)

    @mock.patch.object(zontex, "commit_item_patches")
    @mock.patch.object(zontex, "metadata_items_by_keys")
    @mock.patch.object(zontex, "read_metadata_manifest")
    def test_curate_metadata_batches_once_and_verifies_once(
        self, read_metadata_manifest, metadata_items_by_keys, commit_item_patches
    ):
        before = item(
            tags=["/Reading", "Legacy", "Role/Context", "#Topic/Old"],
            extra="rate: 2",
        )
        after = item(
            tags=["/Reading", "Legacy", "Role/Method", "#Topic/New"],
            extra="rate: 4",
            version=5,
        )
        metadata_items_by_keys.side_effect = [[before], [after]]
        commit_item_patches.return_value = ([{"status": 200}], {})
        proposal = {
            "key": "ITEM0001",
            "expectedVersion": 4,
            "primaryRole": "Role/Method",
            "secondary": [],
            "topics": ["#Topic/New"],
            "rating": 4,
        }
        read_metadata_manifest.return_value = (zontex.load_metadata_profile(), [proposal])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            zontex.cmd_curate_metadata(
                argparse.Namespace(file="metadata.json", expect_count=1, yes=True)
            )
        result = json.loads(output.getvalue())
        self.assertEqual(result["outcome"], "changed")
        self.assertEqual(result["verifiedCount"], 1)
        self.assertNotIn("patch", json.dumps(result))
        commit_item_patches.assert_called_once()
        self.assertEqual(metadata_items_by_keys.call_count, 2)


if __name__ == "__main__":
    unittest.main()
