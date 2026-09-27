import math

from ..transformations.validation import POLLUTANT_UNITS, parse_time


def validate_result(section: dict, name: str) -> None:
    try:
        parse_time(section["generated_at"])
        _validate_window(section["window"], name)
        _validate_cities(section["cities"], name)
    except (AttributeError, KeyError, TypeError) as error:
        raise ValueError(f"{name} does not match the publication contract") from error


def _validate_window(window: dict, name: str) -> None:
    start = window.get("start")
    end = window.get("end_t")

    if start is None and end is None:
        return
    if start is None or end is None:
        raise ValueError(f"{name} window must have both start and end")
    if parse_time(start) > parse_time(end):
        raise ValueError(f"{name} window start must not be after its end")


def _validate_cities(cities: list, name: str) -> None:
    seen = set()
    for city in cities:
        _validate_city(city, name)

        key = city["nis"], city["pollutant"], city["unit"]
        if key in seen:
            raise ValueError(
                f"{name} contains duplicate municipality/pollutant/unit rows"
            )
        seen.add(key)


def _validate_city(city: dict, name: str) -> None:
    pollutant = city["pollutant"]
    if POLLUTANT_UNITS.get(pollutant) != city["unit"]:
        raise ValueError(f"{name} contains a pollutant/unit mismatch")

    average = city["average"]
    if isinstance(average, bool) or not math.isfinite(average):
        raise ValueError(f"{name} average must be finite")

    measurement_count = city["measurement_count"]
    location_count = city["location_count"]
    site_count = city["distinct_sites"]
    _require_positive_integer(measurement_count, f"{name}.measurement_count")
    _require_positive_integer(location_count, f"{name}.location_count")
    _require_positive_integer(site_count, f"{name}.distinct_sites")

    if location_count > measurement_count or site_count > measurement_count:
        raise ValueError(
            f"{name} location and site counts cannot exceed measurement_count"
        )

    earliest = parse_time(city["earliest_observation"])
    latest = parse_time(city["latest_observation"])
    if earliest > latest:
        raise ValueError(f"{name} observation range is invalid")


def _require_positive_integer(value, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be positive")
