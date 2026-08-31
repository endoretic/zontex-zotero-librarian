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
SPEC = importlib.util.spec_from_file_location("zontex_batch_test", SCRIPT)
assert SPEC and SPEC.loader
zontex = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = zontex
SPEC.loader.exec_module(zontex)


def create_rows(count: int) -> list[dict]:
    return [
        {
            "clientId": f"source-{index + 1}",
            "itemType": "journalArticle",
            "title": f"Paper {index + 1}",
            "creators": [],
            "tags": [],
            "collections": [],
        }
        for index in range(count)
    ]


def successful_response(keys: list[str]) -> zontex.Response:
    return zontex.Response(
        status=200,
        headers={},
        text=json.dumps(
            {"successful": {str(index): {"key": key} for index, key in enumerate(keys)}}
        ),
    )


class BatchItemTests(unittest.TestCase):
    def test_manifest_rejects_client_keys_and_duplicate_client_ids(self):
        with self.assertRaisesRegex(SystemExit, "schemaVersion"):
            zontex.validate_create_items_manifest(
                {"schemaVersion": True, "items": create_rows(1)}, 1
            )
        with self.assertRaisesRegex(SystemExit, "key or version"):
            zontex.validate_create_items_manifest(
                [{"clientId": "A", "key": "BAD", "itemType": "book"}], 1
            )
        with self.assertRaisesRegex(SystemExit, "clientId must be unique"):
            zontex.validate_create_items_manifest(
                [
                    {"clientId": "A", "itemType": "book"},
                    {"clientId": "A", "itemType": "book"},
                ],
                2,
            )

    @mock.patch.object(zontex, "api_get")
    def test_items_by_keys_chunks_and_preserves_requested_order(self, api_get):
        keys = [f"KEY{index:05d}" for index in range(51)]
        api_get.side_effect = [
            [{"data": {"key": key}} for key in reversed(keys[:50])],
            [{"data": {"key": keys[50]}}],
        ]
        rows = zontex.items_by_keys(keys)
        self.assertEqual([row["key"] for row in rows], keys)
        self.assertEqual(api_get.call_count, 2)
        self.assertIn("limit=50", api_get.call_args_list[0].args[0])
        self.assertIn("limit=1", api_get.call_args_list[1].args[0])

    @mock.patch.object(zontex, "api_get")
    def test_items_by_keys_keeps_first_occurrence_of_duplicate_keys(self, api_get):
        api_get.return_value = [
            {"data": {"key": "AAAA1111"}},
            {"data": {"key": "BBBB2222"}},
        ]
        rows = zontex.items_by_keys(["AAAA1111", "BBBB2222", "AAAA1111"])
        self.assertEqual([row["key"] for row in rows], ["AAAA1111", "BBBB2222"])
        self.assertIn("itemKey=AAAA1111%2CBBBB2222", api_get.call_args.args[0])

    @mock.patch.object(zontex, "api_get")
    def test_items_by_keys_reports_missing_keys(self, api_get):
        api_get.return_value = [{"data": {"key": "AAAA1111"}}]
        with self.assertRaisesRegex(SystemExit, "BBBB2222"):
            zontex.items_by_keys(["AAAA1111", "BBBB2222"])

    @mock.patch.object(zontex, "items_by_keys")
    def test_explicit_item_selection_uses_one_logical_bulk_read(self, items_by_keys):
        items_by_keys.return_value = [
            {"key": "AAAA1111"},
            {"key": "BBBB2222"},
        ]
        args = argparse.Namespace(
            item_key=["AAAA1111", "BBBB2222"],
            collection_key=None,
            collection_name=None,
            query=None,
            all_items=False,
            expect_count=2,
        )
        rows = zontex.select_items(args)
        self.assertEqual([row["key"] for row in rows], ["AAAA1111", "BBBB2222"])
        items_by_keys.assert_called_once_with(["AAAA1111", "BBBB2222"])

    @mock.patch.object(zontex, "api_get_response")
    def test_paged_items_reads_complete_inventory(self, api_get_response):
        first = [{"data": {"key": f"K{index:07d}"}} for index in range(100)]
        last = [{"data": {"key": "K0000100"}}]
        api_get_response.side_effect = [
            zontex.Response(
                status=200,
                headers={"Total-Results": "101"},
                text=json.dumps(first),
            ),
            zontex.Response(
                status=200,
                headers={"Total-Results": "101"},
                text=json.dumps(last),
            ),
        ]
        rows = zontex.paged_items(f"{zontex.LOCAL_USER}/items/top")
        self.assertEqual(len(rows), 101)
        self.assertIn("start=0", api_get_response.call_args_list[0].args[0])
        self.assertIn("start=100", api_get_response.call_args_list[1].args[0])

    @mock.patch.object(zontex, "api_get_response")
    def test_paged_items_rejects_an_incomplete_server_result(self, api_get_response):
        api_get_response.return_value = zontex.Response(
            status=200,
            headers={"Total-Results": "1"},
            text="[]",
        )
        with self.assertRaisesRegex(SystemExit, "incomplete"):
            zontex.paged_items(f"{zontex.LOCAL_USER}/items/top")

    def test_inventory_is_compact_and_extracts_available_identifiers(self):
        compact = zontex.compact_inventory_item(
            {
                "key": "AAAA1111",
                "version": 7,
                "itemType": "journalArticle",
                "title": "Example",
                "date": "2026-08-31",
                "DOI": "10.1000/example",
                "ISBN": "978-1-2345-6789-0",
                "extra": "PMID: 12345678\nCitation Key: Example2026",
                "creators": [
                    {"creatorType": "editor", "lastName": "Editor"},
                    {"creatorType": "author", "lastName": "Author"},
                ],
                "collections": ["COLL0001"],
                "tags": [{"tag": "Not returned"}],
            }
        )
        self.assertEqual(compact["firstAuthor"], "Author")
        self.assertEqual(compact["year"], "2026")
        self.assertEqual(
            compact["identifiers"],
            {
                "DOI": "10.1000/example",
                "PMID": "12345678",
                "ISBN": "978-1-2345-6789-0",
            },
        )
        self.assertNotIn("extra", compact)
        self.assertNotIn("creators", compact)
        self.assertNotIn("tags", compact)

    def test_create_response_preserves_unchanged_results(self):
        records = zontex.validate_create_items_manifest(create_rows(1), 1)
        result = zontex.parse_create_items_response(
            {"unchanged": {"0": {"key": "EXISTING"}}}, records
        )
        self.assertEqual(
            result,
            [{"clientId": "source-1", "status": "unchanged", "key": "EXISTING"}],
        )

    @mock.patch.object(zontex, "items_by_keys")
    @mock.patch.object(zontex, "authorized_request")
    @mock.patch.object(zontex, "read_json_file")
    def test_create_items_batches_51_and_reads_back_once(
        self, read_json_file, authorized_request, items_by_keys
    ):
        read_json_file.return_value = create_rows(51)
        keys = [f"NEW{index:05d}" for index in range(51)]
        authorized_request.side_effect = [
            successful_response(keys[:50]),
            successful_response(keys[50:]),
        ]
        items_by_keys.return_value = [
            {"key": key, "title": f"Paper {index + 1}"}
            for index, key in enumerate(keys)
        ]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            zontex.cmd_create_items(
                argparse.Namespace(json_file="items.json", expect_count=51, yes=True)
            )
        result = json.loads(output.getvalue())
        self.assertEqual(result["outcome"], "changed")
        self.assertEqual(result["createdCount"], 51)
        self.assertEqual(result["batchCount"], 2)
        self.assertEqual(result["verifiedCount"], 51)
        self.assertEqual([len(call.kwargs["data"]) for call in authorized_request.call_args_list], [50, 1])
        items_by_keys.assert_called_once_with(keys)
        self.assertNotIn('"payload"', output.getvalue())
        self.assertNotIn('"successful"', output.getvalue())

    @mock.patch.object(zontex, "items_by_keys")
    @mock.patch.object(zontex, "authorized_request")
    @mock.patch.object(zontex, "read_json_file")
    def test_create_items_stops_after_a_partial_batch(
        self, read_json_file, authorized_request, items_by_keys
    ):
        read_json_file.return_value = create_rows(120)
        first_keys = [f"NEW{index:05d}" for index in range(50)]
        second_keys = [f"NEW{index:05d}" for index in range(50, 100)]
        second_body = {
            "successful": {
                str(index): {"key": key}
                for index, key in enumerate(second_keys)
                if index != 1
            },
            "failed": {"1": {"code": 400, "message": "invalid item"}},
        }
        authorized_request.side_effect = [
            successful_response(first_keys),
            zontex.Response(status=200, headers={}, text=json.dumps(second_body)),
        ]
        verified_keys = first_keys + [key for index, key in enumerate(second_keys) if index != 1]
        items_by_keys.return_value = [{"key": key, "title": "Created"} for key in verified_keys]
        output = io.StringIO()
        with self.assertRaises(SystemExit) as raised, contextlib.redirect_stdout(output):
            zontex.cmd_create_items(
                argparse.Namespace(json_file="items.json", expect_count=120, yes=True)
            )
        result = json.loads(output.getvalue())
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(authorized_request.call_count, 2)
        self.assertEqual(result["createdCount"], 99)
        self.assertEqual(result["failedCount"], 1)
        self.assertEqual(result["notAttemptedCount"], 20)
        self.assertEqual(result["outcome"], "partial")
        items_by_keys.assert_called_once_with(verified_keys)

    def test_parser_exposes_inventory_and_create_items(self):
        parser = zontex.build_parser()
        create = parser.parse_args(
            ["create-items", "--json-file", "items.json", "--expect-count", "35"]
        )
        self.assertEqual(create.expect_count, 35)
        inventory = parser.parse_args(["inventory", "--all", "--expect-count", "35"])
        self.assertTrue(inventory.all_items)
        self.assertEqual(inventory.expect_count, 35)


if __name__ == "__main__":
    unittest.main()
