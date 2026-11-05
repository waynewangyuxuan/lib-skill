---
name: lib-review
description: >
  Review MyLibrary Event processing, Entity changes, unresolved evidence, and
  publication state for a day or week. Use for "review today", "review week",
  "lib-review eod", or "lib-review eow".
metadata:
  runtime: mylibrary-tools>=3.7.0
---

# Review receipts and unresolved work

Use completed receipts and original evidence to explain what changed. Daily logs are historical context. An existing heading or old Settle Log does not prove an Event was consumed.

## Daily review

1. Run `mylibrary status`. Collect configured Notion input when connected, unless `lib-settle` will collect in step 2. Record a collection failure as a coverage gap.
2. If the request includes settling, run `lib-settle` on pending Event revisions. Otherwise inspect current receipts without mutating Entities.
3. Read the selected day's completed runs and unresolved Events. Use the 04:00 boundary for historical dates. Retrieve touched Entity descriptions before opening bodies.
4. Compare original sources with supported Context. List decisions, open work, necessary skips, `blocked`, `needs_review`, empty inputs, and source access gaps.
5. Run `mylibrary todo-list --status 待办`. List TODOs created that day, overdue ones (due before today), ones due within three days, and the open count. Report publication state separately. A local apply can succeed while its Notion view remains unpublished or blocked by a human edit.
6. Write the day's summary as a Markdown draft outside the vault, then run `mylibrary daily --day <YYYY-MM-DD> --from <draft>`. It places a `## 今日 #ai-generated` section above that day's Settle Log in `工作记录/` and leaves Wayne's own text alone. Do not edit the day file by hand, rewrite historical work logs, or consume pending Events merely to produce a report. Nothing substantive that day means one sentence, not a padded section.

The `## 今日` section is what Wayne reads first about that day, so write it for a reader, not as a status report:

- Chinese, in the voice of his work log, a few short paragraphs. No headings, tables, or IDs.
- Tell the day by its threads (what he was working on and where it got to), not Entity by Entity. Link `[[Entity]]` where something was settled, so the reader can go deeper.
- End with one paragraph of what is still open: `blocked` and `needs_review` revisions with their reason, decisions waiting on him, and TODOs due within three days. Leave publication state, counts, and coverage gaps to the Settle Log and `mylibrary status`.

## Weekly review

Read the selected week's reviews and receipt-backed Entity changes. Use an explicit bounded audit for stale Context, alias collisions, unsupported descriptions, missing provenance, or under-typed Relations. Preserve the existing relation vocabulary in [relations-vocabulary.md](references/relations-vocabulary.md).

Recurring references may justify a promotion proposal. Group by referent and compare names and aliases before proposing a new Entity. Keep the evidence and attachment relation. Do not create or retype Entities as a side effect of an advisory audit. Accepted changes go through `lib-entity` staging and apply.

An absent work log does not prevent review when Events exist. No available substantive evidence means no padded review. Missing source access and failed checks must appear in the report. Do not claim phone, offline, or Notion UI verification from fixture or API results.

Load [skill-conventions.md](references/skill-conventions.md) for compatibility and retrieval boundaries. Load [runtime-schema.md](references/runtime-schema.md) when inspecting receipts or recovery. Single-skill installs require the shared `mylibrary` runtime.
