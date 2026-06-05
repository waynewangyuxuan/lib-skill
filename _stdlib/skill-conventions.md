# Skill Conventions — shared across all lib-* skills

## Data-Driven Development

All lib-* skills follow the data-driven pattern:
- Behavior driven by config (`_vault.compiled.yaml` + `_folder.compiled.yaml`), not hardcode
- Shared logic in `_stdlib/`, private logic in skill's own `stdlib/`
- New capability = new config key + natural language definition

## Entity-First Architecture

The vault uses an entity-first architecture:
- `_entities/` is the sole entity registry. `[[wikilink]]` resolves to entity pages.
- Entity page = identity (Summary, Access, Context, Relations). Folder = storage.
- Skills resolve targets through entity pages first, then find storage folders via Access.
- `_entities/_tags.yaml` defines tag communities for retrieval partitioning.

## Intelligence Pieces, Not Pipeline

Skills are lightweight intelligence that can be inserted at any point — settle time, query time, review time. They are NOT heavy procedural pipelines. Keep skills short, focused on constraints not procedures. Let Claude use its native capabilities.

## Subagent Pattern

Skills that do substantive work SHOULD dispatch subagents for the actual work:
1. Main skill reads config, determines scope, dispatches subagent
2. Subagent does the work (reads, writes, analysis)
3. Subagent returns structured result
4. Main skill validates, writes to vault

When NOT to subagent: trivial operations (read one file, write one line).

## Config Resolution

1. Read `~/MyLibrary/_vault.compiled.yaml` — vault defaults
2. If target is an entity: read `_entities/X.md` — entity identity + Access
3. If entity has storage folder: read its `_folder.compiled.yaml` — storage config
4. Merge: folder keys override vault keys (deep merge for nested objects)

## Link Convention

- **Vault 内文件** → `[[wikilink]]`。Entity pages, spec docs, 工作记录, 任何在 ~/MyLibrary/ 下的 .md。Obsidian 原生解析，backlink 自动关联。
- **Vault 外资源** → `[name](url/path)`。Web URL, local file outside vault, external repo link。点击直达。

Settle 和 entity extraction 靠这个区分内部引用 vs 外部资源。

## Trigger Mechanism

Skills are triggered by the user in a Claude Code session (e.g., "settle today"). The overnight batch script can also invoke skills headlessly via `claude -p`.

## Naming

- Skill name: `lib-{verb}` (e.g., lib-settle, lib-compile, lib-review)
- Config key in compiled yaml: matches skill name minus `lib-` (e.g., `settle:`, `compile:`)
- Trigger phrases: natural language, supports Chinese + English
