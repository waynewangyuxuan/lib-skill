# lib-review — EOD/EOW Review Generator

Produces structured review files from work logs. Two commands: `eod` (daily) and `eow` (weekly). EOW includes entity graph audit.

**Vault**: `~/MyLibrary`

## Triggers

- "review today" / "lib-review eod" — end of day
- "review week" / "lib-review eow" — end of week

## Command: eod

**Input**: optional `{date}` (default: today, respects 4am day boundary)

1. Resolve work log path: `工作记录/{Month}/{YYYY-M-D}.md`
2. Run lib-context for today → get entities touched
3. Run lib-settle for {date} → get settle report
4. Extract `- [ ]` TODOs from work log, grouped by section
5. Entity report: new entities created today, state changes (captured → active)
6. Write review file to `_reviews/review-{M-DD}.md`:
   - Entities Touched (with [[wikilinks]] to entity pages)
   - Content Settled
   - Entity Updates (new / state changed)
   - Open TODOs
   - Unmatched Sections

## Command: eow

**Input**: optional `{week}` (default: current ISO week)

1. Resolve week date range (Mon–Sun)
2. Read daily reviews from `_reviews/review-*.md` within this week
3. **Entity graph audit (运维层)**:
   - Stale: active entities with no new Context in >14 days → suggest archived
   - Tag health: any tag with >50 entities (split?) or <3 (merge to parent?)
   - Duplicates: entities with overlapping aliases or similar Summaries
   - Orphans: entities with zero Relations
   - Summary quality: entities with >5 new Context entries since last Summary rewrite
4. System health: stale compiled yaml, unsettled sections
5. Aggregate per-entity: appearance frequency → rank as focus areas
6. Write `_reviews/weekly-review-W{N}.md`:
   - This Week's Focus (top entities by frequency)
   - Per-Entity Progress
   - Entity Graph Health (audit results)
   - System Observations
   - Suggestions

## Constraints

- Work log missing → stop, don't write empty review
- Entity audit is advisory — Wayne approves before any changes
- No daily reviews for EOW → entity audit still runs
