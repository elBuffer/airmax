---
name: cohesive-service-design
description: Design and review Lambdas, workers, APIs, event pipelines, and services using deployable-first boundaries with domain, application, and adapter separation. Use when adding, restructuring, or reviewing handlers, processing flows, repositories, validation, queues, or proposed service splits.
---

# Cohesive Service Design

Keep one operational workflow in one deployable, then give that deployable clear internal code
boundaries. **One Lambda does not mean one giant file.**

## 1. Find Deployable Boundaries First

A deployable boundary exists when a workflow has its own trigger, scaling, IAM access, failure
handling, or release lifecycle.

Example with two justified deployables:

```text
SQS → ingestion Lambda → S3 + DynamoDB
Browser → API Lambda → DynamoDB
```

Ingestion and API belong in separate top-level packages because one consumes SQS and writes data,
while the other handles HTTP and reads data. Do not organize the whole repository into global
`domain/`, `application/`, and `adapters/` directories that mix unrelated deployables.

Prefer:

```text
src/product/
├── ingestion/
│   ├── handler.py
│   ├── domain/
│   ├── application/
│   └── adapters/
└── api/
    ├── handler.py
    ├── current.py
    └── site/
```

Name packages after the workflow (`ingestion`, `api`, `publication`), not vague containers such as
`data`, `service`, `core`, or `utils`.

## 2. Separate Responsibilities Inside the Deployable

### Inbound adapter

Knows the external transport: SQS records, SNS envelopes, HTTP events, JSON decoding. It converts
transport input into an application-friendly shape and invokes one use case. It does not own
business validation or persistence rules.

### The handler must tell the workflow story

Read the handler aloud before accepting it. Each line must say what happens in domain language, in
the order it happens, without opening helper bodies. The reader should be able to retell the whole
workflow from those lines alone.

```python
def lambda_handler(event, context=None, writer=None):
    if writer is None:
        writer = configured_raw_writer()
    records_by_partition = group_records_by_partition(records_from(event))
    written_object_keys = write_record_batches(event, records_by_partition, writer)
    return ingestion_summary(written_object_keys, records_by_partition)
```

This reads as: choose the raw writer, partition incoming records, write one batch per partition,
then summarize the ingestion. That sentence is the handler's acceptance test.

Use names that preserve the story:

- functions use a domain verb and object: `group_records_by_partition`, not `process`;
- collections name both content and organization: `records_by_partition`, not `groups`;
- outputs name what they contain: `written_object_keys`, not `result` or `keys`;
- boundary choices name their purpose: `configured_raw_writer`, not `get_adapter`;
- summaries and responses name the use case: `ingestion_summary`, not `build_result`.

If a line cannot be paraphrased without saying “thing,” “data,” “result,” “process,” or “handle,” its
name is too vague. If the handler contains a loop, parsing detail, fallback implementation, storage
key construction, or response-shape construction, move that detail behind the exact workflow step
it implements. Do not overcorrect by hiding the entire sequence behind `run()`, `process()`, a
manager, or a framework callback.

### Application layer

Coordinates one named use case and its order of operations. It contains no boto3 calls, JSON/SQS
knowledge, SQL, or HTTP response formatting.

```python
def ingest_measurement(payload, sent_at, save):
    measurement = Measurement.from_payload(payload)
    if measurement.is_relevant():
        save(measurement, sent_at)
```

Application files are named for operations: `ingest_measurement.py`, `get_current_air_quality.py`,
not generic managers or services.

### Domain layer

Owns business meaning and rules: normalization, required fields, valid coordinates, relevance,
measurement identity, averages, and quality policy. Domain code does not import boto3 or know SQS,
DynamoDB, Lambda events, or HTTP.

### Outbound adapters

Own technical integration with DynamoDB, S3, APIs, or files. They map domain objects to storage and
implement conditional writes, queries, and serialization. They do not decide business relevance or
quality policy.

## 3. Make Each Function Answer One Question

A cohesive service still needs cohesive functions. Each function should have one named outcome and
one reason to change. Branching is fine when every branch serves that outcome; mixing parsing,
fallback policy, persistence, and orchestration is not.

