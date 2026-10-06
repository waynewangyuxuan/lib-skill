"""Manually invoked MyLibrary operations."""

import argparse
import json
import os
from pathlib import Path
import sys

from . import __version__
from .catalog import build_index, neighbors, resolve, search
from .notion import NotionClient, NotionError
from .publish import publish
from .storage import Library, read_json
from .sync import SETUP, collect, config, setup, source_open, workspace


def parser():
    root = argparse.ArgumentParser(prog="mylibrary")
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--vault", type=Path, default=Path(os.environ.get("MYLIBRARY_VAULT", "~/MyLibrary")).expanduser())
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    commands.add_parser("doctor").add_argument("--offline", action="store_true")
    capture = commands.add_parser("capture")
    capture.add_argument("file", type=Path)
    capture.add_argument("--name", default="")
    capture.add_argument("--resource-id")
    capture.add_argument("--mode", choices=("result", "detail", "event"), default="result")
    capture.add_argument("--occurred-at")
    capture_url = commands.add_parser("capture-url")
    capture_url.add_argument("url")
    capture_url.add_argument("--mode", choices=("cache", "if-stale", "live"), default="live")
    commands.add_parser("collect", help="Read all configured input pages with complete pagination")
    pending = commands.add_parser("pending")
    pending.add_argument("--consumer", default="settle")
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--output", type=Path, required=True)
    freeze.add_argument("--consumer", default="settle")
    freeze.add_argument("--method-version", default="lib-settle/3")
    freeze.add_argument("--keys", type=Path)
    for name in ("validate", "apply"):
        commands.add_parser(name).add_argument("staging", type=Path)
    commands.add_parser("recover").add_argument("run_id")
    commands.add_parser("index")
    query = commands.add_parser("search")
    query.add_argument("query")
    query.add_argument("--limit", type=int, default=5)
    query.add_argument("--scope", choices=("personal", "entities", "sources", "all"), default="personal")
    commands.add_parser("resolve").add_argument("reference")
    graph = commands.add_parser("neighbors")
    graph.add_argument("entity_id")
    graph.add_argument("--predicate")
    graph.add_argument("--direction", choices=("incoming", "outgoing", "both"), default="both")
    source = commands.add_parser("source-open")
    source.add_argument("reference")
    source.add_argument("--mode", choices=("cache", "if-stale", "live", "historical"), default="cache")
    source.add_argument("--revision", type=int)
    todo = commands.add_parser("todo-add")
    todo.add_argument("text")
    todo.add_argument("--event", required=True)
    todo.add_argument("--revision", type=int, required=True)
    todo.add_argument("--anchor", required=True)
    todo.add_argument("--due")
    todo.add_argument("--entity", dest="entity_ids", action="append", default=[])
    todos = commands.add_parser("todo-list")
    todos.add_argument("--status")
    log = commands.add_parser("worklog")
    log.add_argument("--run", dest="run_id")
    remote = commands.add_parser("publish")
    remote.add_argument("--entity", action="append", dest="entities")
    provisioning = commands.add_parser("setup", aliases=["notion-setup"])
    location = provisioning.add_mutually_exclusive_group(required=True)
    location.add_argument("--parent")
    location.add_argument("--main")
    provisioning.add_argument("--dry-run", action="store_true")
    commands.add_parser("backup").add_argument("--output", type=Path, required=True)
    return root


def run(args):
    library = Library(args.vault)
    name = args.command
    if name == "status":
        result = library.status()
        for label, path in (("collect", "_state/notion/acquisition.json"), ("publish", "_state/notion/last-publish.json")):
            target = args.vault / path
            result[label] = read_json(target) if target.exists() else {"status": "not_run"}
        result["notion_setup"] = "configured" if (args.vault / SETUP).exists() else "parent_required"
        return result
    if name == "doctor":
        result = {"vault": str(args.vault.resolve()), "runtime_version": __version__, "storage": library.status()}
        if args.offline:
            result["notion"] = {"status": "not_checked", "reason": "offline requested"}
        else:
            client = NotionClient()
            if (args.vault / SETUP).exists():
                settings = config(args.vault)
                result["notion"] = {"workspace_id": workspace(client, settings["workspace_id"]), "resources": settings["resources"]}
                for key in ("events", "entities"):
                    client.request("GET", "/data_sources/" + settings["resources"][key]["data_source_id"])
            else:
                result["notion"] = {"workspace_id": workspace(client), "status": "parent_required"}
        return result
    if name == "capture":
        return library.capture(args.file, resource_id=args.resource_id, name=args.name, occurred_at=args.occurred_at,
                               mode="result" if args.mode == "event" else args.mode)
    if name == "capture-url":
        from .github import capture_url
        return capture_url(args.vault, args.url, mode=args.mode)
    if name == "collect":
        return collect(args.vault)
    if name == "pending":
        return library.pending(consumer=args.consumer)
    if name == "freeze":
        return library.freeze(args.output, consumer=args.consumer, method_version=args.method_version,
                              keys=read_json(args.keys) if args.keys else None)
    if name in {"validate", "apply"}:
        return getattr(library, name)(args.staging)
    if name == "recover":
        return library.recover(args.run_id)
    if name == "index":
        return build_index(args.vault)
    if name == "search":
        return search(args.vault, args.query, limit=args.limit, scope=args.scope)
    if name == "resolve":
        return resolve(args.vault, args.reference)
    if name == "neighbors":
        return neighbors(args.vault, args.entity_id, predicate=args.predicate, direction=args.direction)
    if name == "source-open":
        result = source_open(args.vault, args.reference, args.mode, args.revision)
        if result.get("source", result.get("cached_source", {})).get("identity", {}).get("provider") == "github":
            from .github import source_open as github_source
            return github_source(args.vault, args.reference, mode=args.mode, revision=args.revision)
        return result
    if name == "todo-add":
        from .todo import add_todo
        return add_todo(args.vault, args.text, args.event, args.revision, args.anchor, args.due, args.entity_ids)
    if name == "todo-list":
        from .todo import list_todos
        return list_todos(args.vault, args.status)
    if name == "worklog":
        from .worklog import write_worklog
        return {"written": write_worklog(args.vault, args.run_id)}
    if name == "publish":
        return publish(args.vault, args.entities)
    if name in {"setup", "notion-setup"}:
        return setup(args.vault, args.parent, dry_run=args.dry_run, main=args.main)
    if name == "backup":
        return library.backup(args.output)
    raise ValueError("Unknown operation")


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = run(args)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        failed = {"failed", "blocked", "needs_review", "uncertain", "retryable", "pending_async", "unreachable", "conflict"}
        if isinstance(result, dict):
            if result.get("status") in failed or any(item.get("status") in failed for item in result.get("results", [])):
                return 1
            if any(item.get("status") not in {"excluded_machine_output"} for item in result.get("failures", [])):
                return 1
        return 0
    except BlockingIOError:
        print(json.dumps({"status": "busy", "reason": "Another vault writer holds the shared lock"}), file=sys.stderr)
        return 75
    except (ValueError, OSError, RuntimeError, KeyError) as error:
        print(json.dumps({"status": "failed", "reason": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
