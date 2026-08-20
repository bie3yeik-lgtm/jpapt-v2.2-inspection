---
name: develop-preflight
description: Repository-aware preflight and execution workflow for architecture, investigation, implementation, verification, and handoff tasks. Use when Codex must establish authoritative specifications and scope, protect an existing dirty worktree, plan multi-step work, apply VSDD fail-first development, separate evidence levels, run repository-standard checks, and leave a reproducible Japanese work history.
---

# Develop Preflight

Use this skill as an orchestration layer. Follow the repository's own authority and command
surface; do not impose a phase system, manifest, helper script, or tool that the repository does
not provide.

## 1. Establish authority and scope

1. Locate the repository root and read, in order:
   - the applicable `AGENTS.md` files;
   - the root `README.md`;
   - the relevant file under `docs/specifications/`;
   - applicable decisions under `docs/adr/`;
   - nearby implementation, fixtures, and tests.
2. Treat an approved user plan or named project document as task authority unless it conflicts
   with higher-priority repository instructions. Do not silently replace it with a generic
   architecture.
3. Inspect the current branch, `git status --short`, and task-relevant diffs before editing.
   Preserve unrelated tracked changes and untracked files. Distinguish implementation targets,
   reference trees, generated output, caches, and external artifacts.
4. State or derive the objective, scope, non-goals, acceptance criteria, dependency policy,
   platform boundary, and destructive/external side effects. Ask only when a missing decision
   would materially change the result or require new authority.
5. Classify the work as one or more of:
   - architecture or documentation;
   - investigation or diagnosis;
   - implementation or migration;
   - verification or release preparation.

If the repository contains an explicit phase manifest or task request, follow it. If it does not,
do not invent one and do not block solely because optional governance files are absent.

## 2. Plan with VSDD

For meaningful multi-step work, maintain a concise plan with at most one in-progress step.
Sequence work by dependency and define stop conditions before implementation.

Apply VSDD as follows:

1. Identify the requirement, invariant, input/output contract, and typed failure behavior.
2. Add or run the narrowest fail-first test, probe, or reproducible check when behavior changes.
3. Implement one coherent slice without weakening tests, lint, types, warnings, or security
   controls.
4. Re-run the narrow check, then the owning crate/package checks, then repository checks.
5. Record evidence and unresolved gates before starting the next slice.

Prefer deterministic fixtures, injected clocks/cancellation points, fixed revisions, content
hashes, schema validation, and typed errors. Do not use relaxed tolerances, arbitrary sleeps, or
fallbacks merely to make a gate pass. A documentation-only task may use link, structure, syntax,
and static checks instead of manufacturing runtime tests.

## 3. Execute within repository boundaries

- Make the smallest coherent change that satisfies the approved requirement; avoid unrelated
  refactoring.
- Use `apply_patch` for authored file edits. Do not directly edit generated files or lockfiles.
- Use repository-selected ownership: `mise` for tool versions/tasks, Cargo for Rust, `uv` for
  Python, and `pnpm` for JavaScript/TypeScript unless the repository states otherwise.
- Inspect `mise tasks` before inventing commands. Prefer documented standard commands.
- Keep platform-specific claims separate. Windows behavior requires Windows evidence; macOS
  behavior requires macOS evidence; Premiere behavior requires a named Premiere/runtime check.
- Use a subproject's typed controller and manifest when one exists. For TF-v1 ONNX work, use the
  `hf-workspace` Model Repo/Bucket workflow and fixed source SHA rather than ad hoc model copies.
- Keep credentials out of logs, manifests, source, and final responses. Resolve identity through
  the project's approved command rather than parsing secret values.
- Do not perform external writes, publish, push, delete, or destructive migration beyond the
  user's approved scope. For reviewed-plan workflows, inspect the exact plan before applying it.
- If an optional helper or referenced tool is missing, continue from the repository authority
  and this workflow. Do not create fake files solely to satisfy stale skill instructions.

## 4. Keep evidence levels distinct

Report only the narrowest level actually verified:

| Evidence | Proves | Does not prove |
| --- | --- | --- |
| Source/static | Files, schemas, types, links, syntax | Compilation or runtime behavior |
| Unit/contract | Deterministic behavior at the tested boundary | External integration |
| Local integration | Process, IPC, model, or tool behavior on this host | Another OS or hardware |
| External service/provider | Named API, Repo, Bucket, provider, or remote state | End-user application behavior |
| Platform/runtime | Named OS, GPU, Apple Silicon, Premiere, or packaged runtime | Unmeasured platforms |
| Human acceptance | Visual, UX, editorial, or operational judgment | Automated correctness |

A missing device, credential, service state, or application produces `not verified` or a typed
`BLOCKED` result, never `PASS`. Keep diagnostics, acceptance evidence, and inference clearly
separate.

## 5. Validate and document

Run checks proportionate to the change and finish with the repository-required commands. For
this repository, normally use:

```text
mise run check
git diff --check
```

For an independent Rust crate, also run its locked format, check, test, and Clippy commands.
Run relevant platform-specific checks when the platform is available. Record commands that could
not run and why.

After meaningful investigation, design, implementation, or verification, add or update a dated
Japanese entry under `TelopFlow_Feature/docs/work_history/` containing:

- purpose and approved scope;
- changed files;
- implementation or findings;
- commands and results by evidence level;
- unverified items, blockers, rollback/fallback, and next safe action.

Update affected specifications, ADRs, contracts, and usage documents in the same change when
interfaces, commands, architecture, distribution, or user-visible behavior change.

## 6. Git and handoff

- Do not commit, stage, push, create a PR, merge, stash, or rewrite history unless the user asks
  for that action.
- When asked, stage only approved paths, preserve unrelated work, and verify the exact staged
  diff before committing.
- Do not claim completion from a narrow check. Audit every named requirement, artifact, command,
  gate, invariant, and platform acceptance item against current evidence.
- End with a self-contained report of outcome, changed scope, validation, external state changes,
  unresolved risks, and the next safe action.
