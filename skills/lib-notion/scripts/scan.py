#!/usr/bin/env python3
"""Incremental, read-only Notion scan for MyLibrary. No page content enters the vault."""

import argparse
import ctypes
import getpass
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://api.notion.com/v1"
VERSION = "2026-03-11"
KEYCHAIN_SERVICE = "com.wayne.lib-notion"
DEFAULT_STATE = Path.home() / ".local/state/lib-notion/state.json"
DEFAULT_CONFIG = Path.home() / ".config/lib-notion/config.json"


class ScanError(Exception):
    pass


def utc_now():
    return datetime.now(timezone.utc)


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def stamp(value):
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def token_from_environment_or_keychain():
    token = os.environ.get("NOTION_API_KEY") or os.environ.get("NOTION_PAT")
    if token:
        return token
    if sys.platform == "darwin":
        token = keychain_read()
        if token:
            return token
    raise ScanError("No Notion token: run scripts/store-token-macos.sh or set NOTION_API_KEY securely.")


def keychain_functions():
    framework = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
    find = framework.SecKeychainFindGenericPassword
    find.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32,
                     ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_void_p),
                     ctypes.POINTER(ctypes.c_void_p)]
    find.restype = ctypes.c_int32
    return framework, find


def keychain_read():
    framework, find = keychain_functions()
    service = KEYCHAIN_SERVICE.encode()
    account = getpass.getuser().encode()
    length = ctypes.c_uint32()
    data = ctypes.c_void_p()
    status = find(None, len(service), service, len(account), account,
                  ctypes.byref(length), ctypes.byref(data), None)
    if status == -25300:  # errSecItemNotFound
        return None
    if status != 0:
        raise ScanError(f"Keychain read failed with OSStatus {status}")
    if length.value == 0:
        return None
    try:
        return ctypes.string_at(data, length.value).decode()
    finally:
        free = framework.SecKeychainItemFreeContent
        free.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        free.restype = ctypes.c_int32
        free(None, data)


def keychain_store(token):
    if sys.platform != "darwin":
        raise ScanError("Keychain storage requires macOS")
    if not token:
        raise ScanError("Refusing to store an empty Notion token")
    framework, find = keychain_functions()
    service = KEYCHAIN_SERVICE.encode()
    account = getpass.getuser().encode()
    password = token.encode()
    buffer = ctypes.create_string_buffer(password)
    item = ctypes.c_void_p()
    status = find(None, len(service), service, len(account), account, None, None, ctypes.byref(item))
    if status == 0:
        modify = framework.SecKeychainItemModifyAttributesAndData
        modify.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
        modify.restype = ctypes.c_int32
        status = modify(item, None, len(password), ctypes.cast(buffer, ctypes.c_void_p))
        core_foundation = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        core_foundation.CFRelease.argtypes = [ctypes.c_void_p]
        core_foundation.CFRelease(item)
    elif status == -25300:  # errSecItemNotFound
        add = framework.SecKeychainAddGenericPassword
        add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32,
                        ctypes.c_char_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
        add.restype = ctypes.c_int32
        status = add(None, len(service), service, len(account), account, len(password),
                     ctypes.cast(buffer, ctypes.c_void_p), None)
    if status != 0:
        raise ScanError(f"Keychain write failed with OSStatus {status}")
    if keychain_read() != token:
        raise ScanError("Keychain did not retain the Notion token")


def configured_roots():
    override = os.environ.get("LIB_NOTION_ROOT_PAGE_IDS")
    if override is not None:
        return [value.strip() for value in override.split(",") if value.strip()]
    if DEFAULT_CONFIG.exists():
        config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
        roots = config.get("root_page_ids", [])
        if not isinstance(roots, list) or any(not isinstance(value, str) for value in roots):
            raise ScanError("Invalid root_page_ids in ~/.config/lib-notion/config.json")
        return [value.strip() for value in roots if value.strip()]
    return []


class NotionClient:
    def __init__(self, token):
        self.token = token

    def request(self, method, path, payload=None):
        url = API + path
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Authorization": f"Bearer {self.token}", "Notion-Version": VERSION}
        if data is not None:
            headers["Content-Type"] = "application/json"
        for attempt in range(4):
            try:
                with urlopen(Request(url, data=data, headers=headers, method=method), timeout=30) as response:
                    return json.load(response)
            except HTTPError as error:
                if error.code in (429, 500, 502, 503, 504, 529) and attempt < 3:
                    delay = error.headers.get("Retry-After")
                    try:
                        delay = min(30, max(0, float(delay))) if delay else 2 ** attempt
                    except ValueError:
                        delay = 2 ** attempt
                    time.sleep(delay)
                    continue
                raise ScanError(f"Notion API {method} {path}: HTTP {error.code}") from None
            except URLError as error:
                raise ScanError(f"Notion API unavailable: {error.reason}") from None
        raise ScanError(f"Notion API {method} {path}: retry limit reached")