Keep abstraction levels explicit:

- a parser reads one representation and either returns that value or fails;
- a fallback selector owns only source precedence;
- a formatter renders an already-selected value;
- an orchestrator sequences named steps without reimplementing them;
- a handler adapts the transport and invokes the use case.

Apply DRY to behavior, not incidental syntax: timestamp parsing, fallback precedence, and partition
formatting each need one owner. Do not duplicate parsing or path formatting across valid and invalid
branches.

Do not make a helper retry work its caller already attempted. This hides control flow and gives the
helper two meanings:

```python
# Reject: both parses the primary source and selects fallbacks.
def sent_at(record):
    try:
        return published_at(record)
    except ParseError:
        return sqs_sent_at(record) or utc_now()

# Prefer: parsing, fallback policy, formatting, and orchestration have one owner each.
def published_at(record): ...
def sqs_sent_at(record): ...

def invalid_partition_at(record):
    try:
        return sqs_sent_at(record)
    except ParseError:
        return utc_now()

def hour_partition(prefix, timestamp):
    return f"{prefix}{timestamp:%Y/%m/%d/%H}"

def partition(record):
    try:
        return hour_partition(RAW_PREFIX, published_at(record))
    except ParseError:
        return hour_partition(INVALID_PREFIX, invalid_partition_at(record))
```

Warning signs are names using “and” to join independent outcomes, vague verbs such as `process` or
`handle`, a function that returns values with different meanings, catching an error only to switch
to another responsibility, or transport parsing mixed with a business/storage action. Do not mechanically split every branch
into a function: extraction is useful only when the new function has a precise domain name and an
independently understandable contract. Orchestration itself is one responsibility when its body is
the readable workflow story.

## 4. Give Every Rule One Owner

Do not spread one validation flow across adapters, handlers, application functions, and domain
objects.

- Transport structure belongs to the inbound adapter: valid JSON, optional SNS envelope, object
  shape.
- Measurement normalization and validation belong together in the domain model or one domain
  validator.
- Relevance and calculation policy belong to the domain.
- Use-case ordering belongs to the application layer.
- Storage constraints and serialization belong to the outbound adapter.

A value should not be partly validated in three layers. Search all callers and consolidate the rule
before adding another guard.

## 5. Keep Logical Steps as Function Calls

Do not turn parse, validate, normalize, filter, and save into separate Lambdas and queues merely for
“separation of concerns.” Network boundaries add IAM policies, retries, DLQs, alarms, deployments,
and partial-failure states.

Reject this without an operational requirement:

```text
SQS → parse Lambda → queue → validate Lambda → queue → transform Lambda → DynamoDB
```

Use this instead:

```text
SQS → one ingestion Lambda
          handler → application use case → domain → adapters
```

## 6. Make Data Pipelines Read Top to Bottom

A pipeline needs one obvious orchestration file (`pipeline.py`, `process_batch.py`, or the named use
case) that shows the real execution order as plain function calls:

```python
# pipeline.py: shared preparation only
validated = validate_and_spool(records, workdir)
start, end = rolling_window(validated.latest_reading, window_hours)
readings = within_window(load_readings(validated.path), start, end)
readings = deduplicate(readings, quality)
readings = map_locations(readings, boundaries)
prepared = PreparedReadings(readings, start, end, quality)

# calculations/current.py: calculation-owned policy
cities = aggregate_current(prepared.readings)
```

Shared preparation stops where consumers' mathematical intent diverges. Do not add a flag such as
`hourly_period` to make a shared pipeline choose between current and period aggregation. Current,
WHO, billing, risk or other calculations select and invoke their own terminal policy after receiving
the same prepared stream.

Do not hide this order in framework configuration, decorators, SQL model graphs, factories, or a
giant function named `transform`. Each step gets a specifically named module only when it has real
logic. Keep a one-use dataclass beside the function that produces it; do not create vague `models/`,
`common/`, or `utils/` folders just to hold one type.

Stream source records and spool to bounded temporary disk when a later pass is required. Retaining
compact deduplication keys and aggregate sets is acceptable; loading the complete raw window is not.
Generator counters and sets update only when a terminal consumer iterates the stream; read their
final values after aggregation, not immediately after preparation.

