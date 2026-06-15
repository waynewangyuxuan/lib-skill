---
name: lib-entity
description: >
  Use for MyLibrary entity extraction and management: resolve, create, update,
  tag, promote, and source-check entities in ~/MyLibrary/_entities. Also use
  when asked to extract entities, check sources, or after settle/review needs
  entity graph updates.
---

# lib-entity — Entity Extraction & Management

Extract, resolve, create, update entities, and check sources. A standalone intelligence that can be invoked by settle, review, or directly.

**Vault**: `~/MyLibrary`
**Entity registry**: `~/MyLibrary/_entities/`
**Tag registry**: `~/MyLibrary/_entities/_tags.yaml`

## Triggers

- "extract entities from {file}" — run on specific file
- "extract entities today" — run on today's work log
- "check sources" / "check source {entity}" — check entity Access for changes
- Called by lib-settle after forward + reverse phases
- Called by lib-review during audit

## Entity Extraction

Given content (a file or section), extract and manage entities:

1. **Identify**: Person names, tool/paper/service names, concept terms. Use language signals:
   - 情感升级词 ("真的很", "无比的") → higher confidence
   - 桥接信号 ("配合我们的...") → state: active
   - "我感觉" → concept extraction opportunity
   - `[[wikilink]]` → confirmed entity, state: active

2. **Resolve**: `ls _entities/` → check name + aliases (fuzzy). Uncertain → LLM compare Summary (0-2 fallback calls).

3. **Create**: Unresolved entities → new entity page in `_entities/` with four sections (Summary, Access, Context, Relations).

4. **Update**: Resolved entities → append Context entry (time-descending). Update Relations if new co-occurrences.

5. **Tag**: Check `_tags.yaml`. Reuse existing. New tag only if genuinely new community.

6. **Promote**: If entity now has wikilink / multi-day reference / bridge signal → state: active.

## Source Check (absorbed from lib-source)

Check external sources referenced in entity Access sections for changes.

1. Scan `_entities/` for entities with repo/service references in Access
2. Check by type: local repo → `git log --since=...`, GitHub URL → `gh api`, service → HTTP HEAD
3. Changes found → append Context entry with summary
4. Report: changed / clean / unreachable

## Constraints

- Intake explosion control: entities nested in another artifact's description → don't create standalone
- Entity pages are append-only for Context (never delete existing entries)
- Summary rewrite: only when context accumulates ~5 new entries
- Relations stored on the "passive" side
