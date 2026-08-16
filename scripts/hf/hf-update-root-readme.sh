#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/../.." >/dev/null 2>&1 && pwd)"
cd "$ROOT"

log(){ printf '[hf-update-root-readme] %s\n' "$*" >&2; }
fail(){ printf '[hf-update-root-readme] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "${HF_ALLOCATOR_INTERNAL:-}" == "1" ]] || fail "this script may only run inside the central allocator"
[[ -n "${HF_TOKEN:-}" ]] || fail "HF_TOKEN is required"
[[ -n "${HF_BUCKET:-}" ]] || fail "HF_BUCKET is required"
command -v hf >/dev/null 2>&1 || fail "hf CLI is unavailable"
command -v python >/dev/null 2>&1 || fail "python is unavailable"

BUCKET="${HF_BUCKET#hf://buckets/}"
BUCKET="${BUCKET%/}"
REMOTE_README="hf://buckets/${BUCKET}/README.md"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
README="$WORK/README.md"

# Preserve any human-written content outside the managed marker block.
if ! hf buckets cp --token "$HF_TOKEN" "$REMOTE_README" "$README" >/dev/null 2>"$WORK/read.err"; then
  printf '# %s\n\n' "$BUCKET" > "$README"
fi

for collection in candidates experiments; do
  remote="hf://buckets/${BUCKET}/${collection}"
  if ! hf buckets list --token "$HF_TOKEN" "$remote" -R -q >"$WORK/${collection}.txt" 2>/dev/null; then
    : >"$WORK/${collection}.txt"
  fi
done
if ! hf buckets list --token "$HF_TOKEN" "hf://buckets/${BUCKET}/config/versions" -R -q >"$WORK/config.txt" 2>/dev/null; then
  : >"$WORK/config.txt"
fi

python - "$README" "$WORK" "${HF_ALLOCATED_ID:-unknown}" "${HF_ALLOCATED_COLLECTION:-unknown}" <<'PY'
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import sys

readme = Path(sys.argv[1])
work = Path(sys.argv[2])
last_id = sys.argv[3]
last_collection = sys.argv[4]
START = "<!-- hf-central-allocator:start -->"
END = "<!-- hf-central-allocator:end -->"
PATTERN = re.compile(r"^(?P<id>.+-(?P<n>[0-9]{6}))(?:/|$)")


def current(name: str) -> tuple[str, str]:
    best_n = -1
    best_id = "none"
    for raw in (work / f"{name}.txt").read_text(encoding="utf-8").splitlines():
        path = raw.strip().lstrip("/")
        if not path:
            continue
        first = path.split("/", 1)[0]
        m = PATTERN.match(first + "/")
        if not m:
            continue
        n = int(m.group("n"))
        if n > best_n:
            best_n = n
            best_id = m.group("id")
    return (f"{best_n:06d}" if best_n >= 0 else "000000", best_id)

candidate_n, candidate_id = current("candidates")
experiment_n, experiment_id = current("experiments")
config_n, config_id = current("config")
updated = datetime.now(timezone.utc).isoformat()
block = f"""{START}
## Central Allocator 状態

この節はGitHub Actions `HF Central Sequence Allocator` が採番のたびに自動更新します。手動で番号を書き換えないでください。

- 最終更新: `{updated}`
- 直近の採番: `{last_collection}/{last_id}`
- candidates 現在番号: `{candidate_n}`（`{candidate_id}`）
- experiments 現在番号: `{experiment_n}`（`{experiment_id}`）
- config 現在番号: `{config_n}`（`{config_id}`）

採番規則は各collectionに存在する全prefixの6桁suffixを走査し、最大値 + 1を次の番号とします。複数Repositoryからの採番要求も中央Allocator RepositoryでBucket単位に直列化されます。
{END}"""

text = readme.read_text(encoding="utf-8")
if START in text and END in text:
    before, rest = text.split(START, 1)
    _, after = rest.split(END, 1)
    text = before.rstrip() + "\n\n" + block + after
else:
    text = text.rstrip() + "\n\n" + block + "\n"
readme.write_text(text, encoding="utf-8")
PY

hf buckets cp --token "$HF_TOKEN" "$README" "$REMOTE_README" >/dev/null
log "Updated ${REMOTE_README}"
