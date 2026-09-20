#!/usr/bin/env bash
# scan-day.sh — list MY unlogged commits across every discovered repo for one logical day.
#
# Usage:  scan-day.sh YYYY-MM-DD [vault_root]
# Window: 04:00 that day → 04:00 next day (the vault's day boundary).
#
# Three corrections this encodes, each learned from a real miss:
#   --all          a repo checked out on a feature branch hides its mainline from HEAD.
#   author filter  a shared repo (e.g. Helm: 353/353 commits by a collaborator) otherwise
#                  floods the scan with work that is not yours.
#   worktree dedup handled upstream in discover-repos.sh.

set -uo pipefail
DAY="${1:?usage: scan-day.sh YYYY-MM-DD [vault_root]}"
VAULT="${2:-$HOME/MyLibrary}"
HERE="$(cd "$(dirname "$0")" && pwd)"

NEXT=$(python3 -c "import datetime,sys;d=datetime.date.fromisoformat(sys.argv[1]);print((d+datetime.timedelta(days=1)).isoformat())" "$DAY")

# Whose commits count as "my work". Extend via LIB_SETTLE_AUTHORS (regex, |-separated).
AUTHORS="${LIB_SETTLE_AUTHORS:-$(git -C "$VAULT" config user.email 2>/dev/null)|w.wayne.vip@gmail.com}"

"$HERE/discover-repos.sh" "$VAULT" | while read -r repo; do
  [ -n "$repo" ] || continue
  mine=$(git -C "$repo" log --all --regexp-ignore-case --perl-regexp \
           --author="$AUTHORS" \
           --since="$DAY 04:00" --until="$NEXT 04:00" \
           --format="   %h %ad %an  %s" --date=format:"%H:%M" --reverse 2>/dev/null)
  others=$(git -C "$repo" log --all --since="$DAY 04:00" --until="$NEXT 04:00" --oneline 2>/dev/null | wc -l | tr -d ' ')
  n=$(printf '%s' "$mine" | grep -c . || true)
  if [ "$n" -gt 0 ]; then
    echo "=== $(basename "$repo"): $n mine / $others total ==="
    printf '%s\n' "$mine"
  elif [ "$others" -gt 0 ]; then
    echo "=== $(basename "$repo"): 0 mine / $others total (collaborator-only — context, not your unlogged work) ==="
  fi
done
exit 0
