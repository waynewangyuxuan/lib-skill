---
name: lib-search
description: >
  Retrieve MyLibrary context through Entity IDs, descriptions, typed Relations,
  and source snapshots. Use for "search for X", "what do I know about X",
  "context on X", "找一下X", or "关于X的信息".
metadata:
  runtime: mylibrary-tools>=3.7.0
---

# Retrieve bounded Entity context

Search preserves authoritative Entity and source files. The runtime may refresh rebuildable index caches. Start with descriptions, then read selected bodies and their evidence. Historical work logs and legacy Entity bodies remain available when needed.

1. Resolve an explicit ID, Notion reference, or known alias with `mylibrary resolve <ref>`.
2. Otherwise run `mylibrary search <query> --limit 5`. Compare three to five descriptions before loading full bodies.
3. Read the best matches. Follow one relevant typed hop with `mylibrary neighbors <id>` when it helps answer the question.
4. Record the unresolved question and reason before a second hop, broader full-text search, or more candidates. Use a concrete stopping condition. Do not recursively load every connected page.
5. Open evidence with `mylibrary source-open <ref> --mode cache`. Notion `if-stale` reuses a fresh cache for 300 seconds before checking the source. Use `live` for explicitly current detail or `historical --revision <revision>` for evidence behind a past claim.
6. Return the answer with Entity links, original sources, source versions, and any coverage gap. Distinguish retained evidence from a live read.

Search, resolve, and neighbors refresh derived caches when source hashes change. `mylibrary index` rebuilds them explicitly. Refine queries instead of raising `--limit` above five. Legacy pages remain searchable by aliases, descriptions when present, and body text. A zero-result search does not prove the knowledge never existed.

Load [relations-vocabulary.md](references/relations-vocabulary.md) for edge semantics. Load [source-playbooks.md](references/source-playbooks.md) only for the selected source type. [runtime-schema.md](references/runtime-schema.md) defines CLI and source modes. A single-skill installation requires the shared `mylibrary` runtime.
