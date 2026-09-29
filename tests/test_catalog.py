import json
from pathlib import Path
import tempfile
import unittest

import yaml

from mylibrary.catalog import build_index, neighbors, parse_entity, resolve, search
from mylibrary.publish import publish_one
from mylibrary.storage import Library


class PublisherClient:
    def __init__(self, page_id, data_source_id):
        self.page_id = page_id
        self.data_source_id = data_source_id
        self.markdown = ""
        self.properties = {}

    @staticmethod
    def api_properties(properties):
        result = {}
        for label, value in properties.items():
            kind = next(iter(value))
            result[label] = dict(value, type=kind)
        return result

    def query(self, data_source_id, filter=None):
        return []

    def request(self, method, path, payload=None):
        if (method, path) == ("POST", "/pages"):
            self.properties = self.api_properties(payload["properties"])
            return {"id": self.page_id}
        if (method, path) == ("GET", f"/pages/{self.page_id}"):
            return {
                "id": self.page_id,
                "parent": {"data_source_id": self.data_source_id},
                "archived": False,
                "in_trash": False,
                "properties": self.properties,
            }
        if (method, path) == ("GET", f"/pages/{self.page_id}/markdown"):
            return {"markdown": self.markdown, "truncated": False, "unknown_block_ids": []}
        if (method, path) == ("PATCH", f"/pages/{self.page_id}/markdown"):
            self.markdown = payload["replace_content"]["new_str"]
            return {"object": "page"}
        if (method, path) == ("PATCH", f"/pages/{self.page_id}"):
            self.properties.update(self.api_properties(payload["properties"]))
            return {"id": self.page_id}
        raise AssertionError(f"Unexpected publisher request: {method} {path}")


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.vault = Path(self.temporary.name)
        (self.vault / "_entities").mkdir()

    def entity(self, filename, *, entity_id=None, name=None, aliases=(), description=None,
               summary="A recorded entity.", relations=()):
        metadata = {"type": "concept", "aliases": list(aliases), "tags": ["test"]}
        if entity_id is not None:
            metadata.update(id=entity_id, name=name or Path(filename).stem,
                            description=description or "A catalog test entity.", revision=1)
        body = [f"# {name or Path(filename).stem}", "", "## Summary", summary, "",
                "## Access", "", "## Context", "", "## Relations"]
        body.extend(relations)
        path = self.vault / "_entities" / filename
        path.write_text("---\n" + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False)
                        + "---\n\n" + "\n".join(body) + "\n", encoding="utf-8")
        return path

    def test_stable_id_survives_file_rename(self):
        original = self.entity("alpha.md", entity_id="ent_alpha", name="Alpha")
        self.assertEqual(resolve(self.vault, "ent_alpha")["path"], "_entities/alpha.md")
        original.rename(self.vault / "_entities" / "renamed.md")
        result = resolve(self.vault, "ent_alpha")
        self.assertEqual((result["status"], result["id"], result["path"], result["legacy"]),
                         ("resolved", "ent_alpha", "_entities/renamed.md", False))

    def test_same_name_reports_ambiguity_without_guessing(self):
        self.entity("first.md", entity_id="ent_first", name="Shared name")
        self.entity("second.md", entity_id="ent_second", name="Shared name")
        result = resolve(self.vault, "Shared name")
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual([item["id"] for item in result["matches"]], ["ent_first", "ent_second"])

    def test_source_edit_rebuilds_description_index(self):
        self.entity("alpha.md", entity_id="ent_alpha", name="Alpha",
                    description="Initial description")
        first = build_index(self.vault)
        self.entity("alpha.md", entity_id="ent_alpha", name="Alpha",
                    description="Fresh searchable wording")
        results = search(self.vault, "fresh searchable")
        second = build_index(self.vault)
        self.assertNotEqual(first["source_digest"], second["source_digest"])
        self.assertEqual((results[0]["id"], results[0]["match_reasons"]),
                         ("ent_alpha", ["description"]))
        disk = json.loads((self.vault / "_index/entities.json").read_text(encoding="utf-8"))
        self.assertEqual(disk["source_digest"], second["source_digest"])

    def test_incoming_edge_resolves_alias_with_existing_relation_syntax(self):
        self.entity("parent.md", entity_id="ent_parent", name="Parent",
                    aliases=("Parent Alias",))
        self.entity("child.md", entity_id="ent_child", name="Child",
                    relations=("- part-of:: [[Parent Alias]]",))
        result = neighbors(self.vault, "ent_parent", predicate="part-of", direction="incoming")
        self.assertEqual(result, [{
            "direction": "incoming", "predicate": "part-of", "entity_id": "ent_child",
            "catalog_key": "ent_child", "name": "Child", "path": "_entities/child.md",
            "legacy": False, "target_reference": "Parent Alias", "resolution": "resolved",
            "matched_by": "name_or_alias", "matches": ["_entities/parent.md"],
        }])

    def test_unrelated_query_has_no_forced_candidate(self):
        self.entity("alpha.md", entity_id="ent_alpha", name="Alpha",
                    description="Compiler design notes", summary="Parsing and types.")
        self.assertEqual(search(self.vault, "orchid astronomy"), [])

    def test_unsettled_event_and_page_text_are_searchable_by_scope(self):
        self.entity("alpha.md", entity_id="ent_alpha", name="Alpha")
        library = Library(self.vault)
        event = library.record("notion", "w", "p1", "First line\nThe orchid protocol ships Friday", name="note")
        page = library.record("notion", "w", "p2", "Orchid protocol reference manual", name="Manual",
                              input_kind="source_update")
        personal = search(self.vault, "orchid protocol")
        self.assertEqual([(row["kind"], row["event_id"], row["line"], row["snippet"], row["settled"]) for row in personal],
                         [("event", event["event_id"], 2, "The orchid protocol ships Friday", False)])
        sources = search(self.vault, "orchid protocol", scope="sources")
        self.assertEqual([(row["kind"], row["event_id"]) for row in sources], [("source", page["event_id"])])
        both = search(self.vault, "orchid protocol", scope="all")
        self.assertEqual({row["event_id"] for row in both}, {event["event_id"], page["event_id"]})
        self.assertEqual(search(self.vault, "orchid protocol", scope=["ent_alpha"]), [])

    def test_legacy_page_remains_searchable_with_explicit_marker(self):
        self.entity("old-tool.md", name="Old Tool", aliases=("Old Alias",),
                    summary="A historical scheduling tool.")
        resolved = resolve(self.vault, "Old Alias")
        self.assertEqual((resolved["status"], resolved["id"], resolved["legacy"],
                          resolved["catalog_key"]),
                         ("resolved", None, True, "legacy:_entities/old-tool.md"))
        results = search(self.vault, "historical scheduling")
        self.assertEqual((results[0]["path"], results[0]["legacy"]),
                         ("_entities/old-tool.md", True))

    def test_publisher_mapping_resolves_url_and_at_uuid_to_same_entity(self):
        path = self.entity("alpha.md", entity_id="ent_alpha", name="Alpha")
        before_publish = build_index(self.vault)["source_digest"]
        page_id = "3e75f769-2d89-8069-beca-c3f3b1efe989"
        workspace_id = "fd2903ae-4fa2-4ae7-9833-103a46bc4188"
        data_source_id = "71582e24-3cb4-4d3d-b416-9a727f2581bf"
        result = publish_one(self.vault, path, PublisherClient(page_id, data_source_id), {
            "workspace_id": workspace_id,
            "resources": {"entities": {"data_source_id": data_source_id}},
        })
        self.assertEqual(result["status"], "published")
        mapping = json.loads((self.vault / "_state/notion/entity-map.json").read_text())
        self.assertEqual(mapping["ent_alpha"], {
            "page_id": page_id,
            "workspace_id": workspace_id,
            "data_source_id": data_source_id,
        })
        compact = page_id.replace("-", "")
        from_url = resolve(self.vault, f"https://www.notion.so/Alpha-{compact}")
        from_at_id = resolve(self.vault, f"@{page_id}")
        self.assertNotEqual(before_publish, build_index(self.vault)["source_digest"])
        self.assertEqual((from_url["status"], from_url["id"], from_url["matched_by"]),
                         ("resolved", "ent_alpha", "notion_page_id"))
        self.assertEqual((from_at_id["status"], from_at_id["id"], from_at_id["matched_by"]),
                         ("resolved", "ent_alpha", "notion_page_id"))
        self.assertEqual(from_url["catalog_key"], from_at_id["catalog_key"])

    def test_parse_entity_returns_frontmatter_and_body(self):
        path = self.entity("alpha.md", entity_id="ent_alpha", name="Alpha")
        metadata, body = parse_entity(path)
        self.assertEqual((metadata["id"], metadata["name"]), ("ent_alpha", "Alpha"))
        self.assertTrue(body.startswith("\n# Alpha\n"))


if __name__ == "__main__":
    unittest.main()
