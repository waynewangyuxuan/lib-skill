---
name: lib-export
description: >
  Capture the current session as a MyLibrary Event. Use for "export", "导出",
  "总结一下", "export result", "export detail", or "记录过程".
---

# Capture a session Event

Record the authorized session as a bounded Event. Use result mode by default. Use detail mode when the user asks for process, discussion, or reasoning changes. Do not create Entity pages during capture.

## Prepare and capture

1. Verify `mylibrary status`. If the shared runtime is missing, use [runtime-schema.md](references/runtime-schema.md) for its dependency and command contract.
2. Write temporary Markdown outside `~/MyLibrary`. Match the session language and voice. Preserve artifact URLs and source identities.
3. In result mode, record decisions, outcomes, measurements, artifacts, and open work. In detail mode, add the important reasoning changes and exact user quotes with their context.
4. Run `mylibrary capture <file> --name <session-name> --resource-id <stable-session-id> --mode result`. Use `--mode detail` for the second mode.
5. Report the returned Event ID and revision. Keep the resource ID for retries. A new semantic version remains a revision of the same capture.

Nothing substantive means no padded capture. Exclude credentials and routine tool chatter. Do not claim a behavior was tested when only its code or API response was inspected.

## Preserve the original

Leave existing work logs and human paragraphs intact. Daily Markdown may remain a historical source or optional view. Heading names and a Settle Log do not establish consumption. The Event will be integrated by `lib-settle` through freeze, staging, validation, and apply.

Load [source-playbooks.md](references/source-playbooks.md) for local capture details. Load [skill-conventions.md](references/skill-conventions.md) when resolving legacy references. A single-skill installation requires the shared `mylibrary` runtime installed once from the lib-skill repository.
