import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True)
class CalculationContext:
    generated_at: datetime
    previous_result: dict | None
    raw_objects: list


@dataclass(frozen=True)
class CalculationPlan:
    raw_objects: list
    input_digest: str
    recalculate: bool


def select_objects(objects, window_hours):
    folders = [(item, _partition(item.key)) for item in objects]
    valid = [(item, folder) for item, folder in folders if folder]
    if not valid:
        return []
    latest = max(
        datetime.strptime(folder, "%Y/%m/%d/%H").replace(tzinfo=UTC)
        for _, folder in valid
    )
    selected_folders = {
        (latest - timedelta(hours=offset)).strftime("%Y/%m/%d/%H")
        for offset in range(window_hours + 1)
    }
    return [item for item, folder in valid if folder in selected_folders]


def input_digest(objects):
    return hashlib.sha256(
        "\n".join(sorted(item.key for item in objects)).encode()
    ).hexdigest()


def records(store, objects):
    for item in objects:
        event = json.loads(store.read_text(item.key))
        yield from event.get("Records", [])


def retained_history_covers(objects, window_start):
    partition_hours = []
    for raw_object in objects:
        partition_hour = _partition(raw_object.key)
        if partition_hour is not None:
            partition_hours.append(partition_hour)

    if not partition_hours:
        return False

    earliest_retained_hour = min(
        datetime.strptime(hour, "%Y/%m/%d/%H").replace(tzinfo=UTC)
        for hour in partition_hours
    )
    window_start_hour = window_start.replace(minute=0, second=0, microsecond=0)
    return earliest_retained_hour <= window_start_hour


def _partition(key):
    parts = key.split("/")
    if (
        len(parts) < 6
        or parts[0] != "raw"
        or not all(part.isdigit() for part in parts[1:5])
    ):
        return None
    return "/".join(parts[1:5])
