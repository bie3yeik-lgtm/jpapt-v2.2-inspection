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

.github/workflows/candidate-request-lifecycle-observer.yml
  completion receipt validation -> asr-candidate-protocol receipt-validate
  canonical receipt SHA-256     -> asr-candidate-protocol receipt-sha

.github/workflows/candidate-completion-ack.yml
  ACK/receipt validation -> asr-candidate-protocol
  ACK binding             -> asr-candidate-protocol ack-binding

.github/workflows/candidate-completion-reconcile.yml
  preserved receipt validation -> asr-candidate-protocol receipt-validate
  canonical receipt SHA-256    -> asr-candidate-protocol receipt-sha

.github/workflows/candidate-lifecycle-persist.yml
  rejection validation -> asr-candidate-protocol rejection-validate
  receipt validation   -> asr-candidate-protocol receipt-validate
  ACK validation       -> asr-candidate-protocol ack-validate
  ACK/receipt binding  -> asr-candidate-protocol ack-binding

.github/workflows/candidate-protocol-e2e.yml
  recovered receipt validation -> asr-candidate-protocol receipt-validate
  recovered ACK validation     -> asr-candidate-protocol ack-validate
  recovered ACK/receipt binding -> asr-candidate-protocol ack-binding
```

Durable lifecycle persistence is fail-closed at the canonical evidence boundary. Rejection, completion receipt, and acknowledgement evidence are validated with Rust before being passed to the lifecycle Bucket writer. An `acknowledged` snapshot additionally requires both its preserved completion receipt and acknowledgement artifact, and their binding is revalidated before durable storage.

The cross-repository E2E harness preserves the portability boundary in the opposite direction: the external receiver still validates and constructs ACKs with its self-contained Python/shell bundle, while the orchestrator revalidates the returned receipt/ACK evidence with Rust before declaring the E2E evidence valid.

Focused production-authority contracts are:

```text
.github/workflows/candidate-protocol-production-wiring-contracts.yml
.github/workflows/candidate-lifecycle-persist-protocol-authority-contracts.yml
.github/workflows/candidate-lifecycle-persist-contracts.yml
.github/workflows/candidate-protocol-surface-contracts.yml
.github/workflows/candidate-protocol-e2e-contracts.yml
```

They verify Rust toolchain wiring, absence of superseded Python production builders/validators from orchestrator-owned authority paths, functional receipt/rejection/ACK validation and binding, current lifecycle materialization semantics, the manual cross-repository E2E authority boundary, and the cross-language synthetic boundary.

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

Lifecycle/timeline indexing and query utilities may also remain Python where they are not protocol construction or trust-boundary authority. The migration rule is based on responsibility, not language elimination.

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

No-compute dry-run receipt semantics are also exercised with the production Rust builder by:

```text
.github/workflows/candidate-dry-run-contracts.yml
```

It covers successful dry-run completion, non-dry execution with no terminal evaluator result, and real orchestration failure without launching candidate/model evaluation compute.

The manual cross-repository harness is protected statically by:

```text
.github/workflows/candidate-protocol-e2e-contracts.yml
```

That contract proves the harness remains manual-only, hard-codes the dry-run cost boundary, uses bounded V2 dispatch, preserves external receiver preflight, and uses Rust authority for recovered receipt/ACK validation and ACK binding. A real successful cross-repository routing run still requires the dedicated external fixture tracked by Issue #70.

## Migration rule

Do not migrate an external receiver workflow to Rust merely because a Rust implementation exists in the orchestrator repository.

A receiver-side Rust migration is valid only if the receiver installation contract is changed to provide a self-contained Rust executable or another portable artifact with an explicit version/distribution policy. Until then:

- orchestrator-owned request/completion/rejection construction and canonical protocol validation should prefer Rust;
- orchestrator-owned durable persistence must validate canonical protocol evidence with Rust before storage;
- orchestrator-side recovery of externally returned protocol evidence should use Rust authority;
- external receiver validation and ACK construction should remain portable;
- lifecycle/timeline query utilities may remain Python when they are not protocol trust authority;
- parity CI must protect the boundary between the two implementations.
