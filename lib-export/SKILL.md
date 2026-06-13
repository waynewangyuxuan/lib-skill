---
name: lib-export
description: >
  Use when Wayne asks to capture the current session into the vault work log —
  triggers on "export", "导出", "总结一下", "记到工作记录", "export detail",
  "export result", "export log", "记录过程".
---

# lib-export — Session Export to Work Log

Export the current session into the work log. Two modes: result / detail.

**Vault**: `~/MyLibrary`
**Work log**: `工作记录/{Month}/{YYYY-M-D}.md`

## Flow

Steps are ordered and gated. Step 0 and Step 3 are **hard gates** — do not skip, do not eyeball.

### Step 0 — Compute today（4am 日界线）— HARD GATE
1. Run `date "+%Y-%m-%d %H:%M"`.
2. If **hour < 4**, today = 日历日期减一天（before 4am 算前一天）.
3. **Output the resolved target path** (`工作记录/{Month}/{YYYY-M-D}.md`) before doing anything else.
- Never write to the calendar date without running `date` and applying this rule.
- Existing file at target → read it. Missing → create with frontmatter (`created`, `date`, `tags: []`).

### Step 1 — Read the target work log
理解已有内容、style、已有的 `## sections`。Match density、换行、语言。

### Step 2 — Read relevant entity pages
`ls`/`grep _entities/` for entities this session touches。了解它们当前状态,以便正确归属。

### Step 3 — Placement & heading — HARD GATE
**Every new `## heading` MUST be a `[[wikilink]]`. A free-text `## heading` is forbidden.**

Decide placement per section of content:
1. 已有匹配的 `## [[entity]]` section → append 在下面。
2. 没有,但内容**实质上是关于某个 entity** → resolve 主体 entity:
   - `grep _entities/` 命中(名字或 alias) → 复用 `## [[that-entity]]`。
   - 没命中,但这东西值得独立成 entity → **直接 mint 新的 `## [[new-entity]]`**。写一个指向尚不存在页面的 wikilink 是合法的——这正是 entity 诞生的方式(unresolved link)。命名用 kebab-case,选一个稳定的 canonical name。
3. 内容少 / 没有清晰的主体 entity → 不开新 heading,直接在已有 section 下插几行 inline。

判断"挂已有 vs mint 新":内容是不是反复出现、值得日后被检索的一个独立 thing?是 → mint。只是某 entity 的一条进展 → 挂到那个 entity 下。拿不准 → 挂已有 / inline(宁可不爆炸)。

### Step 4 — Write
直接 edit 工作记录。**只 append/insert,绝不 overwrite Wayne 已有内容。**
- AI 生成的 heading 打 `#AI总结` tag。
- 描述性小标题降级成 **bold lead 行**,不要占用 `##`(那是 entity 的位置)。

### Step 5 — Report new entities（不建页）
列出本次写下的、但 `_entities/` 里**还不存在页面**的 `## [[entity]]` headings。
- 这些保持为 unresolved link,**等下次 settle / lib-entity 被动 materialize**。
- **export 不创建 entity 页面,也不调用 lib-entity。** 只报告,让 Wayne 知道有新 entity 引用待落地。

## Two Modes

### Result mode（默认）— "export" / "导出" / "总结一下"
做了什么、结果是什么。Compact,结论导向。**不**描述过程。
- Include: decisions, results with numbers, features completed, key artifacts, TODOs。
- Exclude: process, dead ends, verbose explanations。

### Detail mode — "export detail" / "记录过程" / "export log"
怎么做的——过程、讨论、pivots、关键 quotes。记录思考演变,不只是终态。
- Include: 上面全部 + 讨论过程、设计演变、pushbacks、Wayne 的关键原话(5-10 条)。
- Exclude: routine tool calls, AI meta-commentary。
- **必须含 quotes**:`>` blockquote,Wayne 原话不改字,每条前用一句 context 引导,不能被淹没。

## Writing Rules

- **Match Wayne's style** — 紧凑,段落间不要多余空行。
- **最多一个 `###`** per export。其余用 inline、bullets、tables。
- **No fancy HTML**。
- **Language**: match session 的 中英混合。
- **Voice**: first person, casual。
- **Links**: vault 内 `[[wikilink]]`,vault 外 `[name](url/path)`。

## Red Flags — STOP

- 准备写一个**不是 `[[wikilink]]`** 的 `## heading` → STOP。resolve 成 entity、mint 新 entity wikilink,或降级 inline。自由文本 `##` 永不允许。
- **没跑 `date` 就用日历日期** → STOP。先 Step 0 算 4am 边界。
- 凌晨(hour < 4)却把内容写进了"今天"日历日期的文件 → 错文件,应是前一天。
- 想顺手"帮忙"创建 entity 页面 / 调 lib-entity → STOP。export 只写引用,建页是 settle/lib-entity 的事。
- 准备 overwrite 或重写 Wayne 已有的段落 → STOP。只 append/insert。

## Constraints

- Nothing substantive → say so, don't pad。
- Read before write — always。
- 新建文件也要先 Step 0 算对日期。
