import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "skills/lib-notion/scripts/scan.py"
SPEC = importlib.util.spec_from_file_location("notion_scan", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def page(identifier, revision, parent=None):
    return {
        "object": "page", "id": identifier, "last_edited_time": revision,
        "created_time": revision, "url": f"https://www.notion.so/{identifier}",
        "parent": {"type": "page_id", "page_id": parent} if parent else {"type": "workspace", "workspace": True},
        "properties": {"title": {"type": "title", "title": [{"plain_text": identifier}]}},
    }


class FakeClient:
    def __init__(self, objects, fail_markdown=False, ancestors=None):
        self.objects = objects
        self.fail_markdown = fail_markdown
        self.ancestors = ancestors or {}

    def request(self, method, path, payload=None):
        if path == "/search":
            if payload.get("start_cursor"):
                return {"results": self.objects[1:], "has_more": False}
            return {"results": self.objects[:1], "has_more": len(self.objects) > 1, "next_cursor": "next"}
        if path in self.ancestors:
            return self.ancestors[path]
        if self.fail_markdown:
            raise module.ScanError("Notion API unavailable")
        return {"markdown": f"Content for {path}", "unknown_block_ids": []}


class NotionScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / "state.json"
        self.now = datetime(2026, 9, 25, 21, 0, tzinfo=timezone.utc)

    def run_scan(self, client, roots=()):
        return module.scan(client, self.state, roots, output_dir=self.root / "run", now=self.now)

    def test_revisions_are_incremental_and_pagination_is_complete(self):
        client = FakeClient([page("a", "2026-09-25T20:00:00Z"), page("b", "2026-09-25T19:00:00Z")])
        manifest = self.run_scan(client)
        self.assertEqual(json.loads(manifest.read_text())["changed_pages"], 2)
        self.assertEqual(json.loads(self.run_scan(client).read_text())["changed_pages"], 0)
        self.now += timedelta(hours=1)
        client.objects[1]["last_edited_time"] = "2026-09-25T21:30:00Z"
        self.assertEqual(json.loads(self.run_scan(client).read_text())["pages"][0]["id"], "b")

    def test_failed_content_fetch_does_not_advance_checkpoint(self):
        client = FakeClient([page("a", "2026-09-25T20:00:00Z")], fail_markdown=True)
        with self.assertRaises(module.ScanError):
            self.run_scan(client)
        self.assertFalse(self.state.exists())
        client.fail_markdown = False
        self.assertEqual(json.loads(self.run_scan(client).read_text())["changed_pages"], 1)

    def test_root_scope_includes_descendant_only(self):
        client = FakeClient([
            page("child", "2026-09-25T20:00:00Z", "root"),
            page("root", "2026-09-25T20:00:00Z"),
            page("other", "2026-09-25T20:00:00Z"),
        ])
        result = json.loads(self.run_scan(client, roots=("root",)).read_text())
        self.assertEqual({entry["id"] for entry in result["pages"]}, {"root", "child"})

    def test_root_scope_follows_database_ancestors(self):
        row = page("row", "2026-09-25T20:00:00Z")
        row["parent"] = {"type": "data_source_id", "data_source_id": "source"}
        source = {"object": "data_source", "id": "source", "parent": {"type": "database_id", "database_id": "db"}}
        database = {"object": "database", "id": "db", "parent": {"type": "page_id", "page_id": "root"}}
        client = FakeClient([row, source, page("root", "2026-09-25T20:00:00Z")], ancestors={"/databases/db": database})
        result = json.loads(self.run_scan(client, roots=("root",)).read_text())
        self.assertEqual({entry["id"] for entry in result["pages"]}, {"row", "root"})


if __name__ == "__main__":
    unittest.main()
