# Notion source playbook

Load this when an Event, reference, or question involves Notion. It says what the workspace holds for MyLibrary, how to read it, what counts as evidence, and what to return.

## What this source contains

| Area | Role | Local copy |
|---|---|---|
| Events database | Wayne's input. One page is one Event identity. Each semantic edit becomes a new revision. | `_events/<event_id>/revisions/<n>/{body.md,raw.json,event.json}` plus `_sources/src_<same key>/snapshots/<n>/` |
| Watched workspace pages and database rows | Wayne's own notes outside Events (`authorship: wayne`). The first pass is a non-pending baseline; each later edit is a pending `source_update` revision. | `_events/<event_id>/revisions/<n>/` with `input_kind: source_update`, structure in `_state/notion/watch.json` |
| Pages an Event mentions or links, outside the watch area | Reference material, not input. Never pending, never a user decision. | `_sources/<source_id>/` with `role: reference` in `source.json` |
| Entities database (`ENT <name>` pages) | Machine-published views of local Entities. Output only. | The local `_entities/*.md` file is the authority |
| Main page and the Entities page | Layout. | Never collected |

The watch area is every workspace root page and root database except the IDs in `watch.exclude` of `_state/notion/setup.json` (currently 日子 and 历史存档) and the MyLibrary page. Search only lists those roots. Everything below them is found by following child pages and database rows, and a page is reread only when its `last_edited_time` changes. Database templates are not returned by queries and are not watched.

## How to read it

1. **Local first.** `mylibrary search <words> --scope all` finds Event and reference text with path and line. Read `body.md` directly. `mylibrary source-open <event_id> --mode cache` returns an Event's current snapshot. Use `--mode historical --revision <n>` for the version behind an earlier claim.
2. **Refresh inputs.** `mylibrary collect` lists every page in Events with full pagination. It compares normalized content and records a revision only when body, user properties, mention IDs, or attachment bytes change. It re-reads referenced pages only when their `last_edited_time` changes.
3. **Live check.** `mylibrary source-open <event_id> --mode live` rereads one Event page. Use it when the question is about the current state, not about what was true when settled.
4. **Resolve mentions.** Body text shows a mention as `Title [notion-page:<uuid>]`. Run `mylibrary resolve <uuid>`. `matched_by: notion_page_id` is a hard identity match. `not_found` means the page is not an Entity. It could be the Main page, a reference, or an unpublished Entity.

Block anchors look like `<!-- block:<uuid> -->` above each block in `body.md`. Cite them as `block:<uuid>` or as line ranges.

## What counts as evidence

- Text Wayne wrote in an Event body, cited by Event ID, revision, SHA-256, and a line or block anchor.
- User-set properties in `raw.json`, such as `Occurred`.
- Attachment bytes saved under `_sources/<id>/attachments/<sha256>`. A file name or a Notion URL is not the file.
- Reference page text, cited by its source ID and snapshot revision. It shows what the page said, not that Wayne endorses it.

These are not evidence:

- An `ENT` page body. It is our own published output. Citing it is circular.
- `last_edited_time`, editor IDs, and signed file URLs. They change without any change in meaning.
- A page title alone.
- The existence of a mention. A mention says the Event refers to something, not what Wayne concluded about it.

## Common pitfalls

- **Truncated or unsupported content.** `coverage.status: partial` lists gaps with a `continue` path. An unsupported block renders as `[Unparsed <type>]`. Do not integrate a conclusion that depends on a gap. Use `blocked` or a `coverage_ack` that explains why the gap cannot matter.
- **Expired file links.** Notion file URLs expire after about an hour. Only saved bytes count. An attachment with `status: unavailable` is a gap.
- **Child pages.** A child page inside an Event renders as `[Title](url) [child not imported]`. Its content is not in the snapshot.
- **Access versus absence.** HTTP 404 or 403 on a reference means the integration cannot see it. Report `unavailable`. Never read it as "the page does not exist" or "nothing was written".
- **Deleted or moved Events.** A page that stops appearing is listed in `not_observed`. Its local revisions stay. Do not treat that as a retraction unless Wayne says so.
- **Empty pages.** A page created by a stray button click is `readiness: empty` and never pending. Leave it alone.
- **Same text, different pages.** Two pages with identical text are two Events. Never merge them by hash.
- **Machine edits.** Our publish never writes to Events, so a changed Event means Wayne changed it.

## What to return

For each Notion item used: title, Event ID and revision or reference source ID and revision, the Notion URL, the anchor, and coverage status with any gap. Say whether each statement is Wayne's own text, reference text, or your inference. For a current-state question, state whether you read the retained snapshot or did a live read, and when.

## Tools on this machine

Checked 2026-09-29.

- The runtime uses the REST API, version `2026-03-11`, with an integration token. `scripts/mylibrary` injects `NOTION_PAT` from Doppler (project `mylibrary`, config `dev`), with a Keychain fallback. Queries and block reads paginate until `has_more` is false. A repeated cursor is an error, not a complete list. Rate limits and server errors retry up to three times. Writes that lose their response become `UncertainWrite` and are reconciled, not repeated.
- The Claude Notion connector (MCP) suits interactive reading. It uses separate OAuth and can expire independently of the runtime token. Do not use it for collection, because it has no coverage record.
- The integration sees only pages shared with it. A reference outside that scope is `unavailable`.

## Examples

- **Event mentions `ENT Notion`.** Resolve the page ID to `ent_notion` and read that Entity directly. Do not run a five-candidate search to double-check a hard match.
- **Event says "这篇先存着，还没读" with a link.** Keep the link and the stated intent. The reference snapshot may exist, but do not write its conclusions into an Entity as if Wayne had read or adopted them.
- **A reference returned 403.** Report it as unavailable, and say which claim cannot be checked. Do not write "no prior discussion found".
- **Two Events contradict each other.** Keep both with their dates. Prefer the later one only if it clearly revises the earlier one, and say so.
- **Wrong: citing the `ENT MyLibrary` page to support a new Context line.** That page was generated from the Entity you are editing.
