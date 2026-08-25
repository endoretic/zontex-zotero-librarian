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
        args = parser.parse_args(["set-rating", "--item-key", "ABCD2345", "--value", "5"])
        self.assertEqual(args.value, 5)
        self.assertEqual(args.item_key, ["ABCD2345"])
        args = parser.parse_args(["clear-status", "--collection-name", "BN5001"])
        self.assertIsNone(args.name)

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
