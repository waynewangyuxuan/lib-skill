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

## Orchestration — fan-out reads, single-writer writes

Work is a pipeline of read→write units, **not** a two-phase "read everything, then write everything." A big read decomposes into small read→write units that interleave — a unit may write as soon as its own read returns while other reads still run. The win from interleaving is **latency**, not parallel writes to a shared file.

**Parallelize by the independence of the WRITE target. Three tiers:**
- **Reads / scans / source-checks / audits** → always fan out. No mutation ⇒ always independent.
- **Writes to disjoint files** (compile's per-folder yaml; minting new entity pages with distinct canonical names) → may run in parallel; no contention.
- **Writes to one shared file** (工作记录, an existing entity page) → **must serialize through a single writer.**

**The single writer holds the target's live heading tree.** Any shared write target is owned by one serial writer that maintains the current `##`/`###` structure of that file and updates it after every write; each unit decides placement against this live tree. This is the mechanism that prevents duplicate `## [[entity]]` sections and write races — never let two units append to the same file blind.

### Read side — map-reduce distillation

When a read fans out wide (many repos, many entity pages, a long transcript):
1. **Map** — each subagent reads its source and writes a **distilled temp artifact**: not a raw dump — distilled, reflected, framed in *our* (the vault's) view, bounded and inspectable in length.
2. **Reduce** — fold temp level-1 → level-2 → … recursively, each level bounded, so the main agent only ever reads the top.
3. **Hard constraints:**
   - **temp lives OUTSIDE the vault** (e.g. `/tmp/lib-run-{date}/`) — the auto-commit watcher commits anything inside `~/MyLibrary`.
   - **provenance survives the reduce** — carry source anchors (note id, repo commit, URL) through every level. Distill prose, never links.
   - **default shallow** — daily work is 1 level; recurse only for large fan-outs.

### Write side — constraints, not a ladder

Placement into notes/work logs is **judgment from the target's current context**, not a fixed step-by-step procedure. Enforce these constraints; let Claude decide the rest:
- **Hold the target's live structure before writing** — you cannot place well without it.
- **Never duplicate** an entity's existing `##` section (or a child entity's existing `###`). Append into it.
- **Follow the note's existing flow and style** — don't manufacture top-level headings for convenience.
- **Preserve provenance** on everything written.

When NOT to orchestrate: trivial work (read one file, write one line) → just do it inline.

## Config Resolution

1. Read `~/MyLibrary/_vault.compiled.yaml` — vault defaults
2. If target is an entity: read `_entities/X.md` — entity identity + Access
3. If entity has storage folder: read its `_folder.compiled.yaml` — storage config
4. Merge: folder keys override vault keys (deep merge for nested objects)

## Link Convention

- **Vault 内文件** → `[[wikilink]]`。Entity pages, spec docs, 工作记录, 任何在 ~/MyLibrary/ 下的 .md。Obsidian 原生解析，backlink 自动关联。
- **Vault 外资源** → `[name](url/path)`。Web URL, local file outside vault, external repo link。点击直达。
- **Always materialize — bare text = information loss.** 凡提到的东西都带链接，写 log / spec / note / entity 时一律执行：
  - commit / PR → 完整 GitHub URL（不留 bare `@hash`）
  - research / 外部来源 → 原始 URL（provenance，可回溯）
  - 顺带提到的相关 entity（哪怕只一句带过）→ `[[wikilink]]` backlink，让它出现在对方的 backlinks 面板
  这是 provenance 原则（见 Orchestration → 读侧）从 entity 页延伸到所有书写：留住来源、连上关系。

Settle 和 entity extraction 靠这个区分内部引用 vs 外部资源。

## Trigger Mechanism

Skills are triggered by the user in a Claude Code session (e.g., "settle today"). The overnight batch script can also invoke skills headlessly via `claude -p`.

## Naming

- Skill name: `lib-{verb}` (e.g., lib-settle, lib-compile, lib-review)
- Config key in compiled yaml: matches skill name minus `lib-` (e.g., `settle:`, `compile:`)
- Trigger phrases: natural language, supports Chinese + English
