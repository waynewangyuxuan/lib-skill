"""Receipt-backed settle sections and the daily summary in the work log."""

import calendar
from datetime import date, datetime, timezone
from pathlib import Path
import re

from .catalog import build_index
from .storage import Library, _atomic_bytes, read_json, writer_lock

ROOT = "工作记录"
HEADING = "## Settle Log · 回执 #ai-generated"
DAILY_HEADING = "## 今日 #ai-generated"
TIMESTAMP_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}T(\d{2}:\d{2})")


def _section(heading):
    return re.compile(r"^" + re.escape(heading) + r"\n.*?(?=^## |\Z)", re.M | re.S)


SECTION = _section(HEADING)
DAILY_SECTION = _section(DAILY_HEADING)


def day_path(day):
    return f"{ROOT}/{calendar.month_name[day.month]}/{day.year}-{day.month}-{day.day}.md"


def _label(event):
    name = event.get("name") or event["event_id"]
    match = TIMESTAMP_NAME.match(name)
    if match:
        name = f"{match.group(1)} 的记录"
    url = event.get("source_url") or ""
    label = f"[{name}]({url})" if url.startswith("https://") else name
    if event["revision"] > 1:
        label += f" rev {event['revision']}"
    return label


def _latest_attempt(library, event):
    """The most recent outcome receipt of a revision that has no completion pointer."""
    attempts = list(library._path("_runs").glob(f"*/outcomes/settle/{event['event_id']}/{event['revision']}.json"))
    if not attempts:
        return None
    return read_json(max(attempts, key=lambda path: path.stat().st_mtime))


def _days(vault):
    """Per logical day: what each Event revision became, ordered by its moment."""
    library = Library(vault)
    stems = {item["id"]: Path(item["path"]).stem for item in build_index(vault)["entities"] if item["id"]}
    days = {}
    for path in sorted(library._path("_events").glob("*/revisions/*/event.json")):
        event = read_json(path)
        completed = library._completed("settle", event["event_id"], event["revision"])
        if completed:
            receipt = read_json(library._path(completed["receipt_path"]))
            note = (receipt.get("summary") or receipt.get("reason") or "").strip()
            if receipt["outcome"] == "integrated":
                kind = "integrated"
                detail = ([stems.get(entity, entity) for entity in receipt["entity_ids"]], note)
            else:
                kind, detail = "recorded", note
        elif event["readiness"] == "ready":
            attempt = _latest_attempt(library, event)
            if attempt and attempt.get("outcome") in {"blocked", "needs_review"}:
                kind, detail = "blocked", (attempt.get("reason") or "").strip()
            else:
                kind, detail = "waiting", None
        else:
            continue
        moment = datetime.fromisoformat(library.event_moment(event).replace("Z", "+00:00"))
        moment = moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
        days.setdefault(library.event_day(event), []).append((moment, event["revision"], _label(event), kind, detail))
    return {day: sorted(rows, key=lambda row: row[:2]) for day, rows in days.items()}


def _with_reasons(items):
    """`label — reason` per item, collapsed to one trailing reason when all share it."""
    reasons = {reason for _, reason in items}
    if len(reasons) == 1:
        joined = "、".join(label for label, _ in items)
        reason = reasons.pop()
        return joined + (f" — {reason}" if reason else "")
    return "；".join(f"{label} — {reason}" if reason else label for label, reason in items)


def render_day(rows):
    settled, recorded, blocked, waiting = {}, [], [], []
    for _, _, label, kind, detail in rows:
        if kind == "integrated":
            entities, note = detail
            for entity in entities:
                settled.setdefault(entity, []).append(f"  - {note} ← {label}" if note else f"  - ← {label}")
        elif kind == "recorded":
            recorded.append((label, detail))
        elif kind == "blocked":
            blocked.append((label, detail))
        else:
            waiting.append(label)
    parts = []
    if settled:
        parts.append("**沉淀**\n" + "\n".join(f"- [[{entity}]]\n" + "\n".join(lines) for entity, lines in settled.items()))
    if recorded:
        parts.append(f"**只记录** {len(recorded)} 条：" + _with_reasons(recorded))
    if blocked:
        parts.append(f"**卡住** {len(blocked)} 条：" + _with_reasons(blocked))
    if waiting:
        parts.append(f"**未处理** {len(waiting)} 条：" + "、".join(waiting))
    return HEADING + "\n\n由 settle 回执生成，重跑会整节重写。\n\n" + "\n\n".join(parts) + "\n"


def _replace_section(text, pattern, section, *, before=None):
    """Replace the section `pattern` matches, or insert it before `before`'s section, else append."""
    match = pattern.search(text)
    if match:
        tail = text[match.end():]
        return text[:match.start()] + section + ("\n" if tail else "") + tail
    anchor = before.search(text) if before else None
    if anchor:
        return text[:anchor.start()] + section + "\n" + text[anchor.start():]
    return text.rstrip("\n") + "\n\n" + section


def _write_section(vault, day, pattern, section, before=None):
    relative = day_path(day)
    target = vault / relative
    if target.exists():
        text = _replace_section(target.read_text(encoding="utf-8"), pattern, section, before=before)
    else:
        text = f"---\ncreated: {day}\ndate: {day}\ntags: []\n---\n\n" + section
    _atomic_bytes(target, text.encode("utf-8"))
    return relative


def write_worklog(vault, run_id=None):
    vault = Path(vault).resolve()
    library = Library(vault)
    days = _days(vault)
    selected = set(days)
    if run_id is not None:
        receipt = read_json(library._path(f"_runs/{run_id}/receipt.json"))
        touched = {tuple(Path(path).parts[-2:]) for path in receipt["outcome_receipts"]}
        selected = {library.event_day(read_json(library._path(f"_events/{event_id}/revisions/{Path(name).stem}/event.json")))
                    for event_id, name in touched}
    with writer_lock(vault):
        return [_write_section(vault, day, SECTION, render_day(days[day])) for day in sorted(selected & set(days))]


def write_daily(vault, day, text):
    """Place the day's AI summary above the Settle Log, keeping everything else in the file."""
    vault = Path(vault).resolve()
    day = date.fromisoformat(str(day))
    body = text.strip()
    if body.startswith(DAILY_HEADING):
        body = body[len(DAILY_HEADING):].strip()
    if not body:
        raise ValueError("Daily summary is empty")
    with writer_lock(vault):
        return _write_section(vault, day, DAILY_SECTION, DAILY_HEADING + "\n\n" + body + "\n", before=SECTION)
