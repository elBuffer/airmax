# Next steps to production

This plan turns the AirMax proof of concept into a production service only after its data-source feasibility is resolved. It is based on [`AirMax × OpenAQ feasibility (1).pdf`](../AirMax%20%C3%97%20OpenAQ%20feasibility%20%281%29.pdf), the current implementation, and the architecture review.

Product behaviour remains owned by [`story.txt`](../story.txt). Measured source evidence remains owned by [`data-findings.md`](data-findings.md). This document owns delivery order and production-readiness gates.

## Current decision

The pipeline and dashboard demonstrate the technical approach. The production blocker is the source, not another infrastructure component:

- the analysed OpenAQ capture delivered data about every six hours rather than hourly;
- geographic and pollutant coverage is incomplete;
- measurement-time semantics and conflicting co-located instruments remain unresolved;
- the official IRCEL-CELINE source may offer fresher data but has different coverage.

Do not market the service as real-time nationwide air quality or invest in production scale until Phase 1 selects the source and confirms that it supports the intended customer claim.

## Phase 1 — Decide whether the data supports the product

**Goal:** choose OpenAQ, IRCEL-CELINE, both, or stop.

1. Ask OpenAQ to clarify:
   - the observed six-hour delivery rhythm;
   - the physical meaning of `date.utc` and the measurement period;
   - multiple station IDs at identical coordinates;
   - whether corrections, delays, and publication frequency have a stable contract.
2. Capture at least 24–48 representative hours from OpenAQ and IRCEL-CELINE. Use `make capture-ircel START=<ISO-8601> END=<ISO-8601>` for the IRCEL-CELINE feasibility sample.
3. Compare the sources for freshness, municipality coverage, pollutants, station identity, units, licensing, continuity, and operating cost.
4. Replay production-sized intervals and record transformation duration, peak memory, object count, S3 requests, rejected records, and result freshness.
5. Update [`data-findings.md`](data-findings.md) with measured evidence and a source recommendation.
6. Agree on the honest product wording: latest available source data, not “real time,” unless measurements support the stronger claim.

**Exit gate:** a written decision names the source, supported customer claim, target municipalities/pollutants, freshness expectation, known limitations, and reasons to continue. Stop the project if no source supports a useful sales proposition.

### IRCEL-CELINE integration if selected

Keep the source pull as a separate deployable because its scheduled HTTP trigger and failure mode differ from the OpenAQ SQS consumer:

```text
EventBridge → IRCEL-CELINE ingestion Lambda → raw/ircel/<observation hour>/
OpenAQ SNS → SQS → OpenAQ ingestion Lambda → raw/openaq/<publish hour>/
                                                   ↓
                                      shared transformation
```

The production adapter should preserve the IRCEL-CELINE response before transformation, add an explicit source-specific parser, include source identity in deduplication and published evidence, and define a measured conflict policy before combining two readings from the same physical station. Do not disguise IRCEL-CELINE rows as OpenAQ SNS messages or average both sources together without that decision.

## Phase 2 — Make the proof of concept repeatable

**Goal:** another developer can deploy and demonstrate the same result safely.

1. Reconcile documentation with Terraform:
   - current production enablement state;
   - deployed ingestion batch size;
   - existing DLQ;
   - Terraform minimum version;
   - activation, smoke-test, rollback, and queue-ownership instructions.
2. Add a dev/QA SQS event-source mapping so ingestion is tested through the deployed trigger rather than direct Lambda invocation.
3. Configure and verify INFO-level structured logs for ingestion and transformation.
4. Return an explicit “data not available yet” response before the first result exists.
5. Include municipality reference data and locked calculation dependencies in result invalidation.
6. Add cache headers for immutable website assets and municipality geometry; keep live API responses uncached.
7. Replay a retained representative interval through deployed QA and compare its output with the local replay byte-for-byte or by the explicit JSON contract.

**Exit gate:** a clean checkout can build, deploy to dev, send a recorded batch through SQS, produce a result, serve the dashboard, and be removed using the documented commands.

## Phase 3 — Automate delivery

**Goal:** changes reach production only through tested, reviewable promotion.

