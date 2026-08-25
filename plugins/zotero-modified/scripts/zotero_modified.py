#!/usr/bin/env python3
"""Safe Zotero 10 local-library management for Codex.

The Zotero 10 local API supports authenticated writes. This helper adds a
small, auditable command surface around those writes. Mutating commands are
preview-only unless ``--yes`` is supplied, and every update carries Zotero's
current object version to prevent overwriting concurrent edits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_BASE_URL = os.environ.get("ZOTERO_LOCAL_BASE_URL", "http://127.0.0.1:23119")
LOCAL_USER = "/api/users/0"
API_HEADERS = {"Zotero-API-Version": "3"}
APP_NAME = "Zotero Modified"
TEXT_LIMIT = 500
WRITE_TIMEOUT = 180.0
MAX_BATCH = 50
MODIFIED_STATUS_PATH = f"{LOCAL_USER}/zotero-modified/statuses"
MODIFIED_STYLES_PATH = f"{LOCAL_USER}/zotero-modified/styles"
STATUS_PREFIX = "/"
RATE_LINE_RE = re.compile(r"^\s*rate\s*:\s*([1-5])\s*$", re.IGNORECASE)
CSL_NAMESPACE = "http://purl.org/net/xbiblio/csl"


@dataclass(frozen=True)
class Response:
    status: int | None
    headers: dict[str, str]
    text: str
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300


def dump_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False))


def exit_with(message: str) -> None:
    raise SystemExit(message)


def header(headers: dict[str, str], name: str) -> str | None:
    wanted = name.casefold()
    for key, value in headers.items():
        if key.casefold() == wanted:
            return value
    return None


def url_for(path: str) -> str:
    return DEFAULT_BASE_URL.rstrip("/") + path


def request(
    path: str,
    *,
    method: str = "GET",
    data: Any = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10.0,
) -> Response:
    req_headers = dict(API_HEADERS if path.startswith("/api") else {})
    req_headers.update(headers or {})
    body: bytes | None = None
    if data is not None:
        if isinstance(data, (dict, list)):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")
        elif isinstance(data, bytes):
            body = data
        else:
            body = str(data).encode("utf-8")

    try:
        req = urllib.request.Request(url_for(path), data=body, method=method, headers=req_headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return Response(
                status=response.status,
                headers=dict(response.headers.items()),
                text=response.read().decode("utf-8", errors="replace"),
            )
    except urllib.error.HTTPError as exc:
        return Response(
            status=exc.code,
            headers=dict(exc.headers.items()),
            text=exc.read().decode("utf-8", errors="replace"),
            error=str(exc),
        )
    except Exception as exc:
        return Response(status=None, headers={}, text="", error=str(exc))


def parse_body(response: Response) -> Any:
    if not response.text:
        return None
    try:
        return json.loads(response.text)
    except json.JSONDecodeError:
        return response.text


def require_ok(response: Response, action: str) -> Response:
    if response.ok:
        return response
    detail = response.text[:TEXT_LIMIT] or response.error or "no response"
    hints = {
        401: "write authorization is missing or expired",
        403: "the local API is disabled or the authorization request was denied",
        409: "the Zotero library is temporarily locked",
        412: "the Zotero server/object version changed; preview again before retrying",
        428: "a Zotero server ID or object-version precondition is missing",
    }
    hint = f" ({hints[response.status]})" if response.status in hints else ""
    exit_with(f"{action} failed: status={response.status}{hint}; detail={detail}")
    raise AssertionError("unreachable")


def api_get(path: str) -> Any:
    api_path = path if path.startswith("/api") else "/api" + path
    return parse_body(require_ok(request(api_path), f"GET {api_path}"))


def api_get_response(path: str) -> Response:
    api_path = path if path.startswith("/api") else "/api" + path
    return require_ok(request(api_path), f"GET {api_path}")


def library_version() -> int:
    response = api_get_response(f"{LOCAL_USER}/items?limit=1")
    raw = header(response.headers, "Last-Modified-Version")
    if raw is None or not raw.isdigit():
        exit_with("Zotero did not report a library version")
    return int(raw)


def credential_path() -> Path:
    if platform.system() == "Windows" and os.environ.get("LOCALAPPDATA"):
        root = Path(os.environ["LOCALAPPDATA"])
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "Codex" / "ZoteroModified" / "credentials.json"


def read_credentials() -> dict[str, Any]:
    path = credential_path()
    if not path.exists():
        return {"servers": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"servers": {}}
    if not isinstance(value, dict) or not isinstance(value.get("servers"), dict):
        return {"servers": {}}
    return value


def write_credentials(value: dict[str, Any]) -> None:
    path = credential_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    temporary.replace(path)


def cached_authorization(server_id: str) -> dict[str, Any] | None:
    value = read_credentials().get("servers", {}).get(server_id)
    return value if isinstance(value, dict) and value.get("key") else None


def cache_authorization(server_id: str, key: str, remember: bool) -> None:
    credentials = read_credentials()
    credentials.setdefault("servers", {})[server_id] = {
        "key": key,
        "remember": bool(remember),
    }
    write_credentials(credentials)


def drop_authorization(server_id: str) -> None:
    credentials = read_credentials()
    servers = credentials.setdefault("servers", {})
    if server_id in servers:
        del servers[server_id]
        write_credentials(credentials)


def server_info() -> dict[str, Any]:
    response = require_ok(request("/api/", timeout=3), "GET /api/")
    version = header(response.headers, "X-Zotero-Version")
    server_id = header(response.headers, "Zotero-Server-ID")
    major_match = re.match(r"(\d+)", version or "")
    major = int(major_match.group(1)) if major_match else None
    return {
        "zoteroVersion": version,
        "apiVersion": header(response.headers, "Zotero-API-Version"),
        "schemaVersion": header(response.headers, "Zotero-Schema-Version"),
        "serverID": server_id,
        "writeSupported": bool(major is not None and major >= 10 and server_id),
    }


def companion_info() -> dict[str, Any]:
    response = request(MODIFIED_STATUS_PATH, timeout=3)
    if response.status == 200:
        body = parse_body(response)
        return {
            "available": True,
            "version": body.get("version") if isinstance(body, dict) else None,
            "manualInstallRequired": False,
        }
    return {
        "available": False,
        "status": response.status,
        "detail": (response.text or response.error or "unavailable")[:TEXT_LIMIT],
        "manualInstallRequired": True,
        "nextStep": (
            "Install the matching Zotero Modified Bridge XPI manually in Zotero's "
            "Plugins/Add-ons Manager, restart Zotero, then run status again."
        ),
    }


def require_companion() -> None:
    info = companion_info()
    if not info["available"]:
        exit_with(
            "The Zotero Modified Bridge companion add-on is required for colored statuses "
            "and CSL installation. First use requires a one-time manual installation of the "
            "matching released XPI in Zotero's Plugins/Add-ons Manager. Restart Zotero, then "
            "run status again."
        )


def authorize_write_internal(server: dict[str, Any]) -> dict[str, Any]:
    if not server.get("writeSupported") or not server.get("serverID"):
        exit_with("Zotero 10 or newer is required for authorized local writes")
    response = require_ok(
        request(
            "/api/local/authorize",
            method="POST",
            data={"appName": APP_NAME},
            headers={"Zotero-Server-ID": server["serverID"]},
            timeout=WRITE_TIMEOUT,
        ),
        "POST /api/local/authorize",
    )
    payload = parse_body(response)
    if not isinstance(payload, dict) or not payload.get("key"):
        exit_with("Zotero did not return a local write key")
    remember = bool(payload.get("remember"))
    cache_authorization(server["serverID"], payload["key"], remember)
    return {"serverID": server["serverID"], "remember": remember}


def authorized_request(
    path: str,
    *,
    method: str,
    data: Any,
    headers: dict[str, str] | None = None,
) -> Response:
    server = server_info()
    server_id = server.get("serverID")
    if not server_id:
        exit_with("The running Zotero instance did not report a Zotero-Server-ID")
    authorization = cached_authorization(server_id)
    if authorization is None:
        authorize_write_internal(server)
        authorization = cached_authorization(server_id)
    if authorization is None:
        exit_with("No local Zotero write authorization is available")

    write_headers = dict(headers or {})
    write_headers.update(
        {
            "Zotero-API-Key": str(authorization["key"]),
            "Zotero-Server-ID": server_id,
        }
    )
    response = request(
        path,
        method=method,
        data=data,
        headers=write_headers,
        timeout=WRITE_TIMEOUT,
    )
    if response.status == 401:
        drop_authorization(server_id)
        authorize_write_internal(server)
        authorization = cached_authorization(server_id)
        if authorization is None:
            exit_with("Zotero write reauthorization failed")
        write_headers["Zotero-API-Key"] = str(authorization["key"])
        response = request(
            path,
            method=method,
            data=data,
            headers=write_headers,
            timeout=WRITE_TIMEOUT,
        )
    if response.ok and authorization and not authorization.get("remember"):
        drop_authorization(server_id)
    return response


def data_of(value: dict[str, Any]) -> dict[str, Any]:
    data = value.get("data", value)
    if not isinstance(data, dict):
        exit_with("Unexpected Zotero object shape")
    return data


def collection_rows() -> list[dict[str, Any]]:
    return [data_of(row) for row in api_get(f"{LOCAL_USER}/collections")]


def resolve_collection(*, key: str | None, name: str | None) -> dict[str, Any]:
    if key:
        return data_of(api_get(f"{LOCAL_USER}/collections/{urllib.parse.quote(key)}"))
    if not name:
        exit_with("Provide a collection key or collection name")
    exact = [row for row in collection_rows() if row.get("name") == name]
    if not exact:
        folded = [row for row in collection_rows() if str(row.get("name", "")).casefold() == name.casefold()]
        exact = folded
    if not exact:
        exit_with(f"No Zotero collection matched name: {name}")
    if len(exact) > 1:
        keys = ", ".join(str(row.get("key")) for row in exact)
        exit_with(f"Collection name is ambiguous; use --collection-key. Matches: {keys}")
    return exact[0]


def summarize_collection(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": data.get("key"),
        "name": data.get("name"),
        "parentCollection": data.get("parentCollection"),
        "version": data.get("version"),
    }


def cmd_status(_: argparse.Namespace) -> None:
    server = server_info()
    server_id = server.get("serverID")
    authorization = cached_authorization(server_id) if server_id else None
    server.update(
        {
            "baseURL": DEFAULT_BASE_URL,
            "authorizationCached": bool(authorization),
            "authorizationRemembered": bool(authorization and authorization.get("remember")),
            "credentialPath": str(credential_path()),
            "modifiedBridge": companion_info(),
        }
    )
    dump_json(server)


def cmd_authorize(_: argparse.Namespace) -> None:
    result = authorize_write_internal(server_info())
    result["credentialPath"] = str(credential_path())
    dump_json(result)


def cmd_forget_authorization(_: argparse.Namespace) -> None:
    server = server_info()
    server_id = server.get("serverID")
    if server_id:
        drop_authorization(server_id)
    dump_json(
        {
            "serverID": server_id,
            "localCredentialRemoved": True,
            "note": "Use Zotero Settings > Advanced > Clear Write Authorizations to revoke remembered keys inside Zotero.",
        }
    )


def cmd_list_collections(_: argparse.Namespace) -> None:
    dump_json([summarize_collection(row) for row in collection_rows()])


def cmd_rename_collection(args: argparse.Namespace) -> None:
    current = resolve_collection(key=args.collection_key, name=args.current_name)
    preview = {
        "action": "rename-collection",
        "collectionKey": current.get("key"),
        "before": current.get("name"),
        "after": args.name,
        "version": current.get("version"),
        "changed": current.get("name") != args.name,
        "committed": False,
    }
    if not preview["changed"] or not args.yes:
        dump_json(preview)
        return

    key = str(current.get("key"))
    payload = {
        "key": key,
        "version": current.get("version"),
        "name": args.name,
        "parentCollection": current.get("parentCollection", False),
    }
    response = require_ok(
        authorized_request(
            f"{LOCAL_USER}/collections/{urllib.parse.quote(key)}",
            method="PUT",
            data=payload,
        ),
        f"PUT collection {key}",
    )
    verified = resolve_collection(key=key, name=None)
    preview.update(
        {
            "committed": True,
            "status": response.status,
            "verifiedName": verified.get("name"),
            "newVersion": verified.get("version"),
        }
    )
    dump_json(preview)


def cmd_create_collection(args: argparse.Namespace) -> None:
    parent: dict[str, Any] | None = None
    if args.parent_key or args.parent_name:
        parent = resolve_collection(key=args.parent_key, name=args.parent_name)
    parent_key = parent.get("key") if parent else False
    duplicates = [
        row
        for row in collection_rows()
        if row.get("name") == args.name and row.get("parentCollection", False) == parent_key
    ]
    preview = {
        "action": "create-collection",
        "name": args.name,
        "parentCollection": parent_key,
        "duplicateKeys": [row.get("key") for row in duplicates],
        "committed": False,
    }
    if duplicates and not args.allow_duplicate:
        preview["skipped"] = "an identically named collection already exists under this parent"
        dump_json(preview)
        return
    if not args.yes:
        dump_json(preview)
        return

    value: dict[str, Any] = {"name": args.name}
    if parent_key:
        value["parentCollection"] = parent_key
    response = require_ok(
        authorized_request(
            f"{LOCAL_USER}/collections",
            method="POST",
            data=[value],
            headers={"Zotero-Write-Token": uuid.uuid4().hex},
        ),
        "POST collection",
    )
    preview.update({"committed": True, "status": response.status, "response": parse_body(response)})
    dump_json(preview)


def cmd_delete_collection(args: argparse.Namespace) -> None:
    current = resolve_collection(key=args.collection_key, name=args.collection_name)
    key = str(current.get("key"))
    child_keys = [
        str(row.get("key"))
        for row in collection_rows()
        if row.get("parentCollection") == key
    ]
    preview = {
        "action": "delete-collection",
        "collection": summarize_collection(current),
        "childCollectionKeys": child_keys,
        "note": "Deleting a collection does not delete its library items.",
        "committed": False,
    }
    if not args.yes or args.confirm_key != key:
        preview["requiredConfirmation"] = key
        dump_json(preview)
        return
    response = require_ok(
        authorized_request(
            f"{LOCAL_USER}/collections/{urllib.parse.quote(key)}",
            method="DELETE",
            data=None,
            headers={"If-Unmodified-Since-Version": str(current.get("version"))},
        ),
        f"DELETE collection {key}",
    )
    preview.update({"committed": True, "status": response.status})
    dump_json(preview)


def cmd_backup_collection(args: argparse.Namespace) -> None:
    root = resolve_collection(key=args.collection_key, name=args.collection_name)
    all_collections = collection_rows()
    selected = [root]
    pending = [str(root.get("key"))]
    while pending:
        parent = pending.pop(0)
        children = [row for row in all_collections if row.get("parentCollection") == parent]
        selected.extend(children)
        pending.extend(str(row.get("key")) for row in children)

    items_by_key: dict[str, dict[str, Any]] = {}
    for collection in selected:
        key = urllib.parse.quote(str(collection.get("key")))
        for row in api_get(f"{LOCAL_USER}/collections/{key}/items"):
            data = data_of(row)
            if data.get("key"):
                items_by_key[str(data["key"])] = data

    snapshot = {
        "format": "zotero-modified-collection-backup-v1",
        "exportedAt": datetime.now(timezone.utc).isoformat(),
        "rootCollectionKey": root.get("key"),
        "collections": selected,
        "items": list(items_by_key.values()),
        "note": "Metadata snapshot only; attachment file contents are not included.",
    }
    target = Path(args.file)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dump_json(
        {
            "action": "backup-collection",
            "file": str(target.resolve()),
            "collectionCount": len(selected),
            "itemCount": len(items_by_key),
            "attachmentsIncluded": False,
        }
    )


def read_json_file(path: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        exit_with(f"Could not read JSON file {path}: {exc}")
    except json.JSONDecodeError as exc:
        exit_with(f"Invalid JSON file {path}: {exc}")


def cmd_create_item(args: argparse.Namespace) -> None:
    value = read_json_file(args.json_file)
    if not isinstance(value, dict):
        exit_with("--json-file must contain one Zotero item object")
    value = dict(value.get("data", value))
    if not value.get("itemType"):
        exit_with("The item object must contain itemType")
    value.pop("key", None)
    value.pop("version", None)
    preview = {
        "action": "create-item",
        "itemType": value.get("itemType"),
        "title": value.get("title"),
        "collections": value.get("collections", []),
        "tags": value.get("tags", []),
        "payload": value,
        "committed": False,
    }
    if not args.yes:
        dump_json(preview)
        return
    response = require_ok(
        authorized_request(
            f"{LOCAL_USER}/items",
            method="POST",
            data=[value],
            headers={"Zotero-Write-Token": uuid.uuid4().hex},
        ),
        "POST item",
    )
    preview.update({"committed": True, "status": response.status, "response": parse_body(response)})
    dump_json(preview)


def parse_assignment(raw: str, *, label: str) -> tuple[str, str]:
    if "=" not in raw:
        exit_with(f"{label} must use FIELD=VALUE syntax: {raw}")
    left, right = raw.split("=", 1)
    if not left:
        exit_with(f"{label} has an empty field/name: {raw}")
    return left, right


def parse_json_assignment(raw: str) -> tuple[str, Any]:
    field, value = parse_assignment(raw, label="--set-json")
    try:
        return field, json.loads(value)
    except json.JSONDecodeError as exc:
        exit_with(f"--set-json value for {field!r} is invalid JSON: {exc}")


def unique_items(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        data = data_of(row)
        key = str(data.get("key") or row.get("key") or "")
        if key and key not in seen:
            seen.add(key)
            result.append(data)
    return result


def select_items(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.item_key:
        rows = [api_get(f"{LOCAL_USER}/items/{urllib.parse.quote(key)}") for key in args.item_key]
    elif args.collection_key or args.collection_name:
        collection = resolve_collection(key=args.collection_key, name=args.collection_name)
        key = urllib.parse.quote(str(collection.get("key")))
        rows = api_get(f"{LOCAL_USER}/collections/{key}/items/top")
    elif args.query:
        rows = api_get(f"{LOCAL_USER}/items/top?{urllib.parse.urlencode({'q': args.query})}")
    elif args.all_items:
        rows = api_get(f"{LOCAL_USER}/items/top")
    else:
        exit_with("Select items by key, collection, query, or --all")
    items = unique_items(rows)
    if args.expect_count is not None and len(items) != args.expect_count:
        exit_with(f"Expected {args.expect_count} selected items, found {len(items)}; no changes made")
    return items


def replace_tags(tags: list[dict[str, Any]], replacements: list[tuple[str, str]]) -> list[dict[str, Any]]:
    mapping = dict(replacements)
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for original in tags:
        value = dict(original)
        name = str(value.get("tag", ""))
        value["tag"] = mapping.get(name, name)
        if value["tag"] and value["tag"] not in seen:
            seen.add(value["tag"])
            result.append(value)
    return result


def make_item_patch(data: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    forbidden = {"key", "version", "tags", "collections", "creators", "relations"}
    for raw in args.set_values or []:
        field, value = parse_assignment(raw, label="--set")
        if field in forbidden:
            exit_with(f"Use the dedicated option instead of --set for field: {field}")
        if field == "itemType":
            exit_with("Use --item-type instead of --set itemType=...")
        if field not in data:
            exit_with(f"Field {field!r} is not valid for item {data.get('key')} ({data.get('itemType')})")
        if data.get(field) != value:
            patch[field] = value
    for field in args.clear_fields or []:
        if field in forbidden or field == "itemType":
            exit_with(f"Field cannot be cleared with --clear: {field}")
        if field not in data:
            exit_with(f"Field {field!r} is not valid for item {data.get('key')} ({data.get('itemType')})")
        if data.get(field) != "":
            patch[field] = ""
    for raw in args.set_json_values or []:
        field, value = parse_json_assignment(raw)
        if field in {"key", "version", "itemType", "tags", "collections"}:
            exit_with(f"Field cannot be changed with --set-json: {field}")
        if field not in data:
            exit_with(f"Field {field!r} is not valid for item {data.get('key')} ({data.get('itemType')})")
        if data.get(field) != value:
            patch[field] = value
    if args.item_type and data.get("itemType") != args.item_type:
        patch["itemType"] = args.item_type

    original_tags = [dict(tag) for tag in data.get("tags", [])]
    tags = replace_tags(
        original_tags,
        [parse_assignment(raw, label="--replace-tag") for raw in (args.replace_tags or [])],
    )
    removed = set(args.remove_tags or [])
    tags = [tag for tag in tags if tag.get("tag") not in removed]
    existing = {str(tag.get("tag")) for tag in tags}
    for name in args.add_tags or []:
        if name not in existing:
            tags.append({"tag": name})
            existing.add(name)
    if tags != original_tags:
        patch["tags"] = tags

    original_collections = list(data.get("collections", []))
    collections = [
        key for key in original_collections if key not in set(args.remove_collection_keys or [])
    ]
    for key in args.add_collection_keys or []:
        if key not in collections:
            collections.append(key)
    if collections != original_collections:
        patch["collections"] = collections
    return patch


def chunks(values: list[Any], size: int) -> Iterable[list[Any]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def verify_collection_keys(keys: Iterable[str]) -> None:
    for key in sorted(set(keys)):
        resolve_collection(key=key, name=None)


def commit_item_patches(planned: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    responses: list[dict[str, Any]] = []
    failed: dict[str, Any] = {}
    for batch in chunks(planned, MAX_BATCH):
        payload = [
            {"key": row["key"], "version": row["version"], **row["patch"]} for row in batch
        ]
        response = require_ok(
            authorized_request(f"{LOCAL_USER}/items", method="POST", data=payload),
            "POST batch item update",
        )
        body = parse_body(response)
        responses.append({"status": response.status, "response": body})
        if isinstance(body, dict) and body.get("failed"):
            failed.update(body["failed"])
    return responses, failed


def cmd_batch_update_items(args: argparse.Namespace) -> None:
    verify_collection_keys((args.add_collection_keys or []) + (args.remove_collection_keys or []))
    items = select_items(args)
    planned: list[dict[str, Any]] = []
    for data in items:
        patch = make_item_patch(data, args)
        if patch:
            before = {field: data.get(field) for field in patch}
            planned.append(
                {
                    "key": data.get("key"),
                    "version": data.get("version"),
                    "title": data.get("title"),
                    "itemType": data.get("itemType"),
                    "before": before,
                    "patch": patch,
                }
            )
    preview = {
        "action": "batch-update-items",
        "selectedCount": len(items),
        "changedCount": len(planned),
        "unchangedCount": len(items) - len(planned),
        "committed": False,
        "updates": planned,
    }
    if not args.yes or not planned:
        dump_json(preview)
        return

    responses, failed = commit_item_patches(planned)

    preview.update(
        {
            "committed": True,
            "batchCount": len(responses),
            "responses": responses,
            "failed": failed,
        }
    )
    dump_json(preview)
    if failed:
        raise SystemExit(2)


def make_simple_patch(data: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": data.get("key"),
        "version": data.get("version"),
        "title": data.get("title"),
        "itemType": data.get("itemType"),
        "before": {field: data.get(field) for field in patch},
        "patch": patch,
    }


def normalize_status_name(name: str) -> str:
    value = name.strip()
    if not value:
        exit_with("Status name cannot be empty")
    return value if value.startswith(STATUS_PREFIX) else STATUS_PREFIX + value


def update_extra_rating(extra: str, value: int | None) -> str:
    lines = [line for line in extra.splitlines() if not RATE_LINE_RE.match(line)]
    if value is not None:
        lines.append(f"rate: {value}")
    return "\n".join(lines).strip()


def cmd_set_rating(args: argparse.Namespace) -> None:
    if args.value is not None and not 1 <= args.value <= 5:
        exit_with("Style-compatible rating must be between 1 and 5")
    items = select_items(args)
    planned: list[dict[str, Any]] = []
    for data in items:
        before = str(data.get("extra") or "")
        after = update_extra_rating(before, args.value)
        if after != before:
            planned.append(make_simple_patch(data, {"extra": after}))
    preview = {
        "action": "clear-rating" if args.value is None else "set-rating",
        "value": args.value,
        "selectedCount": len(items),
        "changedCount": len(planned),
        "committed": False,
        "updates": planned,
    }
    if not args.yes or not planned:
        dump_json(preview)
        return
    responses, failed = commit_item_patches(planned)
    preview.update({"committed": True, "responses": responses, "failed": failed})
    dump_json(preview)
    if failed:
        raise SystemExit(2)


def bridge_statuses() -> list[dict[str, Any]]:
    require_companion()
    body = api_get(MODIFIED_STATUS_PATH)
    if not isinstance(body, dict) or not isinstance(body.get("statuses"), list):
        exit_with("Unexpected response from Zotero Modified Bridge")
    return body["statuses"]


def bridge_colored_tags() -> list[dict[str, Any]]:
    require_companion()
    body = api_get(MODIFIED_STATUS_PATH)
    if not isinstance(body, dict) or not isinstance(body.get("coloredTags"), list):
        exit_with("Unexpected response from Zotero Modified Bridge")
    return body["coloredTags"]


def cmd_list_statuses(_: argparse.Namespace) -> None:
    dump_json(bridge_statuses())


def cmd_list_colored_tags(_: argparse.Namespace) -> None:
    dump_json(bridge_colored_tags())


def cmd_set_colored_tag(args: argparse.Namespace) -> None:
    name = args.name.strip()
    if not name:
        exit_with("Colored tag name cannot be empty")
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", args.color):
        exit_with("Tag color must use #RRGGBB syntax")
    existing = {row.get("name"): row for row in bridge_colored_tags()}
    preview = {
        "action": "set-colored-tag",
        "name": name,
        "color": args.color,
        "position": args.position,
        "before": existing.get(name),
        "coloredTagCountAfter": len(existing) + (0 if name in existing else 1),
        "note": "Keep this set small; ordinary topical tags do not need colors.",
        "committed": False,
    }
    if not args.yes:
        dump_json(preview)
        return
    response = require_ok(
        authorized_request(
            MODIFIED_STATUS_PATH,
            method="PUT",
            data={"name": name, "color": args.color, "position": args.position},
        ),
        f"PUT colored tag {name}",
    )
    preview.update({"committed": True, "status": response.status, "response": parse_body(response)})
    dump_json(preview)


def cmd_clear_colored_tag(args: argparse.Namespace) -> None:
    name = args.name.strip()
    existing = {row.get("name"): row for row in bridge_colored_tags()}
    preview = {
        "action": "clear-colored-tag",
        "name": name,
        "before": existing.get(name),
        "note": "The ordinary tag and item assignments are retained; only its color is removed.",
        "committed": False,
    }
    if not args.yes or args.confirm_name != name:
        preview["requiredConfirmation"] = name
        dump_json(preview)
        return
    query = urllib.parse.urlencode({"name": name, "deleteTag": "0"})
    response = require_ok(
        authorized_request(f"{MODIFIED_STATUS_PATH}?{query}", method="DELETE", data=None),
        f"DELETE color assignment for {name}",
    )
    preview.update({"committed": True, "status": response.status})
    dump_json(preview)


def cmd_create_status(args: argparse.Namespace) -> None:
    name = normalize_status_name(args.name)
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", args.color):
        exit_with("Status color must use #RRGGBB syntax")
    existing = {row.get("name"): row for row in bridge_statuses()}
    preview = {
        "action": "create-or-update-status",
        "name": name,
        "color": args.color,
        "position": args.position,
        "before": existing.get(name),
        "committed": False,
    }
    if not args.yes:
        dump_json(preview)
        return
    response = require_ok(
        authorized_request(
            MODIFIED_STATUS_PATH,
            method="PUT",
            data={"name": name, "color": args.color, "position": args.position},
        ),
        f"PUT slash-prefixed status {name}",
    )
    preview.update({"committed": True, "status": response.status, "response": parse_body(response)})
    dump_json(preview)


def cmd_set_status(args: argparse.Namespace) -> None:
    name = normalize_status_name(args.name) if args.name else None
    statuses = {row.get("name") for row in bridge_statuses()} if name else set()
    if name and name not in statuses:
        exit_with(f"Status {name!r} is not a configured colored status; create it first")
    items = select_items(args)
    planned: list[dict[str, Any]] = []
    for data in items:
        original = [dict(tag) for tag in data.get("tags", [])]
        tags = [tag for tag in original if not str(tag.get("tag", "")).startswith(STATUS_PREFIX)]
        if name:
            tags.append({"tag": name})
        if tags != original:
            planned.append(make_simple_patch(data, {"tags": tags}))
    preview = {
        "action": "clear-status" if name is None else "set-status",
        "status": name,
        "selectedCount": len(items),
        "changedCount": len(planned),
        "committed": False,
        "updates": planned,
    }
    if not args.yes or not planned:
        dump_json(preview)
        return
    responses, failed = commit_item_patches(planned)
    preview.update({"committed": True, "responses": responses, "failed": failed})
    dump_json(preview)
    if failed:
        raise SystemExit(2)


def cmd_delete_status(args: argparse.Namespace) -> None:
    name = normalize_status_name(args.name)
    matches = api_get(
        f"{LOCAL_USER}/items/top?{urllib.parse.urlencode({'tag': name})}"
    )
    count = len(matches) if isinstance(matches, list) else 0
    preview = {
        "action": "delete-status",
        "name": name,
        "affectedItemCount": count,
        "note": "This removes the status tag from every item and removes its color assignment.",
        "committed": False,
    }
    if not args.yes or args.confirm_name != name:
        preview["requiredConfirmation"] = name
        dump_json(preview)
        return
    require_companion()
    query = urllib.parse.urlencode({"name": name, "deleteTag": "1"})
    response = require_ok(
        authorized_request(f"{MODIFIED_STATUS_PATH}?{query}", method="DELETE", data=None),
        f"DELETE slash-prefixed status {name}",
    )
    preview.update({"committed": True, "status": response.status})
    dump_json(preview)


def cmd_trash_items(args: argparse.Namespace) -> None:
    items = select_items(args)
    planned = [
        make_simple_patch(data, {"deleted": 1})
        for data in items
        if not data.get("deleted")
    ]
    preview = {
        "action": "trash-items",
        "selectedCount": len(items),
        "changedCount": len(planned),
        "committed": False,
        "items": [{"key": row["key"], "title": row["title"]} for row in planned],
    }
    if not args.yes or not planned:
        dump_json(preview)
        return
    responses, failed = commit_item_patches(planned)
    preview.update({"committed": True, "responses": responses, "failed": failed})
    dump_json(preview)
    if failed:
        raise SystemExit(2)


def cmd_delete_items(args: argparse.Namespace) -> None:
    items = select_items(args)
    preview = {
        "action": "delete-items-permanently",
        "selectedCount": len(items),
        "items": [
            {"key": row.get("key"), "title": row.get("title"), "version": row.get("version")}
            for row in items
        ],
        "committed": False,
    }
    if not args.yes or args.confirm != "DELETE-PERMANENTLY":
        preview["requiredConfirmation"] = "DELETE-PERMANENTLY"
        dump_json(preview)
        return
    completed: list[str] = []
    for data in items:
        key = str(data.get("key"))
        require_ok(
            authorized_request(
                f"{LOCAL_USER}/items/{urllib.parse.quote(key)}",
                method="DELETE",
                data=None,
                headers={"If-Unmodified-Since-Version": str(data.get("version"))},
            ),
            f"DELETE item {key}",
        )
        completed.append(key)
    preview.update({"committed": True, "deletedKeys": completed})
    dump_json(preview)


def find_csl_metadata(text: str) -> dict[str, str]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        exit_with(f"Invalid CSL XML: {exc}")

    info = next(
        (element for element in root if element.tag.rsplit("}", 1)[-1] == "info"),
        None,
    )
    if info is None:
        exit_with("CSL must include an info element")

    def first(local_name: str) -> str | None:
        for element in info.iter():
            if element.tag.rsplit("}", 1)[-1] == local_name and element.text:
                return element.text.strip()
        return None

    style_id = first("id")
    title = first("title")
    if not style_id or not title:
        exit_with("CSL must include info/id and info/title")
    return {"id": style_id, "title": title}


def csl_backup_dir() -> Path:
    return credential_path().parent / "csl-backups"


def backup_csl(style_id: str, csl: str) -> Path:
    root = csl_backup_dir()
    root.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", style_id.rsplit("/", 1)[-1]).strip("-") or "style"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = root / f"{slug}-{stamp}.csl"
    path.write_text(csl, encoding="utf-8")
    return path


def bridge_style(style_id: str) -> dict[str, Any] | None:
    require_companion()
    response = request(f"{MODIFIED_STYLES_PATH}?{urllib.parse.urlencode({'id': style_id})}")
    if response.status == 404:
        return None
    require_ok(response, f"GET CSL style {style_id}")
    body = parse_body(response)
    return body if isinstance(body, dict) else None


def cmd_list_styles(_: argparse.Namespace) -> None:
    require_companion()
    dump_json(api_get(MODIFIED_STYLES_PATH))


def cmd_install_csl(args: argparse.Namespace) -> None:
    csl = Path(args.file).read_text(encoding="utf-8")
    metadata = find_csl_metadata(csl)
    existing = bridge_style(metadata["id"])
    preview = {
        "action": "install-csl",
        "file": str(Path(args.file).resolve()),
        "style": metadata,
        "sha256": hashlib.sha256(csl.encode("utf-8")).hexdigest(),
        "replacesExisting": bool(existing),
        "committed": False,
    }
    if not args.yes:
        dump_json(preview)
        return
    if existing and existing.get("csl"):
        preview["backup"] = str(backup_csl(metadata["id"], str(existing["csl"])))
    response = require_ok(
        authorized_request(
            MODIFIED_STYLES_PATH,
            method="POST",
            data={"csl": csl, "origin": Path(args.file).name},
        ),
        f"POST CSL style {metadata['id']}",
    )
    preview.update({"committed": True, "status": response.status, "response": parse_body(response)})
    dump_json(preview)


def cmd_uninstall_csl(args: argparse.Namespace) -> None:
    existing = bridge_style(args.id)
    if not existing:
        exit_with(f"CSL style not installed: {args.id}")
    preview = {
        "action": "uninstall-csl",
        "style": {"id": existing.get("id"), "title": existing.get("title")},
        "committed": False,
    }
    if not args.yes or args.confirm_id != args.id:
        preview["requiredConfirmation"] = args.id
        dump_json(preview)
        return
    if existing.get("csl"):
        preview["backup"] = str(backup_csl(args.id, str(existing["csl"])))
    query = urllib.parse.urlencode({"id": args.id})
    response = require_ok(
        authorized_request(f"{MODIFIED_STYLES_PATH}?{query}", method="DELETE", data=None),
        f"DELETE CSL style {args.id}",
    )
    preview.update({"committed": True, "status": response.status})
    dump_json(preview)


def add_collection_selector(parser: argparse.ArgumentParser, *, rename: bool = False) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--collection-key")
    group.add_argument("--current-name" if rename else "--collection-name")


def add_item_selector(parser: argparse.ArgumentParser) -> None:
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--item-key", action="append", help="Repeat to select multiple keys")
    selection.add_argument("--collection-key")
    selection.add_argument("--collection-name")
    selection.add_argument("--query")
    selection.add_argument("--all", action="store_true", dest="all_items")
    parser.add_argument("--expect-count", type=int, help="Abort unless exactly this many items match")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage Zotero 10 through its authorized local API. Writes preview by default."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status", help="Show local API and write-authorization status")
    status.set_defaults(func=cmd_status)

    authorize = commands.add_parser(
        "authorize-write",
        help="Ask Zotero for a local write key; choose Always Allow for unattended future writes",
    )
    authorize.set_defaults(func=cmd_authorize)

    forget = commands.add_parser("forget-write-key", help="Delete the locally cached write key")
    forget.set_defaults(func=cmd_forget_authorization)

    collections = commands.add_parser("collections", help="List Zotero collections")
    collections.set_defaults(func=cmd_list_collections)

    rename = commands.add_parser("rename-collection", help="Preview or rename one collection")
    add_collection_selector(rename, rename=True)
    rename.add_argument("--name", required=True, help="New collection name")
    rename.add_argument("--yes", action="store_true", help="Commit the previewed change")
    rename.set_defaults(func=cmd_rename_collection)

    create = commands.add_parser("create-collection", help="Preview or create a collection")
    create.add_argument("--name", required=True)
    parent = create.add_mutually_exclusive_group()
    parent.add_argument("--parent-key")
    parent.add_argument("--parent-name")
    create.add_argument("--allow-duplicate", action="store_true")
    create.add_argument("--yes", action="store_true", help="Commit the previewed change")
    create.set_defaults(func=cmd_create_collection)

    delete_collection = commands.add_parser(
        "delete-collection", help="Preview or delete one collection without deleting its items"
    )
    add_collection_selector(delete_collection)
    delete_collection.add_argument("--confirm-key")
    delete_collection.add_argument("--yes", action="store_true")
    delete_collection.set_defaults(func=cmd_delete_collection)

    create_item = commands.add_parser("create-item", help="Preview or create one Zotero item")
    create_item.add_argument("--json-file", required=True)
    create_item.add_argument("--yes", action="store_true")
    create_item.set_defaults(func=cmd_create_item)

    backup_collection = commands.add_parser(
        "backup-collection", help="Export a collection subtree and item metadata to JSON"
    )
    add_collection_selector(backup_collection)
    backup_collection.add_argument("--file", required=True)
    backup_collection.set_defaults(func=cmd_backup_collection)

    batch = commands.add_parser(
        "batch-update-items",
        help="Preview or batch-update item fields, type, tags, or collection membership",
    )
    add_item_selector(batch)
    batch.add_argument("--set", action="append", dest="set_values", metavar="FIELD=VALUE")
    batch.add_argument(
        "--set-json",
        action="append",
        dest="set_json_values",
        metavar="FIELD=JSON",
        help="Set structured metadata such as creators or relations",
    )
    batch.add_argument("--clear", action="append", dest="clear_fields", metavar="FIELD")
    batch.add_argument("--item-type")
    batch.add_argument("--add-tag", action="append", dest="add_tags")
    batch.add_argument("--remove-tag", action="append", dest="remove_tags")
    batch.add_argument("--replace-tag", action="append", dest="replace_tags", metavar="OLD=NEW")
    batch.add_argument("--add-collection-key", action="append", dest="add_collection_keys")
    batch.add_argument("--remove-collection-key", action="append", dest="remove_collection_keys")
    batch.add_argument("--yes", action="store_true", help="Commit all previewed changes")
    batch.set_defaults(func=cmd_batch_update_items)

    set_rating = commands.add_parser("set-rating", help="Preview or set style-compatible rate: N")
    add_item_selector(set_rating)
    set_rating.add_argument("--value", type=int, choices=range(1, 6), required=True)
    set_rating.add_argument("--yes", action="store_true")
    set_rating.set_defaults(func=cmd_set_rating)

    clear_rating = commands.add_parser("clear-rating", help="Preview or remove Style-compatible rating")
    add_item_selector(clear_rating)
    clear_rating.add_argument("--yes", action="store_true")
    clear_rating.set_defaults(func=cmd_set_rating, value=None)

    colored_tags = commands.add_parser("colored-tags", help="List Zotero colored tags")
    colored_tags.set_defaults(func=cmd_list_colored_tags)

    set_colored_tag = commands.add_parser(
        "set-colored-tag", help="Preview or assign one native Zotero tag color"
    )
    set_colored_tag.add_argument("--name", required=True)
    set_colored_tag.add_argument("--color", required=True)
    set_colored_tag.add_argument("--position", type=int, default=0)
    set_colored_tag.add_argument("--yes", action="store_true")
    set_colored_tag.set_defaults(func=cmd_set_colored_tag)

    clear_colored_tag = commands.add_parser(
        "clear-colored-tag", help="Preview or clear one native Zotero tag color"
    )
    clear_colored_tag.add_argument("--name", required=True)
    clear_colored_tag.add_argument("--confirm-name")
    clear_colored_tag.add_argument("--yes", action="store_true")
    clear_colored_tag.set_defaults(func=cmd_clear_colored_tag)

    statuses = commands.add_parser("statuses", help="List colored slash-prefixed statuses")
    statuses.set_defaults(func=cmd_list_statuses)

    create_status = commands.add_parser(
        "create-status", help="Preview or create a colored slash-prefixed status"
    )
    create_status.add_argument("--name", required=True)
    create_status.add_argument("--color", required=True)
    create_status.add_argument("--position", type=int, default=12)
    create_status.add_argument("--yes", action="store_true")
    create_status.set_defaults(func=cmd_create_status)

    set_status = commands.add_parser("set-status", help="Preview or set one status on items")
    add_item_selector(set_status)
    set_status.add_argument("--name", required=True)
    set_status.add_argument("--yes", action="store_true")
    set_status.set_defaults(func=cmd_set_status)

    clear_status = commands.add_parser("clear-status", help="Preview or clear item statuses")
    add_item_selector(clear_status)
    clear_status.add_argument("--yes", action="store_true")
    clear_status.set_defaults(func=cmd_set_status, name=None)

    delete_status = commands.add_parser(
        "delete-status", help="Preview or remove a status and all of its item assignments"
    )
    delete_status.add_argument("--name", required=True)
    delete_status.add_argument("--confirm-name")
    delete_status.add_argument("--yes", action="store_true")
    delete_status.set_defaults(func=cmd_delete_status)

    trash_items = commands.add_parser("trash-items", help="Preview or move items to Zotero trash")
    add_item_selector(trash_items)
    trash_items.add_argument("--yes", action="store_true")
    trash_items.set_defaults(func=cmd_trash_items)

    delete_items = commands.add_parser(
        "delete-items", help="Preview or permanently delete selected items"
    )
    add_item_selector(delete_items)
    delete_items.add_argument("--confirm")
    delete_items.add_argument("--yes", action="store_true")
    delete_items.set_defaults(func=cmd_delete_items)

    styles = commands.add_parser("styles", help="List installed CSL styles")
    styles.set_defaults(func=cmd_list_styles)

    install_csl = commands.add_parser("install-csl", help="Validate, preview, and install a CSL file")
    install_csl.add_argument("--file", required=True)
    install_csl.add_argument("--yes", action="store_true")
    install_csl.set_defaults(func=cmd_install_csl)

    uninstall_csl = commands.add_parser("uninstall-csl", help="Back up and uninstall one CSL style")
    uninstall_csl.add_argument("--id", required=True)
    uninstall_csl.add_argument("--confirm-id")
    uninstall_csl.add_argument("--yes", action="store_true")
    uninstall_csl.set_defaults(func=cmd_uninstall_csl)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
