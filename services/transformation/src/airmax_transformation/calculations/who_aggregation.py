from math import ceil
from typing import Any

from ..transformations.validation import iso


def aggregate_period(mapped_readings, start, hours: int) -> list[dict]:
    site_hours: dict[tuple[str, str, str, str, int, float, float], dict[str, Any]] = {}
    groups: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    for reading, (name, nis) in mapped_readings:
        key = name, nis, reading.pollutant, reading.unit
        hour = min(hours - 1, int((reading.sent_at - start).total_seconds() // 3600))
        site_key = key + (hour, reading.latitude, reading.longitude)
        site = site_hours.setdefault(site_key, {"sum": 0.0, "count": 0})
        site["sum"] += reading.value
        site["count"] += 1

        group = groups.setdefault(
            key,
            {
                "count": 0,
                "locations": set(),
                "sites": set(),
                "observations": set(),
                "latitude": 0.0,
                "longitude": 0.0,
                "earliest": reading.sent_at,
                "latest": reading.sent_at,
            },
        )
        group["count"] += 1
        group["locations"].add(reading.location_id)
        group["sites"].add((reading.latitude, reading.longitude))
        group["observations"].add(reading.sent_at)
        group["latitude"] += reading.latitude
        group["longitude"] += reading.longitude
        group["earliest"] = min(group["earliest"], reading.sent_at)
        group["latest"] = max(group["latest"], reading.sent_at)

    city_hours: dict[tuple[str, str, str, str, int], list[float]] = {}
    for site_key, site in site_hours.items():
        city_hour = site_key[:5]
        city_hours.setdefault(city_hour, []).append(site["sum"] / site["count"])

    period_values: dict[tuple[str, str, str, str], list[float]] = {}
    for city_hour, site_values in city_hours.items():
        city_key = city_hour[:4]
        city_mean = sum(site_values) / len(site_values)
        period_values.setdefault(city_key, []).append(city_mean)

    cities = []
    for key, hourly_values in sorted(period_values.items()):
        name = key[0]
        nis = key[1]
        pollutant = key[2]
        unit = key[3]
        group = groups[key]
        count = group["count"]
        cities.append(
            {
                "municipality": name,
                "nis": nis,
                "pollutant": pollutant,
                "unit": unit,
                "average": sum(hourly_values) / len(hourly_values),
                "measurement_count": count,
                "location_count": len(group["locations"]),
                "distinct_sites": len(group["sites"]),
                "latitude": group["latitude"] / count,
                "longitude": group["longitude"] / count,
                "earliest_observation": iso(group["earliest"]),
                "latest_observation": iso(group["latest"]),
                "observation_count": len(group["observations"]),
                "observation_hour_count": len(hourly_values),
                "required_hour_count": ceil(hours * 0.75),
            }
        )
    return cities
