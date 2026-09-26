#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This helper requires macOS Keychain." >&2
  exit 2
fi

service="com.wayne.lib-notion"
account="$(id -un)"
echo "Keychain will prompt for the Notion token without putting it in shell history."
security add-generic-password -U -a "$account" -s "$service" -w >/dev/null
echo "Stored Notion token in macOS Keychain under $service."
