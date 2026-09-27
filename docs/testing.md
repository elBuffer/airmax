# Testing

Tests are calculation guardrails, not evidence that OpenAQ coverage is commercially or scientifically adequate. Measured source findings belong in [`data-findings.md`](data-findings.md).

## Commands

```sh
make replay       # run the real local handlers over fixtures
make test         # Python regression checks
make pre-commit   # lint, type check, replay and tests
make docker-test  # checks the Lambda Linux environment
```

## Current coverage

| File | Protects |
|---|---|
| `tests/test_ingestion.py` | unchanged raw records and SNS-hour partitioning |
| `tests/test_transformation.py` | windows, validation, deduplication, aggregation, late files and publication |
| `tests/test_website.py` | HTTP routes and dashboard presentation states |
| `tests/test_reference_data.py` | byte-identical municipality data in both deployables |

The headline regression is Gent PM2.5 at `13.6474010878 µg/m³` from 6 measurements, 6 location IDs and 5 physical sites.

## Evidence limits

The checked-in fixtures are engineered and narrow. They do not prove nationwide coverage, production volume, source freshness, browser rendering, AWS permissions or operational reliability.

## Missing before production

- CI running `make pre-commit` and `make docker-test`;
- a transformation-to-website contract check using real replay output;
- browser tests for current, stale, empty and WHO coverage states;
- dev replay through the deployed SQS trigger;
- QA replay of a retained production-sized interval with measured runtime and memory;
- production smoke checks and freshness/error alarms.

Only production consumes the live OpenAQ queue. Dev and QA must use their own queues so they cannot steal production messages.
