#!/usr/bin/env python3
from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "candidate-package-evaluate-v2.yml"


def block(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def main() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    global_env = block(text, "\nenv:\n", "\njobs:\n")
    assert "secrets." not in global_env, "workflow-level env must not contain secrets"
    assert "HF_DEFAULT_NAMESPACE: ${{ vars.HF_DEFAULT_NAMESPACE }}" in global_env

    resolve = block(text, "  resolve:\n", "\n  build:\n")
    assert "    environment: Private-Secrets\n" in resolve

    source_fetch = block(
        text,
        "      - name: Fetch source repository routing config\n",
        "      - name: Infer HF namespace\n",
    )
    assert "SOURCE_REPO_TOKEN: ${{ secrets.SOURCE_REPO_TOKEN }}" in source_fetch
    assert "TARGET_REPO_TOKEN: ${{ secrets.TARGET_REPO_TOKEN }}" not in source_fetch
    assert "HF_TOKEN: ${{ secrets.HF_TOKEN }}" not in source_fetch

    namespace = block(
        text,
        "      - name: Infer HF namespace\n",
        "      - name: Resolve with Rust contract\n",
    )
    assert "HF_TOKEN: ${{ secrets.HF_TOKEN }}" in namespace
    assert "SOURCE_REPO_TOKEN: ${{ secrets.SOURCE_REPO_TOKEN }}" not in namespace
    assert "TARGET_REPO_TOKEN: ${{ secrets.TARGET_REPO_TOKEN }}" not in namespace

    candidate_fetch = block(
        text,
        "      - name: Resolve candidate identity and materialize only when building\n",
        "      - uses: docker/setup-buildx-action@v3\n",
    )
    assert "HF_TOKEN: ${{ secrets.HF_TOKEN }}" in candidate_fetch
    assert "SOURCE_REPO_TOKEN: ${{ secrets.SOURCE_REPO_TOKEN }}" not in candidate_fetch
    assert "TARGET_REPO_TOKEN: ${{ secrets.TARGET_REPO_TOKEN }}" not in candidate_fetch

    completion = text[text.index("  completion:\n") :]
    assert "    environment: Private-Secrets\n" in completion
    dispatch = completion[completion.index("      - name: Dispatch completion event\n") :]
    assert "RECEIPT_TOKEN: ${{ secrets.TARGET_REPO_TOKEN }}" in dispatch
    assert "secrets.SOURCE_REPO_TOKEN" not in dispatch

    # SOURCE_REPO_TOKEN is confined to source routing. TARGET_REPO_TOKEN is confined
    # to external receipt delivery, and both jobs are attached to Private-Secrets.
    assert text.count("${{ secrets.SOURCE_REPO_TOKEN }}") == 1
    assert text.count("${{ secrets.TARGET_REPO_TOKEN }}") == 1

    print("candidate package secret-scope contracts: PASS")


if __name__ == "__main__":
    main()
