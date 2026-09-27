import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class RawObject:
    key: str
    modified: datetime


class LocalStore:
    def __init__(self, root: Path):
        self.root = root

    def raw_objects(
        self, prefix: str, start_after: str = "", stop_at: str | None = None
    ) -> list[RawObject]:
        """Keys under prefix, in key order, after start_after and before stop_at."""
        objects = (
            RawObject(
                path.relative_to(self.root).as_posix(),
                datetime.fromtimestamp(path.stat().st_mtime, UTC),
            )
            for path in self.root.glob(f"{prefix}**/*.json")
        )
        return sorted(
            (
                item
                for item in objects
                if item.key.startswith(prefix)
                and item.key > start_after
                and (stop_at is None or item.key < stop_at)
            ),
            key=lambda item: item.key,
        )

    def read_text(self, key: str) -> str:
        return (self.root / key).read_text(encoding="utf-8")

    def read_result(self) -> tuple[dict | None, str | None]:
        path = self.root / "results/latest.json"
        if not path.exists():
            return None, None
        content = path.read_bytes()
        return json.loads(content), hashlib.sha256(content).hexdigest()

    def write_result(self, value, etag: str | None) -> bool:
        path = self.root / "results/latest.json"
        current_etag = (
            hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        )
        if current_etag != etag:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
            encoding="utf-8",
        )
        return True
