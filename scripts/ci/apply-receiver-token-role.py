#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ENVIRONMENT = "Private-Secrets"


def replace_once(path: Path, old: str, new: str) -> bool:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 0:
        if new in text:
            return False
        raise SystemExit(f"expected text not found in {path}: {old[:100]!r}")
    if count != 1:
        raise SystemExit(f"expected exactly one match in {path}, found {count}: {old[:100]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return True


def ensure_job_environment(path: Path, job: str) -> bool:
    text = path.read_text(encoding="utf-8")
    marker = f"  {job}:\n"
    start = text.find(marker)
    if start < 0:
        raise SystemExit(f"job {job!r} not found in {path}")
    next_job = text.find("\n  ", start + len(marker))
    end = len(text) if next_job < 0 else next_job + 1
    block = text[start:end]
    environment_line = f"    environment: {ENVIRONMENT}\n"
    if environment_line in block:
        return False
    text = text[: start + len(marker)] + environment_line + text[start + len(marker) :]
    path.write_text(text, encoding="utf-8")
    return True


def main() -> int:
    changed: list[str] = []

    # Source config reads remain SOURCE_REPO_TOKEN; external receiver operations use TARGET_REPO_TOKEN.
    v2 = Path(".github/workflows/candidate-package-evaluate-v2.yml")
    if ensure_job_environment(v2, "resolve"):
        changed.append(str(v2))
    if ensure_job_environment(v2, "completion"):
        changed.append(str(v2))
    if replace_once(
        v2,
        "          RECEIPT_TOKEN: ${{ secrets.SOURCE_REPO_TOKEN }}\n",
        "          RECEIPT_TOKEN: ${{ secrets.TARGET_REPO_TOKEN }}\n",
    ):
        changed.append(str(v2))
    if replace_once(
        v2,
        '            echo "::error::SOURCE_REPO_TOKEN is required to deliver completion receipt to $RECEIPT_REPOSITORY"\n',
        '            echo "::error::TARGET_REPO_TOKEN is required to deliver completion receipt to $RECEIPT_REPOSITORY"\n',
    ):
        changed.append(str(v2))

    readiness = Path(".github/workflows/candidate-protocol-readiness.yml")
    if ensure_job_environment(readiness, "audit"):
        changed.append(str(readiness))
    if replace_once(
        readiness,
        "          SOURCE_REPO_TOKEN: ${{ secrets.SOURCE_REPO_TOKEN }}\n          HF_TOKEN: ${{ secrets.HF_TOKEN }}\n",
        "          TARGET_REPO_TOKEN: ${{ secrets.TARGET_REPO_TOKEN }}\n          HF_TOKEN: ${{ secrets.HF_TOKEN }}\n",
    ):
        changed.append(str(readiness))
    if replace_once(
        readiness,
        '          [[ -n "${SOURCE_REPO_TOKEN:-}" ]] || {\n            echo "::error::SOURCE_REPO_TOKEN is not configured"\n',
        '          [[ -n "${TARGET_REPO_TOKEN:-}" ]] || {\n            echo "::error::TARGET_REPO_TOKEN is not configured"\n',
    ):
        changed.append(str(readiness))
    if replace_once(
        readiness,
        "          GH_TOKEN: ${{ secrets.SOURCE_REPO_TOKEN }}\n          RECEIPT_REPOSITORY: ${{ inputs.receipt_repository }}\n",
        "          GH_TOKEN: ${{ secrets.TARGET_REPO_TOKEN }}\n          RECEIPT_REPOSITORY: ${{ inputs.receipt_repository }}\n",
    ):
        changed.append(str(readiness))
    if replace_once(
        readiness,
        "            echo '- orchestrator SOURCE_REPO_TOKEN / HF_TOKEN: configured'\n",
        "            echo '- orchestrator TARGET_REPO_TOKEN / HF_TOKEN: configured'\n",
    ):
        changed.append(str(readiness))

    e2e = Path(".github/workflows/candidate-protocol-e2e.yml")
    if replace_once(
        e2e,
        "env:\n  SOURCE_REPO_TOKEN: ${{ secrets.SOURCE_REPO_TOKEN }}\n",
        "env:\n  TARGET_REPO_TOKEN: ${{ secrets.TARGET_REPO_TOKEN }}\n",
    ):
        changed.append(str(e2e))
    if ensure_job_environment(e2e, "e2e"):
        changed.append(str(e2e))
    if replace_once(
        e2e,
        "          GH_TOKEN: ${{ secrets.SOURCE_REPO_TOKEN }}\n          RECEIPT_REPOSITORY: ${{ inputs.receipt_repository }}\n",
        "          GH_TOKEN: ${{ secrets.TARGET_REPO_TOKEN }}\n          RECEIPT_REPOSITORY: ${{ inputs.receipt_repository }}\n",
    ):
        changed.append(str(e2e))
    if replace_once(
        e2e,
        '            echo "::error::SOURCE_REPO_TOKEN is required for cross-repository E2E delivery and preflight"\n',
        '            echo "::error::TARGET_REPO_TOKEN is required for cross-repository E2E delivery and preflight"\n',
    ):
        changed.append(str(e2e))

    bootstrap = Path(".github/workflows/candidate-receiver-bootstrap.yml")
    if replace_once(
        bootstrap,
        "env:\n  SOURCE_REPO_TOKEN: ${{ secrets.SOURCE_REPO_TOKEN }}\n",
        "env:\n  TARGET_REPO_TOKEN: ${{ secrets.TARGET_REPO_TOKEN }}\n",
    ):
        changed.append(str(bootstrap))
    if ensure_job_environment(bootstrap, "bootstrap"):
        changed.append(str(bootstrap))
    for old, new in [
        ("          GH_TOKEN: ${{ secrets.SOURCE_REPO_TOKEN }}\n", "          GH_TOKEN: ${{ secrets.TARGET_REPO_TOKEN }}\n"),
        ('            echo "::error::SOURCE_REPO_TOKEN is required for receiver bootstrap"\n', '            echo "::error::TARGET_REPO_TOKEN is required for receiver bootstrap"\n'),
    ]:
        text = bootstrap.read_text(encoding="utf-8")
        if old in text:
            bootstrap.write_text(text.replace(old, new), encoding="utf-8")
            changed.append(str(bootstrap))

    reconcile = Path(".github/workflows/candidate-completion-reconcile.yml")
    if replace_once(
        reconcile,
        "env:\n  SOURCE_REPO_TOKEN: ${{ secrets.SOURCE_REPO_TOKEN }}\n",
        "env:\n  TARGET_REPO_TOKEN: ${{ secrets.TARGET_REPO_TOKEN }}\n",
    ):
        changed.append(str(reconcile))
    if ensure_job_environment(reconcile, "reconcile"):
        changed.append(str(reconcile))
    if replace_once(
        reconcile,
        '          token="${SOURCE_REPO_TOKEN:-}"\n',
        '          token="${TARGET_REPO_TOKEN:-}"\n',
    ):
        changed.append(str(reconcile))
    if replace_once(
        reconcile,
        '            echo "::error::SOURCE_REPO_TOKEN is required to reconcile completion delivery to $RECEIPT_REPOSITORY"\n',
        '            echo "::error::TARGET_REPO_TOKEN is required to reconcile completion delivery to $RECEIPT_REPOSITORY"\n',
    ):
        changed.append(str(reconcile))

    print("receiver token role migration: ok")
    for item in sorted(set(changed)):
        print(f"changed: {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
