"""Allowlisted Notion acquisition and reviewable workspace setup."""

from pathlib import Path
from datetime import datetime, timezone
import fcntl
import os
import re
from urllib.parse import quote
import uuid

from .notion import API_VERSION, NotionClient, NotionError, UncertainWrite, rich, title
from .storage import Library, atomic_json, digest, read_json, timestamp, writer_lock

SETUP = "_state/notion/setup.json"
NORMALIZER = "notion-blocks/1"


def notion_id(value):
    match = re.search(r"([0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})(?:[?#]|$)", value)
    if not match:
        raise ValueError("A Notion page or data-source UUID is required")
    return str(uuid.UUID(match.group(1)))


def page_url(identifier):
    return "https://www.notion.so/" + notion_id(identifier).replace("-", "")


def config(vault):
    result = read_json(Library(vault)._path(SETUP))
    if result.get("schema_version") != 1:
        raise ValueError("Unsupported Notion setup schema")
    sources = result.get("resources", {})
    for name in ("events", "entities"):
        if not sources.get(name, {}).get("data_source_id"):
            raise ValueError("Notion setup is incomplete: " + name)
    ids = [notion_id(sources[name]["data_source_id"]) for name in ("events", "entities")]
    if len(set(ids)) != 2:
        raise ValueError("Input and machine data sources must be distinct")
    for name, identifier in zip(("events", "entities"), ids):
        sources[name]["data_source_id"] = identifier
    result["workspace_id"] = notion_id(result["workspace_id"])
    return result


def workspace(client, expected=None):
    me = client.request("GET", "/users/me")
    identity = me.get("bot", {}).get("workspace_id")
    if not identity:
        raise NotionError("Notion did not return an authenticated workspace identity")
    if expected and notion_id(identity) != notion_id(expected):
        raise NotionError("Credential workspace does not match the configured workspace")
    return notion_id(identity)


def text_value(items, mentions):
    output = []
    for item in items:
        mention = item.get("mention", {})
        if mention.get("type") == "page":
            target = notion_id(mention["page"]["id"])
            mentions.add(target)
            output.append(item.get("plain_text", "@page") + f" [notion-page:{target}]")
        else:
            content = item.get("plain_text", item.get("text", {}).get("content", ""))
            link = item.get("href") or (item.get("text", {}).get("link") or {}).get("url")
            output.append(f"[{content}]({link})" if link else content)
    return "".join(output)


def properties(client, page, mentions):
    expanded = {}
    for name, original in page.get("properties", {}).items():
        value = dict(original)
        kind = value.get("type")
        if kind in {"title", "rich_text", "relation"} and (value.get("has_more") or len(value.get(kind, [])) >= 25):
            items, cursor = [], None
            while True:
                path = f"/pages/{page['id']}/properties/{quote(value['id'], safe='')}?page_size=100"
                if cursor:
                    path += "&start_cursor=" + quote(cursor, safe="")
                response = client.request("GET", path)
                if response.get("object") != "list":
                    raise NotionError("Expected a paginated page property")
                items.extend(item[kind] for item in response["results"] if kind in item)
                if not response.get("has_more"):
                    break
                advancing = response.get("next_cursor")
                if not advancing or advancing == cursor:
                    raise NotionError("Page property has no advancing cursor")
                cursor = advancing
            value[kind] = items
            value["has_more"] = False
        if kind in {"created_time", "last_edited_time", "created_by", "last_edited_by"}:
            continue
        if kind == "relation":
            for target in value.get("relation", []):
                mentions.add(notion_id(target["id"]))
        if kind == "files":
            expanded[name] = {"type": kind, "files": value.get("files", [])}
        elif kind in {"title", "rich_text"}:
            expanded[name] = {"type": kind, "text": text_value(value.get(kind, []), mentions)}
        else:
            expanded[name] = {"type": kind, "value": value.get(kind)}
    return expanded


