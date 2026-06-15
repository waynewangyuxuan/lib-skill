---
name: lib-compile
description: >
  Use for MyLibrary folder intent realization: compile _folder.md into
  _folder.compiled.yaml, create folder dashboards, initialize folders, or run
  "compile", "compile all", "init", "编译", or "初始化" workflows.
---

# lib-compile — Folder Intent Realizer

Reads `_folder.md` and makes the folder match its description: compiled config, dashboard file, subfolder structure. Storage-layer only — identity lives in entity pages.

**Vault**: `~/MyLibrary`
**Shared stdlib**: `../_stdlib/yaml-schema.md` (or installed as `_stdlib/yaml-schema.md`) — config schema reference.

## Triggers

- "compile {folder}" / "lib-compile {folder}" / "编译 {folder}"
- "compile all" / "编译所有"
- "init {folder}" / "初始化 {folder}"

## Command: compile

**Input**: `{folder}` — folder name or path

1. Read `_folder.md` (source of truth), existing `_folder.compiled.yaml`, and list folder contents
2. Understand intent: purpose, described structure, naming rules, Claude behavior rules
3. Realize structure: create described subfolders that don't exist
4. Extract config: map natural language to yaml keys per yaml-schema.md. **Storage config only** — aliases, matching, source.repo have moved to entity pages. Only extract: settle (consumer, target, dimensions), entry, frontmatter, scaffold.
5. Semantic diff: compare extracted config with current state. No changes → skip.
6. Write `_folder.compiled.yaml` with header (source, source_hash, compiled_at, inherits)
7. Regenerate `_index.md` dashboard: frontmatter + title + Dataview query. Preserve existing content.
8. Append changelog to `_folder.md ## Changelog`

## Command: init

Scaffold minimal folder infrastructure.

1. Create folder, `_folder.md`, minimal `_folder.compiled.yaml`, `_index.md` with Dataview query
2. If called from parent compile with description → pre-fill Intent

## Command: compile-all

Walk all folders with `_folder.md`, compile vault root first, then each folder. Also compile `_entities/_folder.md`. Skip unchanged.

## Constraints

- `_index.md` has user-added content → preserve it
- Prose instructions stay in `_folder.md` — only skill-mapped keys go to compiled yaml
- Identity fields (aliases, source repo) belong in entity pages, not compiled yaml
