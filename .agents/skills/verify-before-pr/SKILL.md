---
name: verify-before-pr
description: Perform a lightweight pre-PR verification focused only on files changed by the current task. Use before creating or updating a pull request. Prefer targeted checks and avoid repository-wide analysis, builds, or tests unless explicitly required.
---

---

# Verify Before PR

Perform the minimum verification necessary to determine whether the current
change is ready for review.

The goal is not to audit the repository.

Do not expand the task into unrelated investigation, cleanup, refactoring, or
repository-wide validation.

## 1. Inspect Git state

Run:

```sh
git status --short
git branch --show-current
git diff --stat
git diff --name-status
```

Run `git diff --cached --name-status` only when staged changes exist.

Do not run `git fetch`, `git pull`, or inspect remote branches unless the task
explicitly requires remote state.

Treat the current checkout as authoritative.

## 2. Determine the affected scope

Identify only:

- files changed by the current task;
- directly affected package, crate, or module;
- directly relevant tests;
- lockfiles or generated files changed by the task.

Do not inspect unrelated directories.

Do not perform a repository-wide architecture analysis.

Do not recursively enumerate the repository unless required to locate an
unknown changed dependency.

## 3. Check for accidental changes

Review the changed-file list for unexpected modifications.

Pay particular attention to:

- `mise.toml`
- `rust-toolchain.toml`
- `Cargo.lock`
- `pnpm-lock.yaml`
- `uv.lock`
- `go.mod`
- `go.sum`
- `.github/`
- `.devcontainer/`
- `.codex/`
- `.devin/`
- `.agents/`
- environment setup scripts

Do not inspect these files when they are unchanged.

If an unrelated change is present, do not silently include or discard it.

Never discard pre-existing user changes.

## 4. Secret safety

Inspect only changed files for obvious accidental credentials.

Examples include:

- API keys;
- access tokens;
- passwords;
- private keys;
- authentication cookies;
- `.env` contents;
- credentials embedded in URLs.

Never print secret values.

If a secret appears to be present, report the affected file and issue type
without reproducing the value.

Do not perform a repository-wide secret scan unless explicitly requested.

## 5. Use repository tasks when available

If a relevant validation command is already known, use it directly.

Otherwise inspect available mise tasks only when necessary:

```sh
mise tasks ls
```

Prefer an existing targeted task over constructing a broader validation
workflow.

Do not execute every available task.

## 6. Validate only affected ecosystems

Do not validate languages or packages unaffected by the current diff.

### Rust

For Rust changes, use the `rust-validation` skill.

Prefer package- or crate-scoped validation.

Do not run workspace-wide Rust validation merely as a precaution.

### JavaScript / TypeScript

Use pnpm.

Inspect only the relevant `package.json` when necessary.

Run the narrowest applicable script, such as:

```sh
pnpm run lint
pnpm run typecheck
pnpm run test -- <target>
```

Do not automatically run every script.

Do not use npm or yarn.

### Python

Use uv.

Prefer targeted commands such as:

```sh
uv run pytest <relevant-test>
```

Do not automatically run the complete Python test suite.

### Go

Prefer validation of the affected package:

```sh
go test ./path/to/affected/package/...
```

Do not automatically run:

```sh
go test ./...
```

unless shared or repository-wide Go code was changed.

## 7. Lockfiles

Inspect a lockfile only when it changed.

A lockfile change should correspond to an intentional dependency change.

Do not regenerate lockfiles merely for additional confidence.

Do not reinstall dependencies unless validation demonstrates that dependencies
are missing or stale.

## 8. Generated files

Check generated artifacts only when the current change affects their source or
when generated files themselves changed.

Do not proactively regenerate the entire project.

Use the narrowest authoritative generation command when regeneration is
required.

## 9. Whitespace check

Run:

```sh
git diff --check
```

Fix only whitespace errors introduced by the current task.

Do not modify unrelated pre-existing whitespace issues.

## 10. Inspect the final patch

Inspect the relevant diff:

```sh
git diff -- <changed-paths>
```

For a small change, inspecting the complete `git diff` is acceptable.

Verify only that:

- the requested behavior is implemented;
- no obvious debugging code remains;
- no unintended file changes are included;
- configuration and lockfile changes are intentional.

Do not turn the final inspection into a broader code review.

## 11. Validation expansion policy

Start with the narrowest useful validation.

Expand validation only when one of the following is true:

- the targeted check reveals a dependency on another component;
- shared interfaces changed;
- root workspace configuration changed;
- generated interfaces changed;
- the user explicitly requested comprehensive validation.

Do not run broader validation merely for additional confidence.

Full repository builds and test suites are opt-in, not default.

## 12. Failure handling

When a validation command fails:

1. inspect the existing error;
2. classify the likely failure;
3. run only the smallest additional diagnostic needed.

Possible categories include:

- implementation;
- formatting;
- lint;
- tests;
- dependency;
- environment;
- authentication;
- network.

Do not launch multiple speculative diagnostic commands.

Do not repeatedly retry authentication or network failures without changing
the relevant condition.

Do not change unrelated configuration to make a check pass.

## 13. Stop condition

Stop verification when:

- the requested change is present;
- the final diff has been inspected;
- directly relevant validation succeeds;
- no known blocker remains.

Do not continue searching for additional improvements after these conditions
are satisfied.

## 14. Final report

Report concisely:

- affected area;
- validation commands actually run;
- pass or failure status;
- any validation not performed because it was unnecessary;
- remaining blocker, if any.

Do not claim that a check passed unless the command actually completed
successfully.