def read_page(client, identifier):
    identifier = notion_id(identifier)
    page = client.request("GET", "/pages/" + identifier)
    if page.get("archived") or page.get("in_trash"):
        raise NotionError("Page is explicitly archived; retained local revisions are unchanged")
    mentions, attachments, gaps, blocks, lines = set(), [], [], [], []
    user_properties = properties(client, page, mentions)
    for name, value in user_properties.items():
        if value["type"] != "files":
            continue
        normalized = []
        for index, file in enumerate(value.pop("files")):
            item = {"id": f"property:{name}:{index}", "name": file.get("name", "attachment")}
            try:
                url = file.get(file.get("type", ""), {}).get("url")
                if not url:
                    raise NotionError("Attachment property URL unavailable")
                item["content"] = client.download(url)
            except NotionError as error:
                item.update(status="unavailable", gap=str(error))
                gaps.append({"property": name, "reason": str(error), "continue": "/pages/" + identifier + "/properties"})
            attachments.append(item)
            normalized.append({"id": item["id"], "name": item["name"]})
        value["value"] = normalized
    count = 0
    known = {"paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item",
             "numbered_list_item", "to_do", "toggle", "quote", "callout", "code",
             "divider", "image", "file", "pdf", "audio", "video", "bookmark", "embed",
             "link_preview", "link_to_page", "child_page", "child_database", "table", "table_row",
             "column", "column_list", "synced_block", "breadcrumb", "table_of_contents", "equation"}

    def walk(parent, depth=0):
        nonlocal count
        if depth > 32 or count >= 20000:
            gaps.append({"block_id": parent, "reason": "collection limit", "continue": "/blocks/" + parent + "/children"})
            return
        try:
            children = client.children(parent)
        except NotionError as error:
            gaps.append({"block_id": parent, "reason": str(error), "continue": "/blocks/" + parent + "/children"})
            return
        for block in children:
            count += 1
            blocks.append(block)
            bid, kind = block["id"], block.get("type", "unsupported")
            data = block.get(kind, {})
            words = text_value(data.get("rich_text", []), mentions)
            rendered = words
            if kind.startswith("heading_"):
                rendered = "#" * int(kind[-1]) + " " + words
            elif kind in {"bulleted_list_item", "numbered_list_item"}:
                rendered = ("- " if kind.startswith("bulleted") else "1. ") + words
            elif kind == "to_do":
                rendered = "- [" + ("x" if data.get("checked") else " ") + "] " + words
            elif kind == "code":
                rendered = "```" + data.get("language", "") + "\n" + words + "\n```"
            elif kind == "divider":
                rendered = "---"
            elif kind == "equation":
                rendered = "$$" + data.get("expression", "") + "$$"
            elif kind == "table_row":
                rendered = " | ".join(text_value(cell, mentions) for cell in data.get("cells", []))
            elif kind in {"bookmark", "embed", "link_preview"}:
                rendered = data.get("url", "") + " " + text_value(data.get("caption", []), mentions)
            elif kind == "link_to_page":
                target = data.get(data.get("type"), "")
                rendered = "Referenced page " + str(target)
                if data.get("type") == "page_id":
                    mentions.add(notion_id(target))
            elif kind in {"child_page", "child_database"}:
                rendered = f"[{data.get('title', kind)}]({page_url(bid)}) [child not imported]"
            elif kind in {"image", "file", "pdf", "audio", "video"}:
                item = {"id": bid, "name": data.get("name") or kind}
                url = data.get(data.get("type", ""), {}).get("url")
                try:
                    if not url:
                        raise NotionError("Attachment URL unavailable")
                    item["content"] = client.download(url)
                except NotionError as error:
                    item.update(status="unavailable", gap=str(error))
                    gaps.append({"block_id": bid, "reason": str(error), "continue": "/blocks/" + bid})
                attachments.append(item)
                rendered = f"[{item['name']}] [attachment:{bid}] " + text_value(data.get("caption", []), mentions)
            elif kind not in known:
                gaps.append({"block_id": bid, "reason": "unsupported block " + kind, "continue": "/blocks/" + bid})
                rendered = "[Unparsed " + kind + "]"
            if rendered:
                lines.append(f"<!-- block:{bid} -->\n" + rendered)
            if block.get("has_children") and kind not in {"child_page", "child_database"}:
                walk(bid, depth + 1)

    walk(identifier)
    occurred = next((value["value"].get("start") for name, value in user_properties.items()
                     if name == "Occurred" and value.get("value")), None)
    return {"page": page, "body": "\n\n".join(lines), "mentions": sorted(mentions),
            "attachments": attachments, "semantic": {"normalizer_version": NORMALIZER,
            "properties": {key: value for key, value in user_properties.items() if value["type"] != "title"}},
            "occurred_at": occurred, "raw": {"page": page, "properties": user_properties, "blocks": blocks},
            "coverage": {"status": "partial" if gaps else "complete", "included": ["page", "properties", "blocks"],
                         "gaps": gaps, "continuation": [item["continue"] for item in gaps]}}


