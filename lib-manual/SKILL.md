---
name: lib-manual
description: >
  Use when starting work in the MyLibrary vault and need to understand how
  it works, its design principles, paradigms, and where things are. Also use
  when asking "how does the vault work", "what's the design philosophy",
  "where do I find X", "vault manual", "lib-manual", or before starting a
  new feature that touches vault infrastructure.
---

# lib-manual — Vault User Manual

Dynamically assembles a guide to how this Obsidian vault works. Read-only.

**Vault**: `~/MyLibrary`

## Triggers

- "lib-manual" / "vault manual" / "how does the vault work"
- "lib-manual {topic}" for deep dive

## Topics

| Keyword | META room | What to read |
|---|---|---|
| `entities` | `02-content-flow` | Entity layer: _entities/, entity page structure, tag registry, three-layer query |
| `folders` | `01-folder-system` | Storage layer: _folder.md → compiled yaml → _index.md |
| `content` / `settle` | `02-content-flow` | Stream → entity settle, consumer abstraction, reverse settle |
| `frontmatter` | `04-frontmatter` | Templater + frontmatter conventions |
| `sources` / `external` | `05-external-sources` | Source sync via entity Access sections (外部资源/ deprecated) |
| `review` | `06-review` | EOD/EOW review + entity graph audit |
| `skills` | `07-skills` | Skill system: lib-settle, lib-entity, lib-context, lib-review, lib-source, lib-compile, lib-export |
| `ui` / `theme` | `08-ui-ux` | Theme, DataviewJS, dashboard |
| `project` / `overview` | `00-project-room` | Conventions, constraints, long-term vision |
| (no arg) | — | Full overview of all subsystems |

## Flow

**No topic → overview**: Read CLAUDE.md + `_vault.compiled.yaml` + `图书馆操作手册/图书馆系统设计.md` + entity layer design spec. Synthesize: identity & philosophy, entity-first architecture (entity page = first-class, folder = storage), three-layer query, skill system (7 lib-* skills + lib-entity), infrastructure.

**Topic given → deep dive**: Read the mapped META room + relevant entity pages. Synthesize: what this subsystem does, why, current state, known gaps, practical guidance.

## Key Navigation

| I want to... | Go to... |
|---|---|
| Entity registry | `_entities/` |
| Entity layer spec | `图书馆操作手册/notes/2026-06-04-entity-layer-design.md` |
| Tag registry | `_entities/_tags.yaml` |
| Vault rules | `CLAUDE.md` |
| Vault config | `_vault.compiled.yaml` |
| Design vision | `图书馆操作手册/图书馆系统设计.md` |
| Folder storage config | `{folder}/_folder.md` |
| Work logs | `工作记录/{Month}/{YYYY-M-D}.md` |
| Past reviews | `_reviews/` |
| Skill source | `~/.claude/skills/lib-{name}/SKILL.md` |
| Stdlib | `~/.claude/skills/_stdlib/` |

## Constraints

- Strictly read-only
- Output is narrative prose with wikilinks, not data dumps
- `图书馆系统设计.md` is Wayne's Layer 1 thinking — treat as authoritative
