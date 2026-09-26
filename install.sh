#!/usr/bin/env bash
# Local-development installer. For normal installs, prefer `npx skills add`.
set -euo pipefail

repo_dir="$(cd "$(dirname "$0")" && pwd)"
agent_name="${1:-claude-code}"
skills=(lib-compile lib-entity lib-export lib-manual lib-notion lib-review lib-search lib-settle)

case "$agent_name" in
  codex)
    targets=("$HOME/.agents/skills")
    ;;
  claude-code)
    targets=("$HOME/.claude/skills")
    ;;
  all)
    targets=("$HOME/.agents/skills" "$HOME/.claude/skills")
    ;;
  *)
    echo "Usage: bash install.sh [codex|claude-code|all]" >&2
    exit 2
    ;;
esac

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
