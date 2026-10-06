"""Wayne's TODO list: proposed from evidence, owned in Notion, mirrored locally."""

from datetime import date
from pathlib import Path
import re

from .catalog import build_index
from .notion import NotionError, UncertainWrite, rich
from .storage import (Library, _validate_anchor, atomic_json, digest, local_timezone, logical_day, read_json,
                      timestamp, writer_lock)
from .sync import TODO_STATUSES, notion_id

MAP = "_state/notion/entity-map.json"


def _clean(text):
    return re.sub(r"\s+", " ", str(text)).strip()


def _path(library, identifier):
    return library._path(f"_todos/{identifier}.json")


def add_todo(vault, text, event_id, revision, anchor, due=None, entity_ids=()):
    library, text = Library(vault), _clean(text)
    if not text:
        raise ValueError("TODO text required")
    event = read_json(library._path(f"_events/{event_id}/revisions/{int(revision)}/event.json"))
    _validate_anchor(library._path(event["body_path"]), anchor)
    if due is not None:
        date.fromisoformat(due)
    unknown = set(entity_ids) - {item["id"] for item in build_index(Path(vault))["entities"] if item["id"]}
    if unknown:
        raise ValueError("Unknown Entity IDs: " + ", ".join(sorted(unknown)))
    identifier = "todo_" + digest(event_id + "\n" + text.casefold())[:24]
    path = _path(library, identifier)
    with writer_lock(library.vault):
        if path.exists():
            return read_json(path)
        record = {"id": identifier, "text": text, "status": TODO_STATUSES[0], "due": due,
                  "when": {"start": due} if due else None, "entity_ids": sorted(entity_ids),
                  "source": {"event_id": event_id, "revision": int(revision), "anchor": anchor, "url": event.get("source_url")},
                  "origin": "settle", "notion_page_id": None, "created_day": str(library.event_day(event)),
                  "created_at": timestamp(), "removed": False}
        atomic_json(path, record)
    return record


def list_todos(vault, status=None):
    library = Library(vault)
    root = library._path("_todos")
    todos = [read_json(path) for path in sorted(root.glob("*.json"))] if root.exists() else []
    todos = [todo for todo in todos if not todo.get("removed") and (status is None or todo["status"] == status)]
    return sorted(todos, key=lambda todo: ((todo["when"] or {}).get("start") or todo["due"] or "~", todo["created_day"], todo["id"]))


def _row(todo, mapping):
    properties = {"Name": {"title": [rich(todo["text"][:2000])]}, "Status": {"select": {"name": todo["status"]}},
                  "Todo ID": {"rich_text": [rich(todo["id"])]}}
    if todo["due"]:
        properties["Due"] = {"date": {"start": todo["due"]}}
    if todo["when"]:
        properties["When"] = {"date": todo["when"]}
    pages = [mapping[entity]["page_id"] for entity in todo["entity_ids"] if entity in mapping]
    if pages:
        properties["Entities"] = {"relation": [{"id": page} for page in pages]}
    if (todo["source"] or {}).get("url"):
        properties["Source"] = {"url": todo["source"]["url"]}
    return properties


def publish_todos(vault, client, setup):
    library = Library(vault)
    source = setup["resources"]["todos"]["data_source_id"]
    mapping = read_json(library._path(MAP)) if library._path(MAP).exists() else {}
    results = []
    for todo in list_todos(vault):
        if todo["notion_page_id"] or todo["origin"] != "settle":
            continue
        try:
            matches = client.query(source, {"property": "Todo ID", "rich_text": {"equals": todo["id"]}})
            if len(matches) > 1:
                results.append({"todo": todo["id"], "status": "needs_review", "reason": "Several rows share this Todo ID"})
                continue
            created = not matches
            page = matches[0] if matches else client.request(
                "POST", "/pages", {"parent": {"type": "data_source_id", "data_source_id": source}, "properties": _row(todo, mapping)})
        except UncertainWrite as error:
            results.append({"todo": todo["id"], "status": "retryable", "reason": str(error)})
            continue
        except NotionError as error:
            results.append({"todo": todo["id"], "status": "blocked", "reason": str(error)})
            continue
        with writer_lock(library.vault):
            current = read_json(_path(library, todo["id"]))
            current["notion_page_id"] = notion_id(page["id"])
            atomic_json(_path(library, todo["id"]), current)
        results.append({"todo": todo["id"], "status": "created" if created else "adopted", "page_id": current["notion_page_id"]})
    return results


def _text(value):
    kind = (value or {}).get("type")
    return "".join(item.get("plain_text", item.get("text", {}).get("content", "")) for item in (value or {}).get(kind) or [])


def _date(value):
    found = (value or {}).get("date") or None
    return {key: found[key] for key in ("start", "end") if found.get(key)} if found else None


def collect_todos(vault, client, setup):
    library = Library(vault)
    rows = client.query(setup["resources"]["todos"]["data_source_id"])
    mapping = read_json(library._path(MAP)) if library._path(MAP).exists() else {}
    entities = {notion_id(item["page_id"]): entity for entity, item in mapping.items()}
    root = library._path("_todos")
    known = {todo["id"]: todo for todo in (read_json(path) for path in sorted(root.glob("*.json")))} if root.exists() else {}
    by_page = {todo["notion_page_id"]: todo for todo in known.values() if todo.get("notion_page_id")}
    seen, added = set(), []
    with writer_lock(library.vault, wait_seconds=60):
        for row in rows:
            page_id = notion_id(row["id"])
            seen.add(page_id)
            properties = row.get("properties", {})
            record = known.get(_text(properties.get("Todo ID"))) or by_page.get(page_id)
            if record is None:
                created = row.get("created_time") or timestamp()
                record = {"id": "todo_" + page_id.replace("-", "")[:24], "origin": "notion", "source": None,
                          "created_day": str(logical_day(created, local_timezone())), "created_at": created}
                added.append(record["id"])
            due = _date(properties.get("Due"))
            record.update(text=_clean(_text(properties.get("Name"))),
                          status=((properties.get("Status") or {}).get("select") or {}).get("name") or TODO_STATUSES[0],
                          due=(due or {}).get("start"), when=_date(properties.get("When")),
                          entity_ids=sorted(entities[notion_id(item["id"])] for item in (properties.get("Entities") or {}).get("relation", [])
                                            if notion_id(item["id"]) in entities),
                          notion_page_id=page_id, removed=False, observed_at=timestamp())
            atomic_json(_path(library, record["id"]), record)
        removed = [todo["id"] for todo in known.values() if todo.get("notion_page_id") and todo["notion_page_id"] not in seen
                   and not todo.get("removed")]
        for identifier in removed:
            atomic_json(_path(library, identifier), dict(known[identifier], removed=True, observed_at=timestamp()))
    return {"rows": len(rows), "added_by_hand": added, "removed": removed}