1. Add CI for every change:
   - `make pre-commit`;
   - `make docker-test` where Docker is available;
   - Lambda package creation;
   - `terraform validate`;
   - dependency, secret, and Terraform security scans.
2. Build each ZIP once, record its checksum, and promote that same artifact through dev, QA, and production.
3. Automatically deploy successful changes to dev, then QA.
4. Feed QA with retained raw data, never the live production queue.
5. Require QA contract, replay, AWS smoke, freshness, and error checks before an approved production release.
6. Store Terraform state in a durable remote backend with locking and controlled access when account permissions permit it.
7. Record and test the rollback procedure using the previous known-good artifacts and Terraform revision.

**Exit gate:** no production change is built or applied manually, and rollback has been demonstrated in a non-production stage.

## Phase 4 — Add minimum production operations

**Goal:** detect failure before customers do and recover within agreed limits.

1. Define measurable service objectives:
   - maximum source-to-dashboard delay;
   - acceptable dashboard availability;
   - maximum queue age;
   - transformation duration and failure rate;
   - RTO and RPO;
   - monthly cost ceiling.
2. Add actionable alarms with an owner and runbook for:
   - oldest SQS message;
   - DLQ depth;
   - ingestion and transformation errors/throttles;
   - transformation timeout or abnormal duration;
   - missing or stale `results/latest.json`;
   - website errors/throttles;
   - budget or cost anomaly.
3. Add an EventBridge failure destination or DLQ with explicit retry behaviour for transformation.
4. Write short runbooks for source outage, queue backlog, poison messages, failed publication, stale dashboard, rollback, and raw/result recovery.
5. Exercise one source outage, one failed transformation, one DLQ recovery, and one rollback in QA.
6. Enable S3 versioning for the result bucket so the previous dashboard result can be restored.
7. Decide how raw evidence is protected from accidental deletion. Use versioning or Object Lock only if the agreed recovery requirement justifies it.
8. Verify the externally owned production queue's visibility timeout during deployment instead of relying only on a manual prerequisite.

**Exit gate:** an injected QA failure raises the expected alarm, links to a usable runbook, and is recovered within the agreed objective.

## Phase 5 — Reduce security and availability risk

**Goal:** expose only the permissions and capacity required by the accepted product.

1. Document the existing shared Lambda role's effective policy and risks.
2. When IAM access becomes available, give ingestion, transformation, and website separate least-privilege roles.
3. Protect the public website according to its audience:
   - use authentication for a private sales dashboard; or
   - use a throttled edge/API layer for a public dashboard.
4. Prevent website traffic from exhausting pipeline capacity through suitable concurrency or request-rate isolation.
5. Enable auditable access for material S3 writes and deletes.
6. Define data classification, retention, and deletion rules for unchanged SQS/SNS envelopes.
7. Decide whether single-region recovery is sufficient from the agreed RTO/RPO; do not add multi-region infrastructure without that requirement.

**Exit gate:** permissions, public exposure, retention, and failure domains have named owners and accepted residual risks.

## Phase 6 — Validate launch readiness

Run a production-like QA exercise using representative retained data and record:

- source coverage and freshness;
- queue-drain time;
- transformation p50/p95 duration and peak memory;
- object and request counts;
- website response time and error rate;
- alert delivery and recovery time;
- estimated monthly cost;
- local-versus-QA result reconciliation;
- browser behaviour for current, stale, empty, missing, and insufficient-WHO-coverage states.

Release only when:

- Phase 1's source decision is still supported by measured evidence;
- the dashboard wording matches what the source can prove;
- CI/CD promotes one tested artifact through all stages;
- alarms and runbooks cover the critical data path;
- rollback and recovery have been exercised;
- security and cost risks are explicitly accepted;
- a named owner approves launch.

## Deferred until measurements justify them

Do not add these merely to make the architecture look production-like:

- a database or cleaned-data store;
- hourly compaction or Parquet rollups before file count/runtime requires them;
- multi-region active-active deployment;
- Kubernetes or a workflow platform;
- station history and arbitrary analytics queries;
- a custom caching or retry framework.

The first production investment should improve evidence, repeatability, detection, and recovery—not add more services.
