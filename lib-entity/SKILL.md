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

4. **Update**: Resolved entities → append Context entry (time-descending). Update Relations per `_stdlib/relations-vocabulary.md` (core type by family, stored on the passive side).

5. **Tag**: Check `_tags.yaml`. Reuse existing. New tag only if genuinely new community.

6. **Promote**: If entity now has wikilink / multi-day reference / bridge signal → state: active.

## Nested Heading Promotion

Don't stop at `##` headings. A `###`/deeper heading is a candidate entity when it names a thing (project, repo, paper, service, person, concept). Heading level only affects settle *consumption* — never entity *extraction*.

**Create liberally — the cost of an entity is not its count.** A well-connected graph (hub entities + local clusters) absorbs leaf entities at near-zero query cost. The real failure is an **orphan** (no relation) or a **collision** (name clashes with an existing entity), never "too many." So:
- **Heading/name + its own external identifier** (GitHub/paper/service URL, local repo path) → create/resolve the entity, even if the parent `##` belongs to another entity. (`### Vibe-Trading` + its repo under a Moonbow log ⇒ `[[vibe-trading]]`.)
- **A name merely mentioned inside another artifact's prose** (no heading, no own identifier) → don't mint standalone; record it as a relation on the host entity.
- **Generic subheadings** ("组会", "Thinking", "Next steps") → not entities unless they name a stable thing.

**Two mandatory guards (these are the real cost, not count):**
- **Attach, never orphan.** Every newly minted entity gets a relation back to its parent hub — use the **most specific core type that fits** (a Tier-1 `part-of`/`uses` if structural; `related-to` only as last resort), per `_stdlib/relations-vocabulary.md`.
- **Canonical naming + dedup.** Before minting, check the name and all `aliases:` across `_entities/` by *referent, not exact string* (same as lib-review 认知层). Reuse on match; otherwise pick one stable kebab-case canonical name.

## Source Check (absorbed from lib-source)

Check external sources referenced in entity Access sections for changes.

1. Scan `_entities/` for entities with repo/service references in Access
2. **Check each source (fan out).** Independent reads → one subagent per source per `_stdlib/skill-conventions.md` Orchestration; each returns a bounded, provenance-anchored temp summary. Local repo → `git log --since=...`, GitHub URL → `gh api`, service → HTTP HEAD.
3. Changes found → single writer appends a Context entry per entity (hold each page's structure; append-only).
4. Report: changed / clean / unreachable

## Constraints

- Entity count is cheap; orphans and name collisions are not — every new entity must attach to a hub (relation) and pass canonical-name dedup. See Nested Heading Promotion.
- Entity pages are append-only for Context (never delete existing entries)
- Summary rewrite: only when context accumulates ~5 new entries
- Relations: store each edge once on the passive/derivative side, typed per `_stdlib/relations-vocabulary.md` (reverse via grep; lifecycle pair excepted)
