# lib-settle — Bidirectional Stream ↔ Entity Distribution

Forward (stream → entity storage) + reverse (entity storage → stream). After settle, invoke lib-entity for entity extraction.

**Vault**: `~/MyLibrary`
**Private stdlib**: `stdlib/settle-engine.md` — entity-first matching + consumer execution rules. Read before executing.

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

Scan entity storage folders for new content not in today's work log, write AI summaries back.

1. **Scan entities**: For active workstream entities, check their storage folders for files created/modified on {date}. Also check Access for repo commits.
2. **Filter**: Skip entities already mentioned in work log.
3. **Write to work log**: `## [[{entity}]] #ai-generated` with summary + backlinks.

## After Both Phases: Invoke lib-entity

After settle completes, invoke `lib-entity` on today's work log to extract and update entities. This is a separate intelligence — see lib-entity SKILL.md.

## Constraints

- Settle log entries go in ONE consolidated section at bottom
- `#ai-generated` tag mandatory on all AI-written content
- Idempotency: skip sections already in Settle Log
- Unmatched sections: report for human, don't create files
