# Candidate protocol runtime boundary

The candidate protocol intentionally uses two implementation tiers.

## Orchestrator-owned execution uses Rust

Workflows that run inside `jpapt-v2.2-inspection` and therefore have the repository Rust workspace available use the `asr-contracts` binaries as the production authority for candidate protocol construction and validation.

Current production Rust surfaces are:

```text
rust/crates/asr-contracts/src/bin/asr-candidate-request.rs
rust/crates/asr-contracts/src/bin/asr-candidate-protocol.rs
rust/crates/asr-contracts/src/bin/asr-candidate-protocol-build.rs
```

The principal workflow bindings are:

```text
.github/workflows/candidate-request-gateway.yml
  request resolution -> asr-candidate-request
  rejection builder  -> asr-candidate-protocol-build rejection

.github/workflows/candidate-package-evaluate-v2.yml
  request resolution -> asr-candidate-request
  completion builder -> asr-candidate-protocol-build receipt
```

The production-wiring contract is:

```text
.github/workflows/candidate-protocol-production-wiring-contracts.yml
```

It verifies workflow syntax, Rust toolchain wiring, absence of the superseded Python completion/rejection builders from those orchestrator production jobs, and functional receipt/rejection generation plus Rust validation.

## Receiver bootstrap remains portable Python

A completion receiver may be installed into an arbitrary external repository. That repository is not required to contain this project's Rust workspace, Cargo lockfile, or Rust toolchain.

Therefore the receiver bundle intentionally remains self-contained Python/shell rather than depending on `asr-contracts` binaries.

The reference receiver is:

```text
.github/workflows/candidate-completion-receipt.yml
```

Its portable protocol helpers include:

```text
scripts/ci/build-candidate-completion-receipt.py
scripts/ci/build-candidate-completion-ack.py
scripts/ci/build-candidate-request-rejection.py
scripts/ci/validate-candidate-protocol-binding.py
scripts/ci/portable/validate-candidate-protocol-binding.py
```

These Python implementations are compatibility/portability surfaces, not the preferred orchestrator production implementation.

## Cross-language compatibility is required

The Rust and portable Python implementations must continue to agree on protocol bytes and semantics where both implement the same contract.

Focused parity coverage is provided by:

```text
.github/workflows/candidate-protocol-rust-contracts.yml
.github/workflows/candidate-protocol-rust-build-contracts.yml
```

The synthetic end-to-end chain intentionally crosses the runtime boundary:

```text
Gateway-style normalized request
  -> Rust completion receipt
  -> portable Python ACK
  -> lifecycle completed/acknowledged
  -> timeline reduction
```

That test lives in:

```text
.github/workflows/candidate-protocol-synthetic-e2e.yml
```

A matching canonical receipt SHA-256 across the Rust receipt implementation and portable Python ACK implementation is part of the test contract.

## Migration rule

Do not migrate an external receiver workflow to Rust merely because a Rust implementation exists in the orchestrator repository.

A receiver-side Rust migration is valid only if the receiver installation contract is changed to provide a self-contained Rust executable or another portable artifact with an explicit version/distribution policy. Until then:

- orchestrator-owned request/completion/rejection logic should prefer Rust;
- external receiver validation and ACK construction should remain portable;
- parity CI must protect the boundary between the two implementations.
