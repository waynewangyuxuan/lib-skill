#!/usr/bin/env bash
# Copy shared source references into each independently installable skill.
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

copy_reference() {
  source_name="$1"
  shift
  for target_skill in "$@"; do
    target_dir="$repo_dir/skills/$target_skill/references"
    mkdir -p "$target_dir"
    cp "$repo_dir/_stdlib/$source_name" "$target_dir/$source_name"
  done
}

copy_reference yaml-schema.md lib-compile
copy_reference consumer-interface.md lib-settle
copy_reference relations-vocabulary.md lib-entity lib-review lib-search
copy_reference skill-conventions.md lib-compile lib-entity lib-export lib-review lib-search lib-settle

echo "Synchronized shared references into distributable skills."
