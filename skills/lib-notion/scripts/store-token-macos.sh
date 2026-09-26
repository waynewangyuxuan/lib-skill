#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This helper requires macOS Keychain." >&2
  exit 2
fi
if [[ ! -t 0 ]]; then
  echo "Run this helper in an interactive terminal so Keychain can prompt securely." >&2
  exit 2
fi

script_dir="$(cd "$(dirname "$0")" && pwd)"
printf 'Paste Notion personal access token (input hidden), then press Return: ' >&2
IFS= read -r -s token
printf '\n' >&2
if [[ -z "$token" ]]; then
  echo "No token entered; Keychain was not changed." >&2
  exit 2
fi
printf '%s' "$token" | python3 "$script_dir/scan.py" store-token
unset token
