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
   - `###` / deeper headings → candidate entity names when they look like a project, repo, paper, service, person, or concept. Heading level does not matter for extraction; it only affects settle consumption.
   - Heading + external identifier → high confidence. If a nested heading has a GitHub URL, paper URL, service URL, or local repo path nearby, create or resolve an entity even if the parent `##` section belongs to another entity. Example: `### Vibe-Trading` with `https://github.com/HKUDS/Vibe-Trading` under a Moonbow work-log section should become `[[vibe-trading]]`.
   - Relevance language near a name/link ("高度相关", "重要参考", "prior art", "inspired by", "similar to", "style reference") → promote from incidental mention to captured entity.

2. **Resolve**: `ls _entities/` → check name + aliases (fuzzy). Uncertain → LLM compare Summary (0-2 fallback calls).

3. **Create**: Unresolved entities → new entity page in `_entities/` with four sections (Summary, Access, Context, Relations).

4. **Update**: Resolved entities → append Context entry (time-descending). Update Relations if new co-occurrences.

5. **Tag**: Check `_tags.yaml`. Reuse existing. New tag only if genuinely new community.

6. **Promote**: If entity now has wikilink / multi-day reference / bridge signal → state: active.

## Nested Heading Promotion

When extracting from work logs or settled notes, do not stop at `##` headings. Treat `###`/deeper headings as named sub-artifacts inside the parent entity. If the nested artifact has an external source link or explicit relevance signal, it should be promoted to its own entity and then linked from the parent context.

Rules:
- Create entity: nested heading + GitHub/paper/service/local-repo link + relevance signal.
- Usually create entity: nested heading + external link, even without explicit relevance, if the surrounding text analyzes its behavior.
- Do not create entity: generic meeting subheadings ("组会", "Thinking", "Next steps") unless they name a stable person/project/tool/concept.
- Keep parent relations: add `referenced-by:: [[parent-entity]]` or `related-to:: [[parent-entity]]` as appropriate.

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
