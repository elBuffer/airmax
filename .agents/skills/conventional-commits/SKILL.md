---
name: conventional-commits
description: Prepare, review, reword, squash, or create Git commits and pull-request titles for this repository using Conventional Commits 1.0.0. Use for every commit-related task.
---

# Conventional commits

Every commit uses:

```text
<type>[optional scope][!]: <imperative description>

[optional body explaining why]

[optional footer]
```

## Workflow

1. Run `git status --short`.
2. Inspect both `git diff` and `git diff --staged`; never infer content from filenames.
3. Identify one logical change. If changes are unrelated, propose separate commits.
4. Run the checks relevant to that change.
5. Stage only that logical change.
6. Run `git diff --staged --check` and inspect the complete staged diff.
7. Choose the narrowest accurate type and optional scope.
8. Commit only when explicitly asked; otherwise return the proposed message.

Never discard, rewrite, stage or commit unrelated user changes.

## Types

| Type | Use |
|---|---|
| `feat` | New user-visible or operational capability |
| `fix` | Defect correction |
| `docs` | Documentation-only change |
| `refactor` | Code structure change with no behaviour change |
| `test` | Test-only change |
| `perf` | Measured performance improvement |
| `build` | Dependencies or build tooling |
| `ci` | CI/CD configuration |
| `style` | Formatting only |
| `chore` | Maintenance that fits no better type |
| `revert` | Revert an earlier commit |

Use `feat` for capabilities and `fix` for defects; do not hide them under `chore`.

## Preferred scopes

| Scope | Area |
|---|---|
| `ingestion` | SQS landing workflow and adapters |
| `transformation` | Raw loading and snapshot publication workflow |
| `models` | SQL migrations, models and data checks |
| `dashboard` | Website and result presentation |
| `terraform` | Infrastructure definitions |
| `sandbox` | Account-safety tooling and access docs |
| `scripts` | Replay, backfill and developer commands |
| `deps` | Dependency changes |

Omit the scope for a genuinely cross-cutting change. Do not invent a scope merely to fill the slot.

## Header rules

- imperative: `add`, `fix`, `remove`, not `added` or `adds`;
- lowercase first word;
- no trailing period;
- at most 72 characters;
- describe the outcome, not the filename;
- do not combine multiple changes with `and`.

Examples:

```text
docs: define the Aurora implementation path
feat(ingestion): archive SQS batches in raw S3
fix(models): exclude duplicate measurement identities
build(terraform): provision the Aurora Data API cluster
```

## Body and breaking changes

Use a body only when the reason or trade-off is not obvious. Wrap near 72 characters. Mark a breaking contract with `!` and explain migration in a footer:

```text
feat(models)!: rename municipality result fields

BREAKING CHANGE: consumers must replace `city_id` with `nis_code`.
```

Changes to raw S3 layout, measurement identity, mart columns, result JSON or Terraform ownership are breaking unless backwards compatible.

## No agent attribution

Never add AI, model, tool or harness attribution to any commit message. No generated-by text, session links, bot `Co-authored-by`, or equivalent trailers. Human co-authors are allowed.

## Final check

- one logical change;
- valid type and useful scope;
- header no longer than 72 characters;
- checks actually ran;
- staged diff contains no credentials, state, plans, ZIPs or unrelated files;
- no claim that undeployed work is live;
- no agent attribution.
