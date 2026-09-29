import unittest
from io import BytesIO
from unittest.mock import patch
from urllib.error import URLError

from mylibrary.notion import NotionClient, NotionError, UncertainWrite


class ScriptedClient(NotionClient):
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        return next(self.responses)


class QueryCoverageTests(unittest.TestCase):
    def test_safe_read_retries_transport_error_but_write_stays_uncertain(self):
        client = NotionClient(token="test")
        with patch("mylibrary.notion.urlopen", side_effect=[URLError("offline"), BytesIO(b'{"ok": true}')]) as request, patch("mylibrary.notion.time.sleep"):
            self.assertEqual(client.request("GET", "/users/me"), {"ok": True})
            self.assertEqual(request.call_count, 2)
        with patch("mylibrary.notion.urlopen", side_effect=URLError("offline")) as request:
            with self.assertRaises(UncertainWrite):
                client.request("POST", "/databases", {"title": []})
            self.assertEqual(request.call_count, 1)

    def test_complete_data_source_query_reads_every_page(self):
        client = ScriptedClient([
            {"results": [{"id": "event-a"}], "has_more": True, "next_cursor": "after-a"},
            {"results": [{"id": "event-b"}], "has_more": False},
        ])
        self.assertEqual(client.query("events"), [{"id": "event-a"}, {"id": "event-b"}])
        self.assertEqual(client.calls[1],
                         ("POST", "/data_sources/events/query", {"page_size": 100, "start_cursor": "after-a"}))

    def test_incomplete_query_is_not_reported_as_complete(self):
        client = ScriptedClient([{"results": [{"id": "event-a"}], "has_more": True}])
        with self.assertRaisesRegex(NotionError, "no advancing cursor"):
            client.query("events")

    def test_repeated_cursor_does_not_loop_or_hide_missing_rows(self):
        client = ScriptedClient([
            {"results": [{"id": "event-a"}], "has_more": True, "next_cursor": "same"},
            {"results": [{"id": "event-b"}], "has_more": True, "next_cursor": "same"},
        ])
        with self.assertRaises(NotionError):
            client.query("events")

    def test_block_children_preserve_complete_pagination(self):
        client = ScriptedClient([
            {"results": [{"id": "block-a"}], "has_more": True, "next_cursor": "next"},
            {"results": [{"id": "block-b"}], "has_more": False},
        ])
        self.assertEqual(client.children("page"), [{"id": "block-a"}, {"id": "block-b"}])
        self.assertEqual(client.calls[1][1], "/blocks/page/children?page_size=100&start_cursor=next")


if __name__ == "__main__":
    unittest.main()
