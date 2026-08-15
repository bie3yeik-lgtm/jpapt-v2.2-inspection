# CI helper scripts

This directory contains thin CI-facing wrappers around the canonical
`parakeet_onnx` Python package.

These scripts must not duplicate core evaluation, revision, configuration, or
run-context logic.

Expected files:

```text
scripts/ci/
├── README.md
├── validate-revisions.py
├── validate-result.py
└── make-run-context.py
```

Run them through the locked project environment:

```bash
uv run python scripts/ci/validate-revisions.py
uv run python scripts/ci/validate-result.py results/<run>
uv run python scripts/ci/make-run-context.py ...
```
