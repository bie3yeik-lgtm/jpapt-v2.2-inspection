# CI helper scripts

This directory contains thin CI-facing wrappers only for responsibilities that
have not yet moved into the canonical Rust crates.

Stable model-independent validation belongs in Rust. Evaluation result and
revision-bundle validation are both provided by `asr-contracts` and must not be
reintroduced as Python business logic.

Current Python migration boundaries are configuration/candidate preparation,
dataset acquisition/materialization where Hugging Face `datasets` is required,
and run-context construction. These wrappers must not duplicate production
runtime or validation behavior.

Representative files:

```text
scripts/ci/
├── README.md
├── validate-revisions.py   # deprecated compatibility exec shim only
└── make-run-context.py
```

Canonical validation commands:

```bash
cargo run --quiet --locked -p asr-contracts --bin asr-contracts -- \
  validate-run results/<run>

cargo run --quiet --locked -p asr-contracts --bin asr-contracts -- \
  validate-revisions --root .ci/hf/config/revisions
```

`hf-fetch-revisions.sh` also uses `asr-contracts resolve-config` and
`validate-revisions`; it no longer performs JSON parsing through Python.

Remaining Python preparation wrappers should run through the locked project
environment until their Rust replacements land:

```bash
uv run python scripts/ci/make-run-context.py ...
```
