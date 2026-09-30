# Runtime storage and staging reference

The installed `mylibrary` command uses the shared Python package. Storage schema version 1 is separate from release version 3.0.0.

## Durable layout

```text
_entities/<name>.md
_events/<event_id>/{event.json,event.md}
_events/<event_id>/revisions/<revision>/{event.json,body.md,raw.json}
_sources/<source_id>/source.json
_sources/<source_id>/snapshots/<revision>/{body.md,raw.json,coverage.json}
_sources/<source_id>/attachments/<sha256>
_state/library.json
_state/notion/{setup.json,entity-map.json,acquisition.json,last-publish.json}
_state/consumption/<consumer>/<event_id>/<revision>.json
_runs/<run_id>/frozen.json
_runs/<run_id>/apply/{journal.json,files/<number>}
_runs/<run_id>/outcomes/<consumer>/<event_id>/<revision>.json
_runs/<run_id>/receipt.json
_index/
```

A source with `role: reference` in `source.json` is a Notion page that an Event mentions or links. `collect` snapshots it once per edit and records `referenced_by`. It has no Event, is never pending, and never counts as a user decision. Read it from `body_path`. `search --scope sources` finds it. A reference that `collect` cannot read is reported as `unavailable`, not as absent.

`provider`, `workspace_id`, and `resource_id` determine Event identity. Identical text on separate resources stays separate. Integer revisions identify immutable normalized evidence. Semantic changes include body, user properties, mention IDs, and actual attachment hashes. Signed file URLs, editor timestamps, and collector bookkeeping do not establish new knowledge.

`_index/` is rebuildable. Backup includes durable Entity, Event, source, and state files plus completed run artifacts. It excludes incomplete runs and the lock artifact. Recover incomplete work before claiming a backup covers its outputs and receipts.

## Freeze

`mylibrary freeze --output /tmp/run/frozen.json --consumer settle` writes outside the vault. Its fields are `schema_version`, `run_id`, `consumer`, `method_version`, `created_at`, `events`, `evidence`, and `baseline`.

`events` contains selected revision records with `frozen_hashes`. `evidence` maps vault-relative artifact paths to full-file SHA-256 values. `baseline` maps formal Entity paths to frozen hashes. A new Entity has a null base hash in staging.

## Staging manifest

Staging is a JSON file outside the vault. Complete replacement Markdown files also stay outside the vault. Copy identity and method fields from the real freeze. Replace this example's placeholder values.

```json
{
  "schema_version": 1,
  "run_id": "run_example",
  "consumer": "settle",
  "method_version": "lib-settle/3",
  "freeze_path": "/tmp/run/frozen.json",
  "freeze_sha256": "FULL_SHA256_OF_FROZEN_JSON_BYTES",
  "files": [
    {
      "path": "_entities/pilot.md",
      "base_sha256": null,
      "staged_path": "/tmp/run/pilot.md"
    }
  ],
  "outcomes": [
    {
      "event_id": "evt_example",
      "revision": 1,
      "outcome": "integrated",
      "entity_ids": ["ent_pilot"],
      "files": ["_entities/pilot.md"],
      "evidence": [
        {
          "path": "_events/evt_example/revisions/1/body.md",
          "sha256": "FULL_SHA256_FROM_FROZEN_EVIDENCE",
          "anchor": "L1-L4"
        }
      ]
    }
  ]
}
```

Entity frontmatter requires nonempty `id`, `name`, `type`, and `description`, plus positive integer `revision`. Retain `Summary`, `Access`, `Context`, and `Relations`. IDs are immutable. An existing migrated Entity increments its revision once. A new or explicitly bootstrapped legacy Entity starts at revision 1. Preserve prior Context evidence.

An evidence reference has `path`, `sha256`, and `anchor`. Its hash covers the exact frozen artifact bytes. Accepted anchors are `L1`, `L1-L4`, `section:<exact heading>`, and `block:<UUID>`. The referenced lines, heading, or block must exist in that frozen artifact. Validation verifies the hash and anchor existence. Semantic review verifies support for the claim. A title, homepage link, or invented anchor is insufficient.