Keep one-use business rules visible at their owner. If deduplication identity is
`location_id + pollutant + source_time`, construct that tuple inside `deduplicate()` rather than
hiding it behind a generic `reading.key` property. Avoid pass-through generators whose only purpose
is incrementing a counter when the consuming loop can own that count directly.

Partition stored data by the timestamp used to query it. Route unparseable timestamps to an explicit
fallback partition rather than dropping them.

Choose dependencies by how much code and hidden execution they remove. A dataframe, database, ORM,
or workflow engine is not automatically simpler than generators and dictionaries. Keep a focused
dependency when it replaces difficult correctness-sensitive code, such as geometry operations.

## 7. Treat JSON as a Service Contract

Independently deployed services communicate through serialized contracts, not shared implementation
classes. The service exposing an API owns its response model and an explicit presenter maps stored
results into that model. Browser code cannot share a Python dataclass.

Use dataclasses when they make construction clearer, not as ceremonial wrappers around every
dictionary. A dataclass improves local naming but does not guarantee compatibility across JSON.
Compatibility requires one boundary-level contract check or schema. A shared output contract does
not require a shared output builder: let each calculation construct its result and validate all
results through the same boundary check. Do not introduce a shared package merely to avoid writing
an explicit adapter.

Make changing policy values configurable when operators may tune them (window duration, staleness,
physical calibration). Keep genuine invariants as constants rather than turning every literal into
configuration.

## 8. Split Services Only for a Real Operational Boundary

A separate deployable requires at least one concrete reason:

- materially different scaling or resource profile;
- independent team ownership or release cadence;
- required asynchronous durability/retry boundary;
- fan-out to independent consumers;
- distinct security or IAM boundary;
- valuable failure isolation;
- measured latency, throughput, or cost problem.

“Separation of concerns,” possible future reuse, and a large file are code-organization reasons,
not infrastructure reasons.

## 9. Avoid Both Extremes

Do not leave a multi-stage workflow in one giant handler. Also do not create empty layers,
one-method classes, factories, or repository interfaces without a boundary they protect.

Extract a module when it has a named responsibility. Prefer functions and domain values over
ceremonial classes. Keep handlers thin enough that the use-case sequence is immediately visible.

Build separate deployment artifacts for separate deployables so an API-only edit does not redeploy
ingestion code.

## Review Procedure

1. Trace the workflow end to end, including triggers and persistence.
2. List deployables and justify each with trigger/scaling/IAM/failure/release differences.
3. Organize code by deployable first.
4. Identify inbound adapter, application use case, domain owner, and outbound adapters.
5. Locate every validation and business rule; ensure each has exactly one owner.
6. Check each function has one named outcome and does not repeat a caller's work before falling back.
7. Read each handler aloud; verify its domain verbs and nouns tell the complete workflow story.
8. Reject vague names (`process`, `handle`, `groups`, `result`, `data`) where a workflow-specific
   name exists.
9. Check that handlers orchestrate rather than implement the workflow.
10. Check that domain/application code has no cloud SDK or transport imports.
11. Check deployment artifacts contain only code needed by that deployable.
12. Count infrastructure introduced by every proposed split.
13. Read the main pipeline/use-case file top to bottom; verify every material stage is visible.
14. Check that large inputs stream or spool instead of accumulating as full in-memory collections.
15. Check that storage partitions match the timestamp and access pattern used by readers.
16. Check API presenters explicitly translate storage results into response contracts.
17. Remove vague folders and move one-use types next to their owner.
18. Name the measurable trigger for any deferred split.

## Output

When reviewing a design, report:

- **deployables:** each unit and its operational justification;
- **package structure:** deployable-first tree;
- **rule ownership:** where parsing, validation, business rules, and persistence live;
- **workflow story:** the handler or pipeline restated in one plain-language sentence;
- **violations:** vague names, unreadable orchestration, mixed layers, duplicated validation, giant
  handlers, or needless services;
- **rejected infrastructure:** queues/Lambdas avoided;
- **split trigger:** evidence that would justify another deployable.
