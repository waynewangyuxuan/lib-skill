---
name: lib-settle
description: >
  Integrate pending MyLibrary Event revisions into stable Entities through a
  frozen source pack, staging, validation, and recoverable apply. Use for
  "settle", "settle today", "settle all unprocessed", or explicit historical
  forward and reverse reads.
---

# Integrate pending Events

The input unit is an Event revision, not a daily heading. Multiple Events may update the same Entity. One Event may support several Entities. Preserve original evidence and human corrections.

## Process a frozen batch

1. Run `mylibrary status`. If Notion input is configured, run `mylibrary collect`. A failed collection is a coverage gap, not an empty successful scan.
2. Run `mylibrary freeze --output /tmp/lib-run/frozen.json --consumer settle`. Read its Event identities and coverage before loading bodies.
3. For each input, compare three to five Entity descriptions with `mylibrary search <topic> --limit 5`. Resolve IDs, mappings, and aliases before opening selected bodies.
4. Load the matching section of [source-playbooks.md](references/source-playbooks.md). Open only the required frozen artifacts and relevant typed neighbors. Give a reason before a second relation hop.
5. Prepare complete Entity replacement files and one staging manifest outside the vault. Preserve Summary, Access, Context, Relations, types, and prior evidence. Use [runtime-schema.md](references/runtime-schema.md) and [consumer-interface.md](references/consumer-interface.md).
6. Give each frozen Event one outcome. Each integration cites its own frozen Event evidence. Partial coverage requires `coverage_ack` explaining why the gap cannot affect the conclusion. Otherwise use `blocked`; uncertain identity uses `needs_review`. Neither outcome authorizes files. A necessary no-write outcome is `recorded_only` with a reason.
7. Run `mylibrary validate <staging>`, then `mylibrary apply <staging>`. Report successful, pending, and blocked Event revisions separately.
8. Run `mylibrary index`. Publish affected pilot Entities with `mylibrary publish --entity <id>` when publication is in scope. Publication failure does not rerun apply.

An interrupted apply uses `mylibrary recover <run_id>`. A human-edited base blocks replacement and requires a new proposal from that base. Only successful outcomes backed by the completed apply receipt count as consumed.

## Read historical work

An explicit date or reverse-settle request may inspect old work logs and repository commits. Use the 04:00 logical day boundary. Load [reverse-scan.md](references/reverse-scan.md) only for repository discovery. Preserve author filtering, all-ref reads, and worktree dedup.

Capture the selected historical evidence as a bounded Event before new integration. Do not scan all history by default. A heading, backlink, legacy Settle Log, or scanner `seen` entry does not skip a pending Event. Migrate only the pilot Entities.

Semantic Entity decisions use `lib-entity` rules within the same proposal. Do not run a second direct-write extraction pass after apply. Load [skill-conventions.md](references/skill-conventions.md) when a boundary or legacy folder contract matters.

The shared `mylibrary` runtime is required even for a single-skill install. Do not write vault META mirrors or read `_personal/` without an explicit request.