`recorded_only` requires `reason` and no formal writes. `blocked` and `needs_review` require an empty `files` list and remain pending. State the missing evidence or unresolved decision. Every output is referenced by an outcome. Every frozen Event key has one outcome.

Each `integrated` outcome includes evidence from its own Event revision's `frozen_hashes`. References to other Events alone are insufficient. If that Event has partial coverage, include a nonempty `coverage_ack` explaining why the missing material cannot change this conclusion. Without that explanation, validation rejects integration. If the gap affects the conclusion, use `blocked` instead.

A staged replacement keeps every earlier frontmatter field, every earlier list value, and every earlier nonempty body line. To remove or rewrite one, add `"drops": [{"item": "<field>" | "<field>: <value>" | "<exact line>", "reason": "<why>"}]` to that file entry. Validation names each undeclared loss and rejects the write. Changing a scalar value such as `state` is an update, not a loss.

Pilot bootstrap without Event inputs uses `purpose: "migration"`. Reconciliation of an already consumed revision requires `prior_receipt_sha256` and nonempty `reconciliation`. Neither option authorizes full historical migration.

## Apply and recovery

`mylibrary validate <staging>` checks frozen evidence, anchors, paths, identities, base hashes, outcomes, and prior receipts. `mylibrary apply <staging>` rechecks under the shared writer lock and journals desired bytes before replacements. Multi-file apply is recoverable, not one atomic filesystem operation.

A completed run receipt follows all required outputs and outcome receipts. Only receipt-backed successful outcomes establish consumption. Missing or corrupt receipt state remains unresolved. Repeating a completed run returns its receipt without appending Context again.

`mylibrary recover <run_id>` compares current files with before and desired hashes. Desired matches are already applied. Before matches can receive staged bytes. Any third hash stops recovery for human-edit reconciliation. Recovery does not roll back human corrections.

## Publication

Publication has separate mapping and attempt records. Each local Entity ID maps to one fixed Notion page. Compare the remote page with the last verified publication before updating. Human edits block replacement until reconciled. Read back properties and body before recording success.

After an uncertain create response, query the configured Entities data source by exact Entity ID. One verified match can be adopted. Multiple matches block. Zero matches after uncertainty remain uncertain; do not create again blindly. Failed publication never reopens semantic consumption or reruns apply.

## CLI surface

```text
mylibrary status
mylibrary doctor [--offline]
mylibrary capture <file> [--name <name>] [--resource-id <id>] [--mode result|detail]
mylibrary capture-url <GitHub-url> [--mode cache|if-stale|live]
mylibrary collect
mylibrary pending [--consumer settle]
mylibrary freeze --output <path> [--consumer settle]
mylibrary validate <staging>
mylibrary apply <staging>
mylibrary recover <run_id>
mylibrary index
mylibrary search <query> [--scope personal|entities|sources|all] [--limit 5]
mylibrary resolve <ref>
mylibrary neighbors <id> [--predicate <type>] [--direction incoming|outgoing|both]
mylibrary source-open <ref> --mode cache|if-stale|live|historical [--revision <revision>]
mylibrary publish [--entity <id>]
mylibrary setup --main <existing-MyLibrary-page-id-or-URL> [--dry-run]
mylibrary setup --parent <parent-id-or-URL> [--dry-run]
mylibrary backup --output <path>
```

Cache and historical reads use retained snapshots. Notion `if-stale` uses a fresh retained cache for 300 seconds without a network read. An older snapshot triggers a source check. Live reads require access. Setup `--main` adopts the exact existing MyLibrary page; `--parent` creates a new MyLibrary child under another page. Dry-run renders the chosen target and layout without remote writes. It does not verify access, Notion UI, or mobile capture. Backup uses a new directory outside the vault with a hash manifest.

The optional global `--vault <path>` selects a fixture or explicit vault. Search, resolve, and neighbors preserve authoritative knowledge while refreshing rebuildable caches when needed. Every manual collection fully paginates the configured input data sources. It does not use the source-read freshness cache to skip input pages.
