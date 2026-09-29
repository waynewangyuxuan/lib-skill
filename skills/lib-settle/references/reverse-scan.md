# Historical repository scan

These read-only helpers support an explicit historical or repository-source request. Their output is evidence for a bounded capture. They do not establish Event consumption or authorize writes into a daily log. Load this reference only when that source type is needed.

Reverse settle only works if the scan actually sees the work. Four failure modes have each
silently eaten real days. All four are mechanical, so they live in
`scripts/discover-repos.sh` + `scripts/scan-day.sh` rather than being left to judgment.

## The four corrections

### 1. Scan every ref, not HEAD — `git log --all`
A repo checked out on a feature branch hides its mainline from `git log`. `evoGraph_DR` sat
on `wayne/report-generation`, so a plain `git log --since=...` returned **0 commits** on days
it actually had 8–26. **Always `--all`.**

### 2. Derive the repo list from entity `## Access` — never hardcode it
A fixed list silently drops every project created after it was written. `~/Peel` and
`~/career-context-compiler` were missing from one, taking **81 commits** with them across
three days. Entity pages already declare where their code lives, so `## Access` is the
source of truth. `discover-repos.sh` reads it two ways:
- explicit local paths (`~/foo`, `/Users/x/foo`)
- a GitHub ref with no local path → try `$HOME/<repo-name>`

**Corollary:** when settle mints an entity for something with a repo, **put the local path in
`## Access`.** That is what makes the next run see it.

### 3. Collapse linked worktrees by shared object store
A `git worktree` shares its parent's object database, so scanning both double-counts every
commit. `~/evoGraph_reportgen` is a worktree of `~/evoGraph_DR` and reports identical hashes.
Dedupe on `git rev-parse --git-common-dir`; keep one root.

### 4. Filter by author — a shared repo is not your work log
Reverse settle answers *"what did **I** do that never got written down."* In a collaborator's
repo that is a different question from "what happened here." `~/Helm` has **353 of 353**
commits by a collaborator; unfiltered it floods the day with work that was never yours.
`scan-day.sh` filters by author and reports collaborator-only repos separately, as
**context, not as your unlogged work**.

Authors default to the vault's `git config user.email` plus the personal address; override
with `LIB_SETTLE_AUTHORS` (a `|`-separated regex).

## Usage

```bash
scripts/discover-repos.sh [vault]        # the repo list, deduped
scripts/scan-day.sh 2026-07-06 [vault]   # my commits that day, per repo
```

`scan-day.sh` uses the vault's 04:00 day boundary (04:00 → 04:00 next day).

## What stays judgment

The scripts identify repository scope and the user's commits. They do not decide what knowledge to integrate. Preserve full commit IDs and relevant file anchors in a bounded source pack. Capture the selected evidence as an Event, then follow [source-playbooks.md](source-playbooks.md) and [skill-conventions.md](skill-conventions.md).

## Auditing a past settle

Run the scan across a date range before trusting earlier runs. A day whose Settle Log says
"no commits" but whose scan disagrees was settled with a blind spot; the honest fix is to
capture the missing evidence and report the historical gap. An old Settle Log is not a consumption receipt.
