# Relations Vocabulary — shared edge types for the entity graph

Entity `## Relations` edges power two consumers: **lib-search** (traversal / context
assembly) and **lib-review** (graph-health audit). A type carries a **tier** (how
strongly to follow) and a **direction** (store once, on the passive/derivative side;
the reverse is a `grep`). This file is the single source of truth — lib-entity writes
by it, lib-search/lib-review read by it.

## Core families

Never invent a new *family*. Mint a vivid specialization only when it adds information
over the core type — then infer its family by meaning to get its tier + direction.

| Tier | Family | Core type — direction | Specialization examples |
|---|---|---|---|
| 1 backbone | Structural | `part-of` child→parent | — |
| 1 backbone | Dependency | `uses` consumer→resource; `provided-by` resource→provider | shares-engine-with, tracked-in |
| 2 context | Provenance | `created-by` thing→maker | authored-by, introduced-by, realized-by, originated-in, prototyped-by, proposed-by |
| 2 context | Lineage | `derived-from` derivative→source; `supersedes`/`superseded-by` (lifecycle, both sides) | inspired-by, builds-on |
| 2 context | Evaluation | `evidence-for`; `baseline-for`/`uses-baseline`; `compares-with` | competes-with, similar-to, contrasts-with, distillation-subject-of |
| 2 context | Social | `led-by` thing→lead; `collaborator` project→person; `recommended-by` thing→person | reviews/reviewed-by, guest-lecturer, involves, co-authored |
| 2 context | Application | `applied-to` concept→use; `studied-in` artifact→research/learning line; `feeds-into` tool→projects | guards, central-to |
| 2 context | Citation | `referenced-by` cited→citer (the stored form) | `references` (active reverse — collapse into `referenced-by`) |
| 3 loose | Generic | `related-to` (symmetric) — the only genuinely loose type | — |

**Three types that drain the overloaded `related-to`** (use these instead of defaulting to `related-to`):
- `studied-in` — an artifact/concept is a reading or topic *within* a research or learning line (e.g. a survey → `[[AI工程的学习和经验]]`).
- `feeds-into` — a skill/tool that applies *across* several projects (e.g. `[[skill-battlefield]]` → Robin, MyLibrary).
- `contrasts-with` — a deliberate counterpoint / 反面锚点, **not** a neutral comparison (use `compares-with`/`similar-to` for neutral).

## Direction rule

Store each edge **once, on the passive/derivative side**, pointing at the canonical/active
side; the reverse is a `grep`:
- child→parent, consumer→resource, thing→maker, derivative→source, workstream→lead-person, concept→where-applied.
- **Pick the most specific core type that fits; `related-to` is the last resort** — including the mandatory hub-attachment when minting a new entity (see lib-entity Nested Heading Promotion).
- **Exception:** the lifecycle pair (`supersedes`/`superseded-by`) lives on *both* pages — staleness must show from the old page ("use the newer one") and the new page alike.

## How lib-search traverses

Compare three to five Entity descriptions first. Read selected bodies and at most one relevant typed hop. Tier 1 and Tier 2 edges supply structure and supported context. Tier 3 edges need a question-specific reason.

Before a second hop or broader audit, record the unresolved question, why expansion helps, and its stopping condition. Do not expand every relation recursively. Preserve the existing vocabulary and edge direction. The index includes reverse edges without duplicating stored Relations.

On `superseded-by`, inspect the newer Entity and retain the old page as historical evidence.

## How lib-review audits

- **Orphan** = a node with **no Tier-1 or Tier-2 edge in either direction** (only `related-to`, or no edge at all). Citation/provenance/etc. count as connected — a paper linked only by `referenced-by` is fine.
- **Under-typed** = a node connected **only by `related-to`** → flag for re-typing to a specific core type.
