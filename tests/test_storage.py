import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from mylibrary.storage import Library, atomic_json, digest, read_json, writer_lock


def entity(name, identity, revision=1, history="", extra=""):
    return (f"---\nid: {identity}\nname: {name}\ntype: system\ndescription: Context for {name}\nrevision: {revision}\n---\n"
            f"# {name}\n\n## Summary\nSummary.\n\n## Access\nLocal.\n\n## Context\n{history}{extra}\n\n## Relations\n")


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.vault = self.root / "vault"
        self.vault.mkdir()
        self.library = Library(self.vault)

    def record(self, resource="page", body="An idea", **kwargs):
        return self.library.record("notion", "workspace", resource, body, **kwargs)

    def stage(self, events=None, files=None, outcome="integrated", reason="", consumer="settle", purpose=None):
        count = len(list(self.root.glob("run-*")))
        run = self.root / f"run-{count}"
        run.mkdir()
        frozen_path = run / "frozen.json"
        frozen = self.library.freeze(frozen_path, consumer=consumer,
                                     keys=[(e["event_id"], e["revision"]) for e in events] if events is not None else None)
        file_items = []
        for index, (path, text) in enumerate(files or []):
            staged = run / f"entity-{index}.md"
            staged.write_text(text)
            formal = self.vault / path
            file_items.append({"path": path, "staged_path": str(staged),
                               "base_sha256": digest(formal) if formal.exists() else None})
        outcomes = []
        for event in frozen["events"]:
            evidence_path = event["body_path"]
            outcomes.append({"event_id": event["event_id"], "revision": event["revision"],
                             "outcome": outcome, "entity_ids": ["ent_alpha"] if outcome == "integrated" else [],
                             "files": [item["path"] for item in file_items],
                             "evidence": [{"path": evidence_path, "sha256": frozen["evidence"][evidence_path], "anchor": "L1"}],
                             "reason": reason})
        stage = {"schema_version": 1, "run_id": frozen["run_id"], "consumer": consumer,
                 "method_version": frozen["method_version"], "freeze_path": str(frozen_path),
                 "freeze_sha256": digest(frozen_path), "files": file_items, "outcomes": outcomes}
        if purpose:
            stage["purpose"] = purpose
        path = run / "staging.json"
        atomic_json(path, stage)
        return path, stage

    def test_equal_text_distinct_identity_and_same_read(self):
        first = self.record("one", "same")
        second = self.record("two", "same")
        self.assertNotEqual(first["event_id"], second["event_id"])
        self.assertEqual(self.record("one", "same"), first)
        self.assertEqual(len(self.library.pending()), 2)
        self.assertEqual((self.vault / first["body_path"]).read_text(), "same")

    def test_reverted_content_is_new_numeric_revision(self):
        self.record(body="A")
        self.assertEqual(self.record(body="B")["revision"], 2)
        self.assertEqual(self.record(body="A")["revision"], 3)
        self.assertEqual([e["revision"] for e in self.library.pending()], [1, 2, 3])

    def test_normalizer_and_raw_url_change_do_not_create_revision(self):
        first = self.record(semantic={"normalizer_version": "1"}, raw={"url": "https://a/?X-Amz-Signature=secret"})
        second = self.record(semantic={"normalizer_version": "2"}, raw={"url": "https://a/?X-Amz-Signature=other"})
        self.assertEqual(first["revision"], second["revision"])
        self.assertEqual(read_json(self.vault / first["raw_path"])["url"], "https://a/")

    def test_complete_coverage_creates_revision_without_body_change(self):
        partial = self.record(coverage={"status": "partial", "gaps": ["missing subtree"],
                                        "retry_at": "first attempt"})
        complete = self.record(coverage={"status": "complete", "gaps": []})
        self.assertEqual((partial["revision"], complete["revision"]), (1, 2))
        self.assertEqual(self.record(coverage={"status": "complete", "gaps": []})["revision"], 2)
        self.assertEqual(self.record(coverage={"status": "partial", "gaps": ["missing subtree"],
                                               "retry_at": "later attempt"})["revision"], 3)

    def test_empty_then_content_and_late_attachment(self):
        empty = self.record(body="")
        self.assertEqual(self.library.pending(), [])
        live = self.record(body="Read material", attachments=[{"id": "image", "status": "unavailable"}],
                           coverage={"status": "partial", "gaps": ["image"]})
        completed = self.record(body="Read material", attachments=[{"id": "image", "content": b"image bytes"}])
        self.assertEqual(live["revision"], empty["revision"] + 1)
        self.assertEqual(completed["revision"], live["revision"] + 1)
        self.assertEqual((self.vault / completed["attachments"][0]["path"]).read_bytes(), b"image bytes")
        self.assertEqual(live["coverage"]["status"], "partial")

    def test_capture_identity_persists(self):
        body = self.root / "capture.md"
        body.write_text("Local idea")
        first = self.library.capture(body, resource_id="session")
        second = Library(self.vault).capture(body, resource_id="session")
        self.assertEqual(first, second)
        self.assertTrue((self.vault / "_state/library.json").exists())

    def test_partial_coverage_needs_a_recorded_integration_decision(self):
        event = self.record(coverage={"status": "partial", "gaps": ["unread image"]})
        path, stage = self.stage([event], [("_entities/alpha.md", entity("Alpha", "ent_alpha"))])
        with self.assertRaisesRegex(ValueError, "coverage decision"):
            self.library.validate(path)
        stage["outcomes"][0]["coverage_ack"] = "The conclusion uses the written text only; image detail remains unknown"
        atomic_json(path, stage)
        self.library.validate(path)

    def test_integrated_outcome_cannot_cite_only_a_different_event(self):
        one, two = self.record("one", "One"), self.record("two", "Two")
        path, stage = self.stage([one, two], [("_entities/alpha.md", entity("Alpha", "ent_alpha"))])
        stage["outcomes"][0]["evidence"] = stage["outcomes"][1]["evidence"]
        atomic_json(path, stage)
        with self.assertRaisesRegex(ValueError, "own Event"):
            self.library.validate(path)

    def test_unresolved_outcome_cannot_authorize_writes(self):
        event = self.record()
        path, _ = self.stage([event], [("_entities/alpha.md", entity("Alpha", "ent_alpha"))], outcome="blocked", reason="missing evidence")
        with self.assertRaisesRegex(ValueError, "Unresolved"):
            self.library.validate(path)

    def test_repeat_apply_returns_receipt_after_later_human_edit(self):
        event = self.record()
        path, stage = self.stage([event], [("_entities/alpha.md", entity("Alpha", "ent_alpha", extra="Original.\n"))])
        receipt = self.library.apply(path)
        target = self.vault / "_entities/alpha.md"
        target.write_text(target.read_text() + "Human correction.\n")
        self.assertEqual(self.library.apply(path), receipt)
        self.assertIn("Human correction.", target.read_text())
        self.assertEqual(self.library.pending(), [])
        self.assertEqual(len(self.library.pending("review")), 1)
        self.assertIn("_entities/alpha.md", receipt["managed_paths"])

    def test_activity_counts_integrated_events_per_entity(self):
        first = self.record("one", occurred_at="2026-09-01")
        path, _ = self.stage([first], [("_entities/alpha.md", entity("Alpha", "ent_alpha", extra="One.\n"))])
        self.library.apply(path)
        second = self.record("two", body="Another", occurred_at="2026-09-03T10:00:00Z")
        path, _ = self.stage([second], [("_entities/alpha.md", entity("Alpha", "ent_alpha", 2, extra="One.\nTwo.\n"))])
        self.library.apply(path)
        noise = self.record("three", body="Noise", occurred_at="2026-09-05")
        path, _ = self.stage([noise], outcome="recorded_only", reason="nothing to add")
        self.library.apply(path)
        self.assertEqual(self.library.activity(), {"ent_alpha": {"event_count": 2, "last_event": "2026-09-03"}})

    def test_migration_cannot_silently_drop_fields_values_or_lines(self):
        legacy = ("---\ntype: artifact\ntags: [research, reading]\naliases: [Alpha]\nstate: captured\ncreated: 2026-05-01\n---\n"
                  "# Alpha\n\n## Summary\nOld summary.\n\n## Access\nLocal.\n\n## Context\n- Old context.\n\n## Relations\n- uses:: [[Beta]]\n")
        (self.vault / "_entities").mkdir(exist_ok=True)
        (self.vault / "_entities/alpha.md").write_text(legacy)
        migrated = ("---\nid: ent_alpha\nname: Alpha\ntype: artifact\ndescription: The alpha artifact\nrevision: 1\n"
                    "tags: [research]\nstate: active\ncreated: 2026-05-01\n---\n"
                    "# Alpha\n\n## Summary\nNew summary.\n\n## Access\nLocal.\n\n## Context\n- Old context.\n- New.\n\n## Relations\n")
        path, stage = self.stage([self.record()], [("_entities/alpha.md", migrated)])
        with self.assertRaises(ValueError) as caught:
            self.library.validate(path)
        for loss in ("aliases", "tags: reading", "Old summary.", "- uses:: [[Beta]]"):
            self.assertIn(loss, str(caught.exception))
        self.assertNotIn("state", str(caught.exception))
        stage["files"][0]["drops"] = [{"item": item, "reason": "superseded in review"} for item in
                                      ("aliases", "tags: reading", "Old summary.", "- uses:: [[Beta]]")]
        atomic_json(path, stage)
        self.library.validate(path)

    def test_interrupted_multifile_recovery_and_independent_publication(self):
        event = self.record()
        path, stage = self.stage([event], [("_entities/alpha.md", entity("Alpha", "ent_alpha")),
                                         ("_entities/beta.md", entity("Beta", "ent_beta"))])
        with self.assertRaises(RuntimeError):
            self.library.apply(path, fault_after=1)
        self.assertTrue((self.vault / "_entities/alpha.md").exists())
        self.assertFalse((self.vault / "_entities/beta.md").exists())
        self.assertEqual(len(self.library.pending()), 1)
        receipt = self.library.recover(stage["run_id"])
        self.assertEqual(receipt["status"], "complete")
        self.assertEqual((self.vault / "_entities/beta.md").read_text(), entity("Beta", "ent_beta"))
        self.assertEqual(self.library.pending(), [])
        self.assertFalse((self.vault / "_state/publication").exists())

    def test_human_edit_stops_recovery(self):
        event = self.record()
        path, stage = self.stage([event], [("_entities/alpha.md", entity("Alpha", "ent_alpha")),
                                         ("_entities/beta.md", entity("Beta", "ent_beta"))])
        with self.assertRaises(RuntimeError):
            self.library.apply(path, fault_after=1)
        alpha = self.vault / "_entities/alpha.md"
        alpha.write_text(alpha.read_text() + "Later human edit")
        with self.assertRaisesRegex(ValueError, "human or concurrent edit"):
            self.library.recover(stage["run_id"])
        self.assertIn("Later human edit", alpha.read_text())
        self.assertFalse((self.vault / "_entities/beta.md").exists())
        self.assertEqual(len(self.library.pending()), 1)

    def test_stale_staging_and_missing_evidence(self):
        target = self.vault / "_entities/alpha.md"
        target.parent.mkdir()
        target.write_text(entity("Alpha", "ent_alpha", history="Old history.\n"))
        event = self.record()
        path, stage = self.stage([event], [("_entities/alpha.md", entity("Alpha", "ent_alpha", 2,
                                                                        history="Old history.\n", extra="New.\n"))])
        target.write_text(target.read_text() + "Human edit")
        with self.assertRaisesRegex(ValueError, "Stale"):
            self.library.apply(path)
        target.write_text(entity("Alpha", "ent_alpha", history="Old history.\n"))
        stage["outcomes"][0]["evidence"][0]["path"] = "_events/nonexistent/body.md"
        atomic_json(path, stage)
        with self.assertRaisesRegex(ValueError, "Evidence"):
            self.library.apply(path)

    def test_blocked_attempt_remains_pending_and_can_retry(self):
        event = self.record()
        path, _ = self.stage([event], outcome="blocked", reason="Source unavailable")
        receipt = self.library.apply(path)
        self.assertEqual(receipt["status"], "complete")
        self.assertEqual(len(self.library.pending()), 1)
        retry, _ = self.stage([event], outcome="recorded_only", reason="Keep the reference")
        self.library.apply(retry)
        self.assertEqual(self.library.pending(), [])

    def test_receipt_corruption_is_explicit(self):
        event = self.record()
        path, _ = self.stage([event], outcome="recorded_only", reason="Reference only")
        receipt = self.library.apply(path)
        (self.vault / receipt["outcome_receipts"][0]).write_text("{}")
        with self.assertRaisesRegex(ValueError, "corrupt"):
            self.library.pending()

    def test_actual_evidence_anchors_and_frozen_files(self):
        identifier = "12345678-1234-1234-1234-123456789abc"
        event = self.record(body="## Decision\nAn idea\n", raw={"blocks": [
            {"object": "block", "id": identifier, "type": "paragraph", "paragraph": {}}]})
        path, stage = self.stage([event], [("_entities/alpha.md", entity("Alpha", "ent_alpha"))])
        reference = stage["outcomes"][0]["evidence"][0]
        for anchor in ("L1-L2", "section:Decision"):
            reference["anchor"] = anchor
            atomic_json(path, stage)
            self.library.validate(path)
        for anchor in ("L3", "L2-L1", "section:Missing", "vague claim"):
            reference["anchor"] = anchor
            atomic_json(path, stage)
            with self.assertRaisesRegex(ValueError, "anchor"):
                self.library.validate(path)
        frozen = read_json(stage["freeze_path"])
        reference.update(path=event["raw_path"], sha256=frozen["evidence"][event["raw_path"]],
                         anchor="block:" + identifier)
        atomic_json(path, stage)
        self.library.validate(path)
        reference["anchor"] = "block:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
        atomic_json(path, stage)
        with self.assertRaisesRegex(ValueError, "anchor"):
            self.library.validate(path)

    def test_consumed_key_requires_explicit_current_base_reconciliation(self):
        event = self.record()
        original, _ = self.stage([event], [("_entities/alpha.md", entity("Alpha", "ent_alpha", extra="Original evidence.\n"))])
        self.library.apply(original)
        repeat, _ = self.stage([event], outcome="recorded_only", reason="Rerun")
        with self.assertRaisesRegex(ValueError, "Already consumed"):
            self.library.apply(repeat)
        correction, stage = self.stage([event], [("_entities/alpha.md", entity("Alpha", "ent_alpha", 2,
                history="Original evidence.\n", extra="Supersession following human correction.\n"))])
        pointer = read_json(self.vault / f"_state/consumption/settle/{event['event_id']}/{event['revision']}.json")
        stage["outcomes"][0].update(prior_receipt_sha256=pointer["sha256"],
                                     reconciliation="Preserve old evidence and append the human correction")
        atomic_json(correction, stage)
        self.library.apply(correction)
        text = (self.vault / "_entities/alpha.md").read_text()
        self.assertEqual(text.count("Original evidence."), 1)
        self.assertIn("Supersession following human correction.", text)
        self.assertEqual(self.library.pending(), [])

    def test_record_repairs_current_pointer_after_revision_install(self):
        event = self.record()
        (self.vault / f"_events/{event['event_id']}/event.json").unlink()
        (self.vault / f"_events/{event['event_id']}/event.md").unlink()
        adopted = self.record()
        self.assertEqual(adopted, event)
        self.assertEqual(read_json(self.vault / f"_events/{event['event_id']}/event.json"), event)

    def test_nonblocking_writer_lock_excludes_second_writer(self):
        with writer_lock(self.vault):
            with self.assertRaises(BlockingIOError):
                with writer_lock(self.vault, wait_seconds=0):
                    pass

    def test_waiting_writer_enters_after_active_writer_releases(self):
        result = []

        def wait_for_lock():
            with writer_lock(self.vault, wait_seconds=1):
                result.append("entered")

        with writer_lock(self.vault):
            waiter = threading.Thread(target=wait_for_lock)
            waiter.start()
            time.sleep(0.05)
            self.assertTrue(waiter.is_alive())
        waiter.join(timeout=2)
        self.assertEqual(result, ["entered"])

    def test_record_waits_out_a_brief_background_writer(self):
        released = threading.Event()

        def background_commit():
            with writer_lock(self.vault):
                released.wait(1)
                time.sleep(0.3)

        holder = threading.Thread(target=background_commit)
        holder.start()
        time.sleep(0.05)
        released.set()
        self.assertEqual(self.record()["revision"], 1)
        holder.join(timeout=2)

    def test_receipt_window_crash_stays_pending_until_final_run_receipt(self):
        event = self.record()
        path, stage = self.stage([event], [("_entities/alpha.md", entity("Alpha", "ent_alpha"))])
        final_path = self.vault / f"_runs/{stage['run_id']}/receipt.json"
        original_atomic = atomic_json

        def interrupt_final(path, value):
            if Path(path).resolve() == final_path.resolve():
                raise RuntimeError("Final run receipt interruption")
            return original_atomic(path, value)

        with patch("mylibrary.storage.atomic_json", side_effect=interrupt_final):
            with self.assertRaisesRegex(RuntimeError, "Final run receipt"):
                self.library.apply(path)
        self.assertTrue((self.vault / "_entities/alpha.md").exists())
        self.assertFalse(final_path.exists())
        self.assertEqual(len(self.library.pending()), 1)
        self.assertEqual(self.library.status()["incomplete_runs"], [stage["run_id"]])
        with self.assertRaisesRegex(ValueError, "Recover unfinished"):
            self.library.backup(self.root / "partial-backup")
        self.library.recover(stage["run_id"])
        self.assertEqual(self.library.pending(), [])
        self.assertEqual((self.vault / "_entities/alpha.md").read_text(), entity("Alpha", "ent_alpha"))

    def test_preserve_context_identity_and_global_duplicates(self):
        target = self.vault / "_entities/alpha.md"
        target.parent.mkdir()
        target.write_text(entity("Alpha", "ent_alpha", history="Old evidence.\n"))
        event = self.record()
        path, stage = self.stage([event], [("_entities/alpha.md", entity("Alpha", "ent_alpha", 2, extra="Lost old text"))])
        with self.assertRaisesRegex(ValueError, "Context"):
            self.library.validate(path)
        Path(stage["files"][0]["staged_path"]).write_text(entity("Alpha", "ent_changed", 2, history="Old evidence.\n"))
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.library.validate(path)
        other, _ = self.stage([event], [("_entities/beta.md", entity("Beta", "ent_alpha"))])
        with self.assertRaisesRegex(ValueError, "Duplicate global"):
            self.library.validate(other)

    def test_legacy_migration_without_events_is_explicit(self):
        target = self.vault / "_entities/legacy.md"
        target.parent.mkdir()
        target.write_text("---\naliases: [Legacy]\n---\n## Summary\nOlder.\n## Access\nLocal.\n## Context\nHistorical context.\n## Relations\n")
        migrated = entity("Legacy", "ent_legacy", history="Historical context.\n").replace(
            "revision: 1\n", "revision: 1\naliases: [Legacy]\n").replace("Summary.", "Older.")
        path, stage = self.stage([], [("_entities/legacy.md", migrated)])
        with self.assertRaisesRegex(ValueError, "migration"):
            self.library.validate(path)
        stage["purpose"] = "migration"
        atomic_json(path, stage)
        self.library.apply(path)
        self.assertIn("Historical context.", target.read_text())

    def test_path_and_symlink_escape_are_rejected(self):
        event = self.record()
        for path in ("../outside.md", "META/spec.md", "_personal/private.md", "_entities/nested/a.md"):
            stage_path, stage = self.stage([event], [("_entities/alpha.md", entity("Alpha", "ent_alpha"))])
            stage["files"][0]["path"] = path
            atomic_json(stage_path, stage)
            with self.assertRaises(ValueError):
                self.library.validate(stage_path)
        entities = self.vault / "_entities"
        entities.mkdir(exist_ok=True)
        stage_path, stage = self.stage([event], [("_entities/beta.md", entity("Alpha", "ent_alpha"))])
        (entities / "alpha.md").symlink_to(self.root / "outside.md")
        with self.assertRaisesRegex(ValueError, "symlink|Symlink"):
            self.library.validate(stage_path)

    def test_backup_restores_authoritative_files_and_excludes_private_index(self):
        event = self.record(attachments=[{"id": "pdf", "content": b"pdf evidence"}])
        path, _ = self.stage([event], [("_entities/alpha.md", entity("Alpha", "ent_alpha"))])
        self.library.apply(path)
        for folder in ("_personal", "_index"):
            (self.vault / folder).mkdir()
            (self.vault / folder / "hidden.txt").write_text("not included")
        atomic_json(self.vault / "_state/notion/entity-map.json", {"ent_alpha": {"page_id": "mapped"}})
        backup = self.root / "backup"
        manifest = self.library.backup(backup)
        restored = self.root / "restored"
        shutil.copytree(backup, restored)
        restored_library = Library(restored)
        self.assertEqual(restored_library.pending(), [])
        self.assertEqual(read_json(restored / "_state/notion/entity-map.json")["ent_alpha"]["page_id"], "mapped")
        self.assertEqual((restored / event["attachments"][0]["path"]).read_bytes(), b"pdf evidence")
        for relative, sha in manifest["files"].items():
            self.assertEqual(digest(restored / relative), sha)
        self.assertFalse((restored / "_personal").exists())
        self.assertFalse((restored / "_index").exists())
        self.assertFalse((backup / "_state/writer.lock").exists())

    def test_inherited_lock_uses_matching_inode_and_does_not_release_parent(self):
        previous = os.environ.get("MYLIBRARY_WRITER_LOCK_FD")
        with writer_lock(self.vault) as descriptor:
            os.environ["MYLIBRARY_WRITER_LOCK_FD"] = str(descriptor)
            try:
                with writer_lock(self.vault):
                    self.assertTrue((self.vault / "_state/writer.lock").exists())
                other = self.root / "other"
                other.mkdir()
                (other / "_state").mkdir()
                (other / "_state/writer.lock").touch()
                with self.assertRaisesRegex(ValueError, "does not match"):
                    with writer_lock(other):
                        pass
            finally:
                if previous is None:
                    os.environ.pop("MYLIBRARY_WRITER_LOCK_FD", None)
                else:
                    os.environ["MYLIBRARY_WRITER_LOCK_FD"] = previous


if __name__ == "__main__":
    unittest.main()
