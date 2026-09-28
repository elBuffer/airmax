"""Replay an IRCEL-CELINE feasibility capture through the real transformation."""

import json
import os
import shutil
from collections import defaultdict
from pathlib import Path

os.environ["AIRMAX_STORE"] = "local"
os.environ.setdefault("AIRMAX_LOCAL_ROOT", ".local")

from airmax_ingestion.adapters.local_writer import LocalWriter
from airmax_transformation.handler import lambda_handler as calculate
from airmax_transformation.transformations.validation import parse_time


def main() -> None:
    source = Path(os.getenv("AIRMAX_DATA", "data/ircel.ndjson"))
    root = Path(os.environ["AIRMAX_LOCAL_ROOT"])
    shutil.rmtree(root, ignore_errors=True)
    records_by_hour = defaultdict(list)
    with source.open(encoding="utf-8") as lines:
        for line in lines:
            record = json.loads(line)
            observed_at = parse_time(record["observed_at"])
            records_by_hour[f"raw/{observed_at:%Y/%m/%d/%H}/ircel.json"].append(record)

    writer = LocalWriter(root)
    for key, records in records_by_hour.items():
        writer.write(key, {"Records": records})

    print(json.dumps(calculate(), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
