import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

# One five-minute refresh cycle tolerates minor source/SNS clock or transit jitter without admitting material backfill.
LATE_TOLERANCE = timedelta(minutes=5)
POLLUTANT_UNITS = {
    "co": "mg/m³",
    "no2": "µg/m³",
    "o3": "µg/m³",
    "pm10": "µg/m³",
    "pm25": "µg/m³",
    "so2": "µg/m³",
}


def iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z") if value else None


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return (
        parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    )


def is_json_number(value) -> bool:
    if type(value) is int:
        return True
    if type(value) is float:
        return True
    return False


def valid_location_id(location_id) -> bool:
    if type(location_id) is int:
        return True
    if isinstance(location_id, str):
        return bool(location_id.strip())
    return False


def valid_pollutant(pollutant) -> bool:
    if not isinstance(pollutant, str):
        return False
    if pollutant not in POLLUTANT_UNITS:
        return False
    return True


def valid_unit(unit, pollutant: str) -> bool:
    if not isinstance(unit, str):
        return False
    if unit != POLLUTANT_UNITS[pollutant]:
        return False
    return True


def valid_value(value) -> bool:
    if not is_json_number(value):
        return False
    try:
        finite = math.isfinite(value)
    except OverflowError:
        return False
    if not finite:
        return False
    if value < 0:
        return False
    return True


def valid_country(country) -> bool:
    if country != "BE":
        return False
    return True


def valid_source_time(source_time, sent_at: datetime) -> bool:
    try:
        parsed_time = parse_time(source_time)
    except (AttributeError, TypeError, ValueError):
        return False
    if parsed_time < sent_at - LATE_TOLERANCE:
        return False
    return True


def valid_coordinates(latitude, longitude) -> bool:
    if not is_json_number(latitude):
        return False
    if not is_json_number(longitude):
        return False
    if not 49.4 <= latitude <= 51.6:
        return False
    if not 2.5 <= longitude <= 6.5:
        return False
    return True


@dataclass
class Reading:
    source: str
    location_id: str
    pollutant: str
    unit: str
    value: float
    source_time: str
    sent_at: datetime
    latitude: float
    longitude: float


def reading_from(
    message: dict, sent_at: datetime, source: str = "OpenAQ"
) -> Reading | None:
    location_id = message["locationId"]
    pollutant = message["parameter"]
    unit = message["unit"]
    value = message["value"]
    country = message["country"]
    source_time = message["date"]["utc"]
    latitude = message["coordinates"]["latitude"]
    longitude = message["coordinates"]["longitude"]

    if not valid_location_id(location_id):
        return None
    if not valid_pollutant(pollutant):
        return None
    if not valid_unit(unit, pollutant):
        return None
    if not valid_value(value):
        return None
    if not valid_country(country):
        return None
    if not valid_source_time(source_time, sent_at):
        return None
    if not valid_coordinates(latitude, longitude):
        return None

    return Reading(
        source=source,
        location_id=str(location_id),
        pollutant=pollutant,
        unit=unit,
        value=float(value),
        source_time=source_time,
        sent_at=sent_at,
        latitude=float(latitude),
        longitude=float(longitude),
    )


def _ircel_reading(record: dict) -> tuple[Reading | None, datetime | None]:
    observed_at = parse_time(record["observed_at"])
    coordinates = record["coordinates"]
    message = {
        "locationId": record["timeseries_id"],
        "parameter": record["pollutant"],
        "unit": record["unit"],
        "value": record["value"],
        "country": "BE",
        "date": {"utc": record["observed_at"]},
        "coordinates": coordinates,
    }
    return reading_from(message, observed_at, "IRCEL-CELINE"), observed_at


def validate(record: dict) -> tuple[Reading | None, datetime | None]:
    try:
        if record.get("source") == "IRCEL-CELINE":
            return _ircel_reading(record)
        envelope = json.loads(record["body"])
        sent_at = parse_time(envelope["Timestamp"])
        message = json.loads(envelope["Message"])
    except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None, None

    try:
        return reading_from(message, sent_at), sent_at
    except (KeyError, TypeError):
        return None, sent_at


def dump_reading(reading: Reading) -> str:
    value = asdict(reading)
    value["sent_at"] = iso(reading.sent_at)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def load_readings(path: Path):
    with path.open(encoding="utf-8") as lines:
        for line in lines:
            value = json.loads(line)
            value["sent_at"] = parse_time(value["sent_at"])
            yield Reading(**value)


def validate_and_spool(records, workdir: Path) -> dict:
    accepted_path = workdir / "accepted.ndjson"
    latest_received: datetime | None = None
    sources = set()

    with accepted_path.open("w", encoding="utf-8") as accepted_file:
        for record in records:
            reading, sent_at = validate(record)
            if sent_at is not None:
                if latest_received is None or sent_at > latest_received:
                    latest_received = sent_at
            if reading is not None:
                sources.add(reading.source)
                accepted_file.write(dump_reading(reading) + "\n")

    if len(sources) > 1:
        raise ValueError("OpenAQ and IRCEL-CELINE require a source conflict policy")
    return {
        "accepted_path": accepted_path,
        "latest_received": latest_received,
        "source": next(iter(sources), "OpenAQ"),
    }
