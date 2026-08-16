#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
import sys


# Project policy. Cache restore/save are optional actions, but when they are
# used they must follow the same v6 major as actions/cache.
REQUIRED = {
    "actions/checkout": "v6",
    "actions/setup-python": "v7",
    "actions/upload-artifact": "v7",
    "actions/cache": "v6",
    "actions/cache/restore": "v6",
    "actions/cache/save": "v6",
}
REQUIRED_PRESENT = {
    "actions/checkout",
    "actions/setup-python",
    "actions/upload-artifact",
    "actions/cache",
}
USES_RE = re.compile(
    r"\buses:\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?)@([^\s#]+)"
)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    workflow_root = root / ".github" / "workflows"
    errors: list[str] = []
    seen: dict[str, int] = {name: 0 for name in REQUIRED}

    for path in sorted(workflow_root.glob("*.yml")):
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            match = USES_RE.search(line)
            if match is None:
                continue
            action, version = match.groups()
            expected = REQUIRED.get(action)
            if expected is None:
                continue
            seen[action] += 1
            if version != expected:
                errors.append(
                    f"{path.relative_to(root)}:{line_number}: "
                    f"{action}@{version} is forbidden; required={action}@{expected}"
                )

    missing = [name for name in sorted(REQUIRED_PRESENT) if seen[name] == 0]
    if missing:
        errors.append(
            "required version-policy actions were not found in any workflow; if an "
            f"action is intentionally removed, update the policy explicitly: {missing!r}"
        )

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    for action, version in REQUIRED.items():
        requirement = "required" if action in REQUIRED_PRESENT else "if-used"
        print(f"OK: {action}@{version} ({seen[action]} use(s), {requirement})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
