# Source-specific processing playbooks

Load the current source section after reading the frozen Event record. Load additional sources only when a claim needs them. Keep a bounded source pack with input identity, required artifacts, coverage gaps, and precise evidence references.

## A user Event

1. Read frozen body and user properties. Resolve Entity mentions by page IDs or stable mappings before comparing titles.
2. Separate user observations, decisions, questions, and future work. Preserve direct quotes.
3. Open references needed to interpret those claims. Verify source URLs, retained bytes, or source blocks.
4. Compare existing Entity descriptions. Stage supported Context and Relations. A generic heading does not establish a new Entity.
5. If no Entity knowledge is added, use `recorded_only` with a reason. Unresolved identity or required evidence becomes `needs_review` or `blocked`.

## A source update

1. Compare the collected revision with the relevant earlier snapshot.
2. Read changed body, user properties, mentions, and attachment versions. Edit timestamps or signed-URL rotation alone are insufficient.
3. State what changed and why it affects the Entity. A source change is not a user decision.
4. Cite old and new snapshots when explaining a change. Resolve repeated updates to the same Entity ID.
5. If a required block or attachment is inaccessible, leave the affected interpretation blocked. For an unaffected conclusion from partial coverage, add `coverage_ack` explaining why the gap cannot change it. Explain optional source reads that you skip.

## A local session capture

1. Write bounded temporary Markdown from the authorized session. Include artifact links and source identifiers.
2. Use result mode for decisions and outcomes. Use detail mode for reasoning changes and exact user quotes.
3. Run `mylibrary capture <file> --resource-id <stable-session-id> --mode result` or `--mode detail`.
4. Reuse the resource ID when retrying the same capture. A semantic edit creates another revision of that resource.
5. Process the frozen Event through resolve, stage, validate, and apply. A daily heading does not replace receipt-backed consumption.

## A repository source

1. Read Entity Access and repository instructions. Record the root, remote URL, branch, and full commit ID.
2. Inspect the requested range and relevant files. Preserve author filtering and common-object-store dedup in historical reverse-scan helpers.
3. Distinguish user work from collaborator changes. Run the relevant behavior check when possible.
4. For a GitHub source, use `mylibrary capture-url <url> --mode live`. For local evidence, capture a bounded report with exact commit and file anchors. A diff summary does not prove tests passed.
5. If a check cannot run, state the missing dependency or service. If no commit affects the question, explain the skip without consuming unrelated Events.

## Check the staged interpretation

For each Context entry, confirm the referent, source location, full-artifact hash, and distinction between facts and inference. Each integrated outcome cites at least one artifact from its own Event revision. Other Events cannot replace that provenance. Preserve human corrections. Recheck the frozen base before apply.

If coverage is partial, integrate only an unaffected conclusion with an explicit `coverage_ack`. Block the outcome when the missing material matters. `blocked` and `needs_review` never authorize formal file writes.

Unsupported media, empty input, inaccessible content, ambiguous references, and failed validation are explicit gaps. Do not advance consumption to hide them. Report fixture tests, live API tests, Notion UI tests, phone tests, and offline tests separately. Fixture or API success does not prove the phone interface works.
