# AirMax real-time air-quality PoC

A local-first pipeline that taps the OpenAQ stream, calculates each Belgian municipality's current
air quality as the latest source-anchored three-hour average, reports the measurement evidence, and
serves a dependency-free map. Data-quality findings qualify the view; they do not replace it.

## Run locally

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), and `make`.

```sh
make install
make install-hooks # activate the versioned pre-commit hook
make replay
make replay-data # replay data/openaq-andre-raw.jsonl
make lint
make typecheck
make test
make serve       # http://localhost:8000
```

No AWS credentials are used by those commands. Generated files are under `.local/`. Repository
rules for coding agents live in `AGENTS.md`; `make pre-commit` checks Ruff, mypy and regression behavior.

For a Linux environment matching AWS Lambda, start Docker Desktop and run:

```sh
make docker-test
make docker-replay
```

## Layout

- `services/ingestion`: SQS to unchanged raw storage.
- `services/transformation`: raw storage to calculated city results.
- `services/website`: results to HTTP and the map.
- `tests`: regression checks and fixtures.
- `tools`: local replay commands.
- `infra/terraform`: AWS deployment.

Each service is an independent package and deployment artifact. See `AGENTS.md` for the repository map and authoritative documentation index.

## Data flow

```text
OpenAQ SNS → SQS → ingestion Lambda → S3 raw/<SNS publish hour>/
                                               ↓ every five minutes
                                  streaming transformation Lambda
                                               ↓
                                  S3 results/latest.json
                                               ↓
                                      website Lambda → map
```

See the human-readable [ingestion and listing rules](services/ingestion/RULES.md),
[transformation rules](services/transformation/RULES.md), [architecture](docs/architecture.md), [findings](docs/data-findings.md),
[testing strategy](docs/testing.md), and [Terraform instructions](infra/terraform/README.md).

## AWS setup

Copy the committed template, fill in your own credentials and account ID, then verify access:

```powershell
Copy-Item .env.example .env
.\with-env.ps1 aws sts get-caller-identity
```

`.env` is ignored by Git. Never put real credentials in `.env.example`.

## Deploy

See the step-by-step [Terraform instructions](infra/terraform/README.md).
