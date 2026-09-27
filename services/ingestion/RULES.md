# Ingestion contract

Product requirements live in [`story.txt`](../../story.txt). This file owns only the ingestion workflow and its boundary with transformation.

## Code

- Handler and routing: `src/airmax_ingestion/handler.py`
- Local and S3 writers: `src/airmax_ingestion/adapters/`
- Downstream listing: `../transformation/src/airmax_transformation/application/refresh_air_quality.py`

## Workflow

```text
SQS batch
  → read each SNS Timestamp only for routing
  → group records by publish hour
  → write one immutable raw object per group
```

Ingestion does not validate measurements, filter countries, deduplicate, map municipalities or calculate results.

## Raw records

Each item under `Records` is written unchanged, including its SQS attributes, SNS envelope and OpenAQ message. Objects are never updated or appended to.

Retries may create another object containing the same record. This is expected: transformation deduplicates calculations, while raw storage preserves the replay evidence.

If one grouped write fails, the invocation fails so SQS can retry. Groups already written may therefore be written again under new UUID keys.

## Partitions

A record with a valid SNS `Timestamp` goes to:

```text
raw/YYYY/MM/DD/HH/batch-<uuid>.json
```

The hour is the SNS publish hour in UTC. Never use `date.utc`, Lambda invocation time, upload time or the first record in the batch. A batch crossing an hour boundary produces more than one object.

A record without a usable SNS timestamp goes to:

```text
raw/invalid/YYYY/MM/DD/HH/batch-<uuid>.json
```

Its filing hour comes from SQS `attributes.SentTimestamp`, falling back to current UTC only when neither timestamp is usable. This fallback files the evidence; it does not make the record valid calculation input.

## Downstream contract

Transformation relies on these properties:

- dated raw keys are immutable and sortable;
- `raw/invalid/` sorts after dated `raw/` keys and is excluded from calculations;
- a late delivery still lands in its original SNS publish-hour folder;
- unique object keys make a changed sorted-key digest reveal new input;
- the first calculation lists all dated history; later calculations start from the previous source-time window rather than wall-clock time.

The deployed SQS batch size is 10. At the observed 3,481-message burst this produces about 349 objects. Measure object count and runtime before adding compaction or changing batch size.

## Safety

- Keep buckets private.
- Do not log or commit credentials, receipt handles, account IDs or production payloads.
- Terraform owns resources and permissions.
- Raw retention has no lifecycle deletion rule in this proof of concept.

## Changing this contract

Trace both the ingestion write path and transformation read path. Update `story.txt`, this file and `docs/architecture.md`, then run `make pre-commit`.
