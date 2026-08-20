---
name: minimal-change
description: Implement a small, narrowly scoped change with minimal repository exploration, command execution, and validation. Use for targeted bug fixes, small edits, configuration changes, and other tasks where broad investigation is unnecessary.
---

---

# Minimal Change

Use this workflow for narrowly scoped tasks.

## 1. Locate the target

If the user supplied a file path, start there.

Otherwise use one targeted search to locate the relevant implementation.

Do not perform a repository-wide architecture survey.

## 2. Read only immediate context

Inspect:

- the target file;
- directly referenced types or functions when needed;
- the nearest relevant test when one exists.

Do not inspect adjacent subsystems without evidence that they affect the task.

## 3. Implement the smallest change

Modify only what is necessary to satisfy the requested behavior.

Avoid opportunistic refactoring or cleanup.

## 4. Validate narrowly

Run the narrowest relevant validation.

Examples:

```sh
cargo check -p <affected-package>
cargo test -p <affected-package> <affected-test>
pnpm run test -- <affected-target>
uv run pytest <affected-test>
```

Do not run a full workspace or repository test suite unless the change affects
shared infrastructure or the user explicitly requests it.

## 5. Stop

When the requested change is implemented and targeted validation succeeds,
stop.

Do not continue exploring for additional improvements.
