# Settle Engine — Entity-First Matching + Consumer Execution

## Part 1: Entity Resolution

For each `## heading`, find target entity. Stop at first match.

`##` headings are the **settle consumption boundary**. Deeper headings (`###`, `####`) are nested content under the current settle target; do not create separate settle log entries for them. However, nested headings are still entity candidates for lib-entity extraction, especially when paired with a GitHub/paper/service URL or explicit relevance language.

**Priority 1 — Wikilink**: Extract `[[target]]` from heading → find matching entity page in `_entities/`. File name match (case-insensitive).

**Priority 2 — Entity aliases**: Check heading text against `aliases:` in entity page frontmatter (case-insensitive substring). Entity file name is implicit alias. Multiple matches → prefer longest alias.

**Priority 3 — Fuzzy**: Claude's judgment against known entity names. Low confidence → unmatched.

**No match** → report for user, don't create files or backlinks.

### From entity to storage folder

Once entity is matched:
1. Read entity page's `## Access` section
2. Extract storage folder path (e.g., "Storage folder: EvoGraph/")
3. If no explicit storage path → infer from entity name (look for matching folder in vault)
4. If no folder exists → content goes only to entity page Context (no file creation)

## Part 2: Consumer Execution

### Resolve consumer
Read `settle.consumer` from storage folder's `_folder.compiled.yaml`. Absent → vault default `notes`. No storage folder → skip consumer, entity page update only.

### Consumer: `notes`
Target path: `settle.target` from config, fallback `日志/{project}-{M-DD}.md`.
- Multi-dimension: if `settle.dimensions` defined, match content to dimension by context (meeting → Meetings/, experiment → Experiments/, default → Notes/)
- File doesn't exist → create with frontmatter (`created`, `tags: [settled]`, `source`)
- File exists → append with `> [!info]- 沉淀自 工作记录 {date}` callout
- Backlink: `→ 已沉淀到 [[{entity-name}]]`

### Consumer: `feature-room`
For entities with META/. Triage: spec-worthy → fr-ingest to META (as `state: draft`), always save full section to `notes/{YYYY-MM-DD}-{slug}.md`.
- Backlink includes both META and notes targets

### Consumer: `skip`
Do nothing. Report "skipped (consumer: skip)".

### Custom consumer
Read `## Settle Consumer: {name}` in storage folder's `_folder.md`. Natural language definition = prompt. Can't determine → fall back to parent consumer.

## Part 3: Idempotency

- Primary: `## Settle Log` already has `→ 已沉淀到` matching this section's entity
- Legacy: section body has inline `→ 已沉淀到`
- Behavior: skip entirely, no re-copy

## Part 4: Nested Entity Promotion

After consumer execution, scan the full settled section body for nested entity candidates:

- Heading candidates: `### Name` / `#### Name`
- Link candidates: `[name](https://github.com/...)`, paper URLs, service URLs, local repo paths
- Relevance signals: "高度相关", "重要参考", "prior art", "similar to", "inspired by", "Frederick's question", repeated mention, or use as a style/reference source

If a nested candidate is unresolved and has both a heading/name and an external identifier (repo, paper, service URL), create an entity page through lib-entity and convert the nested heading or first mention to a wikilink. Keep the parent section's settle backlink unchanged.
