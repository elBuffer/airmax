import json
import os
import shutil
from pathlib import Path

os.environ["AIRMAX_STORE"] = "local"
os.environ.setdefault("AIRMAX_LOCAL_ROOT", ".local")

from airmax_ingestion.handler import lambda_handler as ingest
from airmax_transformation.handler import lambda_handler as calculate

root = Path(os.environ["AIRMAX_LOCAL_ROOT"])
shutil.rmtree(root, ignore_errors=True)

source = os.getenv("AIRMAX_DATA")
if source:
    batch = []
    with Path(source).open(encoding="utf-8") as lines:
        for line in lines:
            record = json.loads(line)
            batch.append(
                {"body": record["Body"], "attributes": record.get("Attributes", {})}
            )
            if len(batch) == 10:
                ingest({"Records": batch})
                batch = []
    if batch:
        ingest({"Records": batch})
else:
    for path in sorted(Path("tests/fixtures").glob("burst-*/sqs-event.json")):
        ingest(json.loads(path.read_text(encoding="utf-8")))

result = calculate()
print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
