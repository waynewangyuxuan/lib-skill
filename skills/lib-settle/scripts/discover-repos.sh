#!/usr/bin/env bash
# discover-repos.sh — derive the reverse-settle repo list from entity Access sections.
#
# Why this exists: a hardcoded repo list silently drops whole days of work when a new
# project appears. Entity pages already declare where their code lives, so ## Access is
# the source of truth. Learned the hard way — see lib-settle/stdlib/reverse-scan.md.
#
# Usage:  discover-repos.sh [vault_root]      # default: ~/MyLibrary
# Output: one absolute repo root per line — deduped by shared object store, so a linked
#         worktree never appears twice.

set -uo pipefail
VAULT="${1:-$HOME/MyLibrary}"
ENT="$VAULT/_entities"
[ -d "$ENT" ] || { echo "no _entities at $ENT" >&2; exit 1; }

{
  # Rule 1 — explicit local paths (~/foo, /Users/x/foo) inside ## Access blocks.
  for f in "$ENT"/*.md; do
    awk '/^## Access/{a=1;next} /^## /{a=0} a' "$f" 2>/dev/null \
      | grep -oE '(~|/Users/[A-Za-z0-9._-]+)/[A-Za-z0-9._/-]+'
  done
  # Rule 2 — GitHub refs with no local path: try $HOME/<repo-name>.
  for f in "$ENT"/*.md; do
    awk '/^## Access/{a=1;next} /^## /{a=0} a' "$f" 2>/dev/null \
      | grep -oE 'github\.com[/:][A-Za-z0-9._-]+/[A-Za-z0-9._-]+' \
      | sed -E 's#.*/([A-Za-z0-9._-]+)$#'"$HOME"'/\1#'
  done
} | sed -e "s:^~:$HOME:" -e 's:/*$::' -e 's:\.git$::' \
  | sort -u \
  | while read -r p; do
      [ -n "$p" ] || continue
      case "$p" in */.*) continue ;; esac   # skip hidden dirs (.codex/.claude caches)
      git -C "$p" rev-parse --git-dir >/dev/null 2>&1 || continue
      # Key: print "<shared object store>\t<repo root>" so linked worktrees collapse
      # onto their parent instead of being scanned (and counted) twice.
      common=$(git -C "$p" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
      root=$(git -C "$p" rev-parse --show-toplevel 2>/dev/null)
      [ -n "$common" ] && [ -n "$root" ] && printf '%s\t%s\n' "$common" "$root"
    done \
  | sort -u -k1,1 \
  | cut -f2 \
  | sort -u

exit 0
