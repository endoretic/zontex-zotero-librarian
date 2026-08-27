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


SCRIPT = Path(__file__).parents[1] / "scripts" / "zotero_modified.py"
SPEC = importlib.util.spec_from_file_location("zotero_modified", SCRIPT)
assert SPEC and SPEC.loader
zm = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = zm
SPEC.loader.exec_module(zm)


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


class ZoteroManagerTests(unittest.TestCase):
    @mock.patch.object(zm, "request")
    def test_companion_info_reports_manual_install_handoff(self, request):
        request.return_value = zm.Response(status=404, headers={}, text="Not Found")
        info = zm.companion_info()
        self.assertFalse(info["available"])
        self.assertTrue(info["manualInstallRequired"])
        self.assertIn("matching Zotero Modified Bridge XPI", info["nextStep"])

    @mock.patch.object(zm, "request")
    def test_companion_info_clears_manual_install_handoff_when_available(self, request):
        request.return_value = zm.Response(
            status=200,
            headers={"content-type": "application/json"},
            text='{"version":"0.1.0"}',
        )
        info = zm.companion_info()
        self.assertTrue(info["available"])
        self.assertFalse(info["manualInstallRequired"])

    def test_parse_assignment_keeps_equals_in_value(self):
        self.assertEqual(zm.parse_assignment("extra=a=b", label="--set"), ("extra", "a=b"))

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
            add_tags=["Project/BN5001"],
            replace_tags=["Old=New"],
            add_collection_keys=["COLL0002"],
        )
        patch = zm.make_item_patch(data, args)
        self.assertEqual(patch["title"], "New title")
        self.assertEqual(
            patch["tags"],
            [{"tag": "Role/Method"}, {"tag": "New"}, {"tag": "Project/BN5001"}],
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
        patch = zm.make_item_patch(data, batch_args(item_type="manuscript"))
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
        patch = zm.make_item_patch(data, batch_args(set_json_values=[f"creators={creators}"]))
        self.assertEqual(patch["creators"][0]["lastName"], "Lovelace")

    def test_rating_preserves_unrelated_extra_lines(self):
        extra = "DOI: 10.1000/example\nrate: 2\nCitation Key: Doe2026"
        self.assertEqual(
            zm.update_extra_rating(extra, 5),
            "DOI: 10.1000/example\nCitation Key: Doe2026\nrate: 5",
        )
        self.assertEqual(
            zm.update_extra_rating(extra, None),
            "DOI: 10.1000/example\nCitation Key: Doe2026",
        )

    def test_status_names_are_slash_prefixed(self):
        self.assertEqual(zm.normalize_status_name("reading"), "/reading")
        self.assertEqual(zm.normalize_status_name("/done"), "/done")

    def test_csl_metadata_comes_from_info(self):
        csl = """<?xml version="1.0" encoding="utf-8"?>
<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0">
  <info>
    <title>BN5001 Numeric</title>
    <id>http://www.zotero.org/styles/bn5001-numeric</id>
  </info>
  <citation><layout><text variable="title"/></layout></citation>
</style>"""
        self.assertEqual(
            zm.find_csl_metadata(csl),
            {
                "id": "http://www.zotero.org/styles/bn5001-numeric",
                "title": "BN5001 Numeric",
            },
        )

    def test_parser_exposes_extended_commands(self):
        parser = zm.build_parser()
        args = parser.parse_args(["status", "--require-write"])
        self.assertTrue(args.require_write)
        args = parser.parse_args(["set-rating", "--item-key", "ABCD2345", "--value", "5"])
        self.assertEqual(args.value, 5)
        self.assertEqual(args.item_key, ["ABCD2345"])
        args = parser.parse_args(["clear-status", "--collection-name", "BN5001"])
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

    @mock.patch.object(zm, "api_get")
    @mock.patch.object(zm, "require_companion")
    def test_context_prints_bridge_payload(self, require_companion, api_get):
        api_get.return_value = {"reader": {"active": False}}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            zm.cmd_context(argparse.Namespace())
        require_companion.assert_called_once_with()
        api_get.assert_called_once_with(zm.MODIFIED_CONTEXT_PATH)
        self.assertFalse(json.loads(output.getvalue())["reader"]["active"])

    @mock.patch.object(zm, "bridge_post")
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
            zm.cmd_render(args)
        bridge_post.assert_called_once_with(
            zm.MODIFIED_RENDER_PATH,
            {
                "itemKeys": ["ABCD2345"],
                "style": "http://www.zotero.org/styles/apa",
                "locale": "",
                "mode": "bibliography",
            },
            "POST Bridge render",
        )
        self.assertEqual(json.loads(output.getvalue())["text"], "Example")

    @mock.patch.object(zm, "bridge_post")
    def test_navigate_sends_only_the_selected_action(self, bridge_post):
        bridge_post.return_value = {"ok": True}
        args = argparse.Namespace(
            reveal_item=None,
            open_attachment="PDF12345",
            open_annotation=None,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            zm.cmd_navigate(args)
        bridge_post.assert_called_once_with(
            zm.MODIFIED_NAVIGATE_PATH,
            {"action": "open-attachment", "itemKey": "PDF12345"},
            "POST Bridge navigate (open-attachment)",
        )

    def test_parse_expected_version_splits_on_the_last_equals(self):
        self.assertEqual(
            zm.parse_expected_version("KEY=WITH_EQUALS=8"),
            ("KEY=WITH_EQUALS", 8),
        )

    @mock.patch.object(zm, "api_get")
    def test_item_merge_prints_explicit_master_preview(self, api_get):
        api_get.side_effect = [
            {"data": {"key": "ABCD2345", "version": 8, "itemType": "book", "title": "Master"}},
            {"data": {"key": "EFGH6789", "version": 3, "itemType": "book", "title": "Other"}},
        ]
        args = argparse.Namespace(
            master="ABCD2345",
            other=["EFGH6789"],
            expected_version=["ABCD2345=8", "EFGH6789=3"],
            yes=False,
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            zm.cmd_merge_items(args)
        preview = json.loads(output.getvalue())
        self.assertFalse(preview["committed"])
        self.assertEqual(preview["master"]["key"], "ABCD2345")
        self.assertEqual(preview["others"][0]["title"], "Other")

    @mock.patch.object(zm, "bridge_post")
    @mock.patch.object(zm, "api_get")
    def test_item_merge_commits_native_request(self, api_get, bridge_post):
        api_get.side_effect = [
            {"data": {"key": "ABCD2345", "version": 8, "itemType": "book", "title": "Master"}},
            {"data": {"key": "EFGH6789", "version": 3, "itemType": "book", "title": "Other"}},
        ]
        bridge_post.return_value = {"merged": True}
        args = argparse.Namespace(
            master="ABCD2345",
            other=["EFGH6789"],
            expected_version=["ABCD2345=8", "EFGH6789=3"],
            yes=True,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            zm.cmd_merge_items(args)
        bridge_post.assert_called_once_with(
            zm.MODIFIED_ITEM_MERGE_PATH,
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
            zm.make_item_patch(data, batch_args(set_values=["notAField=value"]))

    @mock.patch.object(zm, "request")
    @mock.patch.object(zm, "cached_authorization")
    @mock.patch.object(zm, "server_info")
    def test_authorized_request_sends_server_key_and_api_key(
        self, server_info, cached_authorization, request
    ):
        server_info.return_value = {
            "serverID": "SERVER123",
            "writeSupported": True,
        }
        cached_authorization.return_value = {"key": "LOCALKEY", "remember": True}
        request.return_value = zm.Response(status=204, headers={}, text="")
        response = zm.authorized_request(
            "/api/users/0/items/ABCD2345",
            method="PATCH",
            data={"title": "New"},
        )
        self.assertEqual(response.status, 204)
        sent_headers = request.call_args.kwargs["headers"]
        self.assertEqual(sent_headers["Zotero-Server-ID"], "SERVER123")
        self.assertEqual(sent_headers["Zotero-API-Key"], "LOCALKEY")

    @mock.patch.object(zm, "companion_info")
    @mock.patch.object(zm, "cached_authorization")
    @mock.patch.object(zm, "server_info")
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
            zm.cmd_status(argparse.Namespace(require_write=True))
        self.assertEqual(raised.exception.code, 2)
        result = json.loads(output.getvalue())
        self.assertFalse(result["authorizationGate"]["passed"])
        self.assertIn("authorize-write", result["authorizationGate"]["nextStep"])

    @mock.patch.object(zm, "companion_info")
    @mock.patch.object(zm, "cached_authorization")
    @mock.patch.object(zm, "server_info")
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
            zm.cmd_status(argparse.Namespace(require_write=True))
        result = json.loads(output.getvalue())
        self.assertTrue(result["authorizationGate"]["passed"])
        self.assertIsNone(result["authorizationGate"]["nextStep"])

    @mock.patch.object(zm, "resolve_collection")
    def test_rename_defaults_to_preview(self, resolve_collection):
        resolve_collection.return_value = {
            "key": "KJE93R7T",
            "version": 12,
            "name": "BN5001",
            "parentCollection": False,
        }
        args = argparse.Namespace(
            collection_key="KJE93R7T",
            current_name=None,
            name="BN5001 Review",
            yes=False,
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            zm.cmd_rename_collection(args)
        preview = json.loads(output.getvalue())
        self.assertFalse(preview["committed"])
        self.assertEqual(preview["after"], "BN5001 Review")


if __name__ == "__main__":
    unittest.main()
