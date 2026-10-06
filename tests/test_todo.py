from pathlib import Path
import tempfile
import unittest

from mylibrary.notion import rich
from mylibrary.storage import Library, atomic_json, read_json
from mylibrary.sync import SETUP, collect
from mylibrary.publish import publish
from mylibrary.todo import add_todo, list_todos
from test_sync_publish import ENTITIES, EVENTS, WORKSPACE, MemoryNotion, identifier

TODOS = identifier(5)


class TodoTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.vault = Path(self.temporary.name)
        (self.vault / "_entities").mkdir()
        self.client = MemoryNotion()
        atomic_json(self.vault / SETUP, {"schema_version": 1, "workspace_id": WORKSPACE,
                    "resources": {"events": {"data_source_id": EVENTS}, "entities": {"data_source_id": ENTITIES},
                                  "todos": {"data_source_id": TODOS}}})
        library = Library(self.vault)
        self.event = library.record("notion", WORKSPACE, "page", "Plan\n回头看看 DUNE 是什么", name="Notes")

    def add(self, text="弄清 DUNE 是什么", **kwargs):
        return add_todo(self.vault, text, self.event["event_id"], 1, "L2", **kwargs)

    def test_extracted_todo_is_idempotent_and_anchored(self):
        first = self.add(due="2026-10-10")
        self.assertEqual(self.add(due="2026-10-10"), first)
        self.assertEqual((first["status"], first["due"], first["when"]), ("待办", "2026-10-10", {"start": "2026-10-10"}))
        self.assertEqual(first["source"]["anchor"], "L2")
        self.assertEqual([item["id"] for item in list_todos(self.vault)], [first["id"]])
        with self.assertRaises(ValueError):
            add_todo(self.vault, "Bad anchor", self.event["event_id"], 1, "L99")

    def test_publish_creates_each_row_once_and_collect_mirrors_wayne_edits(self):
        todo = self.add(due="2026-10-10")
        publish(self.vault, [], self.client)
        publish(self.vault, [], self.client)
        rows = self.client.query(TODOS)
        self.assertEqual(len(rows), 1)
        row = self.client.pages[rows[0]["id"]]
        self.assertEqual(row["properties"]["Status"]["select"]["name"], "待办")
        row["properties"]["Status"] = {"type": "select", "select": {"name": "完成"}}
        row["properties"]["When"] = {"type": "date", "date": {"start": "2026-10-08T14:00:00-07:00", "end": "2026-10-08T15:00:00-07:00"}}
        manual = self.client.add_page(40, source=TODOS, text="")
        self.client.pages[manual]["properties"]["Name"]["title"] = [rich("买咖啡豆")]
        collect(self.vault, self.client)
        mirrored = {item["text"]: item for item in list_todos(self.vault)}
        self.assertEqual(mirrored["弄清 DUNE 是什么"]["status"], "完成")
        self.assertEqual(mirrored["弄清 DUNE 是什么"]["when"]["start"], "2026-10-08T14:00:00-07:00")
        self.assertEqual(mirrored["买咖啡豆"]["origin"], "notion")
        publish(self.vault, [], self.client)
        self.assertEqual(self.client.pages[rows[0]["id"]]["properties"]["Status"]["select"]["name"], "完成")
        self.assertEqual(len(self.client.query(TODOS)), 2)
        self.assertEqual(read_json(self.vault / f"_todos/{todo['id']}.json")["notion_page_id"], rows[0]["id"])
