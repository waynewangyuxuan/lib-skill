"""The Notion protocol, credential and coverage boundary."""

import getpass
import json
import os
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

API_VERSION = "2026-03-11"
KEYCHAIN_SERVICE = "com.wayne.lib-notion"
FILE_HOSTS = ("amazonaws.com", "notion-static.com", "notion.so", "notion.com")


def _file_url(url):
    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    if (parsed.scheme != "https" or parsed.username or parsed.password
            or parsed.port not in (None, 443)
            or not any(hostname == host or hostname.endswith("." + host) for host in FILE_HOSTS)):
        raise NotionError("Attachment host is outside the configured Notion file boundary")


class _FileRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _file_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class NotionError(RuntimeError):
    pass


class UncertainWrite(NotionError):
    """The response does not establish whether a remote mutation completed."""


def credential():
    value = os.environ.get("NOTION_API_KEY") or os.environ.get("NOTION_PAT")
    if value:
        return value
    if sys.platform == "darwin":
        result = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-s", KEYCHAIN_SERVICE,
             "-a", getpass.getuser(), "-w"],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    raise NotionError("Dedicated Notion credential unavailable. Supply NOTION_API_KEY securely.")


class NotionClient:
    def __init__(self, token=None, version=API_VERSION):
        self._token = token or credential()
        self.version = version

    def request(self, method, path, payload=None):
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("Notion paths must be relative API paths")
        safe = method == "GET" or path.endswith("/query") or path == "/search"
        data = None if payload is None else json.dumps(payload).encode()
        headers = {"Authorization": "Bearer " + self._token,
                   "Notion-Version": self.version, "Content-Type": "application/json"}
        for attempt in range(3):
            try:
                req = Request("https://api.notion.com/v1" + path, data, headers, method=method)
                with urlopen(req, timeout=30) as response:
                    return json.load(response)
            except HTTPError as error:
                if error.code == 429 and attempt < 2:
                    try:
                        delay = min(10, max(1, float(error.headers.get("Retry-After", "1"))))
                    except ValueError:
                        delay = 1
                    time.sleep(delay)
                    continue
                if error.code >= 500:
                    if safe and attempt < 2:
                        time.sleep(2 ** attempt)
                        continue
                    if not safe:
                        raise UncertainWrite(f"Notion {method} {path}: HTTP {error.code}; reconcile before retry") from None
                raise NotionError(f"Notion {method} {path}: HTTP {error.code}") from None
            except (URLError, TimeoutError, json.JSONDecodeError):
                if safe and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                cls = NotionError if safe else UncertainWrite
                raise cls(f"Notion {method} {path}: response unavailable") from None
        raise NotionError("Notion retry limit reached")

    def query(self, data_source_id, filter=None):
        pages, cursor = [], None
        while True:
            body = {"page_size": 100}
            if filter is not None:
                body["filter"] = filter
            if cursor:
                body["start_cursor"] = cursor
            response = self.request("POST", f"/data_sources/{data_source_id}/query", body)
            pages.extend(response.get("results", []))
            if not response.get("has_more"):
                return pages
            new_cursor = response.get("next_cursor")
            if not new_cursor or new_cursor == cursor:
                raise NotionError("Data-source query has more results but no advancing cursor")
            cursor = new_cursor

    def children(self, block_id):
        blocks, cursor = [], None
        while True:
            params = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            response = self.request("GET", f"/blocks/{block_id}/children?" + urlencode(params))
            blocks.extend(response.get("results", []))
            if not response.get("has_more"):
                return blocks
            new_cursor = response.get("next_cursor")
            if not new_cursor or new_cursor == cursor:
                raise NotionError("Block query has more results but no advancing cursor")
            cursor = new_cursor

    def download(self, url):
        _file_url(url)
        try:
            with build_opener(_FileRedirect()).open(Request(url), timeout=30) as response:
                _file_url(response.url)
                content = response.read(100 * 1024 * 1024 + 1)
                if len(content) > 100 * 1024 * 1024:
                    raise NotionError("Attachment exceeds the 100 MiB collection limit")
                return content
        except (HTTPError, URLError, TimeoutError):
            raise NotionError("Attachment bytes unavailable; retained as a coverage gap") from None


def rich(text, url=None):
    item = {"type": "text", "text": {"content": text}}
    if url:
        item["text"]["link"] = {"url": url}
    return item


def title(page):
    for value in page.get("properties", {}).values():
        if value.get("type") == "title":
            return "".join(x.get("plain_text", x.get("text", {}).get("content", ""))
                           for x in value.get("title", [])) or "Untitled"
    return "Untitled"
