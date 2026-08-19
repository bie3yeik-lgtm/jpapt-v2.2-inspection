#!/usr/bin/env python3
"""Bind Environment-scoped protocol secrets to the jobs that consume them.

The repository stores SOURCE_REPO_TOKEN and JPAPT_ACK_TOKEN in the
`Private-Secrets` GitHub Environment. GitHub only injects Environment Secrets
into jobs that explicitly reference that Environment.

This tool can either patch canonical workflow files in place or check that the
binding is already present. Agent/validation-only workflows are intentionally
ignored.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

WORKFLOW_DIR = Path(".github/workflows")
ENVIRONMENT = "Private-Secrets"
ENVIRONMENT_LINE = f"    environment: {ENVIRONMENT}"
SECRET_MARKERS = (
    "secrets.SOURCE_REPO_TOKEN",
    "secrets.JPAPT_ACK_TOKEN",
)


def iter_job_blocks(lines: list[str]) -> list[tuple[int, int, str]]:
    try:
        jobs_index = lines.index("jobs:")
    except ValueError:
        return []

    starts: list[int] = []
    for index in range(jobs_index + 1, len(lines)):
        line = lines[index]
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
            starts.append(index)

    blocks: list[tuple[int, int, str]] = []
    for offset, start in enumerate(starts):
        end = starts[offset + 1] if offset + 1 < len(starts) else len(lines)
        job_name = lines[start].strip()[:-1]
        blocks.append((start, end, job_name))
    return blocks


def required_bindings(path: Path) -> list[tuple[int, int, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    result: list[tuple[int, int, str]] = []
    for start, end, job_name in iter_job_blocks(lines):
        block = "\n".join(lines[start:end])
        if any(marker in block for marker in SECRET_MARKERS):
            result.append((start, end, job_name))
    return result


def check() -> list[str]:
    errors: list[str] = []
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        if path.name.startswith("agent-"):
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for start, end, job_name in iter_job_blocks(lines):
            block = "\n".join(lines[start:end])
            if not any(marker in block for marker in SECRET_MARKERS):
                continue
            if ENVIRONMENT_LINE not in lines[start:end]:
                errors.append(f"{path}:{job_name}")
    return errors


def patch() -> list[str]:
    changed: list[str] = []
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        if path.name.startswith("agent-"):
            continue
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        plain = [line.rstrip("\n") for line in lines]
        inserts: list[int] = []
        for start, end, _job_name in iter_job_blocks(plain):
            block = "\n".join(plain[start:end])
            if not any(marker in block for marker in SECRET_MARKERS):
                continue
            if ENVIRONMENT_LINE in plain[start:end]:
                continue
            inserts.append(start + 1)

        if not inserts:
            continue
        for index in reversed(inserts):
            lines.insert(index, ENVIRONMENT_LINE + "\n")
        path.write_text("".join(lines), encoding="utf-8")
        changed.append(str(path))
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="patch workflows in place")
    args = parser.parse_args()

    if args.write:
        for path in patch():
            print(f"patched: {path}")

    errors = check()
    if errors:
        for item in errors:
            print(
                f"missing environment {ENVIRONMENT!r} for Environment-scoped secret job: {item}",
                file=sys.stderr,
            )
        return 1

    print("private-secrets environment bindings: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
