# Human-readable landing and downstream listing contract: services/ingestion/RULES.md
import json
from collections import defaultdict
from datetime import UTC, datetime
from uuid import uuid4

from airmax_ingestion.config import Settings
from airmax_ingestion.logging import log

# Object-key paths. AIRMAX_RAW_BUCKET separately names the bucket to write into.
RAW_KEY_PREFIX = "raw/"
INVALID_RAW_KEY_PREFIX = f"{RAW_KEY_PREFIX}invalid/"
TIMESTAMP_PARSE_ERRORS = (
    AttributeError,
    KeyError,
    TypeError,
    ValueError,
    OverflowError,
    OSError,
)


def _published_at(record: dict) -> datetime:
    body = json.loads(record["body"])
    value = datetime.fromisoformat(body["Timestamp"])
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _sqs_sent_at(record: dict) -> datetime:
    milliseconds = record["attributes"]["SentTimestamp"]
    return datetime.fromtimestamp(int(milliseconds) / 1000, UTC)


def _invalid_partition_at(record: dict) -> datetime:
    try:
        return _sqs_sent_at(record)
    except TIMESTAMP_PARSE_ERRORS:
        return datetime.now(UTC)


def _hour_partition(prefix: str, timestamp: datetime) -> str:
    return f"{prefix}{timestamp:%Y/%m/%d/%H}"


def _partition(record: dict) -> str:
    try:
        return _hour_partition(RAW_KEY_PREFIX, _published_at(record))
    except TIMESTAMP_PARSE_ERRORS:
        return _hour_partition(INVALID_RAW_KEY_PREFIX, _invalid_partition_at(record))


def _configured_raw_writer():
    settings = Settings()
    if settings.store == "local":
        from .adapters.local_writer import LocalWriter

        return LocalWriter(settings.local_root)

    from .adapters.s3_writer import S3Writer

    return S3Writer(settings.raw_bucket)


def _group_records_by_partition(records: list[dict]) -> dict[str, list[dict]]:
    records_by_partition = defaultdict(list)
    for record in records:
        records_by_partition[_partition(record)].append(record)
    return records_by_partition


def _write_record_batches(
    event: dict, records_by_partition: dict[str, list[dict]], writer
) -> list[str]:
    written_object_keys = []
    for partition, records in records_by_partition.items():
        key = f"{partition}/batch-{uuid4()}.json"
        writer.write(key, {**event, "Records": records})
        written_object_keys.append(key)
        log("batch_ingested", key=key, records=len(records))
    return written_object_keys


def _ingestion_summary(
    written_object_keys: list[str], records_by_partition: dict[str, list[dict]]
) -> dict:
    return {
        "key": written_object_keys[0] if len(written_object_keys) == 1 else None,
        "keys": written_object_keys,
        "records": sum(map(len, records_by_partition.values())),
    }


def lambda_handler(event, _context=None, writer=None):
    if writer is None:
        writer = _configured_raw_writer()
    records_by_partition = _group_records_by_partition(event.get("Records", []))
    written_object_keys = _write_record_batches(event, records_by_partition, writer)
    return _ingestion_summary(written_object_keys, records_by_partition)
