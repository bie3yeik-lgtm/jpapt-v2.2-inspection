#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "hf" / "hf-fetch-candidate.sh"


def main() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    mode = 'MODE="${2:-}"'
    validate = '[[ -z "$MODE" || "$MODE" == "--resolve-only" ]] || fail "unsupported mode: $MODE"'
    output = 'append_output candidate_id "$CANDIDATE_ID"'
    resolve_only = 'if [[ "$MODE" == "--resolve-only" ]]; then'
    sync = 'hf buckets sync --token "$HF_TOKEN" "$REMOTE" "$STAGING"'

    for marker in (mode, validate, output, resolve_only, sync):
        assert marker in text, marker

    assert text.index(validate) < text.index(output)
    assert text.index(output) < text.index(resolve_only)
    assert text.index(resolve_only) < text.index(sync)

    resolve_block = text[text.index(resolve_only) : text.index(sync)]
    assert "exit 0" in resolve_block
    assert "Resolved candidate without materializing files" in resolve_block

    # Listing and the Rust resolver remain authoritative in both modes.
    assert 'hf buckets list --token "$HF_TOKEN" "$REMOTE_ROOT" -R -q' in text
    assert 'ARGS=(resolve-candidate-location --listing "$listing")' in text
    assert 'cargo run --quiet --locked -p asr-hf -- "${ARGS[@]}"' in text

    print("hf-fetch-candidate resolve-only contracts: PASS")


if __name__ == "__main__":
    main()
