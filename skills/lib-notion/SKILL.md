---
name: lib-notion
description: >
  Connect and collect explicitly configured Notion Events and Pages as MyLibrary
  inputs, retain source evidence, and publish pilot Entity views. Use for Notion
  setup, collection, source reads, or publication recovery.
---

# Collect Notion inputs and publish Entity views

Notion Events and Pages are configured input data sources. Local Entity files and retained evidence are authoritative. Notion Entities are fixed-page output views and are excluded from input collection.

## Configure access and scope

1. Keep the existing private credential route. On macOS, run `bash scripts/store-token-macos.sh` from this skill directory. Enter the credential only in its hidden-input terminal. The dedicated Keychain service remains `com.wayne.lib-notion`.
2. Confirm the intended page and workspace from actual connected state. If Wayne supplied an existing MyLibrary page, run `mylibrary setup --main <page URL or ID> --dry-run`, inspect the result, then adopt that exact page. Use `--parent` only when the intent is to create a new MyLibrary child under another page. A dry-run does not check remote access.
3. Run `mylibrary status` and verify the configured Events, Pages, and Entities mappings. Collection reads the configured input data sources. Do not default to a workspace-wide Search.
4. Run `mylibrary collect`. Inspect retained source URLs, IDs, snapshots, attachment bytes, and coverage gaps before reporting readiness.

`NOTION_API_KEY` or `NOTION_PAT` may come from a secure environment. Never expose a token in chat, command arguments, source files, or receipts. A stored token does not prove workspace access or a working mobile recording route.

## Process and publish

Collection records immutable normalized revisions. Same-resource changes remain revisions. Equal text on separate pages remains separate Events. Empty pages and missing required blocks stay unresolved. System-only edits and rotating signed URLs do not prove new knowledge.

Use `lib-settle` for freeze, semantic staging, validate, and apply. Load [source-playbooks.md](references/source-playbooks.md) for Event and source-update interpretation. Scanner timestamps and `seen` values never establish consumption.

Run `mylibrary publish --entity <id>` for the authorized pilot. Preserve the fixed local-ID-to-page mapping. Read back properties and body before success. A remote human edit blocks replacement. An uncertain create with zero exact-ID matches remains uncertain instead of creating again. Retry publishing independently from semantic apply. See [runtime-schema.md](references/runtime-schema.md).

## Legacy scanner compatibility

`python3 scripts/scan.py` and `python3 scripts/scan.py scan` delegate to `mylibrary collect`. The shared runtime must be installed once from lib-skill, including for single-skill distributions.

Only `python3 scripts/scan.py legacy-scan` runs the old read-only accessible-page scanner. Its legacy options are `--since`, `--state`, and `--output-dir`. It uses an observation checkpoint outside the vault. That checkpoint is not a consumption receipt. Legacy scope may be partial or workspace-wide; inspect its scope explicitly. Never use it as the default Event collector or feed its temporary output into direct Entity writes.

Report local fixture, live API, Notion interface, phone, and offline checks separately. Do not infer interface success from setup or API collection.
