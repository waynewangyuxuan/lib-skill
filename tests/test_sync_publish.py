import copy
import json
from pathlib import Path
import re
import tempfile
import unittest
import unittest.mock
import uuid

from mylibrary.notion import NotionError, UncertainWrite, rich
from mylibrary import publish as publish_module
from mylibrary.publish import publish
from mylibrary.storage import Library, atomic_json, digest, read_json
from mylibrary.catalog import search
from mylibrary.sync import SETUP, collect, setup, source_open


def notion_normalized(markdown):
    markdown = re.sub(r"\n{2,}", "\n", markdown)
    markdown = re.sub(r"(https://app\.notion\.com/p/)[^)\s]*-([0-9a-f]{32})", r"\1\2", markdown)
    parts = markdown.split("`")
    parts[::2] = [re.sub(r"(?<![\w\[])(\w+\.md)(?![\w\]])", r"[\1](http://\1)", part) for part in parts[::2]]
    return "`".join(parts)


def identifier(number):
    return str(uuid.UUID(int=number))


WORKSPACE, EVENTS, ENTITIES = [identifier(value) for value in (1, 2, 4)]


class MemoryNotion:
    def __init__(self):
        self.pages, self.blocks, self.markdown, self.sources = {}, {}, {}, {}
        self.calls, self.next_id = [], 100
        self.database_sources, self.database_parents = {}, {}
        self.lose_create = False
        self.lose_body = False
        self.hide_query = False
        self.download_error = False

    def add_page(self, number, source=EVENTS, text="A thought", mention=None, file_url=None):
        value = identifier(number)
        self.pages[value] = {"id": value, "url": "https://www.notion.so/" + value.replace("-", ""),
                             "parent": {"type": "data_source_id", "data_source_id": source},
                             "properties": {"Name": {"id": "title", "type": "title", "title": [rich("Note")]},
                                            "Edited": {"type": "last_edited_time", "last_edited_time": "time"}}}
        words = [rich(text)]
        if mention:
            words.append({"type": "mention", "mention": {"type": "page", "page": {"id": mention}}, "plain_text": "@Entity"})
        self.blocks[value] = [{"id": identifier(number + 1000), "type": "paragraph", "paragraph": {"rich_text": words}}]
        if file_url:
            self.blocks[value].append({"id": identifier(number + 2000), "type": "image", "image": {"type": "file", "file": {"url": file_url}}})
        self.markdown[value] = ""
        return value

    def query(self, source, filter=None):
        if self.hide_query and source == ENTITIES:
            return []
        pages = [copy.deepcopy(page) for page in self.pages.values() if page.get("parent", {}).get("data_source_id") == source]
        if filter:
            pages = [page for page in pages if "".join(item["text"]["content"] for item in page["properties"].get("Entity ID", {}).get("rich_text", [])) == filter["rich_text"]["equals"]]
        return pages

    def children(self, parent):
        return copy.deepcopy(self.blocks.get(parent, []))

    def download(self, url):
        if self.download_error:
            raise NotionError("image unavailable")
        return b"actual image bytes"

    def request(self, method, path, payload=None):
        self.calls.append((method, path, copy.deepcopy(payload)))
        if path == "/users/me":
            return {"bot": {"workspace_id": WORKSPACE}}
        if method == "POST" and path == "/search":
            kind = payload["filter"]["value"]
            if kind == "data_source":
                return {"results": [{"object": "data_source", "id": source, "parent": {"type": "database_id", "database_id": database}}
                                    for database, source in self.database_sources.items()], "has_more": False}
            return {"results": [copy.deepcopy(page) for page in self.pages.values()
                                if page.get("parent", {}).get("type") == "workspace"], "has_more": False}
        if method == "GET" and path.startswith("/databases/"):
            database = path.split("/")[2]
            return {"id": database, "data_sources": [{"id": self.database_sources[database]}],
                    "parent": self.database_parents.get(database, {"type": "page_id", "page_id": identifier(1)})}
        if method == "GET" and path.startswith("/data_sources/"):
            return copy.deepcopy(self.sources[path.split("/")[-1]])
        if method == "GET" and path.endswith("/markdown"):
            return {"object": "page_markdown", "markdown": self.markdown[path.split("/")[2]], "truncated": False, "unknown_block_ids": []}
        if method == "GET" and path.startswith("/pages/"):
            if path.split("/")[2] not in self.pages:
                raise NotionError("Notion GET " + path + ": HTTP 404")
            return copy.deepcopy(self.pages[path.split("/")[2]])
        if method == "POST" and path in {"/pages", "/databases", "/views"}:
            value = identifier(self.next_id)
            self.next_id += 1
            if path == "/pages":
                page = {"id": value, "parent": payload["parent"], "properties": {}, "url": "https://www.notion.so/" + value}
                self.pages[value] = page
                self.markdown[value] = ""
                self._patch_properties(page, payload["properties"])
                if self.lose_create:
                    self.lose_create = False
                    raise UncertainWrite("lost create")
                return copy.deepcopy(page)
            if path == "/databases":
                source = identifier(self.next_id)
                self.next_id += 1
                props = {label: dict(prop, id=label) for label, prop in payload["initial_data_source"]["properties"].items()}
                self.sources[source] = {"id": source, "properties": props}
                return {"id": value, "data_sources": [{"id": source}]}
            return {"id": value}
        if method == "PATCH" and path.startswith("/data_sources/"):
            source = self.sources[path.split("/")[-1]]
            for label, prop in payload["properties"].items():
                source["properties"][label] = dict(prop, id=label)
            return copy.deepcopy(source)
        if method == "PATCH" and path.endswith("/children"):
            return {"results": [dict(item, id=identifier(self.next_id + index)) for index, item in enumerate(payload["children"])]}
        if method == "PATCH" and path.endswith("/markdown"):
            value = path.split("/")[2]
            self.markdown[value] = notion_normalized(payload["replace_content"]["new_str"])
            if self.lose_body:
                self.lose_body = False
                raise UncertainWrite("lost body update")
            return {"object": "page_markdown", "markdown": self.markdown[value]}
        if method == "PATCH" and path.startswith("/pages/"):
            page = self.pages[path.split("/")[2]]
            self._patch_properties(page, payload["properties"])
            return copy.deepcopy(page)
        raise AssertionError((method, path, payload))

    def _patch_properties(self, page, properties):
        for label, prop in properties.items():
            kind = next(key for key in prop if key != "type")
            page["properties"][label] = dict(prop, type=kind)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.vault = Path(self.temporary.name)
        self.client = MemoryNotion()
        (self.vault / "_entities").mkdir()
        atomic_json(self.vault / SETUP, {"schema_version": 1, "workspace_id": WORKSPACE,
                    "resources": {"events": {"data_source_id": EVENTS},
                                  "entities": {"data_source_id": ENTITIES}}})

    def entity(self, name="Example", revision=1):
        path = self.vault / "_entities/example.md"
        path.write_text(f"---\nid: ent_example\nname: {name}\ntype: concept\ndescription: A personal example\nrevision: {revision}\ntags: [research, reading]\nstate: active\n---\n\n## Summary\n\nKnown result\n\n## Access\n\n[[local-note]]\n\n## Context\n\n- First original source [原页](https://app.notion.com/p/Some-Title-3ea5f7692d8980c7ab79cfa09dad5f27), [[_events/evt_local/revisions/1/body.md]]\n\n## Relations\n", encoding="utf-8")
        return path

    def result(self):
        return publish(self.vault, ["ent_example"], self.client)["results"][0]

    def test_collect_revisions_mentions_bytes_and_scope(self):
        one = self.client.add_page(10, mention=identifier(50), file_url="https://s3.amazonaws.com/a?X-Amz-Signature=first")
        result = collect(self.vault, self.client)
        self.assertEqual(len(result["observations"]), 1)
        envelope = next(event for event in result["pending"] if event["identity"]["resource_id"] == one)
        self.assertEqual(envelope["mentions"], [identifier(50)])
        self.assertEqual(envelope["authorship"], "wayne")
        self.assertEqual((self.vault / envelope["attachments"][0]["path"]).read_bytes(), b"actual image bytes")
        self.client.blocks[one][1]["image"]["file"]["url"] = "https://s3.amazonaws.com/a?X-Amz-Signature=second"
        self.client.pages[one]["properties"]["Edited"]["last_edited_time"] = "later"
        again = collect(self.vault, self.client)
        self.assertEqual([item["revision"] for item in again["observations"]], [1])
        self.assertNotIn("X-Amz-Signature", (self.vault / envelope["raw_path"]).read_text())
        self.assertFalse(any(call[1] == "/search" for call in self.client.calls))

    def test_referenced_pages_are_local_sources_not_inputs(self):
        doc = self.client.add_page(60, source=None, text="Design doc body")
        self.client.pages[doc]["parent"] = {"type": "page_id", "page_id": identifier(1)}
        linked = self.client.add_page(62, source=None, text="Linked notes body")
        self.client.pages[linked]["parent"] = {"type": "page_id", "page_id": identifier(1)}
        self.client.add_page(10, text="See the doc ", mention=doc)
        link = rich("notes", "https://www.notion.so/Notes-" + linked.replace("-", ""))
        self.client.add_page(12, text="Also ")
        self.client.blocks[identifier(12)][0]["paragraph"]["rich_text"].append(link)
        self.client.add_page(14, text="Missing ", mention=identifier(70))
        result = collect(self.vault, self.client)
        references = {item["page_id"]: item for item in result["references"]}
        self.assertEqual({key: item["status"] for key, item in references.items()},
                         {doc: "snapshotted", linked: "snapshotted", identifier(70): "unavailable"})
        self.assertEqual(len(result["pending"]), 3)
        self.assertIn("Design doc body", (self.vault / references[doc]["body_path"]).read_text())
        self.assertEqual(search(self.vault, "linked notes body", scope="sources")[0]["kind"], "reference")
        self.assertEqual(search(self.vault, "linked notes body"), [])
        again = {item["page_id"]: item["status"] for item in collect(self.vault, self.client)["references"]}
        self.assertEqual(again[doc], "unchanged")
        self.client.blocks[doc][0]["paragraph"]["rich_text"] = [rich("Design doc revised")]
        self.client.pages[doc]["last_edited_time"] = "later"
        third = {item["page_id"]: item for item in collect(self.vault, self.client)["references"]}
        self.assertEqual((third[doc]["status"], third[doc]["revision"]), ("snapshotted", 2))

    def watched_page(self, number, parent, text, edited="2026-01-01T00:00:00.000Z"):
        page = self.client.add_page(number, source=None, text=text)
        self.client.pages[page]["parent"] = parent
        self.client.pages[page]["last_edited_time"] = edited
        return page

    def test_watch_area_baselines_then_queues_edits(self):
        settings = read_json(self.vault / SETUP)
        diary = self.watched_page(80, {"type": "workspace", "workspace": True}, "Private diary")
        settings["watch"] = {"exclude": [diary]}
        atomic_json(self.vault / SETUP, settings)
        root = self.watched_page(60, {"type": "workspace", "workspace": True}, "Study root")
        note = self.watched_page(61, {"type": "page_id", "page_id": root}, "Note body")
        row = self.watched_page(62, {"type": "data_source_id", "data_source_id": identifier(70)}, "Row body")
        self.client.database_sources[identifier(69)] = identifier(70)
        self.client.blocks[root] += [{"id": note, "type": "child_page", "child_page": {"title": "Note"}},
                                     {"id": identifier(69), "type": "child_database", "child_database": {"title": "Courses"}}]
        first = collect(self.vault, self.client)
        self.assertEqual(first["watch"]["baseline"], True)
        self.assertEqual(sorted(item["page_id"] for item in first["watch"]["observed"]), sorted([root, note, row]))
        self.assertEqual(first["pending"], [])
        self.assertEqual(search(self.vault, "row body", scope="sources")[0]["kind"], "source")
        self.assertEqual(search(self.vault, "private diary", scope="all"), [])
        calls = len(self.client.calls)
        quiet = collect(self.vault, self.client)
        self.assertEqual(quiet["watch"]["observed"], [])
        self.assertFalse(any(call[1].startswith("/blocks/") for call in self.client.calls[calls:]))
        self.client.blocks[note][0]["paragraph"]["rich_text"] = [rich("Note body revised")]
        self.client.pages[note]["last_edited_time"] = "2099-01-01T00:00:00.000Z"
        edited = collect(self.vault, self.client)
        self.assertEqual([(item["page_id"], item["revision"]) for item in edited["watch"]["observed"]], [(note, 2)])
        self.assertEqual([(event["name"], event["revision"], event["input_kind"]) for event in edited["pending"]],
                         [("Note", 2, "source_update")])
        self.assertEqual(edited["pending"][0]["authorship"], "wayne")

    def test_watch_includes_databases_at_the_workspace_root(self):
        settings = read_json(self.vault / SETUP)
        settings["watch"] = {"exclude": []}
        atomic_json(self.vault / SETUP, settings)
        self.client.database_sources[identifier(90)] = identifier(91)
        self.client.database_parents[identifier(90)] = {"type": "workspace", "workspace": True}
        person = self.watched_page(92, {"type": "data_source_id", "data_source_id": identifier(91)}, "Contact notes")
        result = collect(self.vault, self.client)
        self.assertEqual([item["page_id"] for item in result["watch"]["observed"]], [person])
        late = self.watched_page(93, {"type": "data_source_id", "data_source_id": identifier(91)}, "Old but newly visible")
        fresh = self.watched_page(94, {"type": "data_source_id", "data_source_id": identifier(91)}, "Written after the baseline",
                                  edited="2099-01-01T00:00:00.000Z")
        later = {item["page_id"]: item["readiness"] for item in collect(self.vault, self.client)["watch"]["observed"]}
        self.assertEqual(later, {late: "baseline", fresh: "ready"})

    def test_busy_vault_skips_one_watch_page_without_losing_the_rest(self):
        settings = read_json(self.vault / SETUP)
        settings["watch"] = {"exclude": []}
        atomic_json(self.vault / SETUP, settings)
        root = self.watched_page(60, {"type": "workspace", "workspace": True}, "Study root")
        note = self.watched_page(61, {"type": "page_id", "page_id": root}, "Note body")
        self.client.blocks[root].append({"id": note, "type": "child_page", "child_page": {"title": "Note"}})
        original = Library.record

        def busy_for_note(library, provider, workspace_id, resource_id, body, **kwargs):
            if resource_id == note:
                raise BlockingIOError("writer lock held")
            return original(library, provider, workspace_id, resource_id, body, **kwargs)

        with unittest.mock.patch.object(Library, "record", busy_for_note):
            first = collect(self.vault, self.client)
        self.assertEqual([item["page_id"] for item in first["watch"]["observed"]], [root])
        self.assertEqual([(item["page_id"], item["status"]) for item in first["watch"]["failures"]], [(note, "busy")])
        again = collect(self.vault, self.client)
        self.assertEqual([item["page_id"] for item in again["watch"]["observed"]], [note])

    def test_empty_new_page_then_edit_and_missing_attachment(self):
        page = self.client.add_page(12, text="")
        first = collect(self.vault, self.client)
        self.assertEqual(first["pending"], [])
        self.client.blocks[page][0]["paragraph"]["rich_text"] = [rich("Now written")]
        self.client.blocks[page].append({"id": identifier(99), "type": "image", "image": {"type": "file", "file": {"url": "https://s3.amazonaws.com/x"}}})
        self.client.download_error = True
        second = collect(self.vault, self.client)
        self.assertEqual(second["observations"][0]["revision"], 2)
        self.assertEqual(second["pending"][0]["coverage"]["status"], "partial")
        self.assertEqual(second["pending"][0]["attachments"][0]["status"], "unavailable")
        self.client.download_error = False
        self.assertEqual(collect(self.vault, self.client)["observations"][0]["revision"], 3)

    def test_unknown_blocks_and_failed_subtree_are_explicit(self):
        page = self.client.add_page(13)
        self.client.blocks[page].append({"id": identifier(99), "type": "future_block", "future_block": {}})
        report = collect(self.vault, self.client)
        self.assertEqual(report["pending"][0]["coverage"]["status"], "partial")
        self.assertEqual(report["pending"][0]["coverage"]["gaps"][0]["block_id"], identifier(99))

    def test_cache_and_historical_do_not_contact_notion(self):
        self.client.add_page(14)
        envelope = collect(self.vault, self.client)["pending"][0]
        count = len(self.client.calls)
        cached = source_open(self.vault, envelope["source_id"], client=self.client)
        historic = source_open(self.vault, envelope["event_id"], "historical", 1, self.client)
        self.assertEqual(cached["status"], "cached")
        self.assertEqual(historic["source"]["revision"], 1)
        self.assertEqual(len(self.client.calls), count)

    def test_publish_fixed_page_rename_and_local_links(self):
        path = self.entity()
        first = self.result()
        self.assertEqual(first["status"], "published")
        page = first["page_id"]
        self.assertIn("仅本地可用", self.client.markdown[page])
        self.assertEqual(self.result()["status"], "unchanged")
        self.entity("Renamed", 2)
        again = self.result()
        self.assertEqual(again["page_id"], page)
        self.assertEqual(again["published_revision"], 2)
        creates = [call for call in self.client.calls if call[:2] == ("POST", "/pages")]
        self.assertEqual(len(creates), 1)
        mapping = read_json(self.vault / "_state/notion/entity-map.json")
        self.assertEqual(mapping["ent_example"]["page_id"], page)

    def test_published_title_is_prefixed_and_carries_activity(self):
        path = self.entity()
        first = self.result()
        page = self.client.pages[first["page_id"]]
        self.assertEqual(page["properties"]["Name"]["title"][0]["text"]["content"], "ENT Example")
        self.assertEqual(page["properties"]["Event Count"]["number"], 0)
        self.assertIsNone(page["properties"]["Last Event"]["date"])
        self.assertEqual([item["name"] for item in page["properties"]["Tags"]["multi_select"]], ["reading", "research"])
        self.assertEqual(page["properties"]["State"]["select"]["name"], "active")
        self.assertIn("name: Example", path.read_text())
        self.assertEqual(self.result()["status"], "unchanged")

    def test_page_published_before_prefix_upgrades_without_review(self):
        self.entity()
        first = self.result()
        page = self.client.pages[first["page_id"]]
        page["properties"]["Name"] = {"type": "title", "title": [rich("Example")]}
        for label in ("Event Count", "Last Event"):
            page["properties"].pop(label)
        ledger_path = self.vault / "_state/notion/publication/ent_example.json"
        ledger = read_json(ledger_path)
        ledger["properties_sha256"] = digest(json.dumps(publish_module._properties(page), sort_keys=True, ensure_ascii=False))
        ledger["target_hash"] = "before-prefix"
        atomic_json(ledger_path, ledger)
        again = self.result()
        self.assertEqual(again["status"], "published")
        self.assertEqual(page["properties"]["Name"]["title"][0]["text"]["content"], "ENT Example")

    def test_stray_asterisk_is_escaped_but_emphasis_survives(self):
        path = self.entity()
        path.write_text(path.read_text().replace("Known result",
                        "lib-* skills keep **bold text** and *italic* with `a*b` code, **提出 `lib-catch`——想法**。"))
        page = self.result()["page_id"]
        body = self.client.markdown[page]
        for expected in ("lib-\\* skills", "**bold text**", "*italic*", "`a*b`", "**提出 `lib-catch`——想法**"):
            self.assertIn(expected, body)

    def test_formatting_only_change_is_published(self):
        path = self.entity()
        page = self.result()["page_id"]
        path.write_text(path.read_text().replace("Known result", "**Known** result").replace("revision: 1", "revision: 2"))
        self.assertEqual(self.result()["status"], "published")
        self.assertIn("**Known** result", self.client.markdown[page])

    def test_unchanged_requires_the_exact_markdown_to_have_been_written(self):
        self.entity()
        first = self.result()
        page = first["page_id"]
        desired = self.client.markdown[page]
        self.client.markdown[page] = desired.replace("Known result", "\\*\\*Known result")
        ledger_path = self.vault / "_state/notion/publication/ent_example.json"
        ledger = read_json(ledger_path)
        ledger.pop("written_sha256")
        ledger["remote_sha256"] = digest(publish_module.canonical_markdown(self.client.markdown[page]))
        atomic_json(ledger_path, ledger)
        self.assertEqual(self.result()["status"], "published")
        self.assertEqual(self.client.markdown[page], desired)

    def test_lost_create_is_reconciled_once(self):
        self.entity()
        self.client.lose_create = True
        self.assertEqual(self.result()["status"], "uncertain")
        self.assertEqual(self.result()["status"], "published")
        self.assertEqual(sum(call[:2] == ("POST", "/pages") for call in self.client.calls), 1)

    def test_lost_create_zero_match_never_blindly_recreates(self):
        self.entity()
        self.client.lose_create = True
        self.result()
        self.client.hide_query = True
        self.assertEqual(self.result()["status"], "uncertain")
        self.assertEqual(sum(call[:2] == ("POST", "/pages") for call in self.client.calls), 1)

    def test_lost_body_response_only_finishes_publication(self):
        self.entity()
        self.client.lose_body = True
        first = self.result()
        self.assertEqual(first["status"], "retryable")
        self.assertEqual(self.result()["status"], "published")
        self.assertEqual(sum(call[0] == "PATCH" and call[1].endswith("/markdown") for call in self.client.calls), 1)
        self.assertEqual(Library(self.vault).pending(), [])

    def test_human_property_edit_after_lost_body_response_is_preserved(self):
        self.entity()
        self.client.lose_body = True
        first = self.result()
        self.assertEqual(first["status"], "retryable")
        page = first["page_id"]
        self.client.pages[page]["properties"]["Description"]["rich_text"] = [rich("Human description")]
        self.assertEqual(self.result()["status"], "needs_review")
        self.assertEqual(self.client.pages[page]["properties"]["Description"]["rich_text"][0]["text"]["content"], "Human description")
        self.assertEqual(sum(call[0] == "PATCH" and call[1] == "/pages/" + page for call in self.client.calls), 0)

    def test_human_body_deletion_after_lost_response_is_preserved(self):
        self.entity()
        self.client.lose_body = True
        first = self.result()
        self.assertEqual(first["status"], "retryable")
        page = first["page_id"]
        self.client.markdown[page] = ""
        self.assertEqual(self.result()["status"], "needs_review")
        self.assertEqual(self.client.markdown[page], "")
        self.assertEqual(sum(call[0] == "PATCH" and call[1].endswith("/markdown") for call in self.client.calls), 1)

    def test_human_body_and_property_edits_survive_retries(self):
        self.entity()
        first = self.result()
        page = first["page_id"]
        self.client.markdown[page] += "\nHuman correction"
        self.assertEqual(self.result()["status"], "needs_review")
        self.assertEqual(self.result()["status"], "needs_review")
        self.assertIn("Human correction", self.client.markdown[page])
        self.client.markdown[page] = first["desired_markdown"]
        self.client.pages[page]["properties"]["Description"]["rich_text"] = [rich("Human description")]
        self.assertEqual(self.result()["status"], "needs_review")
        self.assertEqual(self.result()["status"], "needs_review")
        self.assertEqual(self.client.pages[page]["properties"]["Description"]["rich_text"][0]["text"]["content"], "Human description")

    def test_duplicate_ids_and_output_feedback_stop(self):
        self.entity()
        first = self.result()
        page = first["page_id"]
        duplicate = copy.deepcopy(self.client.pages[page])
        duplicate["id"] = identifier(80)
        self.client.pages[duplicate["id"]] = duplicate
        self.assertEqual(self.result()["status"], "needs_review")
        self.client.pages[page]["parent"]["data_source_id"] = EVENTS
        self.client.blocks[page] = [{"id": identifier(90), "type": "paragraph", "paragraph": {"rich_text": [rich("Machine output")]}}]
        report = collect(self.vault, self.client)
        self.assertEqual(report["observations"], [])
        self.assertEqual(report["failures"][0]["status"], "excluded_machine_output")

    def test_workspace_mismatch_prevents_any_capture(self):
        settings = read_json(self.vault / SETUP)
        settings["workspace_id"] = identifier(900)
        atomic_json(self.vault / SETUP, settings)
        self.client.add_page(15)
        with self.assertRaises(NotionError):
            collect(self.vault, self.client)
        self.assertFalse((self.vault / "_events").exists())


