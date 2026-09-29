"""Fixed Entity pages, isolated publication retries and human-edit preflight."""

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re

from .catalog import parse_entity
from .notion import NotionClient, NotionError, UncertainWrite, rich
from .storage import Library, atomic_json, digest, read_json, timestamp, writer_lock
from .sync import config, notion_id, page_url, workspace

MAP = "_state/notion/entity-map.json"


def canonical_markdown(value):
    value = re.sub(r"<!--.*?-->", "", value, flags=re.S)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(line.rstrip() for line in value.replace("\r\n", "\n").splitlines())).strip()


def _text(markdown):
    markdown = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", markdown)
    return re.sub(r"[\s*`\\]", "", markdown)


def _value(page, label):
    property = page.get("properties", {}).get(label, {})
    kind = property.get("type")
    if kind in {"title", "rich_text"}:
        return "".join(item.get("plain_text", item.get("text", {}).get("content", "")) for item in property.get(kind, []))
    if kind == "select":
        return (property.get("select") or {}).get("name")
    return property.get(kind)


def _properties(page):
    return {label: _value(page, label) for label in ("Name", "Entity ID", "Description", "Type", "Published Revision")}


def _chunks(value):
    return [rich(value[index:index + 2000]) for index in range(0, len(value), 2000)] or [rich("")]


def render(vault, metadata, body, mappings):
    vault = Path(vault).resolve()
    library = Library(vault)
    by_name = {}
    for path in sorted((vault / "_entities").glob("*.md")):
        if path.name.startswith("_"):
            continue
        path = library._formal_path(path.relative_to(vault))
        fields, _ = parse_entity(path)
        target = mappings.get(fields.get("id"))
        aliases = fields.get("aliases", [])
        aliases = [aliases] if isinstance(aliases, str) else aliases or []
        for name in [path.stem, fields.get("name", path.stem), *aliases]:
            by_name.setdefault(str(name).casefold(), []).append(target)

    def link(match):
        target, separator, display = match.group(1).partition("|")
        label = display if separator else target
        resource, _, anchor = target.partition("#")
        matches = by_name.get(resource.casefold(), [])
        if len(matches) == 1 and matches[0]:
            return f"[{label}]({page_url(matches[0]['page_id'])})"
        local = vault / resource
        if resource.startswith("_events/") and ".." not in Path(resource).parts and local.is_file():
            local = library._path(resource)
            parent = local.parent
            event_path = parent / "event.json"
            if event_path.is_file():
                original = read_json(event_path).get("source_url")
                if original and original.startswith("https://"):
                    return f"[{label}]({original})"
        return ("`" + label + "`" if "/" in label or "." in label else label) + "（仅本地可用）"

    sections = {}
    for match in re.finditer(r"^## (Summary|Context|Relations|Access)\s*\n(.*?)(?=^## |\Z)", body, re.M | re.S):
        sections[match.group(1)] = match.group(2).strip()
    context = sections.get("Context", "")
    entries = re.split(r"(?=^- )", context, flags=re.M)
    if len(entries) > 9:
        context = "".join(entries[:9]) + "\n\n更早的 Context 仅本地可用。"
    result = "## Description\n\n" + str(metadata["description"]) + "\n\n"
    for label in ("Summary", "Context", "Relations", "Access"):
        result += "## " + label + "\n\n" + (context if label == "Context" else sections.get(label, "")) + "\n\n"
    result = re.sub(r"\[\[([^\]]+)\]\]", link, result)
    result = re.sub(r"\[[^\]]*\]\((?:file://|/Users/|/private/)[^)]*\)", "仅本地可用", result)
    result += "本地 Entity ID `" + metadata["id"] + "`。\n"
    return canonical_markdown(result)