def workspace_roots(client):
    roots, cursor = [], None
    while True:
        body = {"page_size": 100, "filter": {"property": "object", "value": "page"}}
        if cursor:
            body["start_cursor"] = cursor
        response = client.request("POST", "/search", body)
        roots += [page for page in response.get("results", []) if page.get("parent", {}).get("type") == "workspace"]
        if not response.get("has_more"):
            return roots
        if not response.get("next_cursor") or response["next_cursor"] == cursor:
            raise NotionError("Search has more results but no advancing cursor")
        cursor = response["next_cursor"]


def collect_watch(client, library, setup, skip):
    excluded = {notion_id(item) for item in setup["watch"].get("exclude", [])} | skip
    machine = {notion_id(setup["resources"][key]["data_source_id"]) for key in ("events", "entities")}
    path = library._path("_state/notion/watch.json")
    known = read_json(path) if path.exists() else {}
    baseline = not known
    queue = [(notion_id(page["id"]), page.get("last_edited_time")) for page in workspace_roots(client)]
    structure, observed, failures = {}, [], []
    while queue:
        identifier, edited = queue.pop(0)
        if identifier in structure or identifier in excluded:
            continue
        cached = known.get(identifier)
        try:
            if edited is None:
                edited = client.request("GET", "/pages/" + identifier).get("last_edited_time")
            if cached and cached["edited"] == edited:
                entry = cached
            else:
                captured = read_page(client, identifier)
                blocks = captured["raw"]["blocks"]
                entry = {"edited": edited,
                         "children": [notion_id(block["id"]) for block in blocks if block.get("type") == "child_page"],
                         "databases": [notion_id(block["id"]) for block in blocks if block.get("type") == "child_database"]}
                envelope = library.record("notion", setup["workspace_id"], identifier, captured["body"],
                    name=title(captured["page"]), input_kind="source_update", authorship="source_observation",
                    occurred_at=captured["occurred_at"], mentions=captured["mentions"], semantic=captured["semantic"],
                    raw=captured["raw"], attachments=captured["attachments"], coverage=captured["coverage"],
                    source_url=captured["page"].get("url", page_url(identifier)), baseline=baseline)
                observed.append({"page_id": identifier, "event_id": envelope["event_id"], "revision": envelope["revision"],
                                 "readiness": envelope["readiness"], "coverage": captured["coverage"]["status"]})
            structure[identifier] = entry
            for database in entry["databases"]:
                for source in client.request("GET", "/databases/" + database).get("data_sources", []):
                    if notion_id(source["id"]) not in machine:
                        queue += [(notion_id(row["id"]), row.get("last_edited_time")) for row in client.query(source["id"])]
            queue += [(child, None) for child in entry["children"]]
        except (NotionError, ValueError) as error:
            failures.append({"page_id": identifier, "status": "unreachable", "reason": str(error)})
            if cached:
                structure[identifier] = cached
    with writer_lock(library.vault):
        atomic_json(path, structure)
    return {"baseline": baseline, "pages": len(structure), "observed": observed, "failures": failures,
            "not_observed": sorted(set(known) - set(structure))}, set(structure)


