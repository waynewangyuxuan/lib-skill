# lib-review — EOD/EOW Review Generator

Produces structured review files from work logs. Two commands: `eod` (daily) and `eow` (weekly). EOW includes entity graph audit (运维层 + 认知层).

**Vault**: `~/MyLibrary`

## Triggers

- "review today" / "lib-review eod" — end of day
- "review week" / "lib-review eow" — end of week

## Command: eod

**Input**: optional `{date}` (default: today, respects 4am day boundary)

1. Resolve work log path: `工作记录/{Month}/{YYYY-M-D}.md`
2. Run lib-search for today → get entities touched
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
3. **Entity graph audit — 运维层 (every week)**:
   - Stale: active entities with no new Context in >14 days → suggest archived
   - Tag health: any tag with >50 entities (split?) or <3 (merge to parent?)
   - Duplicates: entities with overlapping aliases or similar Summaries
   - Orphans: entities with zero Relations
   - Summary quality: entities with >5 new Context entries since last Summary rewrite
4. **Entity graph audit — 认知层 (biweekly: even ISO week, or on demand)** — recurrence-promotion:
   Detect **implicit entities** — things that ARE entities but have no page, because they only ever appear as modifiers/relations *inside* other entities. This is the systematic blind spot from the failure log (`图书馆操作手册/notes/2026-06-12-entity-layer-failure-patterns.md` B6): token-driven extraction + intake explosion control never mint these.
   - **Scan**: `_entities/*.md` Context sections + this week's work logs for recurring references that are **not** `[[wikilinks]]` and **not** an existing entity name/alias.
   - **Cluster by referent, not string** — first: group surface variants pointing at the same thing ("Frederick 实验室" / "research group" / "我们 lab" = one referent). Count recurrence on the *referent*, never on exact string. Exact-string matching is the failure mode: each variant appears once, nothing crosses the threshold, the blind spot survives.
   - **Candidate** = a referent naming a *thing* (group, org, lab, team, recurring event, system, method, dataset) whose variants together appear in **≥2 distinct entity pages** OR across **≥5 days**.
   - **Filter out**: existing entities — match the referent against every entity's **name AND `aliases:`** (not just titles), so already-promoted things are suppressed; one-off mentions; generic words; pure role/label phrases ("Quant Trading 角色") that name a slot, not a thing.
   - **Watch especially for the group-entity shape**: a container/modifier phrase wrapping already-named entities — "X 实验室 / 组 / 团队 / team / 平台 / 系统" co-occurring with a `[[person]]` + `[[project]]` + `[[artifact]]`. That wrapper IS an implicit group entity (e.g. PI + project + workspace ⇒ the lab). It will never be the grammatical subject, so it never self-promotes — this pass is the only place it surfaces.
   - **For each survivor**: propose promotion — suggested `type` (workstream/person/artifact/concept), a stable kebab-case canonical name, and the **co-occurrence set** (which existing entities would link to it).
5. System health: stale compiled yaml, unsettled sections
6. Aggregate per-entity: appearance frequency → rank as focus areas
7. Write `_reviews/weekly-review-W{N}.md`:
   - This Week's Focus (top entities by frequency)
   - Per-Entity Progress
   - Entity Graph Health — 运维层 (audit results)
   - Promotion Candidates — 认知层 (implicit entities, with evidence: where seen + co-occurrence set) — biweekly
   - System Observations
   - Suggestions

## Constraints

- Work log missing → stop, don't write empty review
- Entity audit is advisory — Wayne approves before any changes
- 认知层 promotion is **proposal only**: list candidates with evidence; actual promotion = create page via lib-entity after Wayne approves, never automatic
- No daily reviews for EOW → entity audit still runs
