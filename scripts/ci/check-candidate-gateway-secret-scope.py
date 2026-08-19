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

    global_env = block(text, "\nenv:\n", "\njobs:\n")
    assert "secrets." not in global_env, "workflow-level env must not contain secrets"
    assert "HF_DEFAULT_NAMESPACE: ${{ vars.HF_DEFAULT_NAMESPACE }}" in global_env

    normalize = block(
        text,
        "      - name: Normalize event inputs\n",
        "      - name: Fetch source repository routing config\n",
    )
    assert "secrets.HF_TOKEN" not in normalize
    assert "secrets.SOURCE_REPO_TOKEN" not in normalize

    source_fetch = block(
        text,
        "      - name: Fetch source repository routing config\n",
        "      - name: Infer HF namespace\n",
    )
    assert "SOURCE_REPO_TOKEN: ${{ secrets.SOURCE_REPO_TOKEN }}" in source_fetch
    assert "secrets.HF_TOKEN" not in source_fetch

    namespace = block(
        text,
        "      - name: Infer HF namespace\n",
        "      - name: Resolve request with Rust contract\n",
    )
    assert "HF_TOKEN: ${{ secrets.HF_TOKEN }}" in namespace
    assert "secrets.SOURCE_REPO_TOKEN" not in namespace

    resolver = block(
        text,
        "      - name: Resolve request with Rust contract\n",
        "      - name: Build planned lifecycle snapshot\n",
    )
    assert "secrets.HF_TOKEN" not in resolver
    assert "secrets.SOURCE_REPO_TOKEN" not in resolver

    rejection = text[text.index("  reject:\n") :]
    dispatch = rejection[rejection.index("      - name: Dispatch rejection event\n") :]
    assert "RECEIPT_TOKEN: ${{ secrets.SOURCE_REPO_TOKEN }}" in dispatch
    assert "secrets.HF_TOKEN" not in rejection

    assert text.count("${{ secrets.HF_TOKEN }}") == 1
    assert text.count("${{ secrets.SOURCE_REPO_TOKEN }}") == 2

    print("candidate gateway secret-scope contracts: PASS")


if __name__ == "__main__":
    main()
