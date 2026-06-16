---
name: lib-settle
description: >
  Use for MyLibrary bidirectional settle workflows: distribute work-log stream
  content into entity storage, reverse-settle unlogged vault/repo changes, and
  invoke lib-entity afterward. Triggers include "settle today", "settle all
  unprocessed", "settle forward", and "settle reverse".
---

# lib-settle — Bidirectional Stream ↔ Entity Distribution

Forward (stream → entity storage) + reverse (entity storage → stream). After settle, invoke lib-entity for entity extraction.

**Vault**: `~/MyLibrary`
**Shared stdlib**: `../_stdlib/consumer-interface.md` and `../_stdlib/skill-conventions.md` — entity-first matching + consumer execution rules. Read before executing.

## Triggers

- "settle today" / "settle {date}" — both phases + entity extraction
- "settle forward {date}" / "settle reverse {date}" — single phase
- "settle all unprocessed"

## Phase 1: Forward Settle

1. **Resolve work log**: Map date to `工作记录/{Month}/{YYYY-M-D}.md`. 4am day boundary: before 4am = yesterday.
2. **Parse sections**: Split by `## ` headings. Skip preamble and `## Settle Log`. No headings → stop.
3. **For each section**: Follow settle-engine.md — entity resolution → find storage folder → resolve consumer → execute → collect backlink.
4. **Nested entity extraction**: `###`/deeper headings, inline links, and relevance language inside a section do **not** become separate settle targets, but they are entity candidates. lib-entity owns this rule — see its Nested Heading Promotion (the full section body is passed to lib-entity in "After Both Phases").
5. **Write consolidated settle log**: Append to `## Settle Log #ai-generated` at bottom of work log. One `→ 已沉淀到 [[entity-name]]` per settled section. Don't duplicate existing entries.

**Then proceed to Phase 2.**

## Phase 2: Reverse Settle

Find work that happened on {date} but isn't in the work log. Sources: vault diff, external repos, work-log links.

**Scan fans out (read side).** Steps 1–3 are independent reads — fan out one subagent per source per `_stdlib/skill-conventions.md` Orchestration (map-reduce distillation): each returns a bounded, provenance-anchored temp artifact in `/tmp/lib-run-{date}/`, not raw diffs. The main agent reads the reduced top.

1. **Vault diff**: `git diff` between day-start and day-end snapshots. Group changed files by entity (file path → entity storage folder or entity page). Ignore vault infra (`.obsidian/`, `.claude/`, `_folder.compiled.yaml`, etc.).
2. **External repos**: For active entities with repo paths in Access, `git diff` / `git log --since/--until`. One subagent per repo.
3. **Work log links**: Probe links mentioned in the work log (URLs, repo refs) for enriching context.
4. **Filter**: Skip entities already covered in the work log (mentioned by name or wikilink).
5. **Write to work log — single writer (write side).** One serial writer holds the work log's live `##`/`###` tree. Per unreported entity: **if a `## [[entity]]` section already exists, append into it — never open a second `## [[entity]]`**; if a matching `###` child exists, append there; mint `## [[entity]]` only when no section for it exists. Follow the note's existing flow; tag AI content `#ai-generated`. (See skill-conventions Write side.)

Resource access is currently git + HTTP. Future: per-resource-type accessors (feishu CLI, etc.) configurable via entity Access.

## After Both Phases: Invoke lib-entity

After settle completes, invoke `lib-entity` on today's work log to extract and update entities. This is a separate intelligence — see lib-entity SKILL.md.
When invoking lib-entity, pass the whole work log/settled sections, not only top-level headings, so nested headings and externally linked artifacts are eligible for entity promotion.

## Constraints

- Settle log entries go in ONE consolidated section at bottom
- `#ai-generated` tag mandatory on all AI-written content
- Idempotency: skip sections already in Settle Log
- Unmatched sections: report for human, don't create files
