import json
from pathlib import Path

from shapely import Point
from shapely.geometry import shape
from shapely.strtree import STRtree

# NIS codes of the German-speaking Community. Other Walloon codes start with 25, 5, 6, 8 or 9.
GERMAN_SPEAKING = {
    "63001",
    "63012",
    "63013",
    "63023",
    "63040",
    "63048",
    "63061",
    "63067",
    "63087",
}
WALLOON_PREFIXES = ("25", "5", "6", "8", "9")


def local_name(properties: dict) -> str:
    """The name a municipality uses itself: Liège, not Luik; both names in bilingual Brussels."""
    nis = str(properties["nis_code"])
    nl: str | None = properties.get("name_nl")
    fr: str | None = properties.get("name_fr")
    de: str | None = properties.get("name_de")
    if nis in GERMAN_SPEAKING:
        name = de or fr or nl
        assert name is not None
        return name
    if nis.startswith("21"):
        return " / ".join(dict.fromkeys(name for name in (fr, nl) if name))
    name = fr or nl or de if nis.startswith(WALLOON_PREFIXES) else nl or fr or de
    assert name is not None
    return name


class Municipalities:
    def __init__(self, path: Path):
        features = json.loads(path.read_text(encoding="utf-8"))["features"]
        self.geometries = [shape(feature["geometry"]) for feature in features]
        self.properties = [feature["properties"] for feature in features]
        self.tree = STRtree(self.geometries)

    def find(self, longitude: float, latitude: float) -> tuple[str, str] | None:
        matches = self.tree.query(Point(longitude, latitude), predicate="within")
        if not len(matches):
            return None
        properties = self.properties[int(matches[0])]
        return local_name(properties), str(properties["nis_code"])


def map_municipalities(readings, municipalities: Municipalities):
    for reading in readings:
        municipality = municipalities.find(reading.longitude, reading.latitude)
        if municipality is not None:
            yield reading, municipality
