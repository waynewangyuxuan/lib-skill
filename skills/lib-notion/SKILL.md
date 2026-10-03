---
name: lib-notion
description: >
  Connect and collect Notion Events and the watched workspace as MyLibrary
  inputs, retain source evidence, and publish Entity views. Use for Notion
  setup, collection, watch-area scope, source reads, or publication recovery.
metadata:
  runtime: mylibrary-tools>=3.5.0
---

# Collect Notion inputs and publish Entity views

The Notion Events database and the watch area are the configured inputs. Local Entity files and retained evidence are authoritative. Notion Entities are fixed-page output views and are excluded from input collection.

## Configure access and scope

1. The vault wrapper `scripts/mylibrary` injects the token from Doppler (project `mylibrary`, config `dev`, secret `NOTION_PAT`) when the Doppler CLI is logged in. Otherwise the runtime reads an existing Keychain item `com.wayne.lib-notion`. Rotate the token with `doppler secrets set NOTION_PAT --project mylibrary --config dev` in Wayne's own terminal.
2. Confirm the intended page and workspace from actual connected state. If Wayne supplied an existing MyLibrary page, run `mylibrary setup --main <page URL or ID> --dry-run`, inspect the result, then adopt that exact page. Use `--parent` only when the intent is to create a new MyLibrary child under another page. A dry-run does not check remote access.
3. Run `mylibrary status` and verify the configured Events and Entities mappings. Collection reads the Events data source and the watch area: every workspace root except the page IDs in `watch.exclude` of `_state/notion/setup.json`. To exclude another root, add its page ID there. See [source-notion.md](references/source-notion.md).
4. Run `mylibrary collect`. Inspect retained source URLs, IDs, snapshots, attachment bytes, and coverage gaps before reporting readiness.

`NOTION_API_KEY` or `NOTION_PAT` may come from a secure environment. Never expose a token in chat, command arguments, source files, or receipts. A stored token does not prove workspace access or a working mobile recording route.

## Process and publish

Collection records immutable normalized revisions. Pages that an Event mentions or links are snapshotted as reference sources, never as Events. Same-resource changes remain revisions. Equal text on separate pages remains separate Events. Empty pages and missing required blocks stay unresolved. System-only edits and rotating signed URLs do not prove new knowledge.

Use `lib-settle` for freeze, semantic staging, validate, and apply. Load [source-playbooks.md](references/source-playbooks.md) for Event and source-update interpretation. Scanner timestamps and `seen` values never establish consumption.

Run `mylibrary publish` after a settle. Unchanged pages are skipped; pages whose links now reach a newly published Entity are refreshed. Use `--entity <id>` only to retry one page. Preserve the fixed local-ID-to-page mapping. Read back properties and body before success. A remote human edit blocks replacement. An uncertain create with zero exact-ID matches remains uncertain instead of creating again. Retry publishing independently from semantic apply. See [runtime-schema.md](references/runtime-schema.md).

Report local fixture, live API, Notion interface, phone, and offline checks separately. Do not infer interface success from setup or API collection.
