import json
import tempfile
import unittest
from pathlib import Path

from airmax_ingestion.adapters.local_writer import LocalWriter
from airmax_ingestion.handler import lambda_handler


class IngestionTest(unittest.TestCase):
    def test_poison_message_is_landed_unchanged(self):
        event = {
            "Records": [
                {
                    "body": "not-json",
                    "attributes": {"SentTimestamp": "1789618380000"},
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = lambda_handler(event, writer=LocalWriter(root))
            self.assertEqual(
                json.loads((root / output["key"]).read_text(encoding="utf-8")), event
            )
            self.assertTrue(output["key"].startswith("raw/invalid/2026/09/17/"))

    def test_unusable_sqs_timestamp_uses_last_resort_partition(self):
        event = {
            "Records": [
                {
                    "body": "not-json",
                    "attributes": {"SentTimestamp": "not-a-number"},
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            output = lambda_handler(event, writer=LocalWriter(Path(directory)))
            self.assertTrue(output["key"].startswith("raw/invalid/"))

    def test_records_are_partitioned_per_message_by_publish_hour(self):
        message = json.dumps({"date": {"utc": "2026-09-17 05:11:22"}})
        event = {
            "Records": [
                {
                    "body": json.dumps(
                        {"Timestamp": "2026-09-17T03:59:59Z", "Message": message}
                    )
                },
                {
                    "body": json.dumps(
                        {"Timestamp": "2026-09-17T04:00:00Z", "Message": message}
                    )
                },
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            output = lambda_handler(event, writer=LocalWriter(Path(directory)))
            self.assertEqual(len(output["keys"]), 2)
            self.assertTrue(
                any(key.startswith("raw/2026/09/17/03/") for key in output["keys"])
            )
            self.assertTrue(
                any(key.startswith("raw/2026/09/17/04/") for key in output["keys"])
            )


if __name__ == "__main__":
    unittest.main()
