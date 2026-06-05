---
name: lib-search
description: >
  Entity-first search and context assembly. Use when querying the vault for
  information about any topic — "search for X", "what do I know about X",
  "context on X", "找一下X", "关于X的信息". Three query depths: index scan,
  entity page read, deep aggregation. Also called by other skills for context.
---

# lib-search — Entity-First Search

Search the vault using the entity layer as primary index. Three query depths. Pure read-only.

**Vault**: `~/MyLibrary`
**Entity registry**: `~/MyLibrary/_entities/`

## Triggers

- "search {topic}" / "lib-search {topic}" / "找 {topic}"
- "search today" — all entities in today's work log
- Called by other skills (lib-review, lib-settle) for context

## Three-Layer Query

**Layer 1: Index scan** — "does this entity exist?"
- `ls _entities/` → match topic against file names + frontmatter aliases
- Tag community filtering: infer tag → `grep -l "{tag}" _entities/`
- Tag miss fallback: scan all entity file names + Summary first line
- Cost: few hundred lines

**Layer 2: Entity page read** — "what is this, what's my relationship"
- Read matched entity's Summary + Access + Context + Relations
- Traverse Relations to related entities (one hop)
- Cost: a few files

**Layer 3: Deep aggregation** — "compile everything for a report"
- Follow Access as action guide: git log, read storage folder, call external services
- Expand Relations recursively
- Cost: many reads + possible external calls

## Depth Selection

AI chooses depth based on intent:
- "Herdr 是什么" → Layer 2
- "Frederick 推荐过什么" → Layer 2 + grep 反查
- "准备 EvoGraph 组会报告" → Layer 3
- Called by lib-review → Layer 1-2

## Constraints

- Strictly read-only
- Entity not found → report closest matches
- When called by another skill, return structured data; when called by user, print narrative
