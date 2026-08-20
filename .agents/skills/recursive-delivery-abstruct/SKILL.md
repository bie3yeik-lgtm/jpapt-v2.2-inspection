---
name: recursive-delivery-abstruct
description: Execute a broad repository task as dependency-ordered, recursively refined work units. Use when a plan spans multiple modules or phases and each unit must be defined, implemented with VSDD, verified, accepted from evidence, and optionally committed before advancing.
---

# Recursive Delivery

Advance an approved plan through the smallest dependency-ordered work units that can be defined,
implemented, verified, and accepted independently. Follow the repository's own authorities, tools,
and terminology; do not require a phase model, manifest, helper skill, GUI, or commit command that
the repository does not provide.

## Establish the delivery contract

Before the first unit:

1. Read the applicable `AGENTS.md`, root `README.md`, relevant specifications and ADRs, and nearby
   implementation and tests.
2. Inspect the current branch, worktree, and task-relevant diff. Preserve unrelated changes and
   distinguish implementation targets from reference trees, generated output, caches, and external
   artifacts.
3. Derive the objective, scope, non-goals, acceptance criteria, dependency policy, platform limits,
   and authorized external or destructive actions from the user's request and repository authority.
4. Decompose the work by dependency. Prefer contracts and tests before adapters, domain behavior,
   integration, presentation, and documentation when that order applies.

Do not invent missing governance artifacts. Ask for direction only when a missing decision would
materially change the outcome, expand authority, or make an external or destructive action unsafe.

## Recursive unit loop

For each unit, complete this loop:

```text
Recursive Unit
- [ ] Orient: identify authority, dependencies, boundaries, and one responsibility
- [ ] Define: state invariants, interfaces, typed failures, and acceptance evidence
- [ ] Prove: add or run the narrowest fail-first test, probe, or static check
- [ ] Implement: make the smallest coherent change
- [ ] Verify: rerun focused checks, then broader owning checks as needed
- [ ] Accept: record evidence, gaps, rollback, and the closed/open decision
- [ ] Commit: commit only when explicitly authorized
- [ ] Advance: select the next unblocked dependency or finish
```

If a unit cannot be accepted or committed without mixing independent responsibilities, split it
again and repeat the loop at the smaller level. Do not advance from a failed unit unless the plan
explicitly permits an independent branch of work.

### Orient and define

- Name the unit by its outcome, not its activity.
- Identify its authoritative requirement and affected input/output contracts.
- State what is in scope, out of scope, and unchanged.
- Choose the minimum evidence needed to close it.
- Return to definition when implementation reveals a contract mismatch; do not conceal the mismatch
  with a fallback or weakened check.

### Prove and implement with VSDD

- For behavior changes, create or run a fail-first test or reproducible probe before implementation
  when practical.
- For documentation or configuration changes, use structural, schema, link, syntax, or search-based
  assertions instead of manufacturing runtime tests.
- Prefer typed boundaries, deterministic fixtures, explicit dependency injection, and observable
  error paths.
- Change only files needed by the current unit. Do not directly edit generated files or lockfiles.
- Use the repository-selected command and package-management surface, normally `mise`, Cargo, `uv`,
  and `pnpm` in this repository.

### Verify and accept

Run the narrowest relevant check first, then package or repository checks in proportion to risk.
Keep evidence levels distinct:

- source/static;
- unit/contract;
- local integration;
- external service or provider;
- named platform or application runtime;
- human acceptance.

Never promote one level into another. A missing device, credential, service, operating system, or
application is `not verified` or blocked evidence, not a pass.

Accept a unit only after recording:

- changed scope and authority;
- commands run and actual results;
- evidence level achieved;
- unverified items and blockers;
- rollback or fallback when relevant;
- the next safe unit.

Update specifications, ADRs, interfaces, usage documents, and the repository-required work history
when the unit changes their subject. In this repository, meaningful work is recorded under
`TelopFlow_Feature/docs/work_history/` with the required purpose, files, implementation, validation,
and unverified sections.

## Git and external-action boundaries

- Do not stage, commit, push, create a pull request, merge, publish, upload, or delete external data
  unless the user authorized that action.
- When commits are requested, prefer one closed responsibility per commit, stage only approved files,
  inspect the staged diff, and use the repository's available Git workflow.
- Do not hard-code a project-specific commit task into this skill.
- Pause before an action that needs credentials, human runtime judgment, destructive synchronization,
  or materially broader scope.

## Completion

Finish only when every approved unit is accepted or explicitly reported as blocked or not verified.
Run the repository-required final checks; for this repository that normally includes
`mise run check` and `git diff --check`. Provide a self-contained handoff covering completed units,
validation, external state changes, remaining risks, and the next safe action.

Use `develop-preflight` alongside this skill when the task also needs full repository preflight and
evidence reporting. This skill owns recursive decomposition and advancement; repository instructions
remain authoritative.