def notion_links(body):
    found = set()
    for url in re.findall(r"https://(?:www\.|app\.)?notion\.(?:so|com)/[^\s)\]]+", body):
        try:
            found.add(notion_id(url))
        except ValueError:
            continue
    return found


def snapshot_reference(client, library, workspace_id, target, events, inputs):
    result = {"page_id": target, "referenced_by": events}
    try:
        page = client.request("GET", "/pages/" + target)
        parent = page.get("parent", {}).get("data_source_id")
        if parent and notion_id(parent) in inputs:
            return dict(result, status="excluded", reason="Configured input or machine page")
        known = library.reference_record("notion", workspace_id, target)
        if known and known.get("last_edited_time") == page.get("last_edited_time"):
            known = library.cite(known["id"], events)
            return dict(result, status="unchanged", source_id=known["id"], revision=known["revision"],
                        body_path=known["body_path"])
        captured = read_page(client, target)
        stored = library.reference("notion", workspace_id, target, captured["body"], name=title(page),
                                   edited=page.get("last_edited_time"), referenced_by=events, raw=captured["raw"],
                                   attachments=captured["attachments"], coverage=captured["coverage"],
                                   source_url=page.get("url", page_url(target)))
        return dict(result, status="snapshotted" if stored["changed"] else "unchanged", source_id=stored["id"],
                    revision=stored["revision"], body_path=stored["body_path"])
    except NotionError as error:
        return dict(result, status="unavailable", reason=str(error))


def collect(vault, client=None):
    vault, client = Path(vault).resolve(), client or NotionClient()
    setup = config(vault)
    workspace(client, setup["workspace_id"])
    machine_source = notion_id(setup["resources"]["entities"]["data_source_id"])
    mapping_path = Library(vault)._path("_state/notion/entity-map.json")
    mapped = read_json(mapping_path) if mapping_path.exists() else {}
    machine_pages = {notion_id(item["page_id"]) for item in mapped.values()}
    library, observations, failures, seen, cited = Library(vault), [], [], set(), {}
    for source in (notion_id(setup["resources"]["events"]["data_source_id"]),):
        try:
            pages = client.query(source)
        except NotionError as error:
            failures.append({"data_source_id": source, "status": "unreachable", "reason": str(error)})
            continue
        for stub in pages:
            identifier = notion_id(stub["id"])
            seen.add(identifier)
            if identifier in machine_pages:
                failures.append({"page_id": identifier, "status": "excluded_machine_output"})
                continue
            try:
                captured = read_page(client, identifier)
                parent = captured["page"].get("parent", {})
                actual = parent.get("data_source_id")
                if not actual or notion_id(actual) != source:
                    raise NotionError("Page moved out of the configured input data source")
                if actual and notion_id(actual) == machine_source:
                    raise NotionError("Machine snapshots cannot be collected as input")
                envelope = library.record("notion", setup["workspace_id"], identifier, captured["body"],
                    name=title(captured["page"]), input_kind="event",
                    occurred_at=captured["occurred_at"], authorship="unknown",
                    mentions=captured["mentions"], semantic=captured["semantic"], raw=captured["raw"],
                    attachments=captured["attachments"], coverage=captured["coverage"],
                    source_url=captured["page"].get("url", page_url(identifier)))
                observations.append({"event_id": envelope["event_id"], "revision": envelope["revision"],
                                     "page_id": identifier, "coverage": captured["coverage"]})
                for target in set(captured["mentions"]) | notion_links(captured["body"]):
                    cited.setdefault(target, set()).add(envelope["event_id"])
            except (NotionError, ValueError) as error:
                failures.append({"page_id": identifier, "status": "unreachable_or_moved", "reason": str(error)})
    inputs = {notion_id(item["data_source_id"]) for key, item in setup["resources"].items()
              if key in {"events", "entities"}}
    skip = seen | machine_pages | {notion_id(setup["resources"][key]["page_id"])
                                   for key in ("main", "entities_page") if key in setup["resources"]}
    watch, watched = collect_watch(client, library, setup, skip) if "watch" in setup else (None, set())
    references = [snapshot_reference(client, library, setup["workspace_id"], target, sorted(events), inputs)
                  for target, events in sorted(cited.items()) if target not in skip | watched]
    state_path = library._path("_state/notion/acquisition.json")
    with writer_lock(vault):
        previous = read_json(state_path) if state_path.exists() else {}
        previously_seen = set(previous.get("known_page_ids", []))
        report = {"schema_version": 1, "checked_at": timestamp(), "observations": observations,
                  "failures": failures, "not_observed": sorted(previously_seen - seen),
                  "known_page_ids": sorted(previously_seen | seen), "references": references, "watch": watch}
        atomic_json(state_path, report)
    report["pending"] = library.pending()
    return report


