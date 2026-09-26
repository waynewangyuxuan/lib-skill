# lib-skill — MyLibrary Vault Skills

Entity-first skills for the MyLibrary Obsidian vault. The repository is compatible with Codex,
Claude Code, the open Agent Skills format, and the portable Agent Plugins 1.0 format.

## Install with `npx skills`

No npm package is published from this repository. The `skills` CLI downloads the skill source from
GitHub and records it in its lock file so later updates can be applied.

```bash
# Inspect the skills available in the repository
npx skills add waynewangyuxuan/lib-skill --list

# Install all skills globally for Codex
npx skills add waynewangyuxuan/lib-skill --skill '*' --agent codex --global --yes

# Or install one skill
npx skills add waynewangyuxuan/lib-skill --skill lib-search --agent codex --global --yes
```

Codex discovers installed skills automatically. Start a new Codex session if an installed skill does
not appear immediately.

### Use without installing

```bash
# Print the generated prompt to stdout
npx skills use waynewangyuxuan/lib-skill@lib-search

# Or launch Codex with that skill
npx skills use waynewangyuxuan/lib-skill@lib-search --agent codex
```

### List and update

```bash
npx skills list --global --agent codex
npx skills update --global
npx skills update lib-search --global
```

`skills update` refreshes skills already tracked in the lock file. If a later release adds a brand-new
skill to this repository, rerun the `skills add ... --skill '*'` command to install the new entry too.

## Install as a Codex plugin

The root `plugin.json` is a portable Agent Plugins 1.0 manifest. `.codex-plugin/plugin.json` remains
as a compatibility fallback, and `.agents/plugins/marketplace.json` exposes the repository as a Codex
marketplace.

```bash
codex plugin marketplace add waynewangyuxuan/lib-skill
codex plugin add lib-skill@lib-skill
```

Refresh a Git-backed marketplace and reinstall the plugin when developing against a newer revision:

```bash
codex plugin marketplace upgrade lib-skill
codex plugin add lib-skill@lib-skill
```

For a local clone, the legacy helper can symlink the canonical skill directories:

```bash
bash install.sh codex
bash install.sh claude-code
```

## Skills

| Skill | 职责 |
|-------|------|
| lib-settle | 内容分发（forward + reverse），完成后调 lib-entity |
| lib-entity | entity 提取/解析/创建/更新 + source check |
| lib-notion | Notion 个人 workspace 的增量扫描与 EOD 来源交接 |
| lib-search | entity-first 搜索（三层深度） |
| lib-review | EOD/EOW review + entity graph 审计 |
| lib-compile | folder storage config 编译 |
| lib-export | session 导出到工作记录（result / detail 模式） |
| lib-manual | vault 使用手册 |

## Shared stdlib

`_stdlib/` contains the authoring source for shared conventions:
- `yaml-schema.md` — compiled yaml schema (storage config only, identity in entity pages)
- `consumer-interface.md` — settle consumer types + entity-first resolution
- `skill-conventions.md` — entity-first architecture, link convention, trigger mechanism

Every distributed skill is self-contained. Run `bash scripts/sync-stdlib.sh` after changing shared
source material; it copies only the references each skill needs into that skill's `references/`
directory. This keeps single-skill installs working without repository-level relative paths.

## Architecture

Entity page (`_entities/X.md`) = identity layer. Folder (`_folder.compiled.yaml`) = storage layer.

See `lib-manual` for full vault documentation, or the entity layer design spec in the vault.
