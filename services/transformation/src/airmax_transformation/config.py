import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    store: str = os.getenv("AIRMAX_STORE", "s3")
    raw_bucket: str = os.getenv("AIRMAX_RAW_BUCKET", "")
    results_bucket: str = os.getenv("AIRMAX_RESULTS_BUCKET", "")
    local_root: Path = Path(os.getenv("AIRMAX_LOCAL_ROOT", ".local"))