def source_open(vault, reference, mode="cache", revision=None, client=None):
    if mode not in {"cache", "historical", "if-stale", "live"}:
        raise ValueError("Unknown source policy")
    vault = Path(vault).resolve()
    library = Library(vault)
    source = None
    for path in sorted(library._path("_events").glob("*/event.json")):
        path = library._path(path.relative_to(vault))
        event = read_json(path)
        if reference in {event["event_id"], event["source_id"], event["identity"]["resource_id"], event.get("source_url")}:
            source = event
            break
    if source is None:
        return {"status": "not_cached", "reference": reference, "mode": mode}
    checks_path = library._path("_state/notion/checks.json")
    checks = read_json(checks_path) if checks_path.exists() else {}
    checked_at = checks.get(source["identity"]["resource_id"], source["collected_at"])
    acquisition_path = library._path("_state/notion/acquisition.json")
    if acquisition_path.exists():
        acquisition = read_json(acquisition_path)
        if any(item.get("event_id") == source["event_id"] for item in acquisition.get("observations", [])):
            checked_at = max(checked_at, acquisition["checked_at"])
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(checked_at.replace("Z", "+00:00"))).total_seconds()
    if mode == "if-stale" and 0 <= age < 300:
        return {"status": "cached", "mode": mode, "source": source, "freshness": "fresh",
                "body_path": str(library._path(source["body_path"])), "coverage": source["coverage"]}
    if mode in {"live", "if-stale"}:
        if source["identity"]["provider"] != "notion":
            return {"status": "unsupported_refresh", "source": source, "mode": mode}
        setup = config(vault)
        client = client or NotionClient()
        workspace(client, setup["workspace_id"])
        try:
            captured = read_page(client, source["identity"]["resource_id"])
            parent = captured["page"].get("parent", {})
            allowed = {item["data_source_id"] for key, item in setup["resources"].items() if key == "events"}
            actual = parent.get("data_source_id")
            if not actual or notion_id(actual) not in allowed:
                raise NotionError("Source is outside the configured input collections")
            source = library.record(**source["identity"], body=captured["body"], name=title(captured["page"]),
                input_kind=source["input_kind"], occurred_at=captured["occurred_at"], authorship=source["authorship"],
                mentions=captured["mentions"], semantic=captured["semantic"], raw=captured["raw"],
                attachments=captured["attachments"], coverage=captured["coverage"], source_url=source.get("source_url"))
            with writer_lock(vault):
                checks = read_json(checks_path) if checks_path.exists() else {}
                checks[source["identity"]["resource_id"]] = timestamp()
                atomic_json(checks_path, checks)
        except NotionError as error:
            return {"status": "unreachable", "mode": mode, "cached_source": source, "reason": str(error)}
    if mode == "historical":
        if revision is None:
            raise ValueError("Historical reads require an explicit revision")
        path = library._path(f"_events/{source['event_id']}/revisions/{int(revision)}/event.json")
        if not path.is_file():
            return {"status": "revision_not_cached", "mode": mode, "revision": revision}
        source = read_json(path)
    return {"status": "cached", "mode": mode, "source": source,
            "body_path": str(library._path(source["body_path"])), "coverage": source["coverage"]}


