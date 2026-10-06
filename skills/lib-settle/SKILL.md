---
name: lib-settle
description: >
  Integrate pending MyLibrary Event revisions into stable Entities through a
  frozen source pack, staging, validation, and recoverable apply, or capture
  the current agent session and settle it at once. Use for "settle", "settle
  today", "settle all unprocessed", "export", "导出", "总结一下", "export
  result", "export detail", "记录过程", or historical forward and reverse reads.
metadata:
  runtime: mylibrary-tools>=3.7.0
---

# Integrate pending Events

The input unit is an Event revision, not a daily heading. Multiple Events may update the same Entity. One Event may support several Entities. Preserve original evidence and human corrections.

## Process a frozen batch

1. Run `mylibrary status`. If Notion input is configured, run `mylibrary collect`. A failed collection is a coverage gap, not an empty successful scan.
2. Run `mylibrary freeze --output "$(mktemp -d)/frozen.json" --consumer settle` so runs never share a freeze file. Read its Event identities and coverage before loading bodies.
3. For each input, first run `mylibrary resolve <page_id>` on every ID in its `mentions`. A resolved mention is a hard match and needs no broad candidate scan. Otherwise compare three to five Entity descriptions with `mylibrary search <topic> --scope entities --limit 5`. Resolve IDs, mappings, and aliases before opening selected bodies.
4. Load the matching section of [source-playbooks.md](references/source-playbooks.md). Open only the required frozen artifacts and relevant typed neighbors. Give a reason before a second relation hop.
5. Prepare complete Entity replacement files and one staging manifest outside the vault. Preserve Summary, Access, Context, Relations, types, and prior evidence. Use [runtime-schema.md](references/runtime-schema.md) and [consumer-interface.md](references/consumer-interface.md).
6. Give each frozen Event one outcome. Each integration cites its own frozen Event evidence. Partial coverage requires `coverage_ack` explaining why the gap cannot affect the conclusion. Otherwise use `blocked`; uncertain identity uses `needs_review`. Neither outcome authorizes files. A necessary no-write outcome is `recorded_only` with a reason.
7. For each actionable statement in an Event (a task, 「回头看看」, something Wayne will do, a deadline), run `mylibrary todo-add "<text>" --event <id> --revision <n> --anchor <L..> [--due YYYY-MM-DD] [--entity <id>]`. Anchor it to the earliest revision that contains the sentence, so its day is when Wayne wrote it. Keep Wayne's wording, set `--due` only when he gave a date, and skip vague wishes and finished work. It is idempotent, so a later revision repeating the sentence adds nothing. Never change an existing TODO; its status, time and text belong to Wayne in Notion. Then run `mylibrary validate <staging>`, then `mylibrary apply <staging>`. Report successful, pending, and blocked Event revisions separately.
8. Run `mylibrary index`, then `mylibrary publish` with no `--entity`. It writes the changed Entities, refreshes pages whose links now point to a newly published Entity, and skips the rest. Publication failure does not rerun apply.
9. Run `mylibrary worklog --run <run_id>`. It rewrites the `## Settle Log · 回执 #ai-generated` section of each affected day in `工作记录/` from receipts, creating the day file if needed. Give each `integrated` outcome a `summary` in staging so the log says what changed. Write `summary` and `reason` as one short line in the language of Wayne's work log, without IDs a reader cannot use. Do not hand-edit that section.

An interrupted apply uses `mylibrary recover <run_id>`. A human-edited base blocks replacement and requires a new proposal from that base. Only successful outcomes backed by the completed apply receipt count as consumed.

## Capture and settle this session

For "export" or "导出", record the current session as a bounded Event, then settle only that Event.

1. Write temporary Markdown outside `~/MyLibrary` in the session's language and voice. Result mode, the default, records decisions, outcomes, measurements, artifacts, and open work. Detail mode, on request for process or discussion, adds important reasoning changes and exact user quotes with context. Preserve artifact URLs and source identities. Exclude credentials and routine tool chatter. Nothing substantive means no capture.
2. Run `mylibrary capture <file> --name <session-name> --resource-id <stable-session-id> --mode result` or `--mode detail`. Reuse the resource ID on retry; a semantic change becomes a new revision.
3. Write `[["<event_id>", <revision>]]` to a keys file and run `mylibrary freeze --output "$(mktemp -d)/frozen.json" --consumer settle --keys <file>`.
4. Continue from step 3 of the batch above for that single Event, through publish and `mylibrary worklog`.

Do not claim a behavior was tested when only its code or API response was inspected.

## Read historical work

An explicit date or reverse-settle request may inspect old work logs and repository commits. Use the 04:00 logical day boundary. Load [reverse-scan.md](references/reverse-scan.md) only for repository discovery. Preserve author filtering, all-ref reads, and worktree dedup.

Capture the selected historical evidence as a bounded Event before new integration, with `--occurred-at <YYYY-MM-DD>` set to the day it was written so the work log places it there. Do not scan all history by default. A heading, backlink, legacy Settle Log, or scanner `seen` entry does not skip a pending Event. Migrate a legacy Entity only when this settle writes it.

Semantic Entity decisions use `lib-entity` rules within the same proposal. Do not run a second direct-write extraction pass after apply. Load [skill-conventions.md](references/skill-conventions.md) when a write boundary matters.

The shared `mylibrary` runtime is required even for a single-skill install. Do not write vault META mirrors or read `_personal/` without an explicit request.
