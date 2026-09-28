"""Capture IRCEL-CELINE hourly measurements for source-feasibility analysis."""

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

API = "https://geo.irceline.be/sos/api/v1"
POLLUTANTS = {
    "10": "co",
    "8": "no2",
    "7": "o3",
    "5": "pm10",
    "6001": "pm25",
    "1": "so2",
}


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamps must include a timezone")
    return parsed.astimezone(UTC)


def _json(path: str):
    with urlopen(f"{API}{path}", timeout=30) as response:
        return json.load(response)


def _rows(series: dict, pollutant: str, values: list[dict]):
    station = series["station"]
    longitude, latitude, *_ = station["geometry"]["coordinates"]
    source_unit = series["uom"]
    for observation in values:
        value = observation["value"]
        if value is None:
            continue
        unit = source_unit
        if pollutant == "co" and source_unit == "µg/m³":
            value /= 1000
            unit = "mg/m³"
        yield {
            "source": "IRCEL-CELINE",
            "timeseries_id": str(series["id"]),
            "station_id": str(station["properties"]["id"]),
            "station": station["properties"]["label"],
            "pollutant": pollutant,
            "unit": unit,
            "value": value,
            "observed_at": datetime.fromtimestamp(observation["timestamp"] / 1000, UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "coordinates": {"latitude": latitude, "longitude": longitude},
        }


def capture(start: datetime, end: datetime, output: Path) -> tuple[int, int]:
    timespan = f"{start.isoformat()}/{end.isoformat()}"
    series_count = row_count = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as destination:
        for phenomenon, pollutant in POLLUTANTS.items():
            for series in _json(f"/timeseries?{urlencode({'phenomenon': phenomenon})}"):
                series_count += 1
                values = _json(
                    f"/timeseries/{series['id']}/getData?"
                    f"{urlencode({'timespan': timespan})}"
                )["values"]
                for row in _rows(series, pollutant, values):
                    destination.write(
                        json.dumps(row, ensure_ascii=False, separators=(",", ":"))
                        + "\n"
                    )
                    row_count += 1
    return series_count, row_count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, type=_time)
    parser.add_argument("--end", required=True, type=_time)
    parser.add_argument("--output", type=Path, default=Path("data/ircel.ndjson"))
    args = parser.parse_args()
    if not args.start < args.end:
        parser.error("--start must be before --end")
    if args.end - args.start > timedelta(hours=48):
        parser.error("IRCEL-CELINE's real-time endpoint exposes at most 48 hours")
    series, rows = capture(args.start, args.end, args.output)
    print(f"Captured {rows} observations from {series} timeseries into {args.output}")


if __name__ == "__main__":
    main()
