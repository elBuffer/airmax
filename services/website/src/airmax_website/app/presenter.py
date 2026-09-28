from datetime import UTC, datetime
from typing import Any

COLORS = ("#b9553f", "#d7a83e", "#8fab63", "#367c59")
WHO_GUIDELINES: dict[str, tuple[float, str, int]] = {
    "co": (4, "mg/m³", 24),
    "no2": (25, "µg/m³", 24),
    "o3": (100, "µg/m³", 8),
    "pm10": (45, "µg/m³", 24),
    "pm25": (15, "µg/m³", 24),
    "so2": (40, "µg/m³", 24),
}
WHO_SOURCE = "https://www.who.int/publications/i/item/9789240034228"


def _unit_key(unit: str) -> str:
    return unit.lower().replace("µ", "u").replace("³", "3").replace("/", "_")


def _time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _who_comparison(row: dict, period: dict, guideline: tuple[float, str, int]) -> dict:
    history_complete = period.get("window", {}).get("history_complete", False)
    coverage_complete = row["observation_hour_count"] >= row["required_hour_count"]
    difference: float | None = (
        row["average"] - guideline[0] if guideline[1] == row["unit"] else None
    )
    if not history_complete or not coverage_complete or difference is None:
        comparison_status = "insufficient_coverage"
    elif difference > 0:
        comparison_status = "above_guideline_value"
    else:
        comparison_status = "at_or_below_guideline_value"
    comparison = {
        "average": row["average"],
        "measurement_count": row["measurement_count"],
        "physical_site_count": row["distinct_sites"],
        "observation_count": row["observation_count"],
        "observation_hour_count": row["observation_hour_count"],
        "required_hour_count": row["required_hour_count"],
        "period_hours": guideline[2],
        "earliest_observation": row["earliest_observation"],
        "latest_observation": row["latest_observation"],
        "generated_at": period.get("generated_at"),
        "guideline": guideline[0] if difference is not None else None,
        "source": WHO_SOURCE,
        "status": comparison_status,
    }
    if difference is not None:
        comparison.update(difference=difference, ratio=row["average"] / guideline[0])
    return comparison


def dashboard_view(result: dict, stale_hours: int, now: datetime | None = None) -> dict:
    who_periods = {24: result.get("who_24h", {}), 8: result.get("who_8h", {})}
    cities: dict[str, dict[str, Any]] = {}
    for hours, period in who_periods.items():
        for row in period.get("cities", []):
            guideline = WHO_GUIDELINES.get(row["pollutant"])
            if not guideline or guideline[2] != hours:
                continue
            city = cities.setdefault(
                row["nis"],
                {
                    "nis_code": row["nis"],
                    "name": row["municipality"],
                    "latitude": row["latitude"],
                    "longitude": row["longitude"],
                    "values": {},
                    "who_values": {},
                },
            )
            key = f"{row['pollutant']}_{_unit_key(row['unit'])}"
            city["who_values"][key] = {
                "parameter": row["pollutant"],
                "unit": row["unit"],
                "comparison": _who_comparison(row, period, guideline),
            }

    for row in result.get("cities", []):
        city = cities.setdefault(
            row["nis"],
            {
                "nis_code": row["nis"],
                "name": row["municipality"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "values": {},
                "who_values": {},
            },
        )
        key = f"{row['pollutant']}_{_unit_key(row['unit'])}"
        city["values"][key] = {
            "parameter": row["pollutant"],
            "unit": row["unit"],
            "average": row["average"],
            "measurement_count": row["measurement_count"],
            "station_count": row["distinct_sites"],
            "earliest_observation": row["earliest_observation"],
            "latest_observation": row["latest_observation"],
            "status": "available",
        }

    for series in {series for city in cities.values() for series in city["values"]}:
        ranked = sorted(
            (city for city in cities.values() if series in city["values"]),
            key=lambda city: city["values"][series]["average"],
            reverse=True,
        )
        for index, city in enumerate(ranked):
            band = min(3, index * 4 // len(ranked))
            city["values"][series].update(rank=index + 1, color=COLORS[band])

    latest_text = result.get("window", {}).get("end_t")
    latest = _time(latest_text)
    now = now or datetime.now(UTC)
    age = None if latest is None else max(0, int((now - latest).total_seconds() / 60))
    status = (
        "unavailable"
        if age is None
        else "stale"
        if age > stale_hours * 60
        else "current"
    )
    return {
        "source": result.get("source", {}),
        "window": {
            "start": result.get("window", {}).get("start"),
            "end": result.get("window", {}).get("end_t"),
            "duration_hours": result.get("window", {}).get("hours"),
        },
        "freshness": {
            "status": status,
            "latest_observation": latest_text,
            "label": "No source message received"
            if age is None
            else f"Latest source message received {age} minutes ago",
        },
        "guidelines": [
            {
                "pollutant": pollutant,
                "guideline": value,
                "unit": unit,
                "period_hours": hours,
                "source": WHO_SOURCE,
            }
            for pollutant, (value, unit, hours) in WHO_GUIDELINES.items()
        ],
        "cities": sorted(cities.values(), key=lambda city: city["name"]),
    }
