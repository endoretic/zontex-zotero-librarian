#!/usr/bin/env python3
"""Safe Zotero 10 local-library management for Codex.

The Zotero 10 local API supports authenticated writes. This helper adds a
small command surface around those writes. Use ``status --require-write`` as
an up-front authorization gate. Mutating commands commit with ``--yes`` and
retain a no-``--yes`` dry-run for workflows that explicitly request a preview
or per-step audit. Every update carries Zotero's current object version to
prevent overwriting concurrent edits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import sys
import time
import unicodedata
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
APP_NAME = "Zontex"
TEXT_LIMIT = 500
WRITE_TIMEOUT = 180.0
MAX_BATCH = 50
MAX_COLORED_TAGS = 9
ZONTEX_STATUS_PATH = f"{LOCAL_USER}/zontex/statuses"
ZONTEX_STYLES_PATH = f"{LOCAL_USER}/zontex/styles"
ZONTEX_CONTEXT_PATH = f"{LOCAL_USER}/zontex/context"
ZONTEX_RENDER_PATH = f"{LOCAL_USER}/zontex/render"
ZONTEX_NAVIGATE_PATH = f"{LOCAL_USER}/zontex/navigate"
ZONTEX_DOCUMENT_SEGMENTS_PATH = f"{LOCAL_USER}/zontex/document-segments"
ZONTEX_ANNOTATIONS_PATH = f"{LOCAL_USER}/zontex/annotations"
ZONTEX_ANNOTATION_NOTE_PATH = f"{LOCAL_USER}/zontex/annotations/note"
ZONTEX_TAG_RENAME_PATH = f"{LOCAL_USER}/zontex/tags/rename"
ZONTEX_TAG_MERGE_PATH = f"{LOCAL_USER}/zontex/tags/merge"
ZONTEX_ITEM_MERGE_PATH = f"{LOCAL_USER}/zontex/items/merge"
STATUS_PREFIX = "/"
RATE_LINE_RE = re.compile(r"^\s*rate\s*:\s*([1-5])\s*$", re.IGNORECASE)
RATE_FIELD_RE = re.compile(r"^\s*rate\s*:", re.IGNORECASE)
CSL_NAMESPACE = "http://purl.org/net/xbiblio/csl"
METADATA_PROFILE_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "metadata-profiles"
    / "ethereal-default-v2.json"
)


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
    text = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False)
    encoding = getattr(sys.stdout, "encoding", None)
    if encoding:
        try:
            text.encode(encoding)
        except (LookupError, UnicodeEncodeError):
            text = json.dumps(value, indent=2, ensure_ascii=True, sort_keys=False)
    print(text)


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


def bridge_post(path: str, data: dict[str, Any], action: str) -> Any:
    require_companion()
    response = require_ok(
        authorized_request(path, method="POST", data=data),
        action,
    )
    payload = parse_body(response)
    if payload is None:
        exit_with(f"{action} returned an empty response")
    return payload


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
    return root / "Codex" / "Zontex" / "credentials.json"


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
    response = request(ZONTEX_STATUS_PATH, timeout=3)
    if response.status == 200:
        body = parse_body(response)
        return {
            "available": True,
            "version": body.get("version") if isinstance(body, dict) else None,
            "compatibility": body.get("compatibility") if isinstance(body, dict) else None,
            "manualInstallRequired": False,
        }
    return {
        "available": False,
        "status": response.status,
        "detail": (response.text or response.error or "unavailable")[:TEXT_LIMIT],
        "manualInstallRequired": True,
        "nextStep": (
            "Install the matching Zontex Bridge XPI manually in Zotero's "
            "Plugins/Add-ons Manager, restart Zotero, then run status again."
        ),
    }


def require_companion() -> None:
    info = companion_info()
    if not info["available"]:
        exit_with(
            "The Zontex Bridge companion add-on is required for colored statuses "
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
    server: dict[str, Any] | None = None,
) -> Response:
    server = server or server_info()
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


def cmd_status(args: argparse.Namespace) -> None:
    server = server_info()
    server_id = server.get("serverID")
    authorization = cached_authorization(server_id) if server_id else None
    gate_passed = bool(server.get("writeSupported") and server_id and authorization)
    blocking_reasons: list[str] = []
    if not server.get("writeSupported") or not server_id:
        blocking_reasons.append("Zotero 10 authorized local writes are unavailable")
    if not authorization:
        blocking_reasons.append("No cached local write authorization is available")
    server.update(
        {
            "baseURL": DEFAULT_BASE_URL,
            "authorizationCached": bool(authorization),
            "authorizationRemembered": bool(authorization and authorization.get("remember")),
            "credentialPath": str(credential_path()),
            "zontexBridge": companion_info(),
            "authorizationGate": {
                "required": bool(getattr(args, "require_write", False)),
                "passed": gate_passed,
                "blockingReasons": blocking_reasons,
                "nextStep": None
                if gate_passed
                else "Run authorize-write, approve the Zotero prompt, then rerun status --require-write.",
            },
        }
    )
    dump_json(server)
    if getattr(args, "require_write", False) and not gate_passed:
        raise SystemExit(2)


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
        "format": "zontex-collection-backup-v1",
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


def load_metadata_profile() -> dict[str, Any]:
    value = read_json_file(str(METADATA_PROFILE_PATH))
    schema_version = value.get("schemaVersion") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != 1
    ):
        exit_with("The bundled metadata profile has an unsupported schema")
    palette = value.get("palette")
    if not isinstance(palette, list) or len(palette) != MAX_COLORED_TAGS:
        exit_with(f"The metadata profile must define exactly {MAX_COLORED_TAGS} colors")
    if any(not isinstance(row, dict) for row in palette):
        exit_with("Metadata profile palette entries must be objects")
    names = [row.get("name") for row in palette]
    positions = [row.get("position") for row in palette]
    colors = [row.get("color") for row in palette]
    if (
        any(not isinstance(name, str) or not name for name in names)
        or len(set(names)) != MAX_COLORED_TAGS
    ):
        exit_with("Metadata profile palette names must be non-empty and unique")
    if (
        any(isinstance(position, bool) or not isinstance(position, int) for position in positions)
        or positions != list(range(MAX_COLORED_TAGS))
    ):
        exit_with("Metadata profile palette positions must be exactly 0–8")
    if any(not isinstance(color, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", color) for color in colors):
        exit_with("Metadata profile colors must use #RRGGBB syntax")

    statuses = value.get("statuses", {}).get("values")
    roles = value.get("roles", {})
    primary = roles.get("primary")
    secondary = roles.get("secondary")
    topics = value.get("topics", {})
    if not all(
        isinstance(rows, list)
        and rows
        and all(isinstance(name, str) and name for name in rows)
        for rows in (statuses, primary, secondary)
    ):
        exit_with("Metadata profile status and role vocabularies must be non-empty lists")
    managed = [*statuses, *primary, *secondary]
    if len(set(managed)) != len(managed) or any(name not in names for name in managed):
        exit_with("Metadata profile managed tags must be unique palette entries")
    if not isinstance(topics.get("prefix"), str) or not topics["prefix"]:
        exit_with("Metadata profile topic prefix must be non-empty")
    return value


def metadata_tag_sets(profile: dict[str, Any]) -> tuple[set[str], set[str], set[str]]:
    statuses = set(profile["statuses"]["values"])
    primary = set(profile["roles"]["primary"])
    secondary = set(profile["roles"]["secondary"])
    return statuses, primary, secondary


def metadata_violations(data: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    names = [str(tag.get("tag", "")) for tag in data.get("tags", [])]
    statuses, primary, secondary = metadata_tag_sets(profile)
    item_statuses = [name for name in names if name.startswith(STATUS_PREFIX)]
    primary_roles = [name for name in names if name in primary]
    role_signals = [name for name in names if name in primary or name in secondary]
    prefix = profile["topics"]["prefix"]
    topics = [name for name in names if name.startswith(prefix)]
    rate_lines = [line for line in str(data.get("extra") or "").splitlines() if RATE_FIELD_RE.match(line)]

    problems: list[str] = []
    if len(item_statuses) > profile["statuses"]["maxPerItem"]:
        problems.append("multiple-statuses")
    if any(name not in statuses for name in item_statuses):
        problems.append("unknown-status")
    if len(primary_roles) != 1:
        problems.append("primary-role-count")
    if not profile["roles"]["minPerItem"] <= len(role_signals) <= profile["roles"]["maxPerItem"]:
        problems.append("role-signal-count")
    if not profile["topics"]["minPerItem"] <= len(topics) <= profile["topics"]["maxPerItem"]:
        problems.append("topic-count")
    if len(rate_lines) != 1:
        problems.append("rating-count")
    elif not RATE_LINE_RE.match(rate_lines[0]):
        problems.append("invalid-rating")
    return problems


def cmd_metadata_profile(_: argparse.Namespace) -> None:
    dump_json(load_metadata_profile())


def cmd_metadata_audit(args: argparse.Namespace) -> None:
    profile = load_metadata_profile()
    items = select_items(args)
    violations = [
        {
            "key": data.get("key"),
            "title": data.get("title"),
            "violations": problems,
        }
        for data in items
        if (problems := metadata_violations(data, profile))
    ]
    dump_json(
        {
            "action": "metadata-audit",
            "profile": profile["name"],
            "selectedCount": len(items),
            "compliantCount": len(items) - len(violations),
            "violationCount": len(violations),
            "violations": violations,
        }
    )


def validate_metadata_proposal(
    value: Any, profile: dict[str, Any], index: int
) -> dict[str, Any]:
    if not isinstance(value, dict):
        exit_with(f"Metadata manifest item {index} must be an object")
    allowed = {
        "key",
        "expectedVersion",
        "status",
        "primaryRole",
        "secondary",
        "topics",
        "rating",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        exit_with(f"Metadata manifest item {index} has unknown fields: {', '.join(unknown)}")
    key = value.get("key")
    if not isinstance(key, str) or not key.strip():
        exit_with(f"Metadata manifest item {index} requires a non-empty key")
    result = dict(value)
    result["key"] = key.strip()
    if "expectedVersion" not in result:
        exit_with(f"Metadata manifest item {index} requires expectedVersion")
    if (
        isinstance(result["expectedVersion"], bool)
        or not isinstance(result["expectedVersion"], int)
        or result["expectedVersion"] < 0
    ):
        exit_with(f"Metadata manifest item {index} expectedVersion must be non-negative")

    statuses, primary, secondary = metadata_tag_sets(profile)
    if "status" in result and result["status"] is not None and result["status"] not in statuses:
        exit_with(f"Metadata manifest item {index} has an unsupported status")
    if "primaryRole" in result or "secondary" in result:
        if result.get("primaryRole") not in primary:
            exit_with(f"Metadata manifest item {index} requires one supported primaryRole")
        extra = result.get("secondary", [])
        if not isinstance(extra, list) or len(extra) != len(set(extra)) or any(tag not in secondary for tag in extra):
            exit_with(f"Metadata manifest item {index} secondary tags must be unique supported values")
        if 1 + len(extra) > profile["roles"]["maxPerItem"]:
            exit_with(f"Metadata manifest item {index} has too many Role/Signal tags")
        result["secondary"] = extra
    if "topics" in result:
        topics = result["topics"]
        prefix = profile["topics"]["prefix"]
        if (
            not isinstance(topics, list)
            or len(topics) != len(set(topics))
            or not profile["topics"]["minPerItem"] <= len(topics) <= profile["topics"]["maxPerItem"]
            or any(not isinstance(topic, str) or not topic.startswith(prefix) or topic == prefix for topic in topics)
        ):
            exit_with(f"Metadata manifest item {index} topics must be 1–3 unique {prefix} tags")
    if "rating" in result and (
        isinstance(result["rating"], bool)
        or not isinstance(result["rating"], int)
        or not 1 <= result["rating"] <= 5
    ):
        exit_with(f"Metadata manifest item {index} rating must be an integer from 1 to 5")
    if not set(result).intersection({"status", "primaryRole", "secondary", "topics", "rating"}):
        exit_with(f"Metadata manifest item {index} does not request a metadata change")
    return result


def read_metadata_manifest(
    path: str, expect_count: int
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    profile = load_metadata_profile()
    value = read_json_file(path)
    if not isinstance(value, dict) or value.get("profile") != profile["name"]:
        exit_with(f"Metadata manifest must select profile {profile['name']!r}")
    rows = value.get("items")
    if expect_count < 1 or not isinstance(rows, list) or len(rows) != expect_count:
        exit_with(f"Expected {expect_count} metadata manifest items")
    proposals = [validate_metadata_proposal(row, profile, index) for index, row in enumerate(rows)]
    keys = [row["key"] for row in proposals]
    if len(keys) != len(set(keys)):
        exit_with("Metadata manifest item keys must be unique")
    return profile, proposals


def metadata_items_by_keys(keys: list[str]) -> list[dict[str, Any]]:
    return items_by_keys(keys)


def make_metadata_patch(
    data: dict[str, Any], proposal: dict[str, Any], profile: dict[str, Any]
) -> dict[str, Any]:
    original_tags = [dict(tag) for tag in data.get("tags", [])]
    tags = list(original_tags)
    tags_changed = False
    statuses, primary, secondary = metadata_tag_sets(profile)

    def replace_group(predicate: Any, desired: list[str]) -> None:
        nonlocal tags, tags_changed
        current = [str(tag.get("tag", "")) for tag in tags if predicate(str(tag.get("tag", "")))]
        if set(current) == set(desired) and len(current) == len(desired):
            return
        tags = [tag for tag in tags if not predicate(str(tag.get("tag", "")))]
        tags.extend({"tag": name} for name in desired)
        tags_changed = True

    if "status" in proposal:
        replace_group(
            lambda name: name.startswith(STATUS_PREFIX),
            [] if proposal["status"] is None else [proposal["status"]],
        )
    if "primaryRole" in proposal or "secondary" in proposal:
        replace_group(
            lambda name: name in primary or name in secondary,
            [proposal["primaryRole"], *proposal.get("secondary", [])],
        )
    if "topics" in proposal:
        prefix = profile["topics"]["prefix"]
        replace_group(lambda name: name.startswith(prefix), proposal["topics"])

    patch: dict[str, Any] = {}
    if tags_changed:
        patch["tags"] = tags
    if "rating" in proposal:
        before = str(data.get("extra") or "")
        after = update_extra_rating(before, proposal["rating"])
        if after != before:
            patch["extra"] = after
    return patch


def metadata_proposal_mismatches(
    data: dict[str, Any], proposal: dict[str, Any], profile: dict[str, Any]
) -> list[str]:
    names = [str(tag.get("tag", "")) for tag in data.get("tags", [])]
    _, primary, secondary = metadata_tag_sets(profile)
    mismatches: list[str] = []
    if "status" in proposal:
        expected = set() if proposal["status"] is None else {proposal["status"]}
        if {name for name in names if name.startswith(STATUS_PREFIX)} != expected:
            mismatches.append("status")
    if "primaryRole" in proposal or "secondary" in proposal:
        expected = {proposal["primaryRole"], *proposal.get("secondary", [])}
        if {name for name in names if name in primary or name in secondary} != expected:
            mismatches.append("roles")
    if "topics" in proposal:
        prefix = profile["topics"]["prefix"]
        if {name for name in names if name.startswith(prefix)} != set(proposal["topics"]):
            mismatches.append("topics")
    if "rating" in proposal:
        rate_lines = [line for line in str(data.get("extra") or "").splitlines() if RATE_FIELD_RE.match(line)]
        if len(rate_lines) != 1 or not (match := RATE_LINE_RE.match(rate_lines[0])) or int(match.group(1)) != proposal["rating"]:
            mismatches.append("rating")
    return mismatches


def cmd_curate_metadata(args: argparse.Namespace) -> None:
    profile, proposals = read_metadata_manifest(args.file, args.expect_count)
    items = metadata_items_by_keys([row["key"] for row in proposals])
    planned: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    for data, proposal in zip(items, proposals):
        expected = proposal["expectedVersion"]
        if data.get("version") != expected:
            exit_with(
                f"Item {proposal['key']} version changed: expected {expected}, found {data.get('version')}"
            )
        patch = make_metadata_patch(data, proposal, profile)
        if patch:
            planned.append(make_simple_patch(data, patch))
            changes.append(
                {
                    "key": proposal["key"],
                    "title": data.get("title"),
                    "fields": sorted(patch),
                }
            )

    output = {
        "action": "curate-metadata",
        "profile": profile["name"],
        "selectedCount": len(items),
        "changedCount": len(planned),
        "unchangedCount": len(items) - len(planned),
        "changes": changes,
        "committed": False,
        "writeAttempted": False,
    }
    if not args.yes or not planned:
        if args.yes and not planned:
            output["committed"] = True
            output["outcome"] = "unchanged"
        dump_json(output)
        return

    responses, failed = commit_item_patches(planned)
    output.update(
        {
            "committed": True,
            "writeAttempted": True,
            "batchCount": len(responses),
            "failed": failed,
        }
    )
    if failed:
        output["outcome"] = "partial"
        dump_json(output)
        raise SystemExit(2)

    verified = metadata_items_by_keys([row["key"] for row in proposals])
    verification_failures = [
        {"key": proposal["key"], "fields": mismatches}
        for data, proposal in zip(verified, proposals)
        if (mismatches := metadata_proposal_mismatches(data, proposal, profile))
    ]
    output.update(
        {
            "outcome": "changed" if not verification_failures else "verification-failed",
            "verifiedCount": len(verified) - len(verification_failures),
            "verificationFailures": verification_failures,
        }
    )
    dump_json(output)
    if verification_failures:
        raise SystemExit(2)


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


def validate_create_items_manifest(value: Any, expect_count: int) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        unknown = sorted(set(value) - {"schemaVersion", "items"})
        if unknown:
            exit_with(f"Create-items manifest has unknown fields: {', '.join(unknown)}")
        schema_version = value.get("schemaVersion", 1)
        if (
            isinstance(schema_version, bool)
            or not isinstance(schema_version, int)
            or schema_version != 1
        ):
            exit_with("Create-items manifest has an unsupported schemaVersion")
        rows = value.get("items")
    else:
        rows = value
    if not isinstance(rows, list) or not rows:
        exit_with("Create-items manifest must contain a non-empty item list")
    if expect_count < 1 or len(rows) != expect_count:
        exit_with(f"Expected {expect_count} create-items entries, found {len(rows)}")

    records: list[dict[str, Any]] = []
    client_ids: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            exit_with(f"Create-items entry {index} must be an object")
        payload = dict(row)
        client_id = payload.pop("clientId", f"item-{index + 1}")
        if not isinstance(client_id, str) or not client_id.strip():
            exit_with(f"Create-items entry {index} has an invalid clientId")
        client_id = client_id.strip()
        if client_id in client_ids:
            exit_with(f"Create-items clientId must be unique: {client_id}")
        client_ids.add(client_id)
        if "key" in payload or "version" in payload:
            exit_with(f"Create-items entry {client_id} must not provide key or version")
        if not isinstance(payload.get("itemType"), str) or not payload["itemType"].strip():
            exit_with(f"Create-items entry {client_id} requires itemType")
        payload["itemType"] = payload["itemType"].strip()
        for field in ("creators", "tags"):
            if field in payload and (
                not isinstance(payload[field], list)
                or any(not isinstance(entry, dict) for entry in payload[field])
            ):
                exit_with(f"Create-items entry {client_id} field {field} must be an object list")
        collections = payload.get("collections", [])
        if (
            not isinstance(collections, list)
            or any(not isinstance(key, str) or not key.strip() for key in collections)
        ):
            exit_with(f"Create-items entry {client_id} collections must be unique keys")
        collections = [key.strip() for key in collections]
        if len(collections) != len(set(collections)):
            exit_with(f"Create-items entry {client_id} collections must be unique keys")
        if collections or "collections" in payload:
            payload["collections"] = collections
        records.append({"clientId": client_id, "payload": payload})
    return records


def create_result_key(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    data = value.get("data")
    key = value.get("key") or (data.get("key") if isinstance(data, dict) else None)
    return str(key) if key else None


def parse_create_items_response(
    body: Any, records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not isinstance(body, dict):
        return [
            {
                "clientId": record["clientId"],
                "status": "failed",
                "error": "Zotero returned an invalid batch response",
            }
            for record in records
        ]
    groups = {
        name: value if isinstance(value, dict) else {}
        for name, value in (
            ("created", body.get("successful")),
            ("unchanged", body.get("unchanged")),
            ("failed", body.get("failed")),
        )
    }
    results: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        raw_index = str(index)
        if raw_index in groups["failed"]:
            results.append(
                {
                    "clientId": record["clientId"],
                    "status": "failed",
                    "error": groups["failed"][raw_index],
                }
            )
            continue
        status = next(
            (name for name in ("created", "unchanged") if raw_index in groups[name]),
            None,
        )
        value = groups[status][raw_index] if status else None
        key = create_result_key(value)
        if status and key:
            results.append({"clientId": record["clientId"], "status": status, "key": key})
        else:
            results.append(
                {
                    "clientId": record["clientId"],
                    "status": "failed",
                    "error": "Zotero omitted the item key from its batch response",
                }
            )
    return results


def summarize_create_record(record: dict[str, Any]) -> dict[str, Any]:
    payload = record["payload"]
    return {
        "clientId": record["clientId"],
        "itemType": payload.get("itemType"),
        "title": payload.get("title"),
        "collections": payload.get("collections", []),
    }


def cmd_create_items(args: argparse.Namespace) -> None:
    records = validate_create_items_manifest(read_json_file(args.json_file), args.expect_count)
    verify_collection_keys(
        key
        for record in records
        for key in record["payload"].get("collections", [])
    )
    requested_batches = (len(records) + MAX_BATCH - 1) // MAX_BATCH
    output: dict[str, Any] = {
        "action": "create-items",
        "requestedCount": len(records),
        "requestedBatchCount": requested_batches,
        "items": [summarize_create_record(record) for record in records],
        "committed": False,
        "writeAttempted": False,
    }
    if not args.yes:
        dump_json(output)
        return

    results: list[dict[str, Any]] = []
    attempted = 0
    for batch in chunks(records, MAX_BATCH):
        response = authorized_request(
            f"{LOCAL_USER}/items",
            method="POST",
            data=[record["payload"] for record in batch],
            headers={"Zotero-Write-Token": uuid.uuid4().hex},
        )
        attempted += 1
        if not response.ok:
            detail = response.text[:TEXT_LIMIT] or response.error or "no response"
            results.extend(
                {
                    "clientId": record["clientId"],
                    "status": "failed",
                    "error": {"httpStatus": response.status, "detail": detail},
                }
                for record in batch
            )
            break
        batch_results = parse_create_items_response(parse_body(response), batch)
        results.extend(batch_results)
        if any(row["status"] == "failed" for row in batch_results):
            break

    attempted_ids = {row["clientId"] for row in results}
    not_attempted = [
        record["clientId"] for record in records if record["clientId"] not in attempted_ids
    ]
    keyed_results = [row for row in results if row.get("key")]
    verified: list[dict[str, Any]] = []
    verification_error: str | None = None
    if keyed_results:
        try:
            verified = items_by_keys([str(row["key"]) for row in keyed_results])
        except SystemExit as exc:
            verification_error = str(exc)
    verified_by_key = {str(row.get("key")): row for row in verified}
    created = [
        {
            "clientId": row["clientId"],
            "key": row["key"],
            "title": verified_by_key.get(str(row["key"]), {}).get("title"),
        }
        for row in results
        if row["status"] == "created"
    ]
    unchanged = [
        {
            "clientId": row["clientId"],
            "key": row["key"],
            "title": verified_by_key.get(str(row["key"]), {}).get("title"),
        }
        for row in results
        if row["status"] == "unchanged"
    ]
    failed = [row for row in results if row["status"] == "failed"]
    verification_missing = [
        row["key"] for row in keyed_results if str(row["key"]) not in verified_by_key
    ]
    if verification_missing and not verification_error:
        verification_error = "Created item readback was incomplete"

    output = {
        "action": "create-items",
        "requestedCount": len(records),
        "requestedBatchCount": requested_batches,
        "batchCount": attempted,
        "createdCount": len(created),
        "unchangedCount": len(unchanged),
        "failedCount": len(failed),
        "notAttemptedCount": len(not_attempted),
        "verifiedCount": len(verified),
        "created": created,
        "unchanged": unchanged,
        "failed": failed,
        "notAttempted": not_attempted,
        "verificationError": verification_error,
        "verificationMissingKeys": verification_missing,
        "committed": True,
        "writeAttempted": True,
    }
    if failed or not_attempted:
        output["outcome"] = "partial" if keyed_results else "failed"
    elif verification_error:
        output["outcome"] = "verification-failed"
    else:
        output["outcome"] = "changed" if created else "unchanged"
    dump_json(output)
    if failed or not_attempted or verification_error:
        raise SystemExit(2)


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


def paged_items(path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = 0
    page_size = 100
    while True:
        query = dict(params or {})
        query.update({"limit": page_size, "start": start})
        response = api_get_response(f"{path}?{urllib.parse.urlencode(query)}")
        page = parse_body(response)
        if not isinstance(page, list):
            exit_with("Unexpected Zotero paged-item response")
        rows.extend(page)
        raw_total = header(response.headers, "Total-Results")
        total = int(raw_total) if raw_total and raw_total.isdigit() else None
        if not page:
            if total is not None and len(rows) < total:
                exit_with("Zotero returned an incomplete paged-item response")
            return rows
        if total is not None and len(rows) >= total:
            return rows
        if len(page) < page_size:
            return rows
        start += len(page)


def select_items(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.item_key:
        rows = items_by_keys(args.item_key)
    elif args.collection_key or args.collection_name:
        collection = resolve_collection(key=args.collection_key, name=args.collection_name)
        key = urllib.parse.quote(str(collection.get("key")))
        rows = paged_items(f"{LOCAL_USER}/collections/{key}/items/top")
    elif args.query:
        rows = paged_items(f"{LOCAL_USER}/items/top", {"q": args.query})
    elif args.all_items:
        rows = paged_items(f"{LOCAL_USER}/items/top")
    else:
        exit_with("Select items by key, collection, query, or --all")
    items = unique_items(rows)
    if args.expect_count is not None and len(items) != args.expect_count:
        exit_with(f"Expected {args.expect_count} selected items, found {len(items)}; no changes made")
    return items


def extra_identifier(extra: Any, name: str) -> str | None:
    pattern = re.compile(rf"^\s*{re.escape(name)}\s*:\s*(.+?)\s*$", re.IGNORECASE)
    for line in str(extra or "").splitlines():
        if match := pattern.match(line):
            return match.group(1)
    return None


def first_author(data: dict[str, Any]) -> str | None:
    creators = [row for row in data.get("creators", []) if isinstance(row, dict)]
    authors = [row for row in creators if row.get("creatorType") == "author"] or creators
    if not authors:
        return None
    author = authors[0]
    return str(author.get("lastName") or author.get("name") or "").strip() or None


def item_year(data: dict[str, Any]) -> str | None:
    match = re.search(
        r"(?<!\d)(1[5-9]\d{2}|20\d{2}|21\d{2})(?!\d)",
        str(data.get("date") or ""),
    )
    return match.group(1) if match else None


def compact_inventory_item(data: dict[str, Any]) -> dict[str, Any]:
    identifiers = {
        name: value
        for name in ("DOI", "PMID", "ISBN")
        if (value := data.get(name) or extra_identifier(data.get("extra"), name))
    }
    return {
        "key": data.get("key"),
        "version": data.get("version"),
        "itemType": data.get("itemType"),
        "title": data.get("title"),
        "firstAuthor": first_author(data),
        "year": item_year(data),
        "identifiers": identifiers,
        "collections": data.get("collections", []),
    }


def cmd_inventory(args: argparse.Namespace) -> None:
    items = select_items(args)
    dump_json(
        {
            "action": "inventory",
            "itemCount": len(items),
            "items": [compact_inventory_item(data) for data in items],
        }
    )


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
    lines = [line for line in extra.splitlines() if not RATE_FIELD_RE.match(line)]
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
    body = api_get(ZONTEX_STATUS_PATH)
    if not isinstance(body, dict) or not isinstance(body.get("statuses"), list):
        exit_with("Unexpected response from Zontex Bridge")
    return body["statuses"]


def bridge_colored_tags() -> list[dict[str, Any]]:
    require_companion()
    body = api_get(ZONTEX_STATUS_PATH)
    if not isinstance(body, dict) or not isinstance(body.get("coloredTags"), list):
        exit_with("Unexpected response from Zontex Bridge")
    return body["coloredTags"]


def cmd_list_statuses(_: argparse.Namespace) -> None:
    dump_json(bridge_statuses())


def cmd_list_colored_tags(_: argparse.Namespace) -> None:
    dump_json(bridge_colored_tags())


def validate_colored_tag_change(
    existing: dict[str, dict[str, Any]], name: str, position: int
) -> None:
    if not 0 <= position < MAX_COLORED_TAGS:
        exit_with(f"Colored tag position must be between 0 and {MAX_COLORED_TAGS - 1}")
    if name not in existing and len(existing) >= MAX_COLORED_TAGS:
        exit_with(f"Zotero allows at most {MAX_COLORED_TAGS} colored tags")


def cmd_set_colored_tag(args: argparse.Namespace) -> None:
    name = args.name.strip()
    if not name:
        exit_with("Colored tag name cannot be empty")
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", args.color):
        exit_with("Tag color must use #RRGGBB syntax")
    existing = {row.get("name"): row for row in bridge_colored_tags()}
    validate_colored_tag_change(existing, name, args.position)
    preview = {
        "action": "set-colored-tag",
        "name": name,
        "color": args.color,
        "position": args.position,
        "before": existing.get(name),
        "coloredTagCountAfter": len(existing) + (0 if name in existing else 1),
        "note": "Colors are library-wide; item metadata changes do not rewrite this palette.",
        "committed": False,
    }
    if not args.yes:
        dump_json(preview)
        return
    response = require_ok(
        authorized_request(
            ZONTEX_STATUS_PATH,
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
        authorized_request(f"{ZONTEX_STATUS_PATH}?{query}", method="DELETE", data=None),
        f"DELETE color assignment for {name}",
    )
    preview.update({"committed": True, "status": response.status})
    dump_json(preview)


def cmd_create_status(args: argparse.Namespace) -> None:
    name = normalize_status_name(args.name)
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", args.color):
        exit_with("Status color must use #RRGGBB syntax")
    all_colored = {row.get("name"): row for row in bridge_colored_tags()}
    validate_colored_tag_change(all_colored, name, args.position)
    preview = {
        "action": "create-or-update-status",
        "name": name,
        "color": args.color,
        "position": args.position,
        "before": all_colored.get(name),
        "coloredTagCountAfter": len(all_colored) + (0 if name in all_colored else 1),
        "committed": False,
    }
    if not args.yes:
        dump_json(preview)
        return
    response = require_ok(
        authorized_request(
            ZONTEX_STATUS_PATH,
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
        current = [
            str(tag.get("tag", ""))
            for tag in original
            if str(tag.get("tag", "")).startswith(STATUS_PREFIX)
        ]
        desired = [] if name is None else [name]
        if set(current) == set(desired) and len(current) == len(desired):
            continue
        tags = [tag for tag in original if not str(tag.get("tag", "")).startswith(STATUS_PREFIX)]
        if name:
            tags.append({"tag": name})
        planned.append(make_simple_patch(data, {"tags": tags}))
    preview = {
        "action": "clear-status" if name is None else "set-status",
        "status": name,
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
        authorized_request(f"{ZONTEX_STATUS_PATH}?{query}", method="DELETE", data=None),
        f"DELETE slash-prefixed status {name}",
    )
    preview.update({"committed": True, "status": response.status})
    dump_json(preview)


def cmd_trash_items(args: argparse.Namespace) -> None:
    items = select_items(args)
    annotations = [data for data in items if data.get("itemType") == "annotation"]
    planned = [
        make_simple_patch(data, {"deleted": 1})
        for data in items
        if data.get("itemType") != "annotation" and not data.get("deleted")
    ]
    preview = {
        "action": "trash-items",
        "selectedCount": len(items),
        "changedCount": len(planned) + len(annotations),
        "trashCount": len(planned),
        "permanentDeleteAnnotationCount": len(annotations),
        "committed": False,
        "items": [
            {
                "key": data.get("key"),
                "title": data.get("title"),
                "itemType": data.get("itemType"),
                "disposition": (
                    "delete-permanently"
                    if data.get("itemType") == "annotation"
                    else "trash"
                ),
            }
            for data in items
        ],
    }
    if annotations:
        preview["confirmationPrompt"] = {
            "zh-CN": (
                "注意：注释删除后无法恢复。如需删除，请回复确认。确认后，其他条目将移入"
                "回收站，注释将永久删除。"
                if planned
                else "注意：注释删除后无法恢复。如需删除，请回复确认。"
            ),
            "en": (
                "Warning: Deleted annotations cannot be restored. Confirm to continue. Other "
                "items will be moved to Trash, while annotations will be permanently deleted."
                if planned
                else "Warning: Deleted annotations cannot be restored. Confirm to continue."
            ),
        }
        preview["requiredConfirmation"] = "DELETE-PERMANENTLY"
    if (
        not args.yes
        or (annotations and getattr(args, "confirm", None) != "DELETE-PERMANENTLY")
        or not (planned or annotations)
    ):
        dump_json(preview)
        return

    responses, failed = commit_item_patches(planned) if planned else ([], {})
    if failed:
        preview.update(
            {
                "committed": True,
                "responses": responses,
                "failed": failed,
                "annotationDeletionSkipped": bool(annotations),
            }
        )
        dump_json(preview)
        raise SystemExit(2)

    deleted_annotation_keys: list[str] = []
    for data in annotations:
        key = str(data.get("key"))
        require_ok(
            authorized_request(
                f"{LOCAL_USER}/items/{urllib.parse.quote(key)}",
                method="DELETE",
                data=None,
                headers={"If-Unmodified-Since-Version": str(data.get("version"))},
            ),
            f"DELETE annotation {key}",
        )
        deleted_annotation_keys.append(key)

    preview.update(
        {
            "committed": True,
            "responses": responses,
            "failed": failed,
            "deletedAnnotationKeys": deleted_annotation_keys,
        }
    )
    dump_json(preview)


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
    response = request(f"{ZONTEX_STYLES_PATH}?{urllib.parse.urlencode({'id': style_id})}")
    if response.status == 404:
        return None
    require_ok(response, f"GET CSL style {style_id}")
    body = parse_body(response)
    return body if isinstance(body, dict) else None


def cmd_list_styles(_: argparse.Namespace) -> None:
    require_companion()
    dump_json(api_get(ZONTEX_STYLES_PATH))


def cmd_context(_: argparse.Namespace) -> None:
    require_companion()
    dump_json(api_get(ZONTEX_CONTEXT_PATH))


def cmd_render(args: argparse.Namespace) -> None:
    payload = bridge_post(
        ZONTEX_RENDER_PATH,
        {
            "itemKeys": args.item_key,
            "style": args.style,
            "locale": args.locale or "",
            "mode": args.mode,
        },
        "POST Bridge render",
    )
    dump_json(payload)


def cmd_navigate(args: argparse.Namespace) -> None:
    selected = [
        ("reveal-item", args.reveal_item),
        ("open-attachment", args.open_attachment),
        ("open-annotation", args.open_annotation),
    ]
    action, item_key = next((action, key) for action, key in selected if key)
    dump_json(
        bridge_post(
            ZONTEX_NAVIGATE_PATH,
            {"action": action, "itemKey": item_key},
            f"POST Bridge navigate ({action})",
        )
    )


def cmd_document_segments(args: argparse.Namespace) -> None:
    params = {"limit": args.limit}
    if args.cursor is not None:
        params["cursor"] = args.cursor
    if args.attachment_key:
        params["attachmentKey"] = args.attachment_key
    if args.include_auxiliary:
        params["includeAuxiliary"] = "1"
    if args.verbose:
        params["verbose"] = "1"
    dump_json(api_get(f"{ZONTEX_DOCUMENT_SEGMENTS_PATH}?{urllib.parse.urlencode(params)}"))


def cmd_create_annotation(args: argparse.Namespace) -> None:
    body = {
        "attachmentKey": args.attachment_key,
        "sourceHash": args.source_hash,
        "target": {"segmentId": args.segment_id, "start": args.start, "end": args.end},
        "expectedText": args.expected_text,
        "type": args.type,
        "color": args.color,
        "comment": args.comment or "",
        "tags": args.tag or [],
    }
    preview = {"action": "create-annotation", "request": body, "committed": False}
    if not args.yes:
        dump_json(preview)
        return
    preview.update({"committed": True, "response": bridge_post(
        ZONTEX_ANNOTATIONS_PATH, body, "POST Bridge annotation"
    )})
    dump_json(preview)


def read_annotation_manifest(path: str) -> Any:
    label = "stdin" if path == "-" else path
    try:
        raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        exit_with(f"Could not read annotation manifest {label}: {exc}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        exit_with(f"Invalid annotation manifest {label}: {exc}")


def utf16_length(value: str) -> int:
    return len(value.encode("utf-16-le", errors="surrogatepass")) // 2


def validate_annotation_manifest(value: Any, expect_count: int) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schemaVersion") != 1:
        exit_with("Annotation manifest must be an object with schemaVersion 1")
    attachment_key = value.get("attachmentKey")
    source_hash = value.get("sourceHash")
    rows = value.get("annotations")
    if not isinstance(attachment_key, str) or not attachment_key.strip():
        exit_with("Annotation manifest attachmentKey is required")
    if not isinstance(source_hash, str) or not source_hash:
        exit_with("Annotation manifest sourceHash is required")
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_BATCH:
        exit_with(f"Annotation manifest must contain 1–{MAX_BATCH} annotations")
    if expect_count < 1 or expect_count > MAX_BATCH:
        exit_with(f"--expect-count must be between 1 and {MAX_BATCH}")
    if len(rows) != expect_count:
        exit_with(
            f"Expected {expect_count} manifest annotations, found {len(rows)}; no changes made"
        )

    client_ids: set[str] = set()
    targets: set[tuple[str, int, int]] = set()
    annotations: list[dict[str, Any]] = []
    for index, raw in enumerate(rows):
        label = f"annotations[{index}]"
        if not isinstance(raw, dict):
            exit_with(f"{label} must be an object")
        client_id = raw.get("clientId")
        if not isinstance(client_id, str) or not client_id.strip() or len(client_id) > 100:
            exit_with(f"{label}.clientId must be a non-empty string of at most 100 characters")
        client_id = client_id.strip()
        if client_id in client_ids:
            exit_with(f"Duplicate annotation clientId: {client_id}")
        client_ids.add(client_id)

        target = raw.get("target")
        if not isinstance(target, dict):
            exit_with(f"{label}.target must be an object")
        segment_id = target.get("segmentId")
        start = target.get("start")
        end = target.get("end")
        if (
            not isinstance(segment_id, str)
            or not segment_id.strip()
            or type(start) is not int
            or type(end) is not int
            or start < 0
            or end <= start
        ):
            exit_with(f"{label}.target must contain segmentId and a non-empty [start,end) range")
        segment_id = segment_id.strip()
        target_key = (segment_id, start, end)
        if target_key in targets:
            exit_with(f"Duplicate annotation target in manifest: {segment_id}[{start},{end})")
        targets.add(target_key)

        expected_text = raw.get("expectedText")
        if not isinstance(expected_text, str) or not expected_text:
            exit_with(f"{label}.expectedText must be a non-empty string")
        if utf16_length(expected_text) != end - start:
            exit_with(
                f"{label}.expectedText must span exactly {end - start} UTF-16 code units"
            )

        annotation_type = raw.get("type", "highlight")
        if annotation_type not in {"highlight", "underline"}:
            exit_with(f"{label}.type must be highlight or underline")
        color = raw.get("color", "#ffd400")
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
            exit_with(f"{label}.color must use #RRGGBB syntax")
        comment = raw.get("comment", "")
        if not isinstance(comment, str) or utf16_length(comment) > 4000:
            exit_with(f"{label}.comment must be at most 4000 UTF-16 code units")
        raw_tags = raw.get("tags", [])
        if not isinstance(raw_tags, list) or len(raw_tags) > 20:
            exit_with(f"{label}.tags must contain at most 20 strings")
        tags: list[str] = []
        for tag in raw_tags:
            if not isinstance(tag, str):
                exit_with(f"{label}.tags must contain only strings")
            tag = unicodedata.normalize("NFC", tag.strip())
            if not tag or utf16_length(tag) > 100:
                exit_with(
                    f"{label}.tags must contain non-empty strings of at most 100 UTF-16 code units"
                )
            if tag not in tags:
                tags.append(tag)

        annotations.append(
            {
                "clientId": client_id,
                "target": {"segmentId": segment_id, "start": start, "end": end},
                "expectedText": expected_text,
                "type": annotation_type,
                "color": color,
                "comment": comment,
                "tags": tags,
            }
        )
    return {
        "schemaVersion": 1,
        "attachmentKey": attachment_key.strip(),
        "sourceHash": source_hash,
        "annotations": annotations,
    }


def annotation_manifest_preview(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "action": "create-annotations",
        "attachmentKey": manifest["attachmentKey"],
        "sourceHash": manifest["sourceHash"],
        "annotationCount": len(manifest["annotations"]),
        "annotations": [
            {
                "clientId": row["clientId"],
                "target": row["target"],
                "type": row["type"],
                "color": row["color"],
                "expectedTextLength": utf16_length(row["expectedText"]),
                "commentPresent": bool(row["comment"]),
                "tagCount": len(row["tags"]),
            }
            for row in manifest["annotations"]
        ],
        "committed": False,
    }


def annotation_tag_names(data: dict[str, Any]) -> list[str]:
    names = []
    for value in data.get("tags", []):
        if isinstance(value, str):
            name = value
        elif isinstance(value, dict):
            name = value.get("tag")
        else:
            name = None
        if isinstance(name, str) and name.strip():
            names.append(unicodedata.normalize("NFC", name.strip()))
    return sorted(set(names))


def annotation_verification_mismatches(
    manifest: dict[str, Any],
    results: list[dict[str, Any]],
    children: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows_by_client = {row["clientId"]: row for row in manifest["annotations"]}
    children_by_key = {str(row.get("key")): row for row in children if row.get("key")}
    mismatches = []
    for result in results:
        row = rows_by_client[result["clientId"]]
        child = children_by_key.get(result["key"])
        fields = []
        if child is None:
            fields.append("key")
        else:
            if child.get("itemType") != "annotation":
                fields.append("itemType")
            if child.get("parentItem") != manifest["attachmentKey"]:
                fields.append("parentItem")
            if child.get("annotationType") != row["type"]:
                fields.append("type")
            if child.get("annotationText") != row["expectedText"]:
                fields.append("text")
            if child.get("annotationComment", "") != row["comment"]:
                fields.append("comment")
            if str(child.get("annotationColor", "")).casefold() != row["color"].casefold():
                fields.append("color")
            if annotation_tag_names(child) != sorted(row["tags"]):
                fields.append("tags")
        if fields:
            mismatches.append(
                {"clientId": result["clientId"], "key": result["key"], "fields": fields}
            )
    return mismatches


def cmd_create_annotations(args: argparse.Namespace) -> None:
    started = time.perf_counter()
    manifest = validate_annotation_manifest(
        read_annotation_manifest(args.file),
        args.expect_count,
    )
    validated = time.perf_counter()
    preview = annotation_manifest_preview(manifest)
    if not args.yes:
        if args.timings:
            preview["timingsMs"] = {
                "validation": round((validated - started) * 1000, 1),
                "total": round((time.perf_counter() - started) * 1000, 1),
            }
        dump_json(preview)
        return

    require_companion()
    server = server_info()
    setup = time.perf_counter()
    results: list[dict[str, Any]] = []
    failed: dict[str, Any] | None = None
    posts = 0
    for row in manifest["annotations"]:
        body = {
            "attachmentKey": manifest["attachmentKey"],
            "sourceHash": manifest["sourceHash"],
            "target": row["target"],
            "expectedText": row["expectedText"],
            "type": row["type"],
            "color": row["color"],
            "comment": row["comment"],
            "tags": row["tags"],
        }
        response = authorized_request(
            ZONTEX_ANNOTATIONS_PATH,
            method="POST",
            data=body,
            server=server,
        )
        posts += 1
        payload = parse_body(response)
        annotation = payload.get("annotation") if isinstance(payload, dict) else None
        key = annotation.get("key") if isinstance(annotation, dict) else None
        created = isinstance(payload, dict) and payload.get("created") is True
        duplicate = isinstance(payload, dict) and payload.get("duplicate") is True
        if not response.ok or not isinstance(key, str) or not key or not (created or duplicate):
            if isinstance(payload, dict):
                error = payload.get("error") or "invalid-response"
                message = payload.get("message") or "Zotero returned an unexpected annotation response"
            else:
                error = "transport-uncertain" if response.status is None else "invalid-response"
                message = response.error or "Zotero returned an unexpected annotation response"
            failed = {
                "clientId": row["clientId"],
                "status": "failed",
                "httpStatus": response.status,
                "error": error,
                "message": message,
            }
            break
        results.append(
            {
                "clientId": row["clientId"],
                "status": "created" if created else "duplicate",
                "key": key,
                "page": annotation.get("pageLabel"),
            }
        )
    writes_finished = time.perf_counter()

    verification = {"ok": True, "checked": len(results), "mismatches": []}
    final_readbacks = 0
    if results:
        final_readbacks = 1
        try:
            annotations = items_by_keys([row["key"] for row in results])
            mismatches = annotation_verification_mismatches(manifest, results, annotations)
            verification.update({"ok": not mismatches, "mismatches": mismatches})
        except SystemExit as exc:
            verification.update({"ok": False, "error": str(exc)})
    verified = time.perf_counter()
    not_attempted = [
        row["clientId"]
        for row in manifest["annotations"][len(results) + (1 if failed else 0):]
    ]
    output = {
        **preview,
        "committed": True,
        "counts": {
            "requested": len(manifest["annotations"]),
            "created": sum(row["status"] == "created" for row in results),
            "duplicate": sum(row["status"] == "duplicate" for row in results),
            "failed": int(failed is not None),
            "notAttempted": len(not_attempted),
        },
        "results": [*results, *([failed] if failed else [])],
        "notAttempted": not_attempted,
        "verification": verification,
        "callCounts": {
            "companionChecks": 1,
            "serverChecks": 1,
            "annotationPosts": posts,
            "finalReadbacks": final_readbacks,
        },
    }
    output.pop("annotations", None)
    if args.timings:
        output["timingsMs"] = {
            "validation": round((validated - started) * 1000, 1),
            "setup": round((setup - validated) * 1000, 1),
            "writes": round((writes_finished - setup) * 1000, 1),
            "verification": round((verified - writes_finished) * 1000, 1),
            "total": round((verified - started) * 1000, 1),
        }
    dump_json(output)
    if failed or not verification["ok"]:
        raise SystemExit(2)


def cmd_annotations_to_note(args: argparse.Namespace) -> None:
    body = {
        "annotationKeys": args.annotation_key,
        "parentItemKey": args.parent_item_key,
        "order": args.order,
        "noComments": args.no_comments,
        "noHeader": args.no_header,
    }
    preview = {"action": "annotations-to-note", "request": body, "committed": False}
    if not args.yes:
        dump_json(preview)
        return
    preview.update({"committed": True, "response": bridge_post(
        ZONTEX_ANNOTATION_NOTE_PATH, body, "POST Bridge annotation note"
    )})
    dump_json(preview)


def colored_tag_map() -> dict[str, dict[str, Any]]:
    body = api_get(ZONTEX_STATUS_PATH)
    rows = body.get("coloredTags", []) if isinstance(body, dict) else []
    return {
        str(row["name"]): {
            "color": row.get("color"),
            "position": row.get("position"),
        }
        for row in rows
        if isinstance(row, dict) and row.get("name")
    }


def tag_item_count(name: str) -> int:
    query = urllib.parse.urlencode({"tag": name, "limit": 1})
    response = api_get_response(f"{LOCAL_USER}/items?{query}")
    raw = header(response.headers, "Total-Results")
    if raw is None or not raw.isdigit():
        exit_with(f"Zotero did not report the impact count for tag: {name}")
    return int(raw)


def tag_item_keys(name: str) -> list[str]:
    keys: list[str] = []
    start = 0
    while True:
        query = urllib.parse.urlencode(
            {"tag": name, "format": "keys", "limit": 100, "start": start}
        )
        response = api_get_response(f"{LOCAL_USER}/items?{query}")
        raw_total = header(response.headers, "Total-Results")
        if raw_total is None or not raw_total.isdigit():
            exit_with(f"Zotero did not report the impact count for tag: {name}")
        total = int(raw_total)
        page = [line.strip() for line in response.text.splitlines() if line.strip()]
        keys.extend(page)
        if len(keys) >= total:
            return keys
        if not page:
            exit_with(f"Zotero returned an incomplete item-key list for tag: {name}")
        start += len(page)


def parse_counted_tag(raw: str, *, label: str = "--source") -> dict[str, Any]:
    if not isinstance(raw, str) or "=" not in raw:
        exit_with(f"{label} must use TAG=EXPECTED_COUNT")
    name, raw_count = raw.rsplit("=", 1)
    name = name.strip()
    try:
        count = int(raw_count)
    except ValueError:
        exit_with(f"{label} expected count must be a non-negative integer")
    if not name or count < 0:
        exit_with(f"{label} must use a non-empty tag and non-negative expected count")
    return {"name": name, "expectedCount": count}


def cmd_rename_tag(args: argparse.Namespace) -> None:
    source = args.from_name.strip()
    target = args.to_name.strip()
    if not source or not target or source == target:
        exit_with("--from and --to must be distinct non-empty tag names")
    if args.expect_count < 0:
        exit_with("--expect-count must be non-negative")
    colors = colored_tag_map()
    source_count = tag_item_count(source)
    target_count = tag_item_count(target)
    preview = {
        "action": "rename-tag",
        "from": source,
        "to": target,
        "expectedCount": args.expect_count,
        "sourceColor": colors.get(source),
        "targetColor": colors.get(target),
        "sourceExists": source_count > 0 or source in colors,
        "targetExists": target_count > 0 or target in colors,
        "actualCount": source_count,
        "countMatches": source_count == args.expect_count,
        "colorPolicy": "preserve-target",
        "committed": False,
    }
    if not args.yes:
        dump_json(preview)
        return
    preview.update(
        {
            "committed": True,
            "response": bridge_post(
                ZONTEX_TAG_RENAME_PATH,
                {"from": source, "to": target, "expectedCount": args.expect_count},
                "POST Bridge tag rename",
            ),
        }
    )
    dump_json(preview)


def cmd_merge_tags(args: argparse.Namespace) -> None:
    sources = [parse_counted_tag(raw) for raw in args.source]
    target = args.into.strip()
    if not target:
        exit_with("--into must be a non-empty tag name")
    names = [source["name"] for source in sources]
    if target in names or len(set(names)) != len(names):
        exit_with("--source names must be unique and must not equal --into")
    colors = colored_tag_map()
    source_keys = {name: set(tag_item_keys(name)) for name in names}
    actual_counts = {name: len(source_keys[name]) for name in names}
    target_count = tag_item_count(target)
    affected_keys = set().union(*source_keys.values())
    preview = {
        "action": "merge-tags",
        "from": [
            {
                **source,
                "actualCount": actual_counts[source["name"]],
                "countMatches": actual_counts[source["name"]] == source["expectedCount"],
                "exists": actual_counts[source["name"]] > 0 or source["name"] in colors,
                "color": colors.get(source["name"]),
            }
            for source in sources
        ],
        "into": target,
        "targetColor": colors.get(target),
        "targetExists": target_count > 0 or target in colors,
        "uniqueAffectedItems": len(affected_keys),
        "colorPolicy": args.color_policy,
        "committed": False,
    }
    if not args.yes:
        dump_json(preview)
        return
    preview.update(
        {
            "committed": True,
            "response": bridge_post(
                ZONTEX_TAG_MERGE_PATH,
                {"sources": sources, "into": target, "colorPolicy": args.color_policy},
                "POST Bridge tag merge",
            ),
        }
    )
    dump_json(preview)


def parse_expected_version(raw: str) -> tuple[str, int]:
    if not isinstance(raw, str) or "=" not in raw:
        exit_with("--expected-version must use ITEM_KEY=VERSION syntax")
    key, raw_version = raw.rsplit("=", 1)
    key = key.strip()
    try:
        version = int(raw_version)
    except ValueError:
        exit_with("--expected-version version must be a non-negative integer")
    if not key or version < 0:
        exit_with("--expected-version must use a non-empty item key and non-negative version")
    return key, version


def item_children(item_key: str) -> list[dict[str, Any]]:
    value = api_get(f"{LOCAL_USER}/items/{urllib.parse.quote(item_key)}/children")
    if not isinstance(value, list):
        exit_with(f"Unexpected Zotero child-item shape for: {item_key}")
    return [data_of(row) for row in value]


def items_by_keys(item_keys: list[str]) -> list[dict[str, Any]]:
    if not item_keys:
        exit_with("Readback requires at least one item key")
    requested = list(dict.fromkeys(item_keys))
    rows: list[dict[str, Any]] = []
    for batch in chunks(requested, MAX_BATCH):
        query = urllib.parse.urlencode(
            {"itemKey": ",".join(batch), "limit": len(batch)}
        )
        value = api_get(f"{LOCAL_USER}/items?{query}")
        if not isinstance(value, list):
            exit_with("Unexpected Zotero multi-item readback shape")
        rows.extend(data_of(row) for row in value)
    by_key = {str(row.get("key")): row for row in rows if row.get("key")}
    missing = [key for key in requested if key not in by_key]
    if missing:
        exit_with(f"Zotero items were not found: {', '.join(missing)}")
    return [by_key[key] for key in requested]


def merge_child_counts(item_key: str) -> dict[str, int]:
    children = item_children(item_key)
    attachments = [child for child in children if child.get("itemType") == "attachment"]
    annotation_count = sum(child.get("itemType") == "annotation" for child in children)
    for attachment in attachments:
        key = attachment.get("key")
        if key:
            annotation_count += sum(
                child.get("itemType") == "annotation" for child in item_children(str(key))
            )
    return {
        "attachmentCount": len(attachments),
        "noteCount": sum(child.get("itemType") == "note" for child in children),
        "annotationCount": annotation_count,
    }


def merge_item_summary(data: dict[str, Any], child_counts: dict[str, int]) -> dict[str, Any]:
    return {
        "key": data.get("key"),
        "version": data.get("version"),
        "itemType": data.get("itemType"),
        "title": data.get("title"),
        "DOI": data.get("DOI"),
        "date": data.get("date"),
        "tagCount": len(data.get("tags", [])) if isinstance(data.get("tags"), list) else 0,
        "collectionCount": len(data.get("collections", [])) if isinstance(data.get("collections"), list) else 0,
        **child_counts,
    }


def cmd_merge_items(args: argparse.Namespace) -> None:
    master_key = args.master.strip()
    other_keys = [key.strip() for key in args.other]
    keys = [master_key, *other_keys]
    if not master_key or not other_keys or any(not key for key in other_keys):
        exit_with("--master and at least one non-empty --other item key are required")
    if len(other_keys) > 20:
        exit_with("At most 20 --other item keys may be merged at once")
    if len(set(keys)) != len(keys):
        exit_with("--master and --other item keys must be unique")

    expected_versions: dict[str, int] = {}
    for raw in args.expected_version:
        key, version = parse_expected_version(raw)
        if key in expected_versions:
            exit_with(f"Duplicate --expected-version for item key: {key}")
        expected_versions[key] = version
    if set(expected_versions) != set(keys):
        exit_with("Provide exactly one --expected-version for every master and other item key")

    items = [
        data_of(api_get(f"{LOCAL_USER}/items/{urllib.parse.quote(key)}"))
        for key in keys
    ]
    summaries = [
        merge_item_summary(item, merge_child_counts(str(item.get("key") or key)))
        for item, key in zip(items, keys)
    ]
    preview = {
        "action": "merge-items",
        "master": summaries[0],
        "others": summaries[1:],
        "expectedVersions": expected_versions,
        "committed": False,
    }
    if not args.yes:
        dump_json(preview)
        return
    preview.update(
        {
            "committed": True,
            "response": bridge_post(
                ZONTEX_ITEM_MERGE_PATH,
                {
                    "master": master_key,
                    "others": other_keys,
                    "expectedVersions": expected_versions,
                },
                "POST Bridge item merge",
            ),
        }
    )
    dump_json(preview)


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
            ZONTEX_STYLES_PATH,
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
        authorized_request(f"{ZONTEX_STYLES_PATH}?{query}", method="DELETE", data=None),
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
        description=(
            "Manage Zotero 10 through its authorized local API. Use status --require-write "
            "as the workflow gate; omit --yes only for an explicitly requested dry-run."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    status = commands.add_parser("status", help="Show local API and write-authorization status")
    status.add_argument(
        "--require-write",
        action="store_true",
        help="Exit with status 2 unless the local API supports writes and a cached authorization exists",
    )
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

    create_items = commands.add_parser(
        "create-items", help="Preview or create many Zotero items from one manifest"
    )
    create_items.add_argument("--json-file", required=True)
    create_items.add_argument("--expect-count", type=int, required=True)
    create_items.add_argument("--yes", action="store_true")
    create_items.set_defaults(func=cmd_create_items)

    inventory = commands.add_parser(
        "inventory", help="Read compact matching fields for selected top-level items"
    )
    add_item_selector(inventory)
    inventory.set_defaults(func=cmd_inventory)

    backup_collection = commands.add_parser(
        "backup-collection", help="Export a collection subtree and item metadata to JSON"
    )
    add_collection_selector(backup_collection)
    backup_collection.add_argument("--file", required=True)
    backup_collection.set_defaults(func=cmd_backup_collection)

    metadata_profile = commands.add_parser(
        "metadata-profile", help="Show the bundled Ethereal-compatible metadata profile"
    )
    metadata_profile.set_defaults(func=cmd_metadata_profile)

    metadata_audit = commands.add_parser(
        "metadata-audit", help="Audit selected items against the bundled metadata profile"
    )
    add_item_selector(metadata_audit)
    metadata_audit.set_defaults(func=cmd_metadata_audit)

    curate_metadata = commands.add_parser(
        "curate-metadata", help="Preview or apply heterogeneous metadata from one manifest"
    )
    curate_metadata.add_argument("--file", required=True)
    curate_metadata.add_argument("--expect-count", type=int, required=True)
    curate_metadata.add_argument("--yes", action="store_true")
    curate_metadata.set_defaults(func=cmd_curate_metadata)

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

    rename_tag = commands.add_parser(
        "rename-tag", help="Preview or natively rename one tag with an expected impact count"
    )
    rename_tag.add_argument("--from", dest="from_name", required=True)
    rename_tag.add_argument("--to", dest="to_name", required=True)
    rename_tag.add_argument("--expect-count", type=int, required=True)
    rename_tag.add_argument("--yes", action="store_true")
    rename_tag.set_defaults(func=cmd_rename_tag)

    merge_tags = commands.add_parser(
        "merge-tags", help="Preview or natively merge tags with expected impact counts"
    )
    merge_tags.add_argument(
        "--source", action="append", required=True, metavar="TAG=EXPECTED_COUNT"
    )
    merge_tags.add_argument("--into", required=True)
    merge_tags.add_argument(
        "--color-policy", choices=["preserve-target"], default="preserve-target"
    )
    merge_tags.add_argument("--yes", action="store_true")
    merge_tags.set_defaults(func=cmd_merge_tags)

    set_colored_tag = commands.add_parser(
        "set-colored-tag", help="Preview or assign one native Zotero tag color"
    )
    set_colored_tag.add_argument("--name", required=True)
    set_colored_tag.add_argument("--color", required=True)
    set_colored_tag.add_argument("--position", type=int, required=True)
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
    create_status.add_argument("--position", type=int, required=True)
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
    trash_items.add_argument("--confirm")
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

    context = commands.add_parser("context", help="Read the current Zotero UI/Reader context")
    context.set_defaults(func=cmd_context)

    render = commands.add_parser("render", help="Preview native Zotero CSL output")
    render.add_argument("--item-key", action="append", required=True)
    render.add_argument("--style", required=True)
    render.add_argument("--locale")
    render.add_argument("--mode", choices=["citation", "bibliography"], default="bibliography")
    render.set_defaults(func=cmd_render)

    navigate = commands.add_parser("navigate", help="Perform a Zotero UI navigation action")
    navigation = navigate.add_mutually_exclusive_group(required=True)
    navigation.add_argument("--reveal-item")
    navigation.add_argument("--open-attachment")
    navigation.add_argument("--open-annotation")
    navigate.set_defaults(func=cmd_navigate)

    segments = commands.add_parser("document-segments", help="Read active PDF SDT segments")
    segments.add_argument("--attachment-key")
    segments.add_argument("--limit", type=int, default=100)
    segments.add_argument("--cursor")
    segments.add_argument("--include-auxiliary", action="store_true")
    segments.add_argument("--verbose", action="store_true")
    segments.set_defaults(func=cmd_document_segments)

    annotation = commands.add_parser("create-annotation", help="Preview or create a native PDF annotation")
    annotation.add_argument("--attachment-key", required=True)
    annotation.add_argument("--source-hash", required=True)
    annotation.add_argument("--segment-id", required=True)
    annotation.add_argument("--start", type=int, required=True)
    annotation.add_argument("--end", type=int, required=True)
    annotation.add_argument("--expected-text", required=True)
    annotation.add_argument("--type", choices=["highlight", "underline"], default="highlight")
    annotation.add_argument("--color", default="#ffd400")
    annotation.add_argument("--comment")
    annotation.add_argument("--tag", action="append")
    annotation.add_argument("--yes", action="store_true")
    annotation.set_defaults(func=cmd_create_annotation)

    annotations = commands.add_parser(
        "create-annotations",
        help="Preview or sequentially create annotations from one manifest",
    )
    annotations.add_argument("--file", required=True, help="Manifest JSON path, or - for stdin")
    annotations.add_argument("--expect-count", type=int, required=True)
    annotations.add_argument("--timings", action="store_true")
    annotations.add_argument("--yes", action="store_true")
    annotations.set_defaults(func=cmd_create_annotations)

    annotation_note = commands.add_parser(
        "annotations-to-note", help="Preview or create a native Zotero note from annotations"
    )
    annotation_note.add_argument("--parent-item-key", required=True)
    annotation_note.add_argument("--annotation-key", action="append", required=True)
    annotation_note.add_argument("--order", choices=["document", "provided"], default="document")
    annotation_note.add_argument("--no-comments", action="store_true")
    annotation_note.add_argument("--no-header", action="store_true")
    annotation_note.add_argument("--yes", action="store_true")
    annotation_note.set_defaults(func=cmd_annotations_to_note)

    merge_items = commands.add_parser(
        "merge-items", help="Preview or natively merge top-level regular items"
    )
    merge_items.add_argument("--master", required=True)
    merge_items.add_argument("--other", action="append", required=True)
    merge_items.add_argument(
        "--expected-version", action="append", required=True, metavar="ITEM_KEY=VERSION"
    )
    merge_items.add_argument("--yes", action="store_true")
    merge_items.set_defaults(func=cmd_merge_items)

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
