"""Rebuildable Entity catalog, exact identity resolution, and typed graph reads."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import unicodedata
from urllib.parse import unquote, urlparse

import yaml


SCHEMA_VERSION = 2
ENTITY_INDEX = Path("_index/entities.json")
EDGE_INDEX = Path("_index/edges.json")
NOTION_ENTITY_MAP = Path("_state/notion/entity-map.json")
RELATION = re.compile(r"^\s*-\s*([A-Za-z0-9][A-Za-z0-9_-]*)\s*::\s*(.*?)\s*$")
WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
NOTION_UUID = re.compile(
    r"(?<![0-9a-fA-F])([0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})(?![0-9a-fA-F])"
)


class CatalogError(ValueError):
    pass


class CatalogAmbiguityError(CatalogError):
    pass


class CatalogNotFoundError(CatalogError):
    pass


def parse_entity(path: Path) -> tuple[dict, str]:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].lstrip("\ufeff").strip() != "---":
        return {}, text
    closing = next((index for index, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if closing is None:
        raise CatalogError(f"Unclosed frontmatter: {path}")
    try:
        metadata = yaml.safe_load("".join(lines[1:closing])) or {}
    except yaml.YAMLError as error:
        raise CatalogError(f"Invalid frontmatter: {path}: {error}") from error
    if not isinstance(metadata, dict):
        raise CatalogError(f"Entity frontmatter must be a mapping: {path}")
    return metadata, "".join(lines[closing + 1:])


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _strings(value) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        values = list(value)
    else:
        values = []
    result = []
    for item in values:
        if isinstance(item, str) and item.strip() and item.strip() not in result:
            result.append(item.strip())
    return result


def _section(body: str, name: str) -> str:
    match = re.search(r"^##[ \t]+" + re.escape(name) + r"[ \t]*\r?\n(.*?)(?=^##[ \t]+|\Z)",
                      body, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""


def _heading_name(body: str, fallback: str) -> str:
    match = re.search(r"^#[ \t]+([^#\r\n].*?)\s*$", body, re.MULTILINE)
    return match.group(1).strip() if match else fallback


def _summary(body: str) -> str:
    value = _section(body, "Summary")
    return value[:2000]


def _clean_reference(reference: str) -> str:
    value = str(reference).strip()
    if value.startswith("[[") and value.endswith("]]"):
        value = value[2:-2]
    if "|" in value and not value.startswith(("http://", "https://")):
        value = value.split("|", 1)[0]
    if "#" in value and not value.startswith(("http://", "https://")):
        value = value.split("#", 1)[0]
    return value.strip()


def _notion_key(reference: str) -> str:
    value = _clean_reference(reference)
    parsed = urlparse(value)
    candidate = unquote(parsed.path.rsplit("/", 1)[-1]) if parsed.scheme else value
    compact = candidate.replace("-", "")
    if re.fullmatch(r"[0-9a-fA-F]{32}", compact):
        return compact.lower()
    match = NOTION_UUID.search(candidate)
    return match.group(1).replace("-", "").lower() if match else _normalize(value)


def _wikilink_key(reference: str) -> str:
    value = _clean_reference(reference)
    if value.casefold().endswith(".md"):
        value = value[:-3]
    return _normalize(value)


def _relations(body: str) -> list[dict]:
    result = []
    for line in _section(body, "Relations").splitlines():
        match = RELATION.match(line)
        if not match:
            continue
        predicate = match.group(1).casefold()
        for link in WIKILINK.findall(match.group(2)):
            target = _clean_reference(link)
            if target:
                result.append({"predicate": predicate, "target_reference": target})
    return result


def _entity_paths(vault: Path) -> list[Path]:
    root = vault / "_entities"
    if not root.is_dir():
        return []
    result = []
    for path in root.rglob("*.md"):
        relative = path.relative_to(root)
        if (not path.is_file() or path.is_symlink()
                or any(part == "_private" or part == "META" or part.startswith(("_", "."))
                       for part in relative.parts)):
            continue
        result.append(path)
    return sorted(result, key=lambda item: item.relative_to(vault).as_posix())


def _mapping_paths(vault: Path) -> list[Path]:
    path = vault / NOTION_ENTITY_MAP
    return [path] if path.is_file() and not path.is_symlink() else []


def _snapshot(vault: Path) -> dict:
    files = {}
    for path in _entity_paths(vault) + _mapping_paths(vault):
        files[path.relative_to(vault).as_posix()] = _sha256(path.read_bytes())
    return {"files": files, "source_digest": _sha256(_canonical(files))}


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _load_cached(vault: Path, snapshot: dict) -> dict | None:
    try:
        entities = json.loads((vault / ENTITY_INDEX).read_text(encoding="utf-8"))
        edges = json.loads((vault / EDGE_INDEX).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (entities.get("schema_version") != SCHEMA_VERSION
            or edges.get("schema_version") != SCHEMA_VERSION
            or entities.get("source_digest") != snapshot["source_digest"]
            or edges.get("source_digest") != snapshot["source_digest"]):
        return None
    try:
        return _combine(entities, edges)
    except (KeyError, TypeError):
        return None


def _mapping(path: Path) -> list[tuple[str, dict]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CatalogError(f"Invalid Notion mapping: {path}: {error}") from error
    if not isinstance(value, dict):
        raise CatalogError(f"Notion mapping must be an object: {path}")
    result = []
    for entity_id, mapping in sorted(value.items()):
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise CatalogError(f"Notion mapping has an invalid local Entity ID: {path}")
        if not isinstance(mapping, dict):
            raise CatalogError(f"Notion mapping for {entity_id!r} must be an object: {path}")
        normalized = {}
        for field in ("page_id", "workspace_id", "data_source_id"):
            field_value = mapping.get(field)
            if not isinstance(field_value, str) or not field_value.strip():
                raise CatalogError(f"Notion mapping for {entity_id!r} lacks {field}: {path}")
            normalized[field] = field_value.strip()
        result.append((entity_id.strip(), normalized))
    return result


def _candidate_paths(index: dict, reference: str) -> tuple[str | None, list[str]]:
    cleaned = _clean_reference(reference)
    if cleaned in index["id_lookup"]:
        return "stable_id", index["id_lookup"][cleaned]
    notion = _notion_key(cleaned)
    if notion in index["notion_lookup"]:
        return "notion_page_id", index["notion_lookup"][notion]
    normalized = _normalize(cleaned)
    if normalized in index["name_lookup"]:
        return "name_or_alias", index["name_lookup"][normalized]
    wikilink = _wikilink_key(cleaned)
    if wikilink in index["wikilink_lookup"]:
        return "wikilink", index["wikilink_lookup"][wikilink]
    if cleaned.startswith("legacy:"):
        path = cleaned[len("legacy:"):]
        if any(item["path"] == path and item["legacy"] for item in index["entities"]):
            return "legacy_key", [path]
    return None, []


def _compile(vault: Path, snapshot: dict) -> dict:
    records = []
    diagnostics = []
    for path in _entity_paths(vault):
        relative = path.relative_to(vault).as_posix()
        try:
            metadata, body = parse_entity(path)
        except CatalogError as error:
            diagnostics.append({"code": "invalid_entity", "path": relative, "detail": str(error)})
            continue
        stable_id = metadata.get("id")
        if stable_id is not None and (not isinstance(stable_id, str) or not stable_id.strip()):
            diagnostics.append({"code": "invalid_id", "path": relative})
            stable_id = None
        stable_id = stable_id.strip() if isinstance(stable_id, str) else None
        description = metadata.get("description")
        description = description.strip() if isinstance(description, str) and description.strip() else None
        name = metadata.get("name")
        name = name.strip() if isinstance(name, str) and name.strip() else _heading_name(body, path.stem)
        records.append({
            "id": stable_id,
            "name": name,
            "aliases": _strings(metadata.get("aliases")),
            "type": metadata.get("type") if isinstance(metadata.get("type"), str) else None,
            "tags": _strings(metadata.get("tags")),
            "description": description,
            "summary_excerpt": _summary(body),
            "path": relative,
            "file_sha256": snapshot["files"][relative],
            "legacy": stable_id is None,
            "notion_page_ids": [],
            "notion_mappings": [],
            "relations": _relations(body),
        })

    id_counts = Counter(item["id"] for item in records if item["id"])
    for item in records:
        if item["id"] and id_counts[item["id"]] == 1:
            item["catalog_key"] = item["id"]
        elif item["id"]:
            item["catalog_key"] = f"duplicate:{item['id']}:{item['path']}"
        else:
            item["catalog_key"] = f"legacy:{item['path']}"
    for stable_id, count in sorted(id_counts.items()):
        if count > 1:
            diagnostics.append({"code": "duplicate_id", "entity_id": stable_id,
                                "paths": [item["path"] for item in records if item["id"] == stable_id]})

    by_id = defaultdict(list)
    by_path = {item["path"]: item for item in records}
    for item in records:
        if item["id"]:
            by_id[item["id"]].append(item["path"])
    for path in _mapping_paths(vault):
        relative = path.relative_to(vault).as_posix()
        try:
            mappings = _mapping(path)
        except CatalogError as error:
            diagnostics.append({"code": "invalid_notion_mapping", "path": relative,
                                "detail": str(error)})
            continue
        for stable_id, mapping in mappings:
            matches = by_id.get(stable_id, [])
            if not matches:
                diagnostics.append({"code": "mapping_missing_entity", "entity_id": stable_id,
                                    "path": relative})
            for match in matches:
                if mapping not in by_path[match]["notion_mappings"]:
                    by_path[match]["notion_mappings"].append(mapping)
                if mapping["page_id"] not in by_path[match]["notion_page_ids"]:
                    by_path[match]["notion_page_ids"].append(mapping["page_id"])

    id_lookup = {key: sorted(value) for key, value in by_id.items()}
    notion_lookup = defaultdict(list)
    name_lookup = defaultdict(list)
    wikilink_lookup = defaultdict(list)
    for item in records:
        for page_id in item["notion_page_ids"]:
            notion_lookup[_notion_key(page_id)].append(item["path"])
        for value in [item["name"], *item["aliases"]]:
            name_lookup[_normalize(value)].append(item["path"])
        wikilink_lookup[_wikilink_key(Path(item["path"]).stem)].append(item["path"])

    entity_index = {
        "schema_version": SCHEMA_VERSION,
        "source_digest": snapshot["source_digest"],
        "source_files": snapshot["files"],
        "entities": sorted(records, key=lambda item: item["path"]),
        "id_lookup": id_lookup,
        "notion_lookup": {key: sorted(set(value)) for key, value in notion_lookup.items()},
        "name_lookup": {key: sorted(set(value)) for key, value in name_lookup.items()},
        "wikilink_lookup": {key: sorted(set(value)) for key, value in wikilink_lookup.items()},
        "diagnostics": diagnostics,
    }

    combined = dict(entity_index, outgoing={}, incoming={})
    outgoing = {item["catalog_key"]: [] for item in records}
    incoming = {item["catalog_key"]: [] for item in records}
    by_path = {item["path"]: item for item in records}
    for source in records:
        for relation in source["relations"]:
            matched_by, matches = _candidate_paths(combined, relation["target_reference"])
            edge = {
                "predicate": relation["predicate"],
                "source_key": source["catalog_key"],
                "source_id": source["id"],
                "source_path": source["path"],
                "target_reference": relation["target_reference"],
                "resolution": "unresolved",
                "matched_by": matched_by,
                "target_key": None,
                "target_id": None,
                "target_path": None,
                "matches": matches,
            }
            if len(matches) == 1:
                target = by_path[matches[0]]
                edge.update(resolution="resolved", target_key=target["catalog_key"],
                            target_id=target["id"], target_path=target["path"])
                incoming[target["catalog_key"]].append(edge)
            elif len(matches) > 1:
                edge["resolution"] = "ambiguous"
            outgoing[source["catalog_key"]].append(edge)
    edge_key = lambda edge: (edge["predicate"], edge["target_reference"], edge["source_path"])
    for edges in outgoing.values():
        edges.sort(key=edge_key)
    for edges in incoming.values():
        edges.sort(key=edge_key)
    edge_index = {
        "schema_version": SCHEMA_VERSION,
        "source_digest": snapshot["source_digest"],
        "outgoing": outgoing,
        "incoming": incoming,
    }
    return _combine(entity_index, edge_index)


def _combine(entities: dict, edges: dict) -> dict:
    return dict(entities, outgoing=edges["outgoing"], incoming=edges["incoming"])


def build_index(vault: Path) -> dict:
    vault = Path(vault).resolve()
    if not vault.is_dir():
        raise CatalogError(f"Vault does not exist: {vault}")
    for _ in range(3):
        try:
            snapshot = _snapshot(vault)
        except FileNotFoundError:
            continue
        cached = _load_cached(vault, snapshot)
        if cached is not None:
            return cached
        try:
            index = _compile(vault, snapshot)
        except (FileNotFoundError, KeyError):
            continue
        if _snapshot(vault)["source_digest"] != snapshot["source_digest"]:
            continue
        entities = {key: value for key, value in index.items() if key not in {"outgoing", "incoming"}}
        edges = {"schema_version": SCHEMA_VERSION, "source_digest": snapshot["source_digest"],
                 "outgoing": index["outgoing"], "incoming": index["incoming"]}
        _atomic_json(vault / ENTITY_INDEX, entities)
        _atomic_json(vault / EDGE_INDEX, edges)
        if _snapshot(vault)["source_digest"] == snapshot["source_digest"]:
            return index
    raise CatalogError("Entity sources changed repeatedly during index rebuild")


def _public(item: dict) -> dict:
    return {key: item[key] for key in (
        "catalog_key", "id", "name", "aliases", "type", "tags", "description",
        "summary_excerpt", "path", "file_sha256", "legacy", "notion_page_ids",
        "notion_mappings"
    )}


def _resolve_in_index(index: dict, reference) -> dict:
    matched_by, paths = _candidate_paths(index, str(reference))
    by_path = {item["path"]: item for item in index["entities"]}
    if not paths:
        return {"status": "not_found", "reference": str(reference), "matches": []}
    if len(paths) > 1:
        return {"status": "ambiguous", "reference": str(reference), "matched_by": matched_by,
                "matches": [_public(by_path[path]) for path in paths]}
    return dict(_public(by_path[paths[0]]), status="resolved", matched_by=matched_by)


def resolve(vault: Path, reference) -> dict:
    return _resolve_in_index(build_index(vault), reference)


def _scope(records: list[dict], scope) -> list[dict]:
    if scope is None:
        return records
    if isinstance(scope, (str, Path)):
        if str(scope) in {"all", "personal", "entities"}:
            return records
        if str(scope) == "sources":
            return []
        selectors = {str(scope)}
    elif isinstance(scope, Sequence):
        selectors = {str(value) for value in scope}
    else:
        raise CatalogError("scope must be personal, sources, all, or exact Entity IDs/paths")
    return [item for item in records
            if item["catalog_key"] in selectors or item["id"] in selectors or item["path"] in selectors]


def _tokens(value: str) -> list[str]:
    return re.findall(r"[^\W_]+", _normalize(value), re.UNICODE)


def _score(item: dict, query: str) -> tuple[int, list[str]]:
    normalized = _normalize(query)
    if item["id"] == _clean_reference(query):
        return 1000, ["stable_id"]
    if _notion_key(query) in {_notion_key(value) for value in item["notion_page_ids"]}:
        return 950, ["notion_page_id"]
    if normalized == _normalize(item["name"]):
        return 900, ["name"]
    if normalized in {_normalize(value) for value in item["aliases"]}:
        return 850, ["alias"]
    if normalized and normalized in _normalize(item["name"]):
        return 700, ["name_contains"]
    if normalized and any(normalized in _normalize(value) for value in item["aliases"]):
        return 650, ["alias_contains"]
    tokens = _tokens(query)
    description = _normalize(item["description"] or "")
    summary = _normalize(item["summary_excerpt"])
    if tokens and all(token in f"{description} {summary}" for token in tokens):
        reasons = []
        score = 300
        if all(token in description for token in tokens):
            score += 100
            reasons.append("description")
        if all(token in summary for token in tokens):
            score += 50
            reasons.append("summary")
        return score, reasons or ["description_summary"]
    return 0, []


def _event_hits(vault: Path, query: str, kinds: set[str]) -> list:
    tokens, phrase = _tokens(query), _normalize(query)
    from .storage import Library
    if not tokens or not kinds:
        return []
    pending = {(item["event_id"], item["revision"]) for item in Library(vault).pending()} if kinds - {"reference"} else set()
    records = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(vault.glob("_events/*/event.json"))]
    if "reference" in kinds:
        records += [dict(source, input_kind="reference", event_id=None, readiness="reference")
                    for source in (json.loads(path.read_text(encoding="utf-8"))
                                   for path in sorted(vault.glob("_sources/*/source.json")))
                    if source.get("role") == "reference"]
    hits = []
    for event in records:
        if event.get("input_kind") not in kinds:
            continue
        body = vault / event["body_path"]
        lines = body.read_text(encoding="utf-8").splitlines() if body.is_file() else []
        text = _normalize(event.get("name", "") + "\n" + "\n".join(lines))
        if not all(token in text for token in tokens):
            continue
        line = next((number for number, value in enumerate(lines, 1)
                     if any(token in _normalize(value) for token in tokens)), None)
        score = (500 if phrase in text else 200) + sum(text.count(token) for token in tokens)
        hits.append((score, {
            "kind": {"event": "event", "source_update": "source"}.get(event["input_kind"], "reference"),
            "event_id": event["event_id"], "source_id": event.get("source_id", event.get("id")),
            "revision": event["revision"], "name": event.get("name", ""),
            "path": event["body_path"], "line": line, "snippet": lines[line - 1].strip()[:200] if line else "",
            "source_url": event.get("source_url"),
            "settled": None if event["input_kind"] == "reference"
            else event.get("readiness") == "ready" and (event["event_id"], event["revision"]) not in pending}))
    return hits


def search(vault: Path, query, limit: int = 5, scope=None) -> list:
    if type(limit) is not int or not 1 <= limit <= 5:
        raise CatalogError("limit must be between 1 and 5")
    query = str(query).strip()
    if not query:
        return []
    vault = Path(vault).resolve()
    records = _scope(build_index(vault)["entities"], scope)
    scored = []
    for item in records:
        score, reasons = _score(item, query)
        if score:
            scored.append((score, item, reasons))
    if not scored:
        tokens = _tokens(query)
        for item in records:
            try:
                _, body = parse_entity(vault / item["path"])
            except (OSError, CatalogError):
                continue
            normalized = _normalize(body)
            if tokens and all(token in normalized for token in tokens):
                scored.append((100 + sum(normalized.count(token) for token in tokens),
                               item, ["full_text"] ))
    named = "personal" if scope is None else str(scope) if isinstance(scope, (str, Path)) else ""
    selected = {"personal": {"event"}, "sources": {"source_update", "reference"},
                "all": {"event", "source_update", "reference"}}.get(named, set())
    scored = [(score, dict(_public(item), kind="entity"), reasons) for score, item, reasons in scored]
    scored += [(score, hit, ["full_text"]) for score, hit in _event_hits(vault, query, selected)]
    scored.sort(key=lambda row: (-row[0], _normalize(row[1]["name"]), row[1]["path"]))
    return [dict(item, score=score, match_reasons=reasons,
                 hard_match=bool({"stable_id", "notion_page_id", "name", "alias"} & set(reasons)))
            for score, item, reasons in scored[:limit]]


def neighbors(vault: Path, entity_id, predicate=None, direction: str = "both") -> list:
    if direction not in {"incoming", "outgoing", "both"}:
        raise CatalogError("direction must be incoming, outgoing, or both")
    index = build_index(vault)
    resolution = _resolve_in_index(index, entity_id)
    if resolution["status"] == "ambiguous":
        raise CatalogAmbiguityError(f"Ambiguous Entity reference: {entity_id}")
    if resolution["status"] == "not_found":
        raise CatalogNotFoundError(f"Unknown Entity reference: {entity_id}")
    key = resolution["catalog_key"]
    by_key = {item["catalog_key"]: item for item in index["entities"]}
    result = []
    if direction in {"outgoing", "both"}:
        for edge in index["outgoing"].get(key, []):
            if predicate is not None and edge["predicate"] != predicate:
                continue
            target = by_key.get(edge["target_key"])
            result.append({
                "direction": "outgoing",
                "predicate": edge["predicate"],
                "entity_id": target["id"] if target else None,
                "catalog_key": target["catalog_key"] if target else None,
                "name": target["name"] if target else None,
                "path": target["path"] if target else None,
                "legacy": target["legacy"] if target else None,
                "target_reference": edge["target_reference"],
                "resolution": edge["resolution"],
                "matched_by": edge["matched_by"],
                "matches": edge["matches"],
            })
    if direction in {"incoming", "both"}:
        for edge in index["incoming"].get(key, []):
            if predicate is not None and edge["predicate"] != predicate:
                continue
            source = by_key[edge["source_key"]]
            result.append({
                "direction": "incoming",
                "predicate": edge["predicate"],
                "entity_id": source["id"],
                "catalog_key": source["catalog_key"],
                "name": source["name"],
                "path": source["path"],
                "legacy": source["legacy"],
                "target_reference": edge["target_reference"],
                "resolution": "resolved",
                "matched_by": edge["matched_by"],
                "matches": edge["matches"],
            })
    return sorted(result, key=lambda item: (item["direction"], item["predicate"],
                                            _normalize(item["name"] or item["target_reference"])))
