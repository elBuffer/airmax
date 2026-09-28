# Human-readable calculation contract: services/transformation/RULES.md
from dataclasses import dataclass
from pathlib import Path

from .transformations.deduplication import deduplicate
from .transformations.municipalities import Municipalities, map_municipalities
from .transformations.validation import load_readings, validate_and_spool
from .transformations.window import rolling_window, within_window

REFERENCE = Path(__file__).parent / "reference" / "municipalities.geojson"


@dataclass
class PreparedReadings:
    readings: object
    window: dict
    source: str


def prepare_readings(records, workdir: Path, window_hours: int) -> PreparedReadings:
    validated = validate_and_spool(records, workdir)
    window_start, window_end = rolling_window(
        validated["latest_received"], window_hours
    )

    readings = ()

    if window_start is not None and window_end is not None:
        readings = within_window(
            load_readings(validated["accepted_path"]), window_start, window_end
        )

        readings = deduplicate(readings)
        readings = map_municipalities(readings, Municipalities(REFERENCE))
    return PreparedReadings(
        readings=readings,
        window={"start": window_start, "end": window_end, "hours": window_hours},
        source=validated["source"],
    )