class SetupTests(unittest.TestCase):
    def test_existing_main_is_adopted_without_a_second_main_page(self):
        with tempfile.TemporaryDirectory() as temporary:
            vault = Path(temporary)
            client = MemoryNotion()
            main = client.add_page(50)
            client.pages[main]["parent"] = {"type": "workspace", "workspace": True}
            client.pages[main]["properties"]["Name"]["title"] = [rich("MyLibrary")]
            original = copy.deepcopy(client.blocks[main])
            plan = setup(vault, main=main, dry_run=True, client=client)
            self.assertEqual(plan["target"], {"kind": "existing_main", "page_id": main})
            self.assertEqual(client.calls, [])
            first = setup(vault, main=main, client=client)
            writes = sum(call[0] in {"POST", "PATCH"} for call in client.calls)
            second = setup(vault, main=main, client=client)
            self.assertEqual(first["resources"], second["resources"])
            self.assertEqual(first["resources"]["main"]["page_id"], main)
            self.assertEqual(sum(call[:2] == ("POST", "/pages") for call in client.calls), 1)
            self.assertEqual(sum(call[0] in {"POST", "PATCH"} for call in client.calls), writes)
            self.assertEqual(client.blocks[main], original)

    def test_existing_main_refuses_unowned_same_title_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            vault = Path(temporary)
            client = MemoryNotion()
            main = client.add_page(50)
            client.pages[main]["parent"] = {"type": "workspace", "workspace": True}
            client.pages[main]["properties"]["Name"]["title"] = [rich("MyLibrary")]
            client.blocks[main].append({"id": identifier(90), "type": "child_page",
                                        "child_page": {"title": "Entities"}})
            with self.assertRaisesRegex(NotionError, "explicit adoption"):
                setup(vault, main=main, client=client)
            self.assertEqual(sum(call[:2] == ("POST", "/pages") for call in client.calls), 0)

    def test_uncertain_child_create_never_claims_later_user_child_by_title(self):
        with tempfile.TemporaryDirectory() as temporary:
            vault = Path(temporary)
            client = MemoryNotion()
            main = client.add_page(50)
            client.pages[main]["parent"] = {"type": "workspace", "workspace": True}
            client.pages[main]["properties"]["Name"]["title"] = [rich("MyLibrary")]
            client.lose_create = True
            with self.assertRaises(UncertainWrite):
                setup(vault, main=main, client=client)
            client.blocks[main].append({"id": identifier(90), "type": "child_page",
                                        "child_page": {"title": "Entities"}})
            with self.assertRaisesRegex(NotionError, "explicit adoption"):
                setup(vault, main=main, client=client)
            state = read_json(vault / SETUP)
            self.assertNotIn("entities_page", state["resources"])

    def test_dry_run_and_repeat_use_one_resource_set(self):
        with tempfile.TemporaryDirectory() as temporary:
            vault = Path(temporary)
            client = MemoryNotion()
            parent = client.add_page(50)
            self.assertEqual(setup(vault, parent, True, client)["remote_writes"], 0)
            self.assertEqual(client.calls, [])
            one = setup(vault, parent, client=client)
            count = sum(call[0] in {"POST", "PATCH"} for call in client.calls)
            two = setup(vault, parent, client=client)
            self.assertEqual(one["resources"], two["resources"])
            self.assertEqual(sum(call[0] in {"POST", "PATCH"} for call in client.calls), count)
            self.assertEqual(len(one["resources"]), 4)

    def test_setup_adds_activity_properties_and_charts_to_existing_setup(self):
        with tempfile.TemporaryDirectory() as temporary:
            vault = Path(temporary)
            client = MemoryNotion()
            parent = client.add_page(50)
            first = setup(vault, parent, client=client)
            source = first["resources"]["entities"]["data_source_id"]
            self.assertEqual(client.sources[source]["properties"]["Days Idle"]["type"], "formula")
            self.assertEqual(client.sources[source]["properties"]["Tags"]["type"], "multi_select")
            charts = [call[2]["configuration"]["chart_type"] for call in client.calls
                      if call[:2] == ("POST", "/views") and call[2]["type"] == "chart"]
            self.assertEqual(sorted(charts), ["bar", "column", "donut", "number"])
            for label in ("Event Count", "Last Event", "Days Idle"):
                client.sources[source]["properties"].pop(label)
            state = read_json(vault / SETUP)
            for label in ("Event Count", "Last Event", "Days Idle"):
                state["resources"]["entities"]["properties"].pop(label)
            atomic_json(vault / SETUP, state)
            second = setup(vault, parent, client=client)
            self.assertEqual(sorted(client.sources[source]["properties"]),
                             sorted(first["resources"]["entities"]["properties"]))
            self.assertEqual(second["resources"]["entities"]["properties"], first["resources"]["entities"]["properties"])
            self.assertEqual(sum(call[:2] == ("POST", "/databases") for call in client.calls), 2)
            self.assertEqual(sum(call[:2] == ("POST", "/views") for call in client.calls), 6)

    def test_setup_lost_create_stops_instead_of_duplicate(self):
        with tempfile.TemporaryDirectory() as temporary:
            vault = Path(temporary)
            client = MemoryNotion()
            parent = client.add_page(50)
            client.lose_create = True
            with self.assertRaises(UncertainWrite):
                setup(vault, parent, client=client)
            with self.assertRaises(UncertainWrite):
                setup(vault, parent, client=client)
            self.assertEqual(sum(call[:2] == ("POST", "/pages") for call in client.calls), 1)


if __name__ == "__main__":
    unittest.main()
