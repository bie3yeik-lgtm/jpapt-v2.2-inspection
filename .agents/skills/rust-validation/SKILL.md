---
name: rust-validation
description: Perform lightweight validation of Rust changes using the repository-selected mise and rustup toolchain. Prefer affected-package checks and targeted tests. Avoid workspace-wide builds, all-features checks, and full test suites unless the change requires them or the user explicitly requests comprehensive validation.
---

---

# Rust Validation

Validate Rust changes using the minimum set of commands needed to establish
confidence in the affected code.

Do not perform workspace-wide validation by default.

Do not change the configured Rust version to work around environment failures.

## 1. Identify the affected Rust scope

Use the current Git diff to determine which Rust files changed.

Prefer:

```sh
git diff --name-only -- '*.rs' 'Cargo.toml' 'Cargo.lock'
```

Identify the affected crate or package from the changed paths and nearby
`Cargo.toml`.

Do not enumerate every crate in the workspace unless the affected package
cannot otherwise be determined.

Do not inspect unrelated Rust packages.

## 2. Trust the repository toolchain

The repository-selected toolchain is authoritative.

Rust is managed through the repository's mise/rustup configuration.

Required components may include:

- rustfmt;
- clippy;
- rust-analyzer.

Do not install another Rust version merely because a validation command fails.

Do not install `cargo-fmt` using:

```sh
cargo install cargo-fmt
```

`cargo fmt` is provided by the rustup `rustfmt` component.

## 3. Diagnose the toolchain only when necessary

Do not run extensive environment diagnostics before validation.

First try the relevant Rust command.

If a toolchain or component error occurs, inspect only:

```sh
rustc --version
cargo --version
rustup show active-toolchain
rustup component list --installed
```

Use `mise current` only when the active toolchain appears inconsistent with the
repository configuration.

Do not repeatedly inspect environment state after it is understood.

## 4. Handle missing cargo-fmt correctly

If:

```text
error: 'cargo-fmt' is not installed for the toolchain ...
```

appears, treat it as a missing `rustfmt` rustup component.

First attempt:

```sh
mise install
```

If `rustfmt` is still missing, repair only the configured toolchain component.

For the currently configured repository toolchain this may be:

```sh
rustup component add \
  --toolchain 1.97.1 \
  rustfmt
```

Add `clippy` or `rust-analyzer` only if the required component is actually
missing.

Then verify:

```sh
cargo fmt --version
```

Do not perform a complete Rust reinstall.

## 5. Formatting

Prefer checking formatting without modifying files:

```sh
cargo fmt --all -- --check
```

If the check fails because files changed by the task need formatting, run the
appropriate formatter.

Inspect the resulting diff afterward.

Do not reformat unrelated files merely to clean up pre-existing formatting.

Formatting is the only workspace-wide operation that is normally acceptable
when the repository's Cargo formatting configuration naturally covers the
workspace and the operation is inexpensive.

## 6. Compile validation

Default to the affected package.

Prefer:

```sh
cargo check -p <affected-package>
```

If the repository is a single crate:

```sh
cargo check
```

Do not automatically run:

```sh
cargo check --workspace
cargo check --all-targets --all-features
```

Expand to workspace validation only when:

- workspace-level configuration changed;
- a shared crate changed;
- public interfaces used across multiple crates changed;
- the targeted check demonstrates that dependent crates must be checked;
- the user explicitly requests comprehensive validation.

## 7. Clippy

Run Clippy only when it provides meaningful validation for the requested
change or when repository policy requires it.

Prefer:

```sh
cargo clippy -p <affected-package> -- -D warnings
```

Add `--all-targets` only when tests, examples, benches, or other targets
affected by the task need linting.

Add `--all-features` only when the task affects feature combinations or the
repository explicitly requires it.

Do not automatically run:

```sh
cargo clippy --all-targets --all-features -- -D warnings
```

for every Rust change.

Do not add broad `#[allow(...)]` annotations merely to silence unrelated
warnings.

## 8. Tests

Start with the smallest relevant test.

Prefer, where possible:

```sh
cargo test -p <affected-package> <relevant-test>
```

If multiple tests in the affected package are directly relevant:

```sh
cargo test -p <affected-package>
```

For a single-crate project:

```sh
cargo test <relevant-test>
```

or:

```sh
cargo test
```

when the crate is small enough that its normal test suite is appropriate.

Do not automatically run:

```sh
cargo test --workspace
```

Expand to dependent crates or workspace tests only when shared behavior changed
or targeted testing reveals the need.

## 9. Feature-gated code

Inspect feature definitions only when the modified code is feature-gated.

Validate only the relevant feature:

```sh
cargo check -p <affected-package> --features <feature>
cargo test -p <affected-package> --features <feature> <relevant-test>
```

Do not test arbitrary feature combinations.

Do not assume that `--all-features` represents a supported configuration.

## 10. Cargo manifest changes

If `Cargo.toml` changed, inspect only the corresponding manifest change and
`Cargo.lock` when it changed.

Use:

```sh
git diff -- <affected-Cargo.toml> Cargo.lock
```

Do not regenerate `Cargo.lock` unless the requested dependency change requires
it.

Do not audit unrelated dependencies.

## 11. Build scripts, FFI, and native dependencies

If the changed Rust code touches:

- `build.rs`;
- FFI;
- native libraries;
- generated bindings;
- platform-specific code;

run only the validation needed for that affected integration.

Distinguish environment failures from code failures.

Examples of environment failures include missing:

- system libraries;
- compilers;
- SDKs;
- pkg-config metadata;
- external command-line tools.

Do not change Rust dependency versions merely to bypass missing system
dependencies.

## 12. Unsafe Rust

Inspect `unsafe` code only when the task adds or modifies it.

Do not perform a general unsafe-code audit of the repository.

For changed unsafe code, verify the immediate invariants required for
correctness.

Do not broaden `unsafe` usage merely to bypass compiler errors.

## 13. Recommended lightweight sequence

For a normal change in one Cargo package, prefer:

```sh
cargo fmt --all -- --check
cargo check -p <affected-package>
cargo test -p <affected-package> <relevant-test>
```

Add Clippy when appropriate:

```sh
cargo clippy -p <affected-package> -- -D warnings
```

If there is no specific test but the affected package has a reasonably sized
test suite:

```sh
cargo test -p <affected-package>
```

Do not automatically expand beyond this sequence.

## 14. Comprehensive validation is opt-in

Commands such as:

```sh
cargo check --workspace
cargo test --workspace
cargo clippy --workspace --all-targets --all-features -- -D warnings
```

should be run only when:

- explicitly requested;
- required by repository policy for the task;
- the change genuinely spans the workspace;
- targeted validation identifies cross-package impact.

They are not the default completion criteria.

## 15. Failure handling

On failure, inspect the existing error before running another command.

Use the minimum diagnostic needed to distinguish:

- source-code failure;
- formatter failure;
- Clippy failure;
- test failure;
- missing rustup component;
- native dependency failure;
- environment failure.

Do not perform broad diagnostics speculatively.

Do not repeatedly rerun the same failing command without changing the relevant
condition.

## 16. Stop condition

Stop Rust validation when:

- formatting is correct;
- the affected package compiles;
- directly relevant tests pass;
- any required targeted lint check passes.

Do not run broader Rust validation merely to obtain additional confidence.

Report broader checks as not run when they were unnecessary.

Do not claim success for commands that were not executed.
