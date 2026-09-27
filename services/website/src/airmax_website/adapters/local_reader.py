from pathlib import Path


class LocalReader:
    def __init__(self, root: Path):
        self.root = root

    def result(self) -> bytes:
        return (self.root / "results/latest.json").read_bytes()

    def municipalities(self) -> bytes:
        path = Path(__file__).parents[1] / "reference" / "municipalities.geojson"
        return path.read_bytes()
