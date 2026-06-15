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
4. **Write consolidated settle log**: Append to `## Settle Log #ai-generated` at bottom of work log. One `→ 已沉淀到 [[entity-name]]` per settled section. Don't duplicate existing entries.

**Then proceed to Phase 2.**

## Phase 2: Reverse Settle

Find work that happened on {date} but isn't in the work log. Two sources: vault diff and external resources.

1. **Vault diff**: `git diff` between day-start and day-end snapshots. Group changed files by entity (file path → entity storage folder or entity page). Ignore vault infra (`.obsidian/`, `.claude/`, `_folder.compiled.yaml`, etc.).
2. **External repos**: For active entities with repo paths in Access, `git diff` or `git log --since/--until` on those repos.
3. **Work log links**: Probe links mentioned in the work log (URLs, repo refs) for context that enriches the log entry.
4. **Filter**: Skip entities already covered in the work log (mentioned by name or wikilink).
5. **Write to work log**: `## [[{entity}]] #ai-generated` with summary of unreported changes.

Resource access is currently git + HTTP. Future: per-resource-type accessors (feishu CLI, etc.) configurable via entity Access.

## After Both Phases: Invoke lib-entity

After settle completes, invoke `lib-entity` on today's work log to extract and update entities. This is a separate intelligence — see lib-entity SKILL.md.

## Constraints

- Settle log entries go in ONE consolidated section at bottom
- `#ai-generated` tag mandatory on all AI-written content
- Idempotency: skip sections already in Settle Log
- Unmatched sections: report for human, don't create files
