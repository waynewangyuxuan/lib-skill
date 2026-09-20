# Consumer Interface — settle consumer types

## What is a consumer?

A consumer defines how a storage folder absorbs content from the stream (工作记录).
Each folder declares its consumer in `_folder.compiled.yaml` under `settle.consumer`.

## Resolution path (entity-first)

1. Entity resolution: `## heading` → match entity in `_entities/` (by name, aliases, wikilink)
2. Storage location: read entity page's Access section → find storage folder path
3. Consumer config: read storage folder's `_folder.compiled.yaml` → `settle.consumer`
4. Execute consumer on the storage folder

Entity page tells you WHERE to store. Folder compiled yaml tells you HOW to store.

## Well-known consumers

### `notes` (vault default)

Copy section content to `{target}` path in the storage folder.
- Target path from `settle.target` (default: `日志/{project}-{M-DD}.md`)
- Multi-dimension: if `settle.dimensions` defined, match content to dimension by context
- Mode: copy (verbatim, no rewriting)
- Add source callout + backlink

### `feature-room`

For projects with META/. Triage: spec-worthy → fr-ingest to META (as `state: draft`), always save full section to `notes/{YYYY-MM-DD}-{slug}.md` (zero content loss safety net).
- Backlink includes both META and notes targets

### `skip`

Do nothing. Don't settle, don't add backlink.
Used for: `日子/`, `_personal/`, folders that don't consume from stream.

## Custom consumers

Defined in `_folder.md` as:

```markdown
## Settle Consumer: {name}
type: consumer
inherits: {parent-consumer}

{natural language behavior definition — this IS the prompt}
```

Compiled yaml declares just the name:
```yaml
settle:
  consumer: {name}
```

### Resolution at runtime

1. Read `settle.consumer` from folder's compiled yaml
2. If well-known → execute directly (see above)
3. If custom → go to `_folder.md`, find `## Settle Consumer: {name}`
4. Read `inherits:` → know fallback behavior
5. Read natural language definition → execute as prompt
6. Can't determine action → fallback to parent consumer

## OOD inheritance chain

```
_vault default (notes)
  ├── folder A: notes (inherited, no override)
  ├── folder B: feature-room (override)
  ├── folder C: skip (override)
  └── folder D: bySection (custom, inherits notes)
        → reads _folder.md definition
        → fallback to notes behavior
```

## Entity extraction (post-consumer step)

After consumer execution, settle runs entity extraction on the section content. This is NOT a consumer — it's a pipeline step that runs after every consumer (except `skip`).

See lib-settle SKILL.md for entity extraction details.
