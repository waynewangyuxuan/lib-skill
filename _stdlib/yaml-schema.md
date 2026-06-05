# Compiled YAML Schema

## Purpose
Defines what a `_folder.compiled.yaml` (or `_vault.compiled.yaml`) looks like. Used by the compile command to know what to extract from natural language `_folder.md`.

## Core Rule
**Top-level key = skill name.** Each key corresponds to a `lib-{key}` skill. Skills only read their own key.

## Two-Layer Architecture

**Entity page** (`_entities/X.md`) = identity layer. Defines what something is, how to access it, relationships.
**Folder compiled yaml** = storage layer. Defines how content is stored, consumed, scaffolded.

Entity page answers "what is this?". Compiled yaml answers "how does this folder work?".

## Schema

```yaml
# Header (always present)
source: _folder.md           # or _vault.md
compiled_at: "YYYY-MM-DD"
inherits: _vault              # only for folder-level; omit for vault-level

# --- settle (lib-settle) ---
settle:
  consumer: notes                         # well-known: notes | feature-room | skip
                                          # or custom name (definition in _folder.md)
  target: "日志/{project}-{M-DD}.md"      # used by 'notes' consumer
  role: source                            # only on source folders (工作记录/)
  dimensions:                             # optional: multi-dimension settle targets
    - path: Notes/
      pattern: "{project}-{M-DD}.md"
    - path: Meetings/
      pattern: "{project}-Meeting-{M-DD}.md"
  # Custom consumers defined in _folder.md as:
  #   ## Settle Consumer: {name}
  #   inherits: {parent-consumer}
  #   {natural language behavior definition}

# --- entry (lib-compile) ---
entry:
  template: "dataview"                    # _index.md dashboard format

# --- frontmatter ---
frontmatter:
  default: [created, tags]                # fields every file gets
  extra: []                               # folder-specific additional fields

# --- scaffold ---
scaffold:
  children: true | false                  # auto-create subfolders

# --- Vault-level only below ---

# --- skills (skill manifest, vault-level only) ---
skills:
  {skill-name}:
    triggers: [trigger-phrases]
    depends_on: [other-skills]

# --- skill_types (vault-level only) ---
skill_types:
  {type-name}:
    interface: [method-names]
    well_known: [implementation-names]
```

### Fields that moved to entity pages

These fields are NO LONGER in compiled yaml — they live in `_entities/X.md`:

| Old compiled yaml field | New location |
|---|---|
| `aliases: []` | Entity page frontmatter `aliases:` |
| `matching.method / fallback / auto_threshold` | Removed. Entity resolution via `_entities/` aliases |
| `source.repo` | Entity page Access section (free text) |

## Extraction Rules

When reading `_folder.md`, map natural language to yaml keys:

| _folder.md section | yaml key | How to extract |
|---|---|---|
| `## Intent` | (not in yaml, stays in Layer 1) | Skip — intent is for humans |
| `## Claude 的行为` with settle-related rules | `settle.consumer`, `settle.target` | Extract consumer type, target patterns |
| `## Settle Consumer: {name}` | `settle.consumer: {name}` | Custom consumer — stays in Layer 1 |
| File/folder structure references | `entry.template`, `scaffold` | Note what structure exists |
| `## 文件命名` or naming rules | `frontmatter` | Extract patterns |

**Key principle:** Only extract what maps to a skill key. Everything else stays in `_folder.md` as Layer 1 natural language. Identity information (aliases, source repo, description) belongs in the entity page, not here.

## Inheritance

Folder-level compiled yaml inherits from vault-level:
1. Load `_vault.compiled.yaml` as base
2. Load `_folder.compiled.yaml`
3. Folder keys override vault keys (deep merge for nested objects)
4. Missing keys in folder → use vault default

## Compiled Config in _folder.md

The compiled config callout lives in `_folder.md`, NOT in the entry file:

```markdown
> [!abstract]- Compiled Config
> \```yaml
> {contents of _folder.compiled.yaml}
> \```

## Changelog
```
