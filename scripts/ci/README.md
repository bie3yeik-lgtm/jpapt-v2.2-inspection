# CI helper scripts

This directory contains thin CI-facing wrappers only for responsibilities that
have not yet moved into the canonical Rust crates.

Stable model-independent validation belongs in Rust. In particular, evaluation
result validation is provided by `asr-contracts` and must not be reintroduced
as Python logic.

Current Python migration boundaries include revision/configuration preparation
and run-context construction. These wrappers must not duplicate production
runtime or validation behavior.

Representative files:

```text
scripts/ci/
├── README.md
├── validate-revisions.py
└── make-run-context.py
```

Canonical evaluation result validation:

```bash
cargo run --quiet --locked -p asr-contracts --bin asr-contracts -- \
  validate-run results/<run>
```

Remaining Python preparation wrappers should run through the locked project
environment until their Rust replacements land:

```bash
uv run python scripts/ci/validate-revisions.py ...
uv run python scripts/ci/make-run-context.py ...
```
