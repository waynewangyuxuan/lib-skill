"""Receipt-backed settle sections in the daily work log."""

import calendar
from pathlib import Path
import re

from .catalog import build_index
from .storage import Library, _atomic_bytes, read_json, writer_lock

ROOT = "工作记录"
HEADING = "## Settle Log · 回执 #ai-generated"
SECTION = re.compile(r"^" + re.escape(HEADING) + r"\n.*?(?=^## |\Z)", re.M | re.S)
LABELS = {"integrated": "整合进", "recorded_only": "只记录"}


def day_path(day):
    return f"{ROOT}/{calendar.month_name[day.month]}/{day.year}-{day.month}-{day.day}.md"


def _rows(vault):
    library = Library(vault)
    stems = {item["id"]: Path(item["path"]).stem for item in build_index(vault)["entities"] if item["id"]}
    rows = {}
    for path in sorted(library._path("_events").glob("*/revisions/*/event.json")):
        event = read_json(path)
        completed = library._completed("settle", event["event_id"], event["revision"])
        if completed:
            receipt = read_json(library._path(completed["receipt_path"]))
            status = LABELS[receipt["outcome"]]
            if receipt["outcome"] == "integrated":
                status += " " + "、".join(f"[[{stems.get(entity, entity)}]]" for entity in receipt["entity_ids"])
            note = receipt.get("summary") or receipt.get("reason")
        elif event["readiness"] == "ready":
            status, note = "未沉淀", None
        else:
            continue
        day = library.event_day(event)
        name = event.get("name") or event["event_id"]
        url = event.get("source_url") or ""
        label = f"[{name}]({url})" if url.startswith("https://") else name
        if event["revision"] > 1:
            label += f" rev {event['revision']}"
        line = f"- {label} · {status}" + (f" · {note.strip()}" if note and note.strip() else "")
        rows.setdefault(day, []).append((name, event["revision"], line))
    return rows


def write_worklog(vault, run_id=None):
    vault = Path(vault).resolve()
    library = Library(vault)
    rows = _rows(vault)
    days = set(rows)
    if run_id is not None:
        receipt = read_json(library._path(f"_runs/{run_id}/receipt.json"))
        touched = {tuple(Path(path).parts[-2:]) for path in receipt["outcome_receipts"]}
        days = {library.event_day(read_json(library._path(f"_events/{event_id}/revisions/{Path(name).stem}/event.json")))
                for event_id, name in touched}
    written = []
    with writer_lock(vault):
        for day in sorted(days & set(rows)):
            lines = [line for *_, line in sorted(rows[day])]
            section = HEADING + "\n\n由 settle 回执生成，重跑会整节重写。\n\n" + "\n".join(lines) + "\n"
            relative = day_path(day)
            target = vault / relative
            if target.exists():
                text = target.read_text(encoding="utf-8")
                match = SECTION.search(text)
                text = (text[:match.start()] + section + ("\n" if match.end() < len(text) else "") + text[match.end():]
                        if match else text.rstrip("\n") + "\n\n" + section)
            else:
                text = f"---\ncreated: {day}\ndate: {day}\ntags: []\n---\n\n" + section
            _atomic_bytes(target, text.encode("utf-8"))
            written.append(relative)
    return written
