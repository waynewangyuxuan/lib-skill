"""Durable Event evidence, Entity replacement plans, and consumer receipts."""

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
import uuid

import yaml

SCHEMA = 1
SUCCESS = {"integrated", "recorded_only"}
OUTCOMES = SUCCESS | {"blocked", "needs_review"}


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def digest(value):
    if isinstance(value, Path):
        value = value.read_bytes()
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_bytes(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"Symlink write refused: {path}")
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_json(path, value):
    _atomic_bytes(path, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n")
    return value


@contextmanager
def writer_lock(vault, wait_seconds=0):
    vault = Path(vault).resolve()
    state = vault / "_state"
    if state.is_symlink():
        raise ValueError("Symlink state directory refused")
    state.mkdir(parents=True, exist_ok=True)
    path = state / "writer.lock"
    if path.is_symlink():
        raise ValueError("Symlink writer lock refused")
    inherited = os.environ.get("MYLIBRARY_WRITER_LOCK_FD")
    if inherited is not None:
        descriptor = int(inherited)
        actual, expected = os.fstat(descriptor), path.stat()
        if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
            raise ValueError("Inherited writer descriptor does not match this vault")
    else:
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        deadline = time.monotonic() + wait_seconds
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise
                time.sleep(min(0.1, remaining))
        yield descriptor
    finally:
        if inherited is None:
            os.close(descriptor)


def _slug(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
        raise ValueError(f"Invalid identifier: {value!r}")
    return value


def _frontmatter(content):
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", content, re.S)
    if not match:
        raise ValueError("Entity frontmatter missing")
    fields = yaml.safe_load(match.group(1))
    if not isinstance(fields, dict):
        raise ValueError("Entity frontmatter must be a mapping")
    return fields, content[match.end():]


def _context(content):
    match = re.search(r"^## Context\s*$\n(.*?)(?=^## |\Z)", content, re.M | re.S)
    return match.group(1).strip() if match else ""


def _safe_raw(value):
    if isinstance(value, dict):
        return {key: _safe_raw(item) for key, item in value.items()
                if key.lower() not in {"authorization", "token", "api_key", "password", "secret"}}
    if isinstance(value, list):
        return [_safe_raw(item) for item in value]
    if isinstance(value, str) and "?" in value and re.search(r"[?&](x-amz-|signature=|token=)", value, re.I):
        return value.split("?", 1)[0]
    return value


def _semantic_coverage(value):
    if isinstance(value, dict):
        return {key: _semantic_coverage(item) for key, item in value.items()
                if key not in {"retry_at", "checked_at", "collected_at", "attempted_at", "continuation"}}
    if isinstance(value, list):
        return [_semantic_coverage(item) for item in value]
    return _safe_raw(value)


def _validate_anchor(path, anchor):
    text = path.read_text(encoding="utf-8")
    lines = re.fullmatch(r"L([1-9][0-9]*)(?:-L([1-9][0-9]*))?", anchor)
    if lines:
        first, last = int(lines[1]), int(lines[2] or lines[1])
        if first <= last <= len(text.splitlines()):
            return
    elif anchor.startswith("section:"):
        heading = anchor[len("section:"):]
        if heading and re.search(r"^#{1,6} " + re.escape(heading) + r"\s*$", text, re.M):
            return
    elif anchor.startswith("block:"):
        identifier = anchor[len("block:"):]
        if re.fullmatch(r"[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}", identifier):
            normalized = identifier.replace("-", "").lower()
            if path.suffix == ".json":
                pending = [json.loads(text)]
                while pending:
                    item = pending.pop()
                    if isinstance(item, dict):
                        kind = item.get("type")
                        is_block = item.get("object") == "block" or (isinstance(kind, str) and kind in item)
                        if is_block and str(item.get("id", "")).replace("-", "").lower() == normalized:
                            return
                        pending.extend(item.values())
                    elif isinstance(item, list):
                        pending.extend(item)
            elif normalized in text.replace("-", "").lower():
                return
    raise ValueError("Evidence anchor does not locate acquired content")


class Library:
    def __init__(self, vault: Path):
        self.vault = Path(vault).resolve()
        if not self.vault.is_dir():
            raise ValueError("Vault must be an existing directory")

    def _path(self, relative):
        relative = Path(relative)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError("Managed path must be relative and confined")
        if relative.parts[0] not in {"_entities", "_events", "_sources", "_state", "_runs"}:
            raise ValueError("Path is outside managed storage")
        current = self.vault
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError(f"Managed symlink refused: {relative}")
        if not current.resolve().is_relative_to(self.vault):
            raise ValueError("Managed path escape")
        return current

    def _formal_path(self, relative):
        relative = Path(relative)
        if (len(relative.parts) != 2 or relative.parts[0] != "_entities"
                or relative.suffix != ".md" or relative.name.startswith("_")):
            raise ValueError("Formal output must be _entities/<entity>.md")
        return self._path(relative)

    def record(self, provider, workspace_id, resource_id, body, *, name="", input_kind="event",
               occurred_at=None, authorship="unknown", mentions=(), semantic=None, raw=None,
               attachments=(), coverage=None, source_url=None):
        if not all(isinstance(value, str) and value for value in (provider, workspace_id, resource_id)):
            raise ValueError("Provider, workspace and resource identity required")
        if not isinstance(body, str) or input_kind not in {"event", "source_update"}:
            raise ValueError("Invalid Event body or kind")
        identity = {"provider": provider, "workspace_id": workspace_id, "resource_id": resource_id}
        key = digest(_canonical(identity))[:32]
        event_id, source_id = "evt_" + key, "src_" + key
        body = body.replace("\r\n", "\n").replace("\r", "\n")
        assets, asset_bytes = [], {}
        for attachment in attachments:
            item = dict(attachment)
            content = item.pop("content", None)
            local_path = item.pop("path", None)
            if content is None and local_path is not None:
                content = Path(local_path).read_bytes()
            asset = {"id": item.get("id", item.get("name", "attachment")), "name": item.get("name", "")}
            if content is not None:
                if not isinstance(content, bytes):
                    raise ValueError("Attachment content must be bytes")
                sha = digest(content)
                asset.update(status="saved", sha256=sha,
                             path=f"_sources/{source_id}/attachments/{sha}")
                asset_bytes[sha] = content
            else:
                asset.update(status=item.get("status", "unavailable"), gap=item.get("gap", "bytes not acquired"))
            assets.append(asset)
        semantic_data = dict(semantic or {})
        semantic_data.pop("normalizer_version", None)
        coverage = coverage or {"status": "complete", "gaps": []}
        content_key = {"body": body, "name": name, "input_kind": input_kind,
                       "semantic": semantic_data, "mentions": sorted(set(mentions)),
                       "attachments": sorted(assets, key=lambda item: (item["id"], item.get("sha256", ""))),
                       "coverage": _semantic_coverage(coverage)}
        content_hash = digest(_canonical(content_key))
        with writer_lock(self.vault):
            revisions = self._path(f"_events/{event_id}/revisions")
            revisions.mkdir(parents=True, exist_ok=True)
            existing = sorted((int(item.name) for item in revisions.iterdir()
                               if item.is_dir() and item.name.isdigit()))
            if existing:
                latest = read_json(self._path(f"_events/{event_id}/revisions/{existing[-1]}/event.json"))
                if latest["semantic_sha256"] == content_hash:
                    pointer = self._path(f"_events/{event_id}/event.json")
                    if not pointer.exists() or read_json(pointer).get("revision") != latest["revision"]:
                        atomic_json(pointer, latest)
                        _atomic_bytes(self._path(f"_events/{event_id}/event.md"), body.encode())
                    return latest
            revision = existing[-1] + 1 if existing else 1
            relative = f"_events/{event_id}/revisions/{revision}"
            source_relative = f"_sources/{source_id}/snapshots/{revision}"
            envelope = {"schema_version": SCHEMA, "event_id": event_id, "revision": revision,
                        "identity": identity, "source_id": source_id, "name": name,
                        "input_kind": input_kind, "occurred_at": occurred_at,
                        "collected_at": timestamp(), "authorship": authorship,
                        "mentions": list(mentions), "semantic": semantic_data,
                        "semantic_sha256": content_hash,
                        "normalizer_version": (semantic or {}).get("normalizer_version", "1"),
                        "body_path": relative + "/body.md", "raw_path": relative + "/raw.json",
                        "source_url": source_url, "attachments": assets, "coverage": coverage,
                        "readiness": "ready" if body.strip() or assets else "empty"}
            for sha, content in asset_bytes.items():
                target = self._path(f"_sources/{source_id}/attachments/{sha}")
                if target.exists() and digest(target) != sha:
                    raise ValueError("Attachment hash conflict")
                if not target.exists():
                    _atomic_bytes(target, content)
            evidence_raw = _safe_raw(raw or {})
            snapshot = self._path(source_relative)
            snapshot.mkdir(parents=True, exist_ok=True)
            _atomic_bytes(snapshot / "body.md", body.encode())
            atomic_json(snapshot / "raw.json", evidence_raw)
            atomic_json(snapshot / "coverage.json", coverage)
            atomic_json(self._path(f"_sources/{source_id}/source.json"),
                        {"id": source_id, "identity": identity, "source_url": source_url})
            temporary = Path(tempfile.mkdtemp(prefix=".revision-", dir=revisions))
            try:
                _atomic_bytes(temporary / "body.md", body.encode())
                atomic_json(temporary / "raw.json", evidence_raw)
                atomic_json(temporary / "event.json", envelope)
                os.replace(temporary, self._path(relative))
                _fsync_directory(revisions)
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
            atomic_json(self._path(f"_events/{event_id}/event.json"), envelope)
            _atomic_bytes(self._path(f"_events/{event_id}/event.md"), body.encode())
            return envelope

    def capture(self, body_file, *, resource_id=None, name="", mode="result"):
        if mode not in {"result", "detail"}:
            raise ValueError("Capture mode must be result or detail")
        with writer_lock(self.vault):
            state = self._path("_state/library.json")
            identity = read_json(state) if state.exists() else {"workspace_id": "local_" + uuid.uuid4().hex}
            if not state.exists():
                atomic_json(state, identity)
        return self.record("local", identity["workspace_id"], resource_id or uuid.uuid4().hex,
                           Path(body_file).read_text(encoding="utf-8"), name=name,
                           authorship="agent_capture", semantic={"capture_mode": mode})

    def _receipt_pointer(self, consumer, event_id, revision):
        return self._path(f"_state/consumption/{_slug(consumer)}/{_slug(event_id)}/{int(revision)}.json")

    def _completed(self, consumer, event_id, revision):
        pointer = self._receipt_pointer(consumer, event_id, revision)
        if not pointer.exists():
            return None
        value = read_json(pointer)
        path = self._path(value["receipt_path"])
        if not path.is_file() or digest(path) != value["sha256"]:
            raise ValueError("Consumer receipt is corrupt; input remains unresolved")
        receipt = read_json(path)
        if (receipt.get("consumer"), receipt.get("event_id"), receipt.get("revision")) != (consumer, event_id, revision):
            raise ValueError("Consumer receipt key mismatch")
        if receipt.get("outcome") not in SUCCESS:
            raise ValueError("Completion pointer does not reference success")
        final_path = self._path(f"_runs/{_slug(receipt['run_id'])}/receipt.json")
        if not final_path.exists():
            return None
        final = read_json(final_path)
        if (final.get("status") != "complete" or final.get("run_id") != receipt["run_id"]
                or final.get("consumer") != consumer
                or final.get("staging_sha256") != receipt.get("staging_sha256")
                or final.get("outcome_hashes", {}).get(value["receipt_path"]) != value["sha256"]):
            raise ValueError("Final consumer receipt is corrupt or inconsistent")
        return value

    def pending(self, consumer="settle"):
        _slug(consumer)
        root = self._path("_events")
        result = []
        if root.exists():
            for path in sorted(root.glob("*/revisions/*/event.json")):
                path = self._path(path.relative_to(self.vault))
                event = read_json(path)
                if event["readiness"] != "empty" and not self._completed(consumer, event["event_id"], event["revision"]):
                    result.append(event)
        return result

    def freeze(self, output: Path, *, consumer="settle", method_version="lib-settle/3", keys=None):
        output = Path(output).resolve()
        if output.is_relative_to(self.vault):
            raise ValueError("Freeze and staging must remain outside vault")
        if keys is None:
            events = self.pending(consumer)
        else:
            requested = {(item["event_id"], item["revision"]) if isinstance(item, dict) else tuple(item) for item in keys}
            events = []
            for event_id, revision in sorted(requested):
                _slug(event_id)
                if type(revision) is not int or revision < 1:
                    raise ValueError("Invalid Event revision")
                event = read_json(self._path(f"_events/{event_id}/revisions/{revision}/event.json"))
                if event["readiness"] == "empty":
                    raise ValueError("Empty Event remains nonconsumable")
                events.append(event)
        frozen_events, evidence = [], {}
        for event in events:
            entry = dict(event)
            paths = [event["body_path"], event["raw_path"],
                     f"_events/{event['event_id']}/revisions/{event['revision']}/event.json"]
            source_snapshot = f"_sources/{event['source_id']}/snapshots/{event['revision']}"
            paths += [source_snapshot + "/" + name for name in ("body.md", "raw.json", "coverage.json")]
            paths += [item["path"] for item in event["attachments"] if item["status"] == "saved"]
            entry["frozen_hashes"] = {path: digest(self._path(path)) for path in paths}
            evidence.update(entry["frozen_hashes"])
            frozen_events.append(entry)
        baseline = {str(path.relative_to(self.vault)): digest(self._formal_path(path.relative_to(self.vault)))
                    for path in sorted(self._path("_entities").glob("*.md")) if not path.name.startswith("_")}
        manifest = {"schema_version": SCHEMA, "run_id": "run_" + uuid.uuid4().hex,
                    "consumer": _slug(consumer), "method_version": method_version,
                    "created_at": timestamp(), "events": frozen_events,
                    "evidence": evidence, "baseline": baseline}
        atomic_json(output, manifest)
        return manifest

    def _entities(self):
        result = {}
        for path in self._path("_entities").glob("*.md"):
            if path.name.startswith("_"):
                continue
            safe = self._formal_path(path.relative_to(self.vault))
            text = safe.read_text(encoding="utf-8")
            try:
                fields, _ = _frontmatter(text)
            except ValueError:
                fields = {}
            result[str(path.relative_to(self.vault))] = (fields, text)
        return result

    def validate(self, staging_path: Path):
        staging_path = Path(staging_path).resolve()
        if staging_path.is_relative_to(self.vault):
            raise ValueError("Staging must remain outside vault")
        stage = read_json(staging_path)
        if stage.get("schema_version") != SCHEMA:
            raise ValueError("Unsupported staging schema")
        _slug(stage["run_id"])
        _slug(stage["consumer"])
        frozen_path = Path(stage["freeze_path"]).resolve()
        if digest(frozen_path) != stage["freeze_sha256"]:
            raise ValueError("Freeze manifest hash mismatch")
        frozen = read_json(frozen_path)
        if frozen.get("schema_version") != SCHEMA:
            raise ValueError("Unsupported freeze schema")
        for field in ("run_id", "consumer", "method_version"):
            if stage[field] != frozen[field]:
                raise ValueError("Staging and freeze disagree")
        for path, sha in frozen["evidence"].items():
            if digest(self._path(path)) != sha:
                raise ValueError("Frozen evidence changed")
        for path, sha in frozen["baseline"].items():
            target = self._formal_path(path)
            if not target.is_file() or digest(target) != sha:
                raise ValueError("Stale Entity baseline hash")
        if set(self._entities()) != set(frozen["baseline"]):
            raise ValueError("Entity baseline membership changed")
        events = {(item["event_id"], item["revision"]): item for item in frozen["events"]}
        if not events and stage.get("purpose") != "migration":
            raise ValueError("No Events; explicit migration purpose required")
        existing = self._entities()
        outputs, output_fields = {}, {}
        for item in stage["files"]:
            path = str(Path(item["path"]))
            target = self._formal_path(path)
            if path in outputs:
                raise ValueError("Duplicate output path")
            current = digest(target) if target.exists() else None
            if current != item["base_sha256"] or frozen["baseline"].get(path) != item["base_sha256"]:
                raise ValueError("Stale Entity base hash")
            staged = Path(item["staged_path"])
            if staged.is_symlink():
                raise ValueError("Staged symlink refused")
            staged = staged.resolve()
            if staged.is_relative_to(self.vault) or not staged.is_file():
                raise ValueError("Staged file must exist outside vault")
            text = staged.read_text(encoding="utf-8")
            fields, _ = _frontmatter(text)
            for required in ("id", "name", "type", "description"):
                if not isinstance(fields.get(required), str) or not fields[required].strip():
                    raise ValueError(f"Entity {required} required")
            _slug(fields["id"])
            if type(fields.get("revision")) is not int or fields["revision"] < 1:
                raise ValueError("Entity revision must be positive integer")
            for section in ("Summary", "Access", "Context", "Relations"):
                if not re.search(r"^## " + section + r"\s*$", text, re.M):
                    raise ValueError(f"Entity {section} section required")
            previous_fields, previous_text = existing.get(path, ({}, ""))
            if previous_fields.get("id"):
                if fields["id"] != previous_fields["id"]:
                    raise ValueError("Entity identity is immutable")
                if fields["revision"] != previous_fields["revision"] + 1:
                    raise ValueError("Entity revision must increment once")
            elif fields["revision"] != 1:
                raise ValueError("Legacy bootstrap or new Entity starts at revision 1")
            history = _context(previous_text)
            if history and history not in _context(text):
                raise ValueError("Prior Context evidence must be preserved")
            outputs[path] = dict(item, path=path, after_sha256=digest(staged))
            output_fields[path] = fields
        global_ids = {}
        for path, pair in existing.items():
            fields = output_fields.get(path, pair[0])
            if fields.get("id"):
                if fields["id"] in global_ids:
                    raise ValueError("Duplicate global Entity ID")
                global_ids[fields["id"]] = path
        for path, fields in output_fields.items():
            if path not in existing:
                if fields["id"] in global_ids:
                    raise ValueError("Duplicate global Entity ID")
                global_ids[fields["id"]] = path
        outcomes = {}
        for item in stage["outcomes"]:
            key = (item["event_id"], item["revision"])
            if key not in events or key in outcomes or item["outcome"] not in OUTCOMES:
                raise ValueError("Invalid or duplicate Event outcome")
            if not set(item["files"]).issubset(outputs):
                raise ValueError("Outcome references undeclared output")
            if not set(item["entity_ids"]).issubset(global_ids):
                raise ValueError("Outcome references unknown Entity")
            refs = item.get("evidence", [])
            if item["outcome"] == "integrated" and (not item["entity_ids"] or not refs):
                raise ValueError("Integrated needs Entity identity and precise frozen evidence")
            if (item["outcome"] == "integrated" and events[key]["coverage"].get("status") != "complete"
                    and not item.get("coverage_ack", "").strip()):
                raise ValueError("Partial evidence requires an explicit coverage decision before integration")
            if item["outcome"] in {"blocked", "needs_review"} and item["files"]:
                raise ValueError("Unresolved outcomes cannot authorize formal writes")
            if item["outcome"] == "recorded_only" and (item["files"] or not item.get("reason", "").strip()):
                raise ValueError("Recorded-only needs reason and no writes")
            for ref in refs:
                if not ref.get("anchor", "").strip() or frozen["evidence"].get(ref["path"]) != ref["sha256"]:
                    raise ValueError("Evidence is not precisely bound to freeze")
                _validate_anchor(self._path(ref["path"]), ref["anchor"])
            if item["outcome"] == "integrated" and not any(ref["path"] in events[key]["frozen_hashes"] for ref in refs):
                raise ValueError("Integrated outcome must cite evidence from its own Event revision")
            completed = self._completed(stage["consumer"], *key)
            if completed and (item.get("prior_receipt_sha256") != completed["sha256"]
                              or not item.get("reconciliation", "").strip()):
                raise ValueError("Already consumed; explicit receipt-bound reconciliation required")
            outcomes[key] = item
        if set(outcomes) != set(events):
            raise ValueError("All frozen Event keys need outcomes")
        referenced = {path for outcome in outcomes.values() for path in outcome["files"]}
        if events and referenced != set(outputs):
            raise ValueError("Every formal write needs an Event outcome")
        return dict(stage, files=list(outputs.values()), staging_sha256=digest(staging_path))

    def apply(self, staging_path: Path, *, fault_after=None):
        stage = read_json(staging_path)
        run_id = _slug(stage["run_id"])
        with writer_lock(self.vault):
            receipt_path = self._path(f"_runs/{run_id}/receipt.json")
            stage_hash = digest(Path(staging_path))
            if receipt_path.exists():
                receipt = read_json(receipt_path)
                if receipt["staging_sha256"] != stage_hash:
                    raise ValueError("Run ID already completed with another manifest")
                return receipt
            journal_path = self._path(f"_runs/{run_id}/apply/journal.json")
            if journal_path.exists():
                if read_json(journal_path)["staging_sha256"] != stage_hash:
                    raise ValueError("Run ID already has another journal")
                return self._finish(run_id, fault_after)
            checked = self.validate(staging_path)
            if checked["staging_sha256"] != stage_hash or checked["run_id"] != run_id:
                raise ValueError("Staging changed while being read")
            operations = []
            for index, item in enumerate(checked["files"]):
                saved = f"_runs/{run_id}/apply/files/{index}"
                _atomic_bytes(self._path(saved), Path(item["staged_path"]).read_bytes())
                operations.append(dict(item, desired_path=saved, status="pending"))
            frozen = read_json(checked["freeze_path"])
            atomic_json(self._path(f"_runs/{run_id}/frozen.json"), frozen)
            journal = {"schema_version": SCHEMA, "run_id": run_id, "consumer": checked["consumer"],
                       "method_version": checked["method_version"], "staging_sha256": checked["staging_sha256"],
                       "operations": operations, "outcomes": checked["outcomes"],
                       "purpose": checked.get("purpose"), "status": "prepared"}
            atomic_json(journal_path, journal)
            return self._finish(run_id, fault_after)

    def _finish(self, run_id, fault_after=None):
        journal_path = self._path(f"_runs/{run_id}/apply/journal.json")
        journal = read_json(journal_path)
        frozen = read_json(self._path(f"_runs/{run_id}/frozen.json"))
        for path, sha in frozen["evidence"].items():
            if digest(self._path(path)) != sha:
                raise ValueError("Frozen evidence changed during recovery")
        for outcome in journal["outcomes"]:
            pointer = self._completed(journal["consumer"], outcome["event_id"], outcome["revision"])
            if pointer:
                receipt = read_json(self._path(pointer["receipt_path"]))
                if receipt["run_id"] != run_id and pointer["sha256"] != outcome.get("prior_receipt_sha256"):
                    raise ValueError("Event consumed by another run; reconcile before recovery")
        replacements = 0
        for item in journal["operations"]:
            target = self._formal_path(item["path"])
            actual = digest(target) if target.exists() else None
            if actual == item["after_sha256"]:
                item["status"] = "applied"
            elif actual == item["base_sha256"]:
                desired = self._path(item["desired_path"])
                if digest(desired) != item["after_sha256"]:
                    raise ValueError("Journal desired bytes corrupt")
                _atomic_bytes(target, desired.read_bytes())
                item["status"] = "applied"
                replacements += 1
            else:
                journal["status"] = "conflict"
                journal["conflict_path"] = item["path"]
                atomic_json(journal_path, journal)
                raise ValueError(f"Recovery stopped at human or concurrent edit: {item['path']}")
            atomic_json(journal_path, journal)
            if fault_after is not None and replacements >= fault_after:
                raise RuntimeError("Injected interruption after formal replacement")
        managed = {f"_runs/{run_id}"}
        receipt_paths = []
        for outcome in journal["outcomes"]:
            relative = f"_runs/{run_id}/outcomes/{journal['consumer']}/{outcome['event_id']}/{outcome['revision']}.json"
            completion = dict(outcome, consumer=journal["consumer"], method_version=journal["method_version"],
                              run_id=run_id, staging_sha256=journal["staging_sha256"],
                              output_hashes={item["path"]: item["after_sha256"] for item in journal["operations"]
                                             if item["path"] in outcome["files"]})
            if outcome["outcome"] in SUCCESS:
                completion["completed_at"] = timestamp()
            path = self._path(relative)
            if not path.exists():
                atomic_json(path, completion)
            elif read_json(path).get("staging_sha256") != journal["staging_sha256"]:
                raise ValueError("Run outcome receipt collision")
            if outcome["outcome"] in SUCCESS:
                pointer_path = self._receipt_pointer(journal["consumer"], outcome["event_id"], outcome["revision"])
                atomic_json(pointer_path, {"receipt_path": relative, "sha256": digest(path)})
                managed.add(str(pointer_path.relative_to(self.vault)))
            receipt_paths.append(relative)
        managed.update(item["path"] for item in journal["operations"])
        journal["status"] = "complete"
        atomic_json(journal_path, journal)
        receipt = {"schema_version": SCHEMA, "run_id": run_id, "consumer": journal["consumer"],
                   "staging_sha256": journal["staging_sha256"], "status": "complete",
                   "completed_at": timestamp(), "outcome_receipts": receipt_paths,
                   "outcome_hashes": {relative: digest(self._path(relative)) for relative in receipt_paths},
                   "changed_entity_ids": sorted({_frontmatter(self._formal_path(item["path"]).read_text())[0]["id"]
                                                 for item in journal["operations"]}),
                   "managed_paths": sorted(managed)}
        atomic_json(self._path(f"_runs/{run_id}/receipt.json"), receipt)
        return receipt

    def recover(self, run_id):
        run_id = _slug(run_id)
        with writer_lock(self.vault):
            path = self._path(f"_runs/{run_id}/receipt.json")
            if path.exists():
                return read_json(path)
            return self._finish(run_id)

    def status(self):
        runs = self._path("_runs")
        return {"pending": len(self.pending()), "completed_runs": len(list(runs.glob("*/receipt.json"))),
                "incomplete_runs": [path.parent.parent.name for path in runs.glob("*/apply/journal.json")
                                    if not (path.parent.parent / "receipt.json").exists()]}

    def backup(self, output: Path):
        output = Path(output).resolve()
        if output.is_relative_to(self.vault) or output.exists():
            raise ValueError("Backup must use a new directory outside vault")
        with writer_lock(self.vault):
            if self.status()["incomplete_runs"]:
                raise ValueError("Recover unfinished apply before backup")
            files = {}
            for folder in ("_entities", "_events", "_sources", "_state", "_runs"):
                root = self._path(folder)
                if not root.exists():
                    continue
                for path in sorted(root.rglob("*")):
                    relative = path.relative_to(self.vault)
                    if path.is_symlink():
                        raise ValueError("Backup excludes symlinks")
                    if not path.is_file() or path.suffix == ".lock" or any(part.startswith(".") for part in relative.parts):
                        continue
                    if folder == "_entities" and path.name.startswith("_"):
                        continue
                    if folder == "_runs" and not self._path(f"_runs/{relative.parts[1]}/receipt.json").exists():
                        continue
                    safe = self._path(relative)
                    files[str(relative)] = digest(safe)
            output.mkdir(parents=True)
            for relative, sha in files.items():
                target = output / relative
                _atomic_bytes(target, self._path(relative).read_bytes())
                if digest(target) != sha:
                    raise ValueError("Backup readback mismatch")
            manifest = {"schema_version": SCHEMA, "created_at": timestamp(), "files": files,
                        "excluded": ["_personal", "_index", "writer.lock", "incomplete runs"]}
            atomic_json(output / "backup-manifest.json", manifest)
            return manifest
