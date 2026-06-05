---
name: lib-export
description: >
  Export conversation to Obsidian work log. Two modes: result (compact summary)
  and detail (process log with quotes). Triggers on "export", "导出", "总结一下",
  "记到工作记录", "export detail", "export result".
---

# lib-export — Session Export to Work Log

Export conversation directly into today's work log. Two modes.

**Vault**: `~/MyLibrary`
**Work log**: `工作记录/{Month}/{YYYY-M-D}.md`（4am day boundary）

## Two Modes

### Result mode（默认）
"export" / "导出" / "总结一下"

做了什么、结果是什么。Compact，结论导向。不描述过程。

### Detail mode
"export detail" / "记录过程" / "export log"

怎么做的——过程、讨论、pivots、关键 quotes。记录思考的演变，不只是终态。
**必须包含 quotes**（Wayne 的原话，blockquote 格式），但要组织好，用 context 一句话引导每条 quote，不能被内容淹没。

## Flow

1. **Read today's work log** — 理解已有内容、style、## sections
2. **Read relevant entity pages** — 了解涉及的 entity 当前状态
3. **Determine placement**:
   - 已有 `## section` → append 在下面
   - 没有 → 创建 `## [[{entity}]]` section
   - 内容少 → 直接插几行，不需要新 heading
4. **Write to file** — 直接 edit 工作记录
5. **Post-export**: 如果有新 entity 出现，flag for lib-entity

## Writing Rules

- **Match Wayne's style** — 读他已有的内容，mirror density、换行习惯、语言。他写得紧凑，段落间不要多余空行。
- **最多一个 ###** per export。其余用 inline text、bullets、tables。
- **No fancy HTML**
- **#AI总结 tag** on any AI-generated heading
- **Language**: match session 的 Chinese/English mix
- **Voice**: first person, casual
- **Links**: vault 内 `[[wikilink]]`，vault 外 `[name](url/path)`
- **Quotes**（detail mode）: `>` blockquote，Wayne 原话不改字，前面用一句话 context 引导

## Content Priority

**Result mode include**: decisions, results with numbers, features completed, key artifacts, TODOs.
**Result mode exclude**: process, dead ends, verbose explanations.

**Detail mode include**: 上面全部 + 讨论过程、设计演变、pivots、pushbacks、Wayne 的关键原话（5-10 条）。
**Detail mode exclude**: routine tool calls, AI meta-commentary.

## Constraints

- Nothing substantive → say so
- Never overwrite Wayne's existing content — only append/insert
- Read before write — always
