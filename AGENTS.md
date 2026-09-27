# AirMax agent entry point

## Purpose

AirMax is a local-first pipeline that preserves OpenAQ events, calculates source-anchored air-quality results for Belgian municipalities, and serves them through a map. Its three deployable services are ingestion, transformation and website.

## Route the task

| Changing | Read first | Skill | Verification |
|---|---|---|---|
| Product behaviour | Relevant section of `story.txt` | `cohesive-service-design` | `make replay` |
| Ingestion | `services/ingestion/RULES.md` | `cohesive-service-design` | `uv run python -m unittest tests/test_ingestion.py` |
| Transformation | `services/transformation/RULES.md` | `cohesive-service-design` | `uv run python -m unittest tests/test_transformation.py` |
| Website | Dashboard sections of `story.txt` | `cohesive-service-design` | `uv run python -m unittest tests/test_website.py` |
| Reference data | `docs/reference-data.md` | — | `uv run python -m unittest tests/test_reference_data.py` |
| Infrastructure | `docs/architecture.md`, `infra/terraform/README.md` | `cohesive-service-design` | `terraform -chdir=infra/terraform validate` |
| Commit or PR title | Current diff | `conventional-commits` | `make pre-commit` |

Read only the context needed for the task, then trace the affected code end to end before editing.

## Repository invariants

- The three services never import one another.
- AWS SDK calls stay in adapters; handlers coordinate workflows.
- Raw events remain unchanged and results are recomputed rather than incrementally counted.
- Transformation order stays visible in `pipeline.py`; large intermediate streams use `/tmp`.
- Record measured evidence only and label missing evidence.
- Never commit credentials, account IDs, Terraform state, plans or built images.

Product-specific values and formulas belong in `story.txt` and are not repeated here.

## Information ownership

| Information | Owner |
|---|---|
| Product behaviour and acceptance criteria | `story.txt` |
| Ingestion workflow | `services/ingestion/RULES.md` |
| Transformation workflow | `services/transformation/RULES.md` |
| Architecture and design rationale | `docs/architecture.md`, `docs/decisions/` |
| Measured source findings | `docs/data-findings.md` |
| Test strategy and evidence limits | `docs/testing.md` |
| Reference-data source and licence | `docs/reference-data.md` |
| Commands | `Makefile` |
| Reusable agent method | matching project skill |

Update the owner of a fact. Other files should link to it instead of copying it. Add a document only when no existing owner fits.

## Project skills

Skills live under `.agents/skills/<name>/SKILL.md`.

| Skill | Use it for |
|---|---|
| `cohesive-service-design` | Lambdas, handlers, adapters, pipelines, validation and service boundaries |
| `conventional-commits` | Creating, reviewing or rewriting commits and PR titles |

Discover the current skills with:

```sh
find .agents/skills -name SKILL.md
```

Read a skill only when its description matches the task. When a project skill is added, removed or renamed, update this table. Product rules do not belong in skills.

## Definition of done

Run the smallest relevant verification while working. Before committing, run `make pre-commit`; run `make docker-test` when Docker is available. Use Conventional Commits and keep each commit to one tested vertical slice.
