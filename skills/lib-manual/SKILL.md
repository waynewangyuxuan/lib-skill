---
name: lib-manual
description: >
  Explain the MyLibrary Event-first workflow, runtime commands, storage,
  compatibility, and recovery. Use for "lib-manual", "vault manual",
  "how does the vault work", or a specific subsystem question.
metadata:
  runtime: mylibrary-tools>=3.1.0
---

# Explain MyLibrary 3.0

Give a bounded, read-only explanation for the requested topic. Start with the relevant shared reference, then inspect actual status or selected local files. Do not load the whole vault to answer one question.

| Topic | Load first |
|---|---|
| Capture, collect, settle | [source-playbooks.md](references/source-playbooks.md) |
| Storage, staging, receipts, recover, publish | [runtime-schema.md](references/runtime-schema.md) |
| Entity identity and compatibility | [skill-conventions.md](references/skill-conventions.md) |
| Typed graph and retrieval | [relations-vocabulary.md](references/relations-vocabulary.md) |

The common route is capture or collect, freeze, compare Entity descriptions, load the needed source pack, stage, validate, apply, index, and publish. `mylibrary status` identifies pending or incomplete work. Recovery and publication have separate retries.

Local files preserve Events, source snapshots, attachment bytes, Entity memory, mappings, and receipts. Notion provides the Events input, local copies of pages that Events reference, and fixed Entity output pages. Daily work logs remain readable history. The existing Entity pages, bodies, and type vocabulary remain compatible. A legacy Entity gains a stable ID and description when a settle first writes it. Untouched Entities stay as they are.

Each Skill's `metadata.runtime` names the minimum `mylibrary-tools` version it needs. Before collecting or writing, run `mylibrary --version`. If the command is missing, ask Wayne to run `uv tool install git+https://github.com/waynewangyuxuan/lib-skill`. If it is older than required, ask for `uv tool upgrade mylibrary-tools`. Skills update separately with `npx skills update`. A development checkout uses `bash install.sh` instead.

For source details, use `source-open` cache or historical mode before requesting a live read. Explain missing scope, unsupported content, and unverified client behavior. Do not infer a working phone route from a setup response.

Respect root governance and folder contracts. Do not read `_personal/` by default or write META mirrors. Treat earlier design documents as historical context when their daily-heading workflow conflicts with the current Event receipt contract.
