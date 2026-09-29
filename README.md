# lib-skill 3.0

MyLibrary captures Events, preserves their source evidence, and integrates supported knowledge into stable Entities. Local files are authoritative. Notion supplies configured Events and Pages inputs and fixed Entity output views.

The upgrade preserves the existing 107 Entity pages, body sections, type vocabulary, typed Relations, historical work logs, and folder compilation. Migrate only the pilot Entities. Daily headings and scanner checkpoints do not establish consumption.

## Install the shared runtime

Use Python 3.11 or newer. Install the package once from a persistent local checkout.

```bash
git clone https://github.com/waynewangyuxuan/lib-skill.git ~/lib-skill
python3 -m venv ~/.venvs/mylibrary
~/.venvs/mylibrary/bin/python -m pip install -e ~/lib-skill
export PATH="$HOME/.venvs/mylibrary/bin:$PATH"
mylibrary --help
```

Keep that environment on the agent's PATH. The runtime uses PyYAML and Python's standard library. Editable installation follows the local checkout. Plugin or single-skill installation does not install the Python runtime automatically.

## Install skills

For a local checkout, the helper installs the runtime with the selected Python and links canonical skill directories. Existing directories are backed up before replacement.

```bash
bash ~/lib-skill/install.sh codex --python ~/.venvs/mylibrary/bin/python
bash ~/lib-skill/install.sh claude-code --python ~/.venvs/mylibrary/bin/python
bash ~/lib-skill/install.sh codex --dry-run
```

`--runtime-only` installs the Python package without linking skills. `--dry-run` makes no changes.

Single-skill installation remains supported through the Agent Skills distribution.

```bash
npx skills add waynewangyuxuan/lib-skill --skill lib-search --agent codex --global --yes
```

Each skill includes its references. It depends on the one shared runtime rather than carrying a duplicate package. `lib-compile` retains its existing local configuration workflow. The portable `plugin.json`, Codex fallback manifest, and marketplace metadata remain available for plugin installation.

## Process one batch

1. Run `mylibrary status` and collect configured input with `mylibrary collect`.
2. Freeze the pending revisions with `mylibrary freeze --output /tmp/lib-run/frozen.json`.
3. Use `lib-settle` to resolve Entity descriptions and load only the needed source pack.
4. Stage complete Entity replacements and an outcome for every frozen Event outside the vault.
5. Run `mylibrary validate <staging>` and `mylibrary apply <staging>`.
6. Run `mylibrary index` and publish the authorized pilot with `mylibrary publish --entity <id>`.

Use `mylibrary recover <run_id>` after an interrupted apply. Retry publication separately. Missing evidence, uncertain identity, and human-edit conflicts remain unresolved rather than consumed.

For local session input, use `lib-export` and `mylibrary capture <file> --resource-id <stable-id> --mode result`. Detail mode retains the important reasoning changes and user quotes.

## Skills

| Skill | Task |
|---|---|
| lib-export | Capture a session Event in result or detail mode |
| lib-settle | Integrate frozen Event revisions through staging and apply |
| lib-entity | Resolve identities and propose supported Entity memory |
| lib-search | Retrieve descriptions, typed neighbors, and source evidence |
| lib-notion | Configure explicit input scope and fixed-page publication |
| lib-review | Review receipts, unresolved Events, and publication gaps |
| lib-manual | Explain commands, compatibility, and recovery |
| lib-compile | Compile existing folder configuration |

## Shared references

`_stdlib/` is the authoring source. Read [runtime-schema.md](_stdlib/runtime-schema.md) for storage, exact staging fields, evidence anchors, recovery, publication, and CLI commands. Read [source-playbooks.md](_stdlib/source-playbooks.md) for Event, source-update, local-capture, and repository-source processing.

Run `bash scripts/sync-stdlib.sh` after changing shared references. It copies the selected files into distributed skills. Keep progressive reads bounded to descriptions, chosen Entity bodies, and relevant frozen artifacts.

The old Notion scanner defaults to the shared collector. Its explicit `legacy-scan` mode remains read-only compatibility with an observation checkpoint. Credential storage retains the dedicated macOS Keychain route. A legacy checkpoint is never an Event consumption receipt.

To use an existing Notion page as the workbench, run `mylibrary setup --main <MyLibrary-page-URL> --dry-run` and then run the same command without `--dry-run`. `--parent` retains its earlier meaning: create a new MyLibrary child under that page. Setup preserves existing Main content and stops on unrelated same-title child collisions.

Report local fixture, live API, Notion UI, phone, and offline verification separately. Neither a successful setup nor a fixture proves a working mobile recording flow.
