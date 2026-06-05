#!/bin/bash
# Install lib-skill plugin — symlinks skills into ~/.claude/skills/
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="$HOME/.claude/skills"

# Skills to install
SKILLS=(_stdlib lib-compile lib-entity lib-export lib-manual lib-review lib-search lib-settle)

for skill in "${SKILLS[@]}"; do
  src="$SCRIPT_DIR/$skill"
  dest="$TARGET/$skill"
  if [ -L "$dest" ]; then
    echo "Re-linking: $skill"
    rm "$dest"
  elif [ -d "$dest" ]; then
    echo "Backing up existing: $skill → ${dest}.bak"
    mv "$dest" "${dest}.bak"
  fi
  ln -s "$src" "$dest"
  echo "Linked: $skill → $dest"
done

echo "Done. $(ls -1d $TARGET/lib-* | wc -l | tr -d ' ') skills installed."