@contextmanager
def _entity_lock(vault, entity_id):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", entity_id):
        raise ValueError("Invalid Entity ID")
    directory = Library(vault)._path("_state/notion/publication")
    with writer_lock(vault, wait_seconds=30):
        directory.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(directory / (entity_id + ".lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(descriptor)


def _read_remote(client, identifier, source, entity_id):
    page = client.request("GET", "/pages/" + identifier)
    parent = page.get("parent", {})
    if (parent.get("data_source_id") != source or page.get("archived") or page.get("in_trash")
            or _value(page, "Entity ID") != entity_id):
        raise NotionError("Mapped page no longer identifies this machine Entity in its data source")
    markdown = client.request("GET", "/pages/" + identifier + "/markdown")
    if markdown.get("truncated") or markdown.get("unknown_block_ids"):
        raise NotionError("Cannot verify a partial machine-page readback")
    body = canonical_markdown(markdown["markdown"])
    return page, body, digest(body), digest(json.dumps(_properties(page), sort_keys=True, ensure_ascii=False))


def publish_one(vault, path, client, setup):
    vault, path = Path(vault).resolve(), Path(path)
    if not path.is_symlink():
        path = path.resolve()
    library = Library(vault)
    path = library._formal_path(path.relative_to(vault))
    metadata, body = parse_entity(path)
    for field in ("id", "name", "type", "description", "revision"):
        if not metadata.get(field):
            raise ValueError("Entity requires migration before publication: " + field)
    entity_id = metadata["id"]
    with _entity_lock(vault, entity_id):
        map_path = library._path(MAP)
        mappings = read_json(map_path) if map_path.exists() else {}
        source = setup["resources"]["entities"]["data_source_id"]
        ledger_path = library._path("_state/notion/publication/" + entity_id + ".json")
        ledger = read_json(ledger_path) if ledger_path.exists() else {}
        markdown = render(vault, metadata, body, mappings)
        wanted = {"Name": metadata["name"], "Entity ID": entity_id, "Description": metadata["description"],
                  "Type": metadata["type"], "Published Revision": metadata["revision"]}
        initial_properties_hash = digest(json.dumps(dict(wanted, **{"Published Revision": None}),
                                                  sort_keys=True, ensure_ascii=False))
        wanted_properties_hash = digest(json.dumps(wanted, sort_keys=True, ensure_ascii=False))
        payload_hash = digest(json.dumps({"markdown": markdown, "properties": wanted}, sort_keys=True, ensure_ascii=False))
        mapped = mappings.get(entity_id)
        if mapped and (mapped.get("workspace_id") != setup["workspace_id"] or mapped.get("data_source_id") != source):
            raise NotionError("Entity mapping belongs to another workspace or data source")

        def save(**values):
            nonlocal ledger
            ledger = dict(ledger, entity_id=entity_id, checked_at=timestamp(), **values)
            with writer_lock(vault, wait_seconds=30):
                atomic_json(ledger_path, ledger)
            return ledger

        matches = client.query(source, {"property": "Entity ID", "rich_text": {"equals": entity_id}})
        if len(matches) > 1:
            return save(status="needs_review", reason="Multiple machine pages have this Entity ID", matches=[p["id"] for p in matches])
        if mapped:
            identifier = mapped["page_id"]
            if not matches or notion_id(matches[0]["id"]) != notion_id(identifier):
                return save(status="needs_review", reason="Mapping and exact ID query disagree")
        elif matches:
            identifier = matches[0]["id"]
            if ledger.get("create_state") not in {"uncertain", "created"}:
                return save(status="needs_review", reason="Unmapped page requires explicit adoption", candidate_page_id=identifier)
        else:
            if ledger.get("create_state") == "uncertain":
                return save(status="uncertain", reason="Lost create response still has no exact ID match; creation was not repeated")
            basic = {"Name": {"title": _chunks(wanted["Name"])}, "Entity ID": {"rich_text": _chunks(entity_id)},
                     "Description": {"rich_text": _chunks(wanted["Description"])}, "Type": {"select": {"name": wanted["Type"]}}}
            save(status="pending", create_state="uncertain", target_hash=payload_hash,
                 initial_properties_sha256=initial_properties_hash, local_sha256=digest(path))
            try:
                created = client.request("POST", "/pages", {"parent": {"type": "data_source_id", "data_source_id": source}, "properties": basic})
            except UncertainWrite:
                return save(status="uncertain", reason="Create response unavailable; retry will reconcile exact Entity ID")
            except NotionError as error:
                return save(status="blocked", create_state="not_created", reason=str(error))
            identifier = created["id"]
            save(create_state="created", page_id=identifier)
        if not mapped:
            with writer_lock(vault, wait_seconds=30):
                mappings = read_json(map_path) if map_path.exists() else {}
                if entity_id in mappings and mappings[entity_id]["page_id"] != identifier:
                    raise NotionError("Concurrent Entity mapping conflict")
                mappings[entity_id] = {"page_id": identifier, "workspace_id": setup["workspace_id"], "data_source_id": source}
                atomic_json(map_path, mappings)
        page, remote_body, remote_hash, property_hash = _read_remote(client, identifier, source, entity_id)
        previous_remote = ledger.get("remote_sha256")
        previous_properties = ledger.get("properties_sha256")
        pending_body = ledger.get("desired_markdown")
        ours = remote_hash == previous_remote or _text(remote_body) in {_text(markdown), _text(pending_body or markdown)}
        acceptable_properties = {previous_properties, ledger.get("initial_properties_sha256"), wanted_properties_hash}
        initial_empty_body = (not remote_body and not pending_body
                              and ledger.get("create_state") in {"created", "uncertain"})
        if (not ours and not initial_empty_body) or property_hash not in acceptable_properties:
            with writer_lock(vault, wait_seconds=30):
                conflict = library._path("_state/notion/conflicts/" + entity_id + "-" + timestamp().replace(":", "") + ".json")
                atomic_json(conflict, {"page_id": identifier, "markdown": remote_body, "properties": _properties(page),
                                       "expected_remote_sha256": previous_remote, "local_sha256": digest(path)})
            return save(status="needs_review", reason="Machine page contains a human or unrecognized edit", conflict_path=str(conflict))
        if ledger.get("target_hash") == payload_hash and ledger.get("status") == "published" and remote_hash == previous_remote and _properties(page) == wanted:
            return dict(ledger, status="unchanged")
        local_sha = digest(path)
        intent = {"schema_version": 1, "entity_id": entity_id, "page_id": identifier, "target_hash": payload_hash,
                  "local_path": str(path.relative_to(vault)), "local_sha256": local_sha, "revision": metadata["revision"],
                  "markdown": markdown, "properties": wanted, "before_remote_sha256": remote_hash,
                  "before_properties_sha256": property_hash,
                  "prepared_at": timestamp()}
        intent_path = library._path("_state/notion/publication/intents/" + entity_id + "-" + payload_hash + ".json")
        with writer_lock(vault, wait_seconds=30):
            if not intent_path.exists():
                atomic_json(intent_path, intent)
        save(status="pending", page_id=identifier, target_hash=payload_hash, local_sha256=local_sha,
             desired_markdown=markdown, intent_path=str(intent_path.relative_to(vault)))
        try:
            if _text(remote_body) != _text(markdown):
                response = client.request("PATCH", "/pages/" + identifier + "/markdown",
                      {"type": "replace_content", "replace_content": {"new_str": markdown}, "allow_async": False})
                if response.get("object") == "async_task":
                    return save(status="pending_async", reason="Await readback; asynchronous acceptance is not completion")
            _, readback_body, _, _ = _read_remote(client, identifier, source, entity_id)
            if _text(readback_body) != _text(markdown):
                return save(status="needs_review", reason="Readback differs from the desired snapshot", observed_markdown=readback_body)
            published_at = timestamp()
            properties = {"Name": {"title": _chunks(wanted["Name"])}, "Entity ID": {"rich_text": _chunks(entity_id)},
                          "Description": {"rich_text": _chunks(wanted["Description"])}, "Type": {"select": {"name": wanted["Type"]}},
                          "Published Revision": {"number": wanted["Published Revision"]}, "Published At": {"date": {"start": published_at}}}
            client.request("PATCH", "/pages/" + identifier, {"properties": properties})
            checked, checked_body, remote_hash, property_hash = _read_remote(client, identifier, source, entity_id)
            if checked_body != readback_body or _properties(checked) != wanted or not _value(checked, "Published At"):
                return save(status="needs_review", reason="Final body/property verification failed")
            return save(status="published", published_at=published_at, published_revision=metadata["revision"],
                        remote_sha256=remote_hash, properties_sha256=property_hash, reason="Verified body and properties",
                        local_changed_during_publish=(digest(path) != local_sha))
        except (UncertainWrite, NotionError) as error:
            return save(status="retryable", reason=str(error))


def publish(vault, entity_ids=None, client=None):
    vault, client = Path(vault).resolve(), client or NotionClient()
    setup = config(vault)
    workspace(client, setup["workspace_id"])
    results, identities = [], set()
    selected = None if entity_ids is None else set(entity_ids)
    paths = []
    for path in sorted((vault / "_entities").glob("*.md")):
        if path.name.startswith("_"):
            continue
        path = Library(vault)._formal_path(path.relative_to(vault))
        metadata, _ = parse_entity(path)
        identity = metadata.get("id")
        if identity and identity in identities:
            raise ValueError("Duplicate local Entity ID: " + identity)
        identities.add(identity) if identity else None
        if identity and (selected is None or identity in selected):
            paths.append(path)
    missing = set(selected or ()) - identities
    if missing:
        raise ValueError("Requested Entity IDs not found: " + ", ".join(sorted(missing)))
    for path in paths:
        try:
            results.append(publish_one(vault, path, client, setup))
        except (ValueError, NotionError, BlockingIOError) as error:
            results.append({"path": str(path.relative_to(vault)), "status": "blocked", "reason": str(error)})
    report = {"checked_at": timestamp(), "results": results}
    with writer_lock(vault, wait_seconds=30):
        atomic_json(Library(vault)._path("_state/notion/last-publish.json"), report)
    return report
