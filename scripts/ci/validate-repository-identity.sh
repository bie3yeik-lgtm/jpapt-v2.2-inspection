#!/usr/bin/env bash
set -euo pipefail

value="${1:-}"
field="${2:-repository}"

if [[ ! "$value" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
  echo "ERROR: $field must use owner/name" >&2
  exit 2
fi

owner="${value%%/*}"
name="${value#*/}"
if [[ "$owner" == "." || "$owner" == ".." || "$name" == "." || "$name" == ".." ]]; then
  echo "ERROR: $field must not contain dot-only path segments" >&2
  exit 2
fi

printf '%s\n' "$value"
