#!/usr/bin/env python3
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "candidate-request-gateway.yml"


def block(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def main() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    workflow_permissions = block(text, "\npermissions:\n", "\nenv:\n")
    assert workflow_permissions == "\npermissions:\n  contents: read\n"

    plan = block(text, "\n  plan:\n", "\n  execute:\n")
    assert "    permissions:\n      contents: read\n      actions: read\n" in plan
    assert "    permissions:\n      contents: read\n      actions: write\n" not in plan

    execute = block(text, "\n  execute:\n", "\n  reject:\n")
    assert "    permissions:\n      contents: read\n      actions: write\n" in execute
    assert "    permissions:\n      contents: read\n      actions: read\n" not in execute

    reject = text[text.index("\n  reject:\n") :]
    assert "    permissions:\n      contents: read\n" in reject
    assert "    permissions:\n      contents: read\n      actions:" not in reject

    # One capability occurrence each in the workflow: read in plan, write in execute.
    assert text.count("      actions: read\n") == 1
    assert text.count("      actions: write\n") == 1

    print("candidate gateway Actions-permission contracts: PASS")


if __name__ == "__main__":
    main()
