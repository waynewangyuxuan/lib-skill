# lib-skill 3.2

MyLibrary captures Events, preserves their source evidence, and integrates supported knowledge into stable Entities. Local files are authoritative. Notion supplies the Events database, a watched workspace area, and fixed Entity output pages.

Existing Entity pages, bodies, type vocabulary, typed Relations, and work logs stay compatible. A legacy Entity gains a stable ID and description when a settle first writes it.

## Install

Two parts are installed separately. The Skills are Markdown folders that `npx skills` manages. The `mylibrary` command is a Python tool that the Skills call. Each Skill's `metadata.runtime` names the minimum runtime version it needs.

```bash
npx skills add waynewangyuxuan/lib-skill --skill '*' --global
uv tool install git+https://github.com/waynewangyuxuan/lib-skill
mylibrary --version
```

Add `--agent claude-code` or `--agent codex` to choose agents, or `--skill lib-search` for one Skill. `pipx install git+https://github.com/waynewangyuxuan/lib-skill` works in place of uv. Python 3.11 or newer is required.

## Update

```bash
npx skills update
uv tool upgrade mylibrary-tools
```

Update both. A Skill that requires a newer runtime than the installed one asks for the upgrade before it collects or writes.

## Develop from a checkout

A development checkout links the Skill folders to the repository and installs the runtime in editable mode, so edits take effect immediately.

```bash
git clone https://github.com/waynewangyuxuan/lib-skill.git ~/lib-skill
bash ~/lib-skill/install.sh all --python ~/.venvs/mylibrary/bin/python
```

`install.sh --dry-run` shows the plan without changes. Bump `mylibrary/__version__` and every Skill's `metadata.runtime` together; `tests/test_packaging.py` fails when they disagree.

## Process one batch

1. Run `mylibrary status` and collect configured input with `mylibrary collect`.
2. Freeze the pending revisions with `mylibrary freeze --output /tmp/lib-run/frozen.json`.
3. Use `lib-settle` to resolve Entity descriptions and load only the needed source pack.
4. Stage complete Entity replacements and an outcome for every frozen Event outside the vault.
5. Run `mylibrary validate <staging>` and `mylibrary apply <staging>`.
6. Run `mylibrary index` and publish each affected Entity with `mylibrary publish --entity <id>`.

Use `mylibrary recover <run_id>` after an interrupted apply. Retry publication separately. Missing evidence, uncertain identity, and human-edit conflicts remain unresolved rather than consumed.

To record the current agent session, ask `lib-settle` to export it: it runs `mylibrary capture <file> --resource-id <stable-id> --mode result` and settles that Event at once. Detail mode retains the important reasoning changes and user quotes.

## Skills

| Skill | Task |
|---|---|
| lib-settle | Integrate pending Event revisions, or capture and settle the current session |
| lib-entity | Resolve identities and propose supported Entity memory |
| lib-search | Retrieve descriptions, typed neighbors, and source evidence |
| lib-notion | Configure explicit input scope and fixed-page publication |
| lib-review | Review receipts, unresolved Events, and publication gaps |
| lib-manual | Explain commands, compatibility, and recovery |

## Shared references

`_stdlib/` is the authoring source. Read [runtime-schema.md](_stdlib/runtime-schema.md) for storage, exact staging fields, evidence anchors, recovery, publication, and CLI commands. Read [source-playbooks.md](_stdlib/source-playbooks.md) for Event, source-update, local-capture, and repository-source processing.

Run `bash scripts/sync-stdlib.sh` after changing shared references. It copies the selected files into distributed skills. Keep progressive reads bounded to descriptions, chosen Entity bodies, and relevant frozen artifacts.

Notion input comes only from `mylibrary collect`. The token is injected from Doppler, with an existing macOS Keychain item as fallback.

To use an existing Notion page as the workbench, run `mylibrary setup --main <MyLibrary-page-URL> --dry-run` and then run the same command without `--dry-run`. `--parent` retains its earlier meaning: create a new MyLibrary child under that page. Setup preserves existing Main content and stops on unrelated same-title child collisions.

Report local fixture, live API, Notion UI, phone, and offline verification separately. Neither a successful setup nor a fixture proves a working mobile recording flow.
