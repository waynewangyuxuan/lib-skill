---
name: lib-entity
description: >
  Resolve and propose MyLibrary Entity identities, descriptions, Context, and
  typed Relations from frozen Events or sources. Use for entity extraction,
  entity updates, source checks, and on-demand migration.
metadata:
  runtime: mylibrary-tools>=3.5.0
---

# Resolve and update Entities

Keep the existing Entity registry and ontology. Stable identity is the referent, not the spelling of its latest heading. The existing 107 pages, aliases, body sections, and typed Relations remain compatible.

## Resolve before creating

1. Run `mylibrary resolve <id-or-ref>` when an ID or mapped Notion page is known.
2. Otherwise run `mylibrary search <topic> --scope entities --limit 5`. Compare descriptions, names, and aliases before opening candidate bodies.
3. Read the selected Summary, Access, Context, and relevant Relations. Use `mylibrary neighbors <id>` for needed typed edges. Record a reason before two-hop expansion.
4. Reuse the existing Entity when references name the same thing. Ambiguous referents remain `needs_review`. Do not mint a page to avoid resolving a collision.

A heading, inline name, or mention is an extraction hint. A stable project, person, artifact, organization, or concept with its own identifier may justify an Entity. Generic headings do not. Attach a new Entity with the most specific supported relation under [relations-vocabulary.md](references/relations-vocabulary.md). Preserve the existing type vocabulary.

## Propose supported memory

Load [source-playbooks.md](references/source-playbooks.md) for the current Event, source update, local capture, or repository source. Read exact frozen evidence before writing a claim. A source update does not establish a user decision.

Stage a complete Entity file outside the vault using [runtime-schema.md](references/runtime-schema.md). Keep `Summary`, `Access`, `Context`, and `Relations`. When an integrated outcome writes a legacy Entity, add stable `id`, concise `description`, and `revision: 1` in the same proposal. Do not migrate Entities that no Event touches unless Wayne asks. Preserve human text and earlier Context evidence. Do not rewrite a Summary merely because a fixed entry count was reached.

Each Context entry identifies its Event revision, full-artifact SHA-256, existing source anchor, and original source link. State inferences as inferences. Update Relations only when the evidence supports their type and direction.

Run validate and apply through the shared runtime. Do not write formal Entity files directly. Source-check failures remain blocked or unreachable; they do not append guessed Context or mark an Event consumed.

Load [skill-conventions.md](references/skill-conventions.md) for write boundaries. Single-skill installs require the shared `mylibrary` runtime. Do not remap all legacy Entity types or migrate untouched Entities without an explicit request.