def setup_plan(parent=None, *, main=None):
    if (parent is None) == (main is None):
        raise ValueError("Choose exactly one Notion --parent or --main page")
    target = {"kind": "existing_main" if main is not None else "create_main_under",
              "page_id": notion_id(main if main is not None else parent)}
    return {"target": target, "api_version": API_VERSION,
            "pages": ["Entities"] if main is not None else ["MyLibrary", "Entities"],
            "collections": ["Events", "Pages", "Entities"],
            "views": ["Recent Events", "Entities"],
            "ui_required": ["Native New Event button creates and opens an Events page", "Move Recent Events into right column",
                            "Full width and side peek", "Phone order and offline New", "Entity page lock and permissions"]}


def setup(vault, parent=None, dry_run=False, client=None, *, main=None):
    plan = setup_plan(parent, main=main)
    if dry_run:
        return dict(plan, status="dry_run", remote_writes=0)
    vault = Path(vault).resolve()
    lock_path = Library(vault)._path("_state/notion/setup.lock")
    with writer_lock(vault, wait_seconds=30):
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _setup(vault, plan, client=client)
    finally:
        os.close(descriptor)


def _setup(vault, plan, client=None):
    vault, client = Path(vault).resolve(), client or NotionClient()
    authenticated = workspace(client)
    target = plan["target"]
    target_page = client.request("GET", "/pages/" + target["page_id"])
    if (not target_page or notion_id(target_page.get("id", "")) != target["page_id"]
            or target_page.get("archived") or target_page.get("in_trash")):
        raise NotionError("Selected Notion page is unavailable or archived")
    if target["kind"] == "existing_main" and title(target_page) != "MyLibrary":
        raise NotionError("Existing Main page must be titled MyLibrary")
    path = Library(vault)._path(SETUP)
    with writer_lock(vault, wait_seconds=30):
        state = read_json(path) if path.exists() else {"schema_version": 1, "workspace_id": authenticated,
                "target": target, "api_version": API_VERSION, "resources": {}, "operations": {}}
        recorded_target = state.get("target") or {"kind": "create_main_under", "page_id": state.get("parent_page_id")}
        if state["workspace_id"] != authenticated or recorded_target != target:
            raise ValueError("Existing setup belongs to another workspace or target")
        state["target"] = target
        atomic_json(path, state)

    def create(key, endpoint, payload, method="POST"):
        with writer_lock(vault, wait_seconds=30):
            state.update(read_json(path))
            prior = state["operations"].get(key)
            if prior:
                if prior["status"] == "done":
                    return prior["result"]
        result = None
        if endpoint in {"/pages", "/databases"}:
            parent_id = payload["parent"]["page_id"]
            expected = (payload["properties"]["title"]["title"][0]["text"]["content"]
                        if endpoint == "/pages" else payload["title"][0]["text"]["content"])
            kind = "child_page" if endpoint == "/pages" else "child_database"
            candidates = [block for block in client.children(parent_id)
                          if block.get("type") == kind and block[kind].get("title") == expected]
            if len(candidates) > 1:
                raise NotionError("Multiple scoped setup resources match " + key)
            if candidates:
                raise NotionError("Existing scoped child needs explicit adoption: " + key)
            elif prior and prior["status"] != "not_created":
                raise UncertainWrite("Lost setup create has no scoped match; creation was not repeated: " + key)
        elif prior:
            raise UncertainWrite("Setup operation needs scoped reconciliation before retry: " + key)
        if result is not None:
            with writer_lock(vault, wait_seconds=30):
                state.update(read_json(path))
                state["operations"][key] = {"status": "done", "method": method, "endpoint": endpoint,
                                            "payload": payload, "result": result, "adopted_at": timestamp()}
                atomic_json(path, state)
            return result
        with writer_lock(vault, wait_seconds=30):
            state.update(read_json(path))
            state["operations"][key] = {"status": "uncertain", "method": method, "endpoint": endpoint,
                                        "payload": payload, "prepared_at": timestamp()}
            atomic_json(path, state)
        try:
            result = client.request(method, endpoint, payload)
        except UncertainWrite:
            raise
        except NotionError:
            with writer_lock(vault, wait_seconds=30):
                state.update(read_json(path))
                state["operations"][key]["status"] = "not_created"
                atomic_json(path, state)
            raise
        with writer_lock(vault, wait_seconds=30):
            state.update(read_json(path))
            state["operations"][key].update(status="done", result=result)
            atomic_json(path, state)
        return result

    if target["kind"] == "existing_main":
        main = {"id": target["page_id"], "url": target_page.get("url", page_url(target["page_id"]))}
        with writer_lock(vault, wait_seconds=30):
            state.update(read_json(path))
            prior = state["operations"].get("main")
            if prior and (prior.get("status") != "done" or prior.get("result", {}).get("id") != main["id"]):
                raise NotionError("Existing Main adoption conflicts with setup journal")
            state["operations"]["main"] = prior or {"status": "done", "mode": "adopted",
                                                       "result": main, "adopted_at": timestamp()}
            atomic_json(path, state)
    else:
        main = create("main", "/pages", {"parent": {"type": "page_id", "page_id": target["page_id"]},
                        "properties": {"title": {"type": "title", "title": [rich("MyLibrary")]}},
                        "icon": {"type": "emoji", "emoji": "📚"}})
    main_id = main["id"]
    current_main = client.request("GET", "/pages/" + main_id)
    actual_parent = current_main.get("parent", {}).get("page_id")
    if (current_main.get("archived") or current_main.get("in_trash")
            or (target["kind"] == "create_main_under"
                and (not actual_parent or notion_id(actual_parent) != target["page_id"]))):
        raise NotionError("Existing Main page is outside the selected parent or archived")
    entities_page = create("entities_page", "/pages", {"parent": {"type": "page_id", "page_id": main_id},
                          "properties": {"title": {"type": "title", "title": [rich("Entities")]}}})
    basics = {"Name": {"type": "title", "title": {}}, "Created": {"type": "created_time", "created_time": {}},
              "Edited": {"type": "last_edited_time", "last_edited_time": {}}}
    schemas = {"events": dict(basics, Occurred={"type": "date", "date": {}}),
               "entities": {"Name": basics["Name"], "Entity ID": {"type": "rich_text", "rich_text": {}},
                            "Description": {"type": "rich_text", "rich_text": {}}, "Type": {"type": "select", "select": {}},
                            "Published Revision": {"type": "number", "number": {}}, "Published At": {"type": "date", "date": {}},
                            "Event Count": {"type": "number", "number": {}}, "Last Event": {"type": "date", "date": {}},
                            "Tags": {"type": "multi_select", "multi_select": {}}, "State": {"type": "select", "select": {}},
                            "Days Idle": {"type": "formula", "formula": {"expression": 'dateBetween(now(), prop("Last Event"), "days")'}}}}
    for name, schema in schemas.items():
        database = create(name, "/databases", {"parent": {"type": "page_id", "page_id": main_id},
                         "title": [rich(name.title())], "is_inline": False, "initial_data_source": {"properties": schema}})
        data_sources = database.get("data_sources", [])
        if len(data_sources) != 1:
            raise NotionError("New database did not return one data source")
        source = client.request("GET", "/data_sources/" + data_sources[0]["id"])
        missing = {label: value for label, value in schema.items() if label not in source.get("properties", {})}
        if missing:
            client.request("PATCH", "/data_sources/" + source["id"], {"properties": missing})
            source = client.request("GET", "/data_sources/" + source["id"])
        for label, expected in schema.items():
            if source.get("properties", {}).get(label, {}).get("type") != expected["type"]:
                raise NotionError("Existing setup data source schema differs: " + name + "/" + label)
        with writer_lock(vault, wait_seconds=30):
            state.update(read_json(path))
            state["resources"][name] = {"database_id": database["id"], "data_source_id": source["id"],
                                        "properties": {label: value["id"] for label, value in source["properties"].items()},
                                        "url": page_url(database["id"])}
            state["resources"]["main"] = {"page_id": main_id, "url": main.get("url", page_url(main_id))}
            state["resources"]["entities_page"] = {"page_id": entities_page["id"], "url": entities_page.get("url", page_url(entities_page["id"]))}
            atomic_json(path, state)
    for name, view_name in (("events", "Recent Events"), ("entities", "Entities")):
        resource = state["resources"][name]
        visible = {"Name", "Created"} if name == "events" else {"Name", "Description", "Type"}
        payload = {"data_source_id": resource["data_source_id"], "name": view_name, "type": "list",
                   "create_database": {"parent": {"type": "page_id", "page_id": entities_page["id"] if name == "entities" else main_id}},
                   "configuration": {"type": "list", "properties": [{"property_id": pid, "visible": label in visible}
                                                for label, pid in resource["properties"].items()]}}
        if name == "events":
            payload["sorts"] = [{"property": resource["properties"]["Created"], "direction": "descending"}]
        view = create("view_" + name, "/views", payload)
        with writer_lock(vault, wait_seconds=30):
            state.update(read_json(path))
            state["resources"][name]["view_id"] = view["id"]
            atomic_json(path, state)
    events, entities = state["resources"]["events"], state["resources"]["entities"]
    charts = {"events_this_week": (events, "Events this week", {"chart_type": "number", "value": {"aggregator": "count"}},
                                   {"timestamp": "created_time", "created_time": {"this_week": {}}}),
              "events_per_week": (events, "Events per week", {"chart_type": "column", "y_axis": {"aggregator": "count"},
                                  "x_axis": {"type": "created_time", "property_id": events["properties"]["Created"],
                                             "group_by": "week", "start_day_of_week": 1, "sort": {"type": "ascending"}}}, None),
              "entities_active": (entities, "Most active Entities", {"chart_type": "bar", "x_axis_property_id": "title",
                                  "y_axis_property_id": entities["properties"]["Event Count"], "sort": "y_descending"},
                                  {"property": "Event Count", "number": {"greater_than": 0}}),
              "entities_by_type": (entities, "Entities by Type", {"chart_type": "donut", "y_axis": {"aggregator": "count"},
                                   "x_axis": {"type": "select", "property_id": entities["properties"]["Type"],
                                              "sort": {"type": "ascending"}}}, None)}
    for key, (resource, chart_name, configuration, chart_filter) in charts.items():
        payload = {"data_source_id": resource["data_source_id"], "name": chart_name, "type": "chart",
                   "create_database": {"parent": {"type": "page_id", "page_id": entities_page["id"]}},
                   "configuration": dict(configuration, type="chart")}
        if chart_filter:
            payload["filter"] = chart_filter
        create("chart_" + key, "/views", payload)
    block = lambda kind, words: {"object": "block", "type": kind, kind: {"rich_text": [rich(words)]}}
    children = [block("heading_1", "New Event"), block("paragraph", "写下一条想法、进展或决定。无需填写项目。"),
                {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [rich("打开 Events →", state["resources"]["events"]["url"])]}},
                {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [rich("Entities →", state["resources"]["entities_page"]["url"])]}},
                block("paragraph", "这里只收取 Events。主页布局中的文字不会自动成为记录。")]
    create("main_layout", f"/blocks/{main_id}/children", {"children": children}, method="PATCH")
    with writer_lock(vault, wait_seconds=30):
        state.update(read_json(path))
        state["status"] = "api_ready_needs_ui"
        state.setdefault("ui_required", plan["ui_required"])
        atomic_json(path, state)
    return state
