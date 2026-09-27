import json
from pathlib import Path


class LocalWriter:
    def __init__(self, root: Path):
        self.root = root

    def write(self, key: str, event: dict) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(event, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