def search_all(client):
    objects = []
    cursor = None
    while True:
        body = {"sort": {"direction": "descending", "timestamp": "last_edited_time"}, "page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        response = client.request("POST", "/search", body)
        if response.get("request_status", {}).get("type") == "incomplete":
            raise ScanError("Notion search returned an incomplete result set; narrow the scope or backfill separately.")
        objects.extend(response.get("results", []))
        if not response.get("has_more"):
            return objects
        cursor = response.get("next_cursor")
        if not cursor:
            raise ScanError("Notion search says has_more without next_cursor")


def parent_id(obj):
    parent = obj.get("parent") or {}
    for key in ("page_id", "data_source_id", "database_id", "block_id"):
        if parent.get(key):
            return parent[key]
    return None


def scope_index(client, objects, roots):
    by_id = {obj["id"]: obj for obj in objects if obj.get("id")}
    if not roots:
        return by_id
    pending = [obj.get("parent") or {} for obj in objects]
    queried = set()
    while pending:
        parent = pending.pop()
        identifier = None
        endpoint = None
        for key, resource in (("page_id", "pages"), ("data_source_id", "data_sources"), ("database_id", "databases")):
            if parent.get(key):
                identifier, endpoint = parent[key], resource
                break
        if not identifier or identifier in by_id or identifier in queried:
            continue
        queried.add(identifier)
        try:
            ancestor = client.request("GET", f"/{endpoint}/{identifier}")
        except ScanError as error:
            if "HTTP 404" in str(error):
                continue
            raise
        by_id[identifier] = ancestor
        pending.append(ancestor.get("parent") or {})
    return by_id


def in_scope(obj, by_id, roots):
    if not roots:
        return True
    seen = set()
    current = obj
    while current and current.get("id") not in seen:
        identifier = current.get("id")
        if identifier in roots:
            return True
        seen.add(identifier)
        current = by_id.get(parent_id(current))
    return False


def title_of(page):
    for prop in (page.get("properties") or {}).values():
        if isinstance(prop, dict) and prop.get("type") == "title":
            title = "".join(x.get("plain_text", "") for x in prop.get("title", []))
            if title:
                return title
    title = page.get("title", [])
    if isinstance(title, list):
        return "".join(x.get("plain_text", "") for x in title) or "Untitled"
    return title or "Untitled"


def markdown_for(client, page_id):
    pending = [page_id]
    visited = set()
    parts = []
    unavailable = []
    while pending:
        block_id = pending.pop(0)
        if block_id in visited:
            continue
        visited.add(block_id)
        try:
            response = client.request("GET", f"/pages/{block_id}/markdown")
        except ScanError as error:
            if block_id != page_id and "HTTP 404" in str(error):
                unavailable.append(block_id)
                continue
            raise
        parts.append(response.get("markdown", ""))
        pending.extend(response.get("unknown_block_ids", []))
        if len(visited) + len(pending) > 500:
            raise ScanError(f"Page {page_id} exceeds the 500-block continuation guard")
    return "\n\n".join(parts), unavailable


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def scan(client, state_path, roots, since=None, output_dir=None, now=None):
    now = now or utc_now()
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    scope = sorted(roots)
    if state.get("scope", scope) != scope:
        raise ScanError("Scan scope changed. Use a new --state path to establish a separate checkpoint.")
    cutoff = parse_time(since) if since else parse_time(state["completed_at"]) - timedelta(minutes=5) if state.get("completed_at") else now - timedelta(hours=24)
    objects = search_all(client)
    by_id = scope_index(client, objects, roots)
    seen = dict(state.get("seen", {}))
    pages = []
    for obj in objects:
        if obj.get("object") != "page" or obj.get("in_trash") or obj.get("archived"):
            continue
        if not in_scope(obj, by_id, set(roots)):
            continue
        revision = obj.get("last_edited_time")
        if not revision or parse_time(revision) < cutoff or seen.get(obj["id"]) == revision:
            continue
        pages.append(obj)
    run_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="lib-notion-"))
    run_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(run_dir, 0o700)
    entries = []
    for page in pages:
        markdown, unavailable = markdown_for(client, page["id"])
        markdown_path = run_dir / f"{page['id']}.md"
        markdown_path.write_text(markdown, encoding="utf-8")
        os.chmod(markdown_path, 0o600)
        entries.append({
            "id": page["id"], "title": title_of(page), "url": page.get("url"),
            "created_time": page.get("created_time"), "last_edited_time": page["last_edited_time"],
            "markdown_file": str(markdown_path), "unavailable_block_ids": unavailable,
            "unknown_block_tags": len(re.findall(r"<unknown\b", markdown)),
        })
        seen[page["id"]] = page["last_edited_time"]
    manifest = {
        "source": "notion", "scope": scope or "all_accessible", "since": stamp(cutoff),
        "scan_started_at": stamp(now), "accessible_objects": len(objects),
        "changed_pages": len(entries), "pages": entries,
    }
    manifest_path = run_dir / "manifest.json"
    atomic_json(manifest_path, manifest)
    atomic_json(state_path, {"scope": scope, "completed_at": stamp(now), "seen": seen})
    return manifest_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["scan", "store-token"])
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--since", help="ISO-8601 timestamp for an explicit backfill window")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "store-token":
            keychain_store(sys.stdin.read().strip())
            print("Stored nonempty Notion token in the dedicated macOS Keychain item.")
            return 0
        path = scan(NotionClient(token_from_environment_or_keychain()), args.state, configured_roots(), args.since, args.output_dir)
    except (ScanError, ValueError, json.JSONDecodeError) as error:
        print(f"lib-notion: {error}", file=sys.stderr)
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
