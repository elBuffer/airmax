# Architecture

Product behaviour belongs in [`story.txt`](../story.txt); service workflows belong in their `RULES.md` files. This document records structure and design rationale.

![AirMax architecture](../images/airmax-architecture.svg)

```text
OpenAQ SNS → SQS → ingestion Lambda → private raw S3 bucket
                                           ↓ scheduled read
                                   transformation Lambda
                                           ↓
                                  results/latest.json
                                           ↓
                           website Lambda → Function URL
```

## Deployable boundaries

| Service | Trigger | Responsibility |
|---|---|---|
| Ingestion | SQS | Partition and preserve raw records |
| Transformation | EventBridge Rule | Recompute current and WHO-period results |
| Website | HTTP Function URL | Serve the result and static map |

The services are separate packages and deployment images because their triggers, IAM access and runtime profiles differ. They communicate through S3 JSON contracts and never import one another.

## Files instead of a database

The workload needs immutable replay input and one precomputed output, not interactive queries. S3 and local filesystem adapters provide both without an always-on database. Raw files are the recovery source; there is no cleaned-data copy to drift and no incremental counter to repair.

Aurora, DynamoDB and SQLite add state without removing rolling-window recomputation. Athena and Glue are not permitted, Redshift is denied, and EventBridge Scheduler is unavailable. The accepted design is estimated around $1/month versus roughly $45/month for the smallest always-on Aurora option; production cost remains to be measured.

## Local-first adapters

Handlers coordinate the workflow and adapters own filesystem or AWS calls. The same handler runs locally and in Lambda. This keeps development independent of AWS credentials and makes a replay exercise production code rather than a second implementation.

## Lambda packaging constraint

The AWS user cannot access ECR, so Terraform deploys ZIP packages to the AWS-managed Python 3.12
Lambda runtime instead of deploying the locally tested container images. Docker remains the local
Linux-runtime check, but this is not byte-for-byte deployment parity because AWS can patch the
managed runtime independently. Native dependencies are packaged as Linux x86_64 wheels, and every
deployment requires a smoke test in AWS. If exact runtime parity becomes necessary, request ECR
access and return to image-based Lambda packages.

## Raw partitioning and replay

Ingestion writes unchanged records under their SNS publish hour. Invalid publish timestamps are preserved under `raw/invalid/`. UUID object keys and immutable writes make retries harmless; transformation deduplicates readings inside each result window.

Transformation lists from the previous source-time window, never from wall-clock time. It hashes selected sorted object keys, so a late immutable object changes the digest even when upload timestamps are equal or out of order. Details live in [`services/ingestion/RULES.md`](../services/ingestion/RULES.md).

## Visible streaming calculation

`pipeline.py` shows shared preparation in execution order. Records stream from one raw object at a time into Lambda `/tmp`; only deduplication keys, municipality geometry and aggregate state stay in memory. Shapely remains the sole calculation dependency because robust polygon matching is smaller and safer than custom geometry code.

Current and WHO calculations reuse preparation but own their aggregation and cadence. WHO's larger period mathematics is isolated beside its orchestrator in `calculations/who_aggregation.py`. Details live in [`services/transformation/RULES.md`](../services/transformation/RULES.md). Co-located instrument weighting and its evidence are recorded in [ADR-0004](decisions/ADR-0004-colocated-instruments.md).

## Scheduled recomputation

A five-minute EventBridge Rule triggers transformation. It exits before reading payloads when selected input keys are unchanged. Scheduling once per refresh avoids launching hundreds of calculations for one source burst.

Recomputation makes retries and duplicate delivery deterministic. If measured GET count or runtime becomes excessive, add immutable hourly raw compaction; keep raw input and full recomputation authoritative.

## Concurrent publication

Transformation uses no reserved concurrency. It publishes `results/latest.json` with the ETag it read. On a precondition failure it rereads the result and compares source `window.end_t`, never Lambda wall-clock time. It stops when the stored result is equally new or newer and retries only with later source data.

For equal source time, the first write wins. A different immutable key set changes the input digest and is corrected on the next scheduled calculation. This accepts at most one refresh cycle of delay instead of adding a lock service.

## Candidate IRCEL-CELINE source

The local feasibility path captures IRCEL-CELINE hourly station timeseries and runs them through the existing windowing, municipality mapping, aggregation, validation and website contract. It is deliberately not deployed yet. If source evaluation selects it, add a separately scheduled ingestion Lambda because HTTP polling has a different trigger and failure mode from OpenAQ SQS; keep the transformation and serving deployables.

Mixed OpenAQ and IRCEL-CELINE results are rejected until station overlap, source precedence and customer-facing provenance have a measured policy. The dashboard displays the source declared by the result rather than hard-coding OpenAQ.

## Serving

The website reads one precomputed file and performs no analytics on the request path. It also serves bundled static assets and municipality boundaries, avoiding CORS and public S3 configuration. Function URL authentication is intentionally disabled for the proof of concept.

## Deferred production work

Add only when evidence justifies it:

- hourly raw compaction for measured file-count or runtime pressure;
- alarms, a dead-letter queue and explicit retry policies;
- Function URL authentication;
- deployed dev/QA replay and browser checks;
- station history or other precomputed queries.
