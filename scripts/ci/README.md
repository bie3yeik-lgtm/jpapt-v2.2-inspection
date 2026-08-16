# CI helper scripts

This directory contains thin CI-facing wrappers only for responsibilities that
have not yet moved into the canonical Rust crates.

Stable model-independent validation, revision selection, project configuration
resolution, and Rust evaluator run-context construction belong in Rust.
`asr-contracts` is the canonical authority for these contracts and they must not
be reintroduced as Python business logic.

The remaining Python migration boundaries are candidate preparation and dataset
acquisition/materialization where Hugging Face `datasets` is required. These
wrappers must not duplicate production runtime, configuration, revision, or
validation behavior.

Representative files:

```text
scripts/ci/
├── README.md
└── validate-revisions.sh   # thin exec wrapper around Rust asr-contracts
```

Canonical Rust commands include:

```bash
cargo run --quiet --locked -p asr-contracts --bin asr-contracts -- \
  validate-run results/<run>

cargo run --quiet --locked -p asr-contracts --bin asr-contracts -- \
  validate-revisions --root .ci/hf/config/revisions

cargo run --quiet --locked -p asr-contracts --bin asr-contracts -- \
  build-run-context \
  --repository-root . \
  --model <model-id> \
  --provider <provider-id> \
  --evaluation <evaluation-id> \
  --environment <environment-id> \
  --revisions .ci/hf/config/revisions \
  --candidate-contract .ci/candidate-contract.json \
  --output .ci/run-context.json
```

`hf-fetch-revisions.sh` uses `asr-contracts resolve-config` and
`validate-revisions`; it does not perform revision JSON parsing through Python.

Python helpers that remain because they cross a Python-native ecosystem boundary
should run through the locked project environment until that boundary can be
reduced further.
