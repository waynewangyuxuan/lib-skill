# lib-skill — MyLibrary Vault Skills

Entity-first skill system for the MyLibrary Obsidian vault. Claude Code plugin format.

## Install

```bash
# As Claude Code plugin (recommended)
claude plugin add /path/to/lib-skill

# Or manual symlink
bash install.sh
```

## Skills

| Skill | 职责 |
|-------|------|
| lib-settle | 内容分发（forward + reverse），完成后调 lib-entity |
| lib-entity | entity 提取/解析/创建/更新 + source check |
| lib-search | entity-first 搜索（三层深度） |
| lib-review | EOD/EOW review + entity graph 审计 |
| lib-compile | folder storage config 编译 |
| lib-export | session 导出到工作记录（result / detail 模式） |
| lib-manual | vault 使用手册 |

## Shared stdlib

`_stdlib/` contains shared conventions:
- `yaml-schema.md` — compiled yaml schema (storage config only, identity in entity pages)
- `consumer-interface.md` — settle consumer types + entity-first resolution
- `skill-conventions.md` — entity-first architecture, link convention, trigger mechanism

## Architecture

Entity page (`_entities/X.md`) = identity layer. Folder (`_folder.compiled.yaml`) = storage layer.

See `lib-manual` for full vault documentation, or the entity layer design spec in the vault.
