# Event consumer interface

The processing unit is `(consumer, event_id, revision)`. One Event may update several Entities. Several Events may resolve to the same Entity. Heading levels do not define consumption.

## Resolve a target

Resolve stable IDs and known Notion mappings first. Then compare names, aliases, descriptions, and the selected Entity bodies. Use typed Relations to check the referent. An uncertain match becomes `needs_review`. Do not create a second Entity merely because an alias differs.

Read the Entity's Access section and source-specific playbook. Preserve the source snapshot and its precise anchors before proposing Context.

## Outcomes

| Outcome | Meaning | Consumption |
|---|---|---|
| `integrated` | Declared Entity outputs contain supported knowledge | After the completed apply receipt |
| `recorded_only` | Retain the Event without formal Entity writes; give a concrete reason | After the completed apply receipt |
| `needs_review` | Identity or interpretation remains uncertain | Pending |
| `blocked` | Required evidence, access, validation, or safe write is unavailable | Pending |

Every frozen Event revision needs exactly one outcome. An integrated output has a declared Entity ID, file path, and precise evidence from its own Event revision. Partial coverage requires `coverage_ack` explaining why the gap does not affect the conclusion. Otherwise keep the Event blocked. Blocked or uncertain outcomes have no authorized files. A necessary skip records why no Entity write is warranted. Empty Events stay retained without being marked consumed.

## Stage and apply

Write complete replacement Entity files and the manifest outside the vault. Use [runtime-schema.md](runtime-schema.md). Run `mylibrary validate <staging>` before `mylibrary apply <staging>`. Keep outputs for uncertain or blocked Events out of the formal write set.

The runtime accepts formal outputs at `_entities/<name>.md`. Consumption receipts are independent of daily Settle Logs, backlinks, and legacy note copies. Retry publication separately from apply.
