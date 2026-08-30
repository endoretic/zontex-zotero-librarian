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
SPEC = importlib.util.spec_from_file_location("zontex", SCRIPT)
assert SPEC and SPEC.loader
zontex = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = zontex
SPEC.loader.exec_module(zontex)


def batch_args(**overrides):
    values = {
        "set_values": [],
        "set_json_values": [],
        "clear_fields": [],
        "item_type": None,
        "add_tags": [],
        "remove_tags": [],
        "replace_tags": [],
        "add_collection_keys": [],
        "remove_collection_keys": [],
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def annotation_manifest():
    return {
        "schemaVersion": 1,
        "attachmentKey": "PDF12345",
        "sourceHash": "HASH",
        "annotations": [
            {
                "clientId": "A1",
                "target": {"segmentId": "block:1", "start": 0, "end": 5},
                "expectedText": "Hello",
                "type": "highlight",
                "color": "#ffd400",
                "comment": "Method",
                "tags": ["Method"],
            },
            {
                "clientId": "A2",
                "target": {"segmentId": "block:1", "start": 6, "end": 11},
                "expectedText": "World",
                "type": "underline",
                "color": "#5fb236",
                "comment": "",
                "tags": [],
            },
        ],
    }


class ZontexTests(unittest.TestCase):
    def test_dump_json_falls_back_to_ascii_escapes_for_gbk_stdout(self):
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="gbk", newline="\n")
        try:
            with contextlib.redirect_stdout(stream):
                zontex.dump_json({"copyright": "©"})
            stream.flush()
            self.assertEqual(
                json.loads(raw.getvalue().decode("gbk")),
                {"copyright": "©"},
            )
        finally:
            stream.detach()

    @mock.patch.object(zontex, "request")
    def test_companion_info_reports_manual_install_handoff(self, request):
        request.return_value = zontex.Response(status=404, headers={}, text="Not Found")
        info = zontex.companion_info()
        self.assertFalse(info["available"])
        self.assertTrue(info["manualInstallRequired"])
        self.assertIn("matching Zontex Bridge XPI", info["nextStep"])

    @mock.patch.object(zontex, "request")
    def test_companion_info_clears_manual_install_handoff_when_available(self, request):
        request.return_value = zontex.Response(
            status=200,
            headers={"content-type": "application/json"},
            text=(
                '{"version":"0.1.0","compatibility":'
                '{"experimental":true,"warnings":["review Zotero update"]}}'
            ),
        )
        info = zontex.companion_info()
        self.assertTrue(info["available"])
        self.assertFalse(info["manualInstallRequired"])
        self.assertTrue(info["compatibility"]["experimental"])
        self.assertEqual(info["compatibility"]["warnings"], ["review Zotero update"])

    def test_parse_assignment_keeps_equals_in_value(self):
        self.assertEqual(zontex.parse_assignment("extra=a=b", label="--set"), ("extra", "a=b"))

    def test_item_patch_preserves_unrelated_tags_and_collections(self):
        data = {
            "key": "ABCD2345",
            "version": 8,
            "itemType": "journalArticle",
            "title": "Old title",
            "extra": "rate: 4",
            "tags": [{"tag": "Role/Method"}, {"tag": "Old"}],
            "collections": ["COLL0001"],
        }
        args = batch_args(
            set_values=["title=New title"],
            add_tags=["Project/SDT Review"],
            replace_tags=["Old=New"],
            add_collection_keys=["COLL0002"],
        )
        patch = zontex.make_item_patch(data, args)
        self.assertEqual(patch["title"], "New title")
        self.assertEqual(
            patch["tags"],
            [{"tag": "Role/Method"}, {"tag": "New"}, {"tag": "Project/SDT Review"}],
        )
        self.assertEqual(patch["collections"], ["COLL0001", "COLL0002"])
        self.assertNotIn("extra", patch)

    def test_item_type_change_is_a_minimal_patch(self):
        data = {
            "key": "ABCD2345",
            "version": 8,
            "itemType": "journalArticle",
            "title": "A preprint",
            "tags": [],
            "collections": [],
        }
        patch = zontex.make_item_patch(data, batch_args(item_type="manuscript"))
        self.assertEqual(patch, {"itemType": "manuscript"})

    def test_structured_metadata_patch_accepts_creators(self):
        data = {
            "key": "ABCD2345",
            "version": 8,
            "itemType": "journalArticle",
            "title": "Title",
            "creators": [{"creatorType": "author", "name": "Consortium"}],
            "tags": [],
            "collections": [],
        }
        creators = '[{"creatorType":"author","firstName":"Ada","lastName":"Lovelace"}]'
        patch = zontex.make_item_patch(data, batch_args(set_json_values=[f"creators={creators}"]))
        self.assertEqual(patch["creators"][0]["lastName"], "Lovelace")

    def test_rating_preserves_unrelated_extra_lines(self):
        extra = "DOI: 10.1000/example\nrate: 2\nCitation Key: Doe2026"
        self.assertEqual(
            zontex.update_extra_rating(extra, 5),
            "DOI: 10.1000/example\nCitation Key: Doe2026\nrate: 5",
        )
        self.assertEqual(
            zontex.update_extra_rating(extra, None),
            "DOI: 10.1000/example\nCitation Key: Doe2026",
        )

    def test_status_names_are_slash_prefixed(self):
        self.assertEqual(zontex.normalize_status_name("reading"), "/reading")
        self.assertEqual(zontex.normalize_status_name("/done"), "/done")

    def test_csl_metadata_comes_from_info(self):
        csl = """<?xml version="1.0" encoding="utf-8"?>
<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0">
  <info>
    <title>SDT Review Numeric</title>
    <id>http://www.zotero.org/styles/sdt-review-numeric</id>
  </info>
  <citation><layout><text variable="title"/></layout></citation>
</style>"""
        self.assertEqual(
            zontex.find_csl_metadata(csl),
            {
                "id": "http://www.zotero.org/styles/sdt-review-numeric",
                "title": "SDT Review Numeric",
            },
        )

    def test_parser_exposes_extended_commands(self):
        parser = zontex.build_parser()
        args = parser.parse_args(["status", "--require-write"])
        self.assertTrue(args.require_write)
        args = parser.parse_args(["set-rating", "--item-key", "ABCD2345", "--value", "5"])
        self.assertEqual(args.value, 5)
        self.assertEqual(args.item_key, ["ABCD2345"])
        args = parser.parse_args(["clear-status", "--collection-name", "SDT Review"])
        self.assertIsNone(args.name)
        args = parser.parse_args([
            "render",
            "--item-key",
            "ABCD2345",
            "--style",
            "http://www.zotero.org/styles/apa",
            "--mode",
            "citation",
        ])
        self.assertEqual(args.item_key, ["ABCD2345"])
        self.assertEqual(args.mode, "citation")
        args = parser.parse_args(["navigate", "--open-attachment", "PDF12345"])
        self.assertEqual(args.open_attachment, "PDF12345")
        args = parser.parse_args(["document-segments", "--limit", "25", "--verbose"])
        self.assertEqual(args.limit, 25)
        self.assertTrue(args.verbose)
        args = parser.parse_args([
            "create-annotation",
            "--attachment-key",
            "PDF12345",
            "--source-hash",
            "HASH",
            "--segment-id",
            "block:1",
            "--start",
            "0",
            "--end",
            "4",
            "--expected-text",
            "Text",
            "--tag",
            "Method",
        ])
        self.assertEqual(args.tag, ["Method"])
        self.assertEqual(args.expected_text, "Text")
        args = parser.parse_args([
            "create-annotations",
            "--file",
            "plan.json",
            "--expect-count",
            "2",
        ])
        self.assertEqual(args.expect_count, 2)
        args = parser.parse_args([
            "annotations-to-note",
            "--parent-item-key",
            "PAPER123",
            "--annotation-key",
            "ANN12345",
        ])
        self.assertEqual(args.order, "document")
        args = parser.parse_args([
            "rename-tag",
            "--from",
            "Legacy",
            "--to",
            "Current",
            "--expect-count",
            "4",
        ])
        self.assertEqual(args.from_name, "Legacy")
        self.assertEqual(args.expect_count, 4)
        args = parser.parse_args([
            "merge-tags",
            "--source",
            "Legacy=4",
            "--source",
            "Old=2",
            "--into",
            "Current",
        ])
        self.assertEqual(args.source, ["Legacy=4", "Old=2"])
        self.assertEqual(args.color_policy, "preserve-target")
        args = parser.parse_args([
            "merge-items",
            "--master",
            "ABCD2345",
            "--other",
            "EFGH6789",
            "--expected-version",
            "ABCD2345=8",
            "--expected-version",
            "EFGH6789=3",
        ])
        self.assertEqual(args.master, "ABCD2345")
        self.assertEqual(args.other, ["EFGH6789"])
        self.assertEqual(args.expected_version, ["ABCD2345=8", "EFGH6789=3"])
        args = parser.parse_args([
            "trash-items",
            "--item-key",
            "ANN12345",
            "--expect-count",
            "1",
            "--confirm",
            "DELETE-PERMANENTLY",
            "--yes",
        ])
        self.assertEqual(args.confirm, "DELETE-PERMANENTLY")

    @mock.patch.object(zontex, "authorized_request")
    @mock.patch.object(zontex, "commit_item_patches")
    @mock.patch.object(zontex, "select_items")
    def test_trash_items_requires_confirmation_before_mixed_deletion(
        self, select_items, commit_item_patches, authorized_request
    ):
        select_items.return_value = [
            {
                "key": "ANN12345",
                "version": 8,
                "itemType": "annotation",
                "parentItem": "PDF12345",
            },
            {
                "key": "PAPER123",
                "version": 4,
                "itemType": "journalArticle",
                "title": "Keep the batch atomic",
            },
        ]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            zontex.cmd_trash_items(argparse.Namespace(yes=True, confirm=None))
        preview = json.loads(output.getvalue())
        self.assertFalse(preview["committed"])
        self.assertEqual(preview["trashCount"], 1)
        self.assertEqual(preview["permanentDeleteAnnotationCount"], 1)
        self.assertIn("注释删除后无法恢复", preview["confirmationPrompt"]["zh-CN"])
        self.assertEqual(preview["requiredConfirmation"], "DELETE-PERMANENTLY")
        commit_item_patches.assert_not_called()
        authorized_request.assert_not_called()

    @mock.patch.object(zontex, "authorized_request")
    @mock.patch.object(zontex, "commit_item_patches")
    @mock.patch.object(zontex, "select_items")
    def test_trash_items_annotation_only_uses_short_warning_then_deletes(
        self, select_items, commit_item_patches, authorized_request
    ):
        select_items.return_value = [
            {"key": "ANN12345", "version": 8, "itemType": "annotation"}
        ]
        authorized_request.return_value = zontex.Response(status=204, headers={}, text="")

        preview_output = io.StringIO()
        with contextlib.redirect_stdout(preview_output):
            zontex.cmd_trash_items(argparse.Namespace(yes=True, confirm=None))
        preview = json.loads(preview_output.getvalue())
        self.assertEqual(
            preview["confirmationPrompt"]["zh-CN"],
            "注意：注释删除后无法恢复。如需删除，请回复确认。",
        )
        commit_item_patches.assert_not_called()
        authorized_request.assert_not_called()

        committed_output = io.StringIO()
        with contextlib.redirect_stdout(committed_output):
            zontex.cmd_trash_items(
                argparse.Namespace(yes=True, confirm="DELETE-PERMANENTLY")
            )
        commit_item_patches.assert_not_called()
        authorized_request.assert_called_once()
        self.assertEqual(
            json.loads(committed_output.getvalue())["deletedAnnotationKeys"],
            ["ANN12345"],
        )

    @mock.patch.object(zontex, "authorized_request")
    @mock.patch.object(zontex, "commit_item_patches", return_value=([{"key": "PAPER123"}], {}))
    @mock.patch.object(zontex, "select_items")
    def test_trash_items_confirms_then_trashes_ordinary_and_deletes_annotation(
        self, select_items, commit_item_patches, authorized_request
    ):
        select_items.return_value = [
            {
                "key": "ANN12345",
                "version": 8,
                "itemType": "annotation",
                "parentItem": "PDF12345",
            },
            {
                "key": "PAPER123",
                "version": 4,
                "itemType": "journalArticle",
                "title": "Mixed deletion",
            },
        ]
        authorized_request.return_value = zontex.Response(status=204, headers={}, text="")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            zontex.cmd_trash_items(
                argparse.Namespace(yes=True, confirm="DELETE-PERMANENTLY")
            )
        planned = commit_item_patches.call_args.args[0]
        self.assertEqual([row["key"] for row in planned], ["PAPER123"])
        self.assertEqual(planned[0]["patch"], {"deleted": 1})
        authorized_request.assert_called_once_with(
            f"{zontex.LOCAL_USER}/items/ANN12345",
            method="DELETE",
            data=None,
            headers={"If-Unmodified-Since-Version": "8"},
        )
        result = json.loads(output.getvalue())
        self.assertTrue(result["committed"])
        self.assertEqual(result["deletedAnnotationKeys"], ["ANN12345"])

    @mock.patch.object(zontex, "authorized_request")
    @mock.patch.object(
        zontex,
        "commit_item_patches",
        return_value=([], {"PAPER123": {"error": "write failed"}}),
    )
    @mock.patch.object(zontex, "select_items")
    def test_trash_items_skips_annotation_deletion_when_trash_write_fails(
        self, select_items, commit_item_patches, authorized_request
    ):
        select_items.return_value = [
            {"key": "ANN12345", "version": 8, "itemType": "annotation"},
            {"key": "PAPER123", "version": 4, "itemType": "journalArticle"},
        ]
        output = io.StringIO()
        with self.assertRaises(SystemExit) as raised, contextlib.redirect_stdout(output):
            zontex.cmd_trash_items(
                argparse.Namespace(yes=True, confirm="DELETE-PERMANENTLY")
            )
        self.assertEqual(raised.exception.code, 2)
        self.assertTrue(json.loads(output.getvalue())["annotationDeletionSkipped"])
        authorized_request.assert_not_called()

    @mock.patch.object(zontex, "commit_item_patches", return_value=([], {}))
    @mock.patch.object(zontex, "select_items")
    def test_trash_items_keeps_normal_item_behavior(self, select_items, commit_item_patches):
        select_items.return_value = [
            {
                "key": "PAPER123",
                "version": 4,
                "itemType": "journalArticle",
                "title": "Ordinary item",
            }
        ]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            zontex.cmd_trash_items(argparse.Namespace(yes=True, confirm=None))
        planned = commit_item_patches.call_args.args[0]
        self.assertEqual(planned[0]["patch"], {"deleted": 1})
        self.assertTrue(json.loads(output.getvalue())["committed"])

    @mock.patch.object(zontex, "api_get")
    @mock.patch.object(zontex, "require_companion")
    def test_context_prints_bridge_payload(self, require_companion, api_get):
        api_get.return_value = {"reader": {"active": False}}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            zontex.cmd_context(argparse.Namespace())
        require_companion.assert_called_once_with()
        api_get.assert_called_once_with(zontex.ZONTEX_CONTEXT_PATH)
        self.assertFalse(json.loads(output.getvalue())["reader"]["active"])

    @mock.patch.object(zontex, "bridge_post")
    def test_render_sends_native_preview_request(self, bridge_post):
        bridge_post.return_value = {"mode": "bibliography", "text": "Example"}
        args = argparse.Namespace(
            item_key=["ABCD2345"],
            style="http://www.zotero.org/styles/apa",
            locale=None,
            mode="bibliography",
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            zontex.cmd_render(args)
        bridge_post.assert_called_once_with(
            zontex.ZONTEX_RENDER_PATH,
            {
                "itemKeys": ["ABCD2345"],
                "style": "http://www.zotero.org/styles/apa",
                "locale": "",
                "mode": "bibliography",
            },
            "POST Bridge render",
        )
        self.assertEqual(json.loads(output.getvalue())["text"], "Example")

    @mock.patch.object(zontex, "bridge_post")
    def test_navigate_sends_only_the_selected_action(self, bridge_post):
        bridge_post.return_value = {"ok": True}
        args = argparse.Namespace(
            reveal_item=None,
            open_attachment="PDF12345",
            open_annotation=None,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            zontex.cmd_navigate(args)
        bridge_post.assert_called_once_with(
            zontex.ZONTEX_NAVIGATE_PATH,
            {"action": "open-attachment", "itemKey": "PDF12345"},
            "POST Bridge navigate (open-attachment)",
        )

    def test_create_annotation_defaults_to_preview(self):
        args = argparse.Namespace(
            attachment_key="PDF12345",
            source_hash="HASH",
            segment_id="block:1",
            start=0,
            end=4,
            expected_text="Text",
            type="highlight",
            color="#ffd400",
            comment=None,
            tag=["Method"],
            yes=False,
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            zontex.cmd_create_annotation(args)
        preview = json.loads(output.getvalue())
        self.assertFalse(preview["committed"])
        self.assertEqual(preview["request"]["target"]["segmentId"], "block:1")
        self.assertEqual(preview["request"]["expectedText"], "Text")

    def test_annotation_manifest_uses_utf16_offsets_and_rejects_duplicate_targets(self):
        value = annotation_manifest()
        value["annotations"] = [{
            **value["annotations"][0],
            "target": {"segmentId": "block:1", "start": 0, "end": 3},
            "expectedText": "A😀",
        }]
        normalized = zontex.validate_annotation_manifest(value, 1)
        self.assertEqual(normalized["annotations"][0]["expectedText"], "A😀")

        value["annotations"][0]["target"]["end"] = 2
        with self.assertRaisesRegex(SystemExit, "UTF-16"):
            zontex.validate_annotation_manifest(value, 1)

        duplicate = annotation_manifest()
        duplicate["annotations"][1]["target"] = dict(duplicate["annotations"][0]["target"])
        duplicate["annotations"][1]["expectedText"] = "Hello"
        with self.assertRaisesRegex(SystemExit, "Duplicate annotation target"):
            zontex.validate_annotation_manifest(duplicate, 2)

    def test_create_annotations_reuses_setup_and_verifies_once(self):
        manifest = annotation_manifest()
        responses = [
            zontex.Response(
                status=200,
                headers={},
                text=json.dumps({
                    "created": True,
                    "annotation": {"key": "ANN00001", "pageLabel": "1"},
                }),
            ),
            zontex.Response(
                status=200,
                headers={},
                text=json.dumps({
                    "created": False,
                    "duplicate": True,
                    "annotation": {"key": "ANN00002", "pageLabel": "2"},
                }),
            ),
        ]
        children = [
            {
                "key": "ANN00001",
                "itemType": "annotation",
                "parentItem": "PDF12345",
                "annotationType": "highlight",
                "annotationText": "Hello",
                "annotationComment": "Method",
                "annotationColor": "#ffd400",
                "tags": [{"tag": "Method"}],
            },
            {
                "key": "ANN00002",
                "itemType": "annotation",
                "parentItem": "PDF12345",
                "annotationType": "underline",
                "annotationText": "World",
                "annotationComment": "",
                "annotationColor": "#5fb236",
                "tags": [],
            },
        ]
        args = argparse.Namespace(
            file="plan.json",
            expect_count=2,
            timings=False,
            yes=True,
        )
        output = io.StringIO()
        with (
            mock.patch.object(zontex, "read_annotation_manifest", return_value=manifest),
            mock.patch.object(zontex, "require_companion") as require_companion,
            mock.patch.object(
                zontex,
                "server_info",
                return_value={"serverID": "SERVER", "writeSupported": True},
            ) as server_info,
            mock.patch.object(zontex, "authorized_request", side_effect=responses) as request,
            mock.patch.object(zontex, "items_by_keys", return_value=children) as items_by_keys,
            contextlib.redirect_stdout(output),
        ):
            zontex.cmd_create_annotations(args)
        result = json.loads(output.getvalue())
        self.assertEqual(result["counts"]["created"], 1)
        self.assertEqual(result["counts"]["duplicate"], 1)
        self.assertTrue(result["verification"]["ok"])
        self.assertEqual(result["callCounts"]["annotationPosts"], 2)
        require_companion.assert_called_once_with()
        server_info.assert_called_once_with()
        self.assertEqual(request.call_count, 2)
        items_by_keys.assert_called_once_with(["ANN00001", "ANN00002"])

    def test_create_annotations_stops_after_first_failure(self):
        manifest = annotation_manifest()
        manifest["annotations"].append({
            "clientId": "A3",
            "target": {"segmentId": "block:1", "start": 12, "end": 17},
            "expectedText": "Third",
            "type": "highlight",
            "color": "#ffd400",
            "comment": "",
            "tags": [],
        })
        responses = [
            zontex.Response(
                status=200,
                headers={},
                text=json.dumps({
                    "created": True,
                    "annotation": {"key": "ANN00001", "pageLabel": "1"},
                }),
            ),
            zontex.Response(
                status=412,
                headers={},
                text=json.dumps({
                    "error": "target-text-mismatch",
                    "message": "The exact target text changed",
                }),
            ),
        ]
        children = [{
            "key": "ANN00001",
            "itemType": "annotation",
            "parentItem": "PDF12345",
            "annotationType": "highlight",
            "annotationText": "Hello",
            "annotationComment": "Method",
            "annotationColor": "#ffd400",
            "tags": [{"tag": "Method"}],
        }]
        args = argparse.Namespace(file="plan.json", expect_count=3, timings=False, yes=True)
        output = io.StringIO()
        with (
            mock.patch.object(zontex, "read_annotation_manifest", return_value=manifest),
            mock.patch.object(zontex, "require_companion"),
            mock.patch.object(
                zontex,
                "server_info",
                return_value={"serverID": "SERVER", "writeSupported": True},
            ),
            mock.patch.object(zontex, "authorized_request", side_effect=responses) as request,
            mock.patch.object(zontex, "items_by_keys", return_value=children),
            contextlib.redirect_stdout(output),
            self.assertRaises(SystemExit) as raised,
        ):
            zontex.cmd_create_annotations(args)
        result = json.loads(output.getvalue())
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(result["counts"]["failed"], 1)
        self.assertEqual(result["notAttempted"], ["A3"])

    @mock.patch.object(zontex, "api_get")
    def test_items_by_keys_uses_one_filtered_readback(self, api_get):
        api_get.return_value = [
            {"data": {"key": "ANN00001", "itemType": "annotation"}},
            {"data": {"key": "ANN00002", "itemType": "annotation"}},
        ]
        rows = zontex.items_by_keys(["ANN00001", "ANN00002"])
        self.assertEqual([row["key"] for row in rows], ["ANN00001", "ANN00002"])
        api_get.assert_called_once()
        path = api_get.call_args.args[0]
        self.assertIn("itemKey=ANN00001%2CANN00002", path)
        self.assertIn("limit=2", path)

    @mock.patch.object(zontex, "bridge_post")
    def test_annotations_to_note_uses_native_route(self, bridge_post):
        bridge_post.return_value = {"created": True}
        args = argparse.Namespace(
            parent_item_key="PAPER123",
            annotation_key=["ANN12345", "ANN67890"],
            order="provided",
            no_comments=False,
            no_header=True,
            yes=True,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            zontex.cmd_annotations_to_note(args)
        bridge_post.assert_called_once_with(
            zontex.ZONTEX_ANNOTATION_NOTE_PATH,
            {
                "annotationKeys": ["ANN12345", "ANN67890"],
                "parentItemKey": "PAPER123",
                "order": "provided",
                "noComments": False,
                "noHeader": True,
            },
            "POST Bridge annotation note",
        )

    def test_parse_counted_tag_splits_on_the_last_equals(self):
        self.assertEqual(
            zontex.parse_counted_tag("Namespace=Legacy=4"),
            {"name": "Namespace=Legacy", "expectedCount": 4},
        )

    @mock.patch.object(zontex, "api_get_response")
    def test_tag_item_count_uses_total_results_header(self, api_get_response):
        api_get_response.return_value = zontex.Response(
            status=200,
            headers={"Total-Results": "7"},
            text="[]",
        )
        self.assertEqual(zontex.tag_item_count("Role/Method"), 7)
        self.assertIn("tag=Role%2FMethod", api_get_response.call_args.args[0])

    @mock.patch.object(zontex, "api_get_response")
    def test_tag_item_keys_reads_every_page(self, api_get_response):
        api_get_response.side_effect = [
            zontex.Response(status=200, headers={"Total-Results": "3"}, text="AAAA1111\nBBBB2222\n"),
            zontex.Response(status=200, headers={"Total-Results": "3"}, text="CCCC3333\n"),
        ]
        self.assertEqual(zontex.tag_item_keys("Role/Method"), ["AAAA1111", "BBBB2222", "CCCC3333"])
        self.assertIn("start=0", api_get_response.call_args_list[0].args[0])
        self.assertIn("start=2", api_get_response.call_args_list[1].args[0])

    @mock.patch.object(zontex, "tag_item_count")
    @mock.patch.object(zontex, "colored_tag_map")
    def test_tag_rename_prints_consolidated_preview(self, colored_tag_map, tag_item_count):
        colored_tag_map.return_value = {
            "Legacy": {"color": "#FF0000", "position": 1},
            "Current": {"color": "#00FF00", "position": 2},
        }
        tag_item_count.side_effect = [4, 2]
        args = argparse.Namespace(
            from_name="Legacy",
            to_name="Current",
            expect_count=4,
            yes=False,
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            zontex.cmd_rename_tag(args)
        preview = json.loads(output.getvalue())
        self.assertFalse(preview["committed"])
        self.assertEqual(preview["expectedCount"], 4)
        self.assertEqual(preview["actualCount"], 4)
        self.assertTrue(preview["countMatches"])
        self.assertTrue(preview["targetExists"])
        self.assertEqual(preview["targetColor"]["color"], "#00FF00")

    @mock.patch.object(zontex, "bridge_post")
    @mock.patch.object(zontex, "tag_item_count")
    @mock.patch.object(zontex, "tag_item_keys")
    @mock.patch.object(zontex, "colored_tag_map")
    def test_tag_merge_commits_one_native_request(
        self, colored_tag_map, tag_item_keys, tag_item_count, bridge_post
    ):
        colored_tag_map.return_value = {}
        tag_item_keys.side_effect = [
            ["AAAA1111", "BBBB2222", "CCCC3333", "DDDD4444"],
            ["EEEE5555", "FFFF6666"],
        ]
        tag_item_count.return_value = 0
        bridge_post.return_value = {"merged": True, "affectedItems": 6}
        args = argparse.Namespace(
            source=["Legacy=4", "Old=2"],
            into="Current",
            color_policy="preserve-target",
            yes=True,
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            zontex.cmd_merge_tags(args)
        bridge_post.assert_called_once_with(
            zontex.ZONTEX_TAG_MERGE_PATH,
            {
                "sources": [
                    {"name": "Legacy", "expectedCount": 4},
                    {"name": "Old", "expectedCount": 2},
                ],
                "into": "Current",
                "colorPolicy": "preserve-target",
            },
            "POST Bridge tag merge",
        )
        preview = json.loads(output.getvalue())
        self.assertTrue(preview["committed"])
        self.assertEqual(preview["uniqueAffectedItems"], 6)

    @mock.patch.object(zontex, "tag_item_count", return_value=1)
    @mock.patch.object(zontex, "tag_item_keys")
    @mock.patch.object(zontex, "colored_tag_map", return_value={})
    def test_tag_merge_preview_counts_overlapping_items_once(
        self, _colored_tag_map, tag_item_keys, _tag_item_count
    ):
        tag_item_keys.side_effect = [
            ["AAAA1111", "BBBB2222"],
            ["BBBB2222", "CCCC3333"],
        ]
        args = argparse.Namespace(
            source=["Legacy=2", "Old=2"],
            into="Current",
            color_policy="preserve-target",
            yes=False,
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            zontex.cmd_merge_tags(args)
        preview = json.loads(output.getvalue())
        self.assertEqual(preview["uniqueAffectedItems"], 3)
        self.assertTrue(preview["targetExists"])

    def test_parse_expected_version_splits_on_the_last_equals(self):
        self.assertEqual(
            zontex.parse_expected_version("KEY=WITH_EQUALS=8"),
            ("KEY=WITH_EQUALS", 8),
        )

    @mock.patch.object(zontex, "api_get")
    def test_item_merge_prints_explicit_master_preview(self, api_get):
        api_get.side_effect = [
            {"data": {"key": "ABCD2345", "version": 8, "itemType": "book", "title": "Master"}},
            {"data": {"key": "EFGH6789", "version": 3, "itemType": "book", "title": "Other"}},
            [
                {"data": {"key": "PDF12345", "itemType": "attachment"}},
                {"data": {"key": "NOTE1234", "itemType": "note"}},
            ],
            [{"data": {"key": "ANN12345", "itemType": "annotation"}}],
            [],
        ]
        args = argparse.Namespace(
            master="ABCD2345",
            other=["EFGH6789"],
            expected_version=["ABCD2345=8", "EFGH6789=3"],
            yes=False,
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            zontex.cmd_merge_items(args)
        preview = json.loads(output.getvalue())
        self.assertFalse(preview["committed"])
        self.assertEqual(preview["master"]["key"], "ABCD2345")
        self.assertEqual(preview["master"]["attachmentCount"], 1)
        self.assertEqual(preview["master"]["noteCount"], 1)
        self.assertEqual(preview["master"]["annotationCount"], 1)
        self.assertEqual(preview["others"][0]["title"], "Other")

    @mock.patch.object(zontex, "bridge_post")
    @mock.patch.object(zontex, "api_get")
    def test_item_merge_commits_native_request(self, api_get, bridge_post):
        api_get.side_effect = [
            {"data": {"key": "ABCD2345", "version": 8, "itemType": "book", "title": "Master"}},
            {"data": {"key": "EFGH6789", "version": 3, "itemType": "book", "title": "Other"}},
            [],
            [],
        ]
        bridge_post.return_value = {"merged": True}
        args = argparse.Namespace(
            master="ABCD2345",
            other=["EFGH6789"],
            expected_version=["ABCD2345=8", "EFGH6789=3"],
            yes=True,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            zontex.cmd_merge_items(args)
        bridge_post.assert_called_once_with(
            zontex.ZONTEX_ITEM_MERGE_PATH,
            {
                "master": "ABCD2345",
                "others": ["EFGH6789"],
                "expectedVersions": {"ABCD2345": 8, "EFGH6789": 3},
            },
            "POST Bridge item merge",
        )

    def test_invalid_field_is_rejected_before_write(self):
        data = {
            "key": "ABCD2345",
            "version": 8,
            "itemType": "journalArticle",
            "title": "Title",
            "tags": [],
            "collections": [],
        }
        with self.assertRaises(SystemExit):
            zontex.make_item_patch(data, batch_args(set_values=["notAField=value"]))

    @mock.patch.object(zontex, "request")
    @mock.patch.object(zontex, "cached_authorization")
    @mock.patch.object(zontex, "server_info")
    def test_authorized_request_sends_server_key_and_api_key(
        self, server_info, cached_authorization, request
    ):
        server_info.return_value = {
            "serverID": "SERVER123",
            "writeSupported": True,
        }
        cached_authorization.return_value = {"key": "LOCALKEY", "remember": True}
        request.return_value = zontex.Response(status=204, headers={}, text="")
        response = zontex.authorized_request(
            "/api/users/0/items/ABCD2345",
            method="PATCH",
            data={"title": "New"},
        )
        self.assertEqual(response.status, 204)
        sent_headers = request.call_args.kwargs["headers"]
        self.assertEqual(sent_headers["Zotero-Server-ID"], "SERVER123")
        self.assertEqual(sent_headers["Zotero-API-Key"], "LOCALKEY")

    @mock.patch.object(zontex, "companion_info")
    @mock.patch.object(zontex, "cached_authorization")
    @mock.patch.object(zontex, "server_info")
    def test_required_status_gate_blocks_without_authorization(
        self, server_info, cached_authorization, companion_info
    ):
        server_info.return_value = {
            "zoteroVersion": "10.0.1",
            "serverID": "SERVER123",
            "writeSupported": True,
        }
        cached_authorization.return_value = None
        companion_info.return_value = {"available": True, "version": "0.1.2"}
        output = io.StringIO()
        with self.assertRaises(SystemExit) as raised, contextlib.redirect_stdout(output):
            zontex.cmd_status(argparse.Namespace(require_write=True))
        self.assertEqual(raised.exception.code, 2)
        result = json.loads(output.getvalue())
        self.assertFalse(result["authorizationGate"]["passed"])
        self.assertIn("authorize-write", result["authorizationGate"]["nextStep"])

    @mock.patch.object(zontex, "companion_info")
    @mock.patch.object(zontex, "cached_authorization")
    @mock.patch.object(zontex, "server_info")
    def test_required_status_gate_passes_with_cached_authorization(
        self, server_info, cached_authorization, companion_info
    ):
        server_info.return_value = {
            "zoteroVersion": "10.0.1",
            "serverID": "SERVER123",
            "writeSupported": True,
        }
        cached_authorization.return_value = {"key": "LOCALKEY", "remember": True}
        companion_info.return_value = {"available": True, "version": "0.1.2"}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            zontex.cmd_status(argparse.Namespace(require_write=True))
        result = json.loads(output.getvalue())
        self.assertTrue(result["authorizationGate"]["passed"])
        self.assertIsNone(result["authorizationGate"]["nextStep"])

    @mock.patch.object(zontex, "resolve_collection")
    def test_rename_defaults_to_preview(self, resolve_collection):
        resolve_collection.return_value = {
            "key": "KJE93R7T",
            "version": 12,
            "name": "SDT Review",
            "parentCollection": False,
        }
        args = argparse.Namespace(
            collection_key="KJE93R7T",
            current_name=None,
            name="SDT Review Archive",
            yes=False,
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            zontex.cmd_rename_collection(args)
        preview = json.loads(output.getvalue())
        self.assertFalse(preview["committed"])
        self.assertEqual(preview["after"], "SDT Review Archive")


if __name__ == "__main__":
    unittest.main()
