from typing import Any

from ..pipeline import prepare_readings
from ..transformations.validation import iso
from .input import (
    CalculationContext,
    CalculationPlan,
    input_digest,
    records,
    select_objects,
)
from .result_validation import validate_result

NAME = "current"
LOOKBACK_HOURS = 3
WINDOW_HOURS = LOOKBACK_HOURS
SOURCE_METADATA = {
    "OpenAQ": {"name": "OpenAQ", "url": "https://openaq.org"},
    "IRCEL-CELINE": {
        "name": "IRCEL-CELINE",
        "url": "https://www.irceline.be/en/",
    },
}
CURRENT_RESULT_FIELDS = (
    "generated_at",
    "window",
    "source",
    "input_digest",
    "cities",
)


def aggregate(mapped_readings) -> list[dict]:
    groups: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for reading, (name, nis) in mapped_readings:
        key = name, nis, reading.pollutant, reading.unit
        group = groups.setdefault(
            key,
            {
                "count": 0,
                "locations": set(),
                "sites": {},
                "latitude": 0.0,
                "longitude": 0.0,
                "earliest": reading.sent_at,
                "latest": reading.sent_at,
            },
        )
        # Location IDs at identical coordinates are co-located instruments of one station (ADR-0004).
        site = group["sites"].setdefault(
            (reading.latitude, reading.longitude), [0.0, 0]
        )
        site[0] += reading.value
        site[1] += 1
        group["count"] += 1
        group["locations"].add(reading.location_id)
        group["latitude"] += reading.latitude
        group["longitude"] += reading.longitude
        group["earliest"] = min(group["earliest"], reading.sent_at)
        group["latest"] = max(group["latest"], reading.sent_at)

    cities = []
    for key, group in sorted(groups.items()):
        name = key[0]
        nis = key[1]
        pollutant = key[2]
        unit = key[3]
        count = group["count"]
        site_means = [total / readings for total, readings in group["sites"].values()]
        cities.append(
            {
                "municipality": name,
                "nis": nis,
                "pollutant": pollutant,
                "unit": unit,
                "average": sum(site_means) / len(site_means),
                "measurement_count": count,
                "location_count": len(group["locations"]),
                "distinct_sites": len(group["sites"]),
                "latitude": group["latitude"] / count,
                "longitude": group["longitude"] / count,
                "earliest_observation": iso(group["earliest"]),
                "latest_observation": iso(group["latest"]),
            }
        )
    return cities


def plan(context: CalculationContext) -> CalculationPlan:
    raw_objects = select_objects(context.raw_objects, WINDOW_HOURS)
    digest = input_digest(raw_objects)
    previous_digest = (
        context.previous_result.get("input_digest")
        if context.previous_result is not None
        else None
    )
    return CalculationPlan(raw_objects, digest, previous_digest != digest)


def empty_result(generated_at):
    return {
        "generated_at": iso(generated_at),
        "window": {"end_t": None, "start": None, "hours": WINDOW_HOURS},
        "source": SOURCE_METADATA["OpenAQ"],
        "input_digest": input_digest([]),
        "cities": [],
    }


def validate(result):
    validate_result(result, NAME)


def calculate(store, context: CalculationContext, plan: CalculationPlan, workdir):
    if not plan.recalculate:
        assert context.previous_result is not None
        return {
            field: context.previous_result[field] for field in CURRENT_RESULT_FIELDS
        }

    workdir.mkdir()
    prepared = prepare_readings(records(store, plan.raw_objects), workdir, WINDOW_HOURS)
    cities = aggregate(prepared.readings)
    return {
        "generated_at": iso(context.generated_at),
        "window": {
            "end_t": iso(prepared.window["end"]),
            "start": iso(prepared.window["start"]),
            "hours": WINDOW_HOURS,
        },
        "source": SOURCE_METADATA[prepared.source],
        "input_digest": plan.input_digest,
        "cities": cities,
    }
