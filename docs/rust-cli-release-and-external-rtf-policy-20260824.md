# Rust CLI release and external RTF policy

## Purpose

RTF GitHub Actions must execute the same reviewed Rust implementation that is
compiled and released by `rust-workspace-release.yml`. Provider and machine
availability is operational configuration, not a value embedded in Rust.

## Contract

`evaluation/manifests/rtf-cost-policy.json` is the versioned policy document.
It defines provider/GPU targets, batch sizes, numeric bounds, allowed modes,
and the remote timeout. The `asr-rtf-cost-policy` CLI requires
`--policy <path>` and fails closed when the document is missing, malformed, or
does not permit the requested plan. The Rust validator contains no provider or
GPU allow-list and no RTF numeric limits.

Remote benchmark Actions fetch the policy from the immutable workflow commit
using `RTF_COST_POLICY_URL` when provided, otherwise the raw URL for
`${GITHUB_REPOSITORY}/${GITHUB_SHA}`. This keeps a provider-side run bound to
the exact policy revision used by the workflow.

## Release flow

1. `Rust Workspace Release` builds the locked workspace with `--release`.
2. It packages the executable set and SHA-256 checksum into a `rust-v*`
   GitHub Release.
3. RTF ranking, service-result collection, HF/RunPod, and Vast workflows run
   `scripts/ci/install-rust-cli.sh`.
4. The installer selects the newest non-draft, non-prerelease `rust-v*`
   release, downloads exactly one archive and checksum, verifies the checksum,
   and requires `asr-rtf-rank`, `asr-rtf-cost-policy`, and `asr-rtf-service`.
5. A missing release or checksum mismatch stops the Action; it never falls
   back to compiling an unpinned source checkout.

`RUST_CLI_RELEASE_TAG` may be set as a repository variable when a workflow
must use a specific released CLI. The GitHub token needs release read access;
no provider secret is passed to the installer.

## Scope and non-goals

This change covers the RTF execution paths. Contract-only workflows may still
compile Rust from source because their purpose is to test the source and lock
file. Model, dataset, fixture, and GHCR revisions remain separately resolved
and immutable; this policy does not replace those identities.

## Verification

Local/source checks:

```text
cargo fmt --all -- --check
cargo test --locked -p asr-contracts
cargo run --locked -p asr-contracts --bin asr-rtf-cost-policy -- \
  --policy evaluation/manifests/rtf-cost-policy.json \
  --provider hf --gpu t4 --batch-size 1 --repeat 3 --sample-count 50 \
  --target-total-sec 5400 --max-duration-sec 600 --mode guarded
git diff --check
```

The actual `rust-v*` release workflow run is the acceptance evidence that the
release archive and checksum can be consumed by the Actions installer.
