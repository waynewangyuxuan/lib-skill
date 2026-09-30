# GitHub source playbook

Load this when an Event, Entity Access section, or question points at a GitHub repository, file, commit, pull request, or comment. It says what each URL kind captures, what counts as evidence, and what to return.

## What this source contains

`mylibrary capture-url <url>` accepts only explicit `https://github.com/...` URLs. Each kind reads different endpoints.

| URL kind | Example | What is captured | Coverage labels |
|---|---|---|---|
| Repository | `/owner/repo` | Name, description, default branch, archived flag. No files, no history. | `repository` |
| File | `/owner/repo/blob/<ref>/<path>` with optional `#L10-L20` | The ref pinned to a full commit SHA, then the exact file bytes at that commit | `resolved_ref`, `file`, sometimes `blob` |
| Commit | `/owner/repo/commit/<sha>` | Message, parents, changed files with patches | `commit` |
| Pull request | `/owner/repo/pull/<n>` | PR body, issue-style discussion, and review comments with `path`, `diff_hunk`, `commit_id`, `in_reply_to_id` | `pull_body`, `discussion`, `review_comments` |
| One comment | `/pull/<n>#issuecomment-<id>`, `/issues/<n>#issuecomment-<id>`, `/pull/<n>#discussion_r<id>` | That comment only, checked to belong to that issue or PR | `issue_comment` or `review_comment` |

An issue body (`/issues/<n>` with no fragment), releases, Actions runs, wikis, and search results are not supported. Say so instead of paraphrasing them from memory.

A capture is stored as a `source_update` Event. It becomes a pending settle input, and settle must decide what it means. It is never a statement by Wayne.

## How to read it

1. **Local first.** `mylibrary source-open <url-or-id> --mode cache` returns the retained snapshot, its coverage, and when it was checked. `--mode historical --revision <n>` returns an earlier capture.
2. **Refresh.** `--mode if-stale` reuses a capture younger than 300 seconds. `--mode live` rereads. Each endpoint sends its own `If-None-Match`. A 304 on one endpoint says nothing about the others.
3. **Pin before quoting code.** A file URL on a branch is resolved to a commit SHA at capture time. Quote with that SHA, not the branch name. The branch may have moved since.
4. **Repository work outside GitHub.** For local history (`git log`, author filters, worktrees), use `lib-settle`'s reverse-scan reference. Capture a bounded report with full commit IDs as a local Event.

## What counts as evidence

- File text at a pinned commit, cited by repository, commit SHA, path, and line range.
- A commit message and patch, cited by full SHA.
- A review comment with its `path`, `diff_hunk`, and `commit_id`. It is tied to specific code at a specific commit.
- A PR body or discussion comment, cited by comment ID and URL. It shows what an author wrote, not what shipped.

These are not evidence:

- The current file on a branch, for a claim about the past.
- A commit title, for a claim about motivation. Titles are short and often written after the fact.
- A PR description, for a claim about test results. It is what the author says, not a check we ran.

## Common pitfalls

- **Partial pull requests.** Discussion and review comments are separate endpoints. If only `pull_body` is complete, coverage is partial. Never describe it as "the whole discussion".
- **Pagination.** Comment lists follow `Link: rel="next"` pages of 100. A repeated cursor or a failure mid-way leaves the label `partial`, with a page count.
- **Rate limits.** When the remaining quota hits zero, later endpoints are deferred with `retry_at`. Report which labels are missing. Do not retry in a loop.
- **Large commits.** At 3000 or more changed files, or when any file lacks a patch, `commit` is partial. Do not claim a complete diff.
- **Binary files.** Bytes are kept as an attachment, and `body.md` says the file is binary. Read the bytes or say they were not interpreted.
- **Moved refs.** A branch name in an old Event may point elsewhere today. Use the SHA stored in `semantic.commit_sha`.
- **Access.** A 404 on a private repository usually means no access. Report `unreachable`, not "deleted".

## What to return

For each GitHub item used: the URL, repository, kind, pinned commit SHA where one exists, path and line range or comment ID, the capture's `checked_at`, and coverage per label with any gaps. Separate what the source says from your reading of it. Name the missing labels when coverage is partial.

## Tools on this machine

Checked 2026-09-29.

- The runtime reads the REST API with `GH_TOKEN` or `GITHUB_TOKEN` if set, otherwise `gh auth token`. `gh` is logged in as `waynewangyuxuan` with `repo`, `read:org`, `workflow`, and `gist` scopes. No GitHub secret is in Doppler.
- `gh` itself is fine for interactive questions. Only `capture-url` produces retained, citable snapshots with coverage.

## Examples

- **"Why did we switch the publisher to text comparison?"** Capture the commit URL, then quote its message and the relevant patch lines by SHA. If the message does not say why, answer "not stated in the commit" and look for the Event or review comment that does.
- **A settle input links a PR to justify a decision.** Capture the PR. If `review_comments` is partial, integrate only what the complete labels support. Add a `coverage_ack` naming the gap, or block.
- **Question about a file's current behavior.** Capture the file at the default branch with `--mode live`, and report the pinned SHA and read time.
- **Wrong: quoting today's `main` file as the design at the time of an older Event.** Use the commit the Event referenced, or say which version you read.
