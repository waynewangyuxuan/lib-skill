#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")" && pwd)"
agent_name="claude-code"
runtime_python="${MYLIBRARY_PYTHON:-python3}"
runtime_only=false
dry_run=false
skills=(lib-entity lib-manual lib-notion lib-review lib-search lib-settle)

usage() {
  echo "Usage: bash install.sh [codex|claude-code|all] [--python executable] [--runtime-only] [--dry-run]"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    codex|claude-code|all) agent_name="$1" ;;
    --python)
      [ "$#" -ge 2 ] || { usage >&2; exit 2; }
      runtime_python="$2"
      shift
      ;;
    --runtime-only) runtime_only=true ;;
    --dry-run) dry_run=true ;;
    --help|-h) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
  shift
done

case "$agent_name" in
  codex) targets=("$HOME/.agents/skills") ;;
  claude-code) targets=("$HOME/.claude/skills") ;;
  all) targets=("$HOME/.agents/skills" "$HOME/.claude/skills") ;;
esac

if $dry_run; then
  printf 'Would run: %q -m pip install -e %q\n' "$runtime_python" "$repo_dir"
  if ! $runtime_only; then
    printf 'Would synchronize shared references and link skills into %s\n' "${targets[@]}"
  fi
  exit 0
fi

"$runtime_python" -m pip install -e "$repo_dir"
if $runtime_only; then
  exit 0
fi
bash "$repo_dir/scripts/sync-stdlib.sh"

for target_dir in "${targets[@]}"; do
  mkdir -p "$target_dir"
  for skill_name in "${skills[@]}"; do
    source_dir="$repo_dir/skills/$skill_name"
    destination="$target_dir/$skill_name"
    if [ -L "$destination" ]; then
      unlink "$destination"
    elif [ -e "$destination" ]; then
      backup_path="${destination}.bak.$(date +%Y%m%d%H%M%S)"
      echo "Backing up existing: $destination -> $backup_path"
      mv "$destination" "$backup_path"
    fi
    ln -s "$source_dir" "$destination"
    echo "Linked: $skill_name -> $destination"
  done
done
