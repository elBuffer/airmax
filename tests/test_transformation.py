import json
import os
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from airmax_ingestion.adapters.local_writer import LocalWriter
from airmax_ingestion.handler import lambda_handler as ingest
from airmax_transformation.adapters.local_store import LocalStore
from airmax_transformation.calculations.current import (
    validate as validate_current_result,
)
from airmax_transformation.handler import REFERENCE
from airmax_transformation.handler import lambda_handler as calculate
from airmax_transformation.transformations.municipalities import (
    Municipalities,
    local_name,
)
from airmax_transformation.transformations.validation import parse_time

FIXTURES = Path(__file__).parent / "fixtures"


class CountingStore(LocalStore):
    reads = 0

    def read_text(self, key):
        self.reads += 1
        return super().read_text(key)


class ListingStore(LocalStore):
    def __init__(self, root):
        super().__init__(root)
        self.listings = []
        self.listed = []

    def raw_objects(self, prefix, start_after="", stop_at=None):
        self.listings.append((prefix, start_after, stop_at))
        objects = super().raw_objects(prefix, start_after, stop_at)
        self.listed.extend(item.key for item in objects)
        return objects


class RacingStore(LocalStore):
    def write_result(self, value, etag):
        if not hasattr(self, "raced"):
            self.raced = True
            later_clock_but_older_data = {
                **value,
                "generated_at": "2026-09-18T11:00:00Z",
                "window": {**value["window"], "end_t": "2026-09-17T03:13:00Z"},
            }
            super().write_result(later_clock_but_older_data, etag)
            return False
        return super().write_result(value, etag)


def _event(timestamp):
    envelope = {"Timestamp": timestamp, "Message": "{}"}
    return {"Records": [{"body": json.dumps(envelope)}]}


class CalculationTest(unittest.TestCase):
    def test_no_raw_data_publishes_empty_result_once(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalStore(Path(directory))
            first = calculate(store=store, now=datetime(2026, 9, 18, 10, tzinfo=UTC))
            self.assertEqual(first["status"], "written")
            self.assertEqual(
                first["result"]["window"], {"end_t": None, "start": None, "hours": 3}
            )
            self.assertEqual(first["result"]["cities"], [])
            self.assertEqual(calculate(store=store)["status"], "unchanged")

    def test_invalid_candidate_result_is_not_publishable(self):
        result = {
            "generated_at": "2026-09-18T10:00:00Z",
            "window": {
                "start": "2026-09-18T11:00:00Z",
                "end_t": "2026-09-18T10:00:00Z",
                "hours": 3,
            },
            "cities": [],
        }
        with self.assertRaisesRegex(
            ValueError, "current window start must not be after its end"
        ):
            validate_current_result(result)

    def test_etag_race_uses_data_progress_not_wall_clock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ingest(_event("2026-09-17T04:13:00Z"), writer=LocalWriter(root))
            status = calculate(
                store=RacingStore(root),
                now=datetime(2026, 9, 18, 10, tzinfo=UTC),
            )["status"]
            result = json.loads(
                (root / "results/latest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(status, "written")
            self.assertEqual(result["generated_at"], "2026-09-18T10:00:00Z")

    def test_no_accepted_data_produces_empty_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            envelope = {
                "Timestamp": "2026-09-17T04:13:00Z",
                "Message": "{}",
            }
            event = {
                "Records": [
                    {"body": json.dumps(envelope)},
                    _event("2026-09-17T01:12:59Z")["Records"][0],
                ]
            }
            ingest(event, writer=LocalWriter(root))
            output = calculate(store=LocalStore(root))["result"]
            self.assertEqual(output["cities"], [])
            self.assertEqual(
                output["window"],
                {
                    "end_t": "2026-09-17T04:13:00Z",
                    "start": "2026-09-17T01:13:00Z",
                    "hours": 3,
                },
            )

    def test_recorded_burst(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event = json.loads(
                (FIXTURES / "burst-2026-09-17T04-13Z/sqs-event.json").read_text(
                    encoding="utf-8"
                )
            )
            outside = json.loads(json.dumps(event["Records"][0]))
            envelope = json.loads(outside["body"])
            message = json.loads(envelope["Message"])
            message["locationId"] = 999
            envelope["Timestamp"] = "2026-09-17T01:00:00Z"
            envelope["Message"] = json.dumps(message)
            outside["body"] = json.dumps(envelope)
            event["Records"].extend([outside, outside.copy()])
            for fixture in (
                "burst-negative/sqs-event.json",
                "burst-validation/sqs-event.json",
            ):
                extra = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
                event["Records"].extend(extra["Records"])
            ingest(event, writer=LocalWriter(root))
            store = CountingStore(root)
            fixed_now = datetime(2026, 9, 18, 10, 15, 3, tzinfo=UTC)
            output = calculate(store=store, now=fixed_now)["result"]

            expected = json.loads(
                (FIXTURES / "expected/gent-pm25.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(output["cities"]), 1)
            self.assertEqual(
                {key: output["cities"][0][key] for key in expected}, expected
            )
            self.assertEqual(output["window"]["end_t"], "2026-09-17T04:13:00Z")
            before = (root / "results/latest.json").read_bytes()
            reads = store.reads
            self.assertEqual(calculate(store=store)["status"], "unchanged")
            self.assertEqual(store.reads, reads)
            self.assertEqual((root / "results/latest.json").read_bytes(), before)

    def test_source_time_over_five_minutes_old_is_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event = json.loads(
                (FIXTURES / "burst-2026-09-17T04-13Z/sqs-event.json").read_text(
                    encoding="utf-8"
                )
            )
            records = []
            for location_id, source_time in (
                (800001, "2026-09-17 04:08:00"),
                (800002, "2026-09-17 04:07:59"),
            ):
                record = json.loads(json.dumps(event["Records"][0]))
                envelope = json.loads(record["body"])
                message = json.loads(envelope["Message"])
                message.update(locationId=location_id)
                message["date"]["utc"] = source_time
                envelope["Message"] = json.dumps(message)
                record["body"] = json.dumps(envelope)
                records.append(record)

            ingest({"Records": records}, writer=LocalWriter(root))
            output = calculate(store=LocalStore(root))["result"]

            self.assertEqual(output["cities"][0]["measurement_count"], 1)

    def test_invalid_numeric_fields_are_excluded_without_stopping_calculation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = json.loads(
                (FIXTURES / "burst-2026-09-17T04-13Z/sqs-event.json").read_text(
                    encoding="utf-8"
                )
            )
            original = fixture["Records"][0]
            records = [original]
            cases = (
                ("value", "12.5"),
                ("value", 10**400),
                ("latitude", "51.0"),
                ("longitude", 10**400),
            )
            for location_id, (field, value) in enumerate(cases, start=800100):
                envelope = json.loads(original["body"])
                message = json.loads(envelope["Message"])
                message["locationId"] = location_id
                if field in ("latitude", "longitude"):
                    message["coordinates"][field] = value
                else:
                    message[field] = value
                envelope["Message"] = json.dumps(message)
                records.append({**original, "body": json.dumps(envelope)})

            ingest({"Records": records}, writer=LocalWriter(root))
            output = calculate(store=LocalStore(root))["result"]

            self.assertEqual(output["cities"][0]["measurement_count"], 1)

    def test_who_window_is_calculated_at_most_hourly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            burst = json.loads(
                (FIXTURES / "burst-2026-09-17T04-13Z/sqs-event.json").read_text(
                    encoding="utf-8"
                )
            )
            old = json.loads(json.dumps(burst["Records"][0]))
            envelope = json.loads(old["body"])
            message = json.loads(envelope["Message"])
            message.update(locationId=700001, value=20)
            message["date"]["utc"] = "2026-09-16 04:13:00"
            envelope.update(
                Timestamp="2026-09-16T04:13:00Z", Message=json.dumps(message)
            )
            old["body"] = json.dumps(envelope)
            burst["Records"].append(old)
            ingest(burst, writer=LocalWriter(root))

            first = calculate(
                store=LocalStore(root), now=datetime(2026, 9, 18, 10, 15, tzinfo=UTC)
            )["result"]
            self.assertEqual(first["cities"][0]["measurement_count"], 6)
            self.assertEqual(first["who_24h"]["cities"][0]["measurement_count"], 7)
            self.assertAlmostEqual(
                first["who_24h"]["cities"][0]["average"], (13.6474010878 + 20) / 2
            )
            self.assertEqual(first["who_24h"]["cities"][0]["observation_hour_count"], 2)
            self.assertEqual(first["who_24h"]["cities"][0]["required_hour_count"], 18)
            self.assertTrue(first["who_24h"]["window"]["history_complete"])

            added = json.loads(json.dumps(burst["Records"][0]))
            envelope = json.loads(added["body"])
            message = json.loads(envelope["Message"])
            message.update(locationId=700002, value=30)
            message["date"]["utc"] = "2026-09-17 04:12:00"
            envelope["Message"] = json.dumps(message)
            added["body"] = json.dumps(envelope)
            ingest({"Records": [added]}, writer=LocalWriter(root))

            same_hour = calculate(
                store=LocalStore(root), now=datetime(2026, 9, 18, 10, 30, tzinfo=UTC)
            )["result"]
            self.assertEqual(same_hour["cities"][0]["measurement_count"], 7)
            self.assertEqual(same_hour["who_24h"], first["who_24h"])

            next_hour = calculate(
                store=LocalStore(root), now=datetime(2026, 9, 18, 11, 0, tzinfo=UTC)
            )["result"]
            self.assertEqual(next_hour["who_24h"]["cities"][0]["measurement_count"], 8)
            self.assertEqual(
                next_hour["who_24h"]["generated_at"], "2026-09-18T11:00:00Z"
            )

    def test_listing_starts_at_previous_window(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            burst = json.loads(
                (FIXTURES / "burst-2026-09-17T04-13Z/sqs-event.json").read_text(
                    encoding="utf-8"
                )
            )
            ingest(burst, writer=LocalWriter(root))
            ingest(_event("2026-09-10T08:00:00Z"), writer=LocalWriter(root))
            ingest(
                {
                    "Records": [
                        {
                            "body": "not json",
                            "attributes": {"SentTimestamp": "1757491200000"},
                        }
                    ]
                },
                writer=LocalWriter(root),
            )
            store = ListingStore(root)

            self.assertEqual(calculate(store=store)["status"], "written")
            self.assertEqual(store.listings, [("raw/", "", "raw/invalid/")])

            store.listings.clear()
            store.listed.clear()
            self.assertEqual(calculate(store=store)["status"], "unchanged")
            self.assertEqual(
                store.listings,
                [
                    ("raw/", "raw/2026/09/16/03/", "raw/invalid/"),
                ],
            )
            self.assertTrue(
                all(
                    not key.startswith(("raw/2026/09/10/", "raw/invalid/"))
                    for key in store.listed
                )
            )

    def test_late_file_with_same_upload_time_is_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            burst = json.loads(
                (FIXTURES / "burst-2026-09-17T04-13Z/sqs-event.json").read_text(
                    encoding="utf-8"
                )
            )
            ingest(burst, writer=LocalWriter(root))
            first = calculate(store=LocalStore(root))["result"]
            existing = next(root.glob("raw/2026/**/*.json"))

            late = json.loads(json.dumps(burst))
            envelope = json.loads(late["Records"][0]["body"])
            envelope["Timestamp"] = "2026-09-17T03:30:00Z"
            message = json.loads(envelope["Message"])
            message["locationId"] = 424242
            envelope["Message"] = json.dumps(message)
            late["Records"] = [{**late["Records"][0], "body": json.dumps(envelope)}]
            ingest(late, writer=LocalWriter(root))
            added = next(path for path in root.glob("raw/2026/09/17/03/*.json"))
            mtime = existing.stat().st_mtime
            os.utime(added, (mtime, mtime))

            second = calculate(store=LocalStore(root))
            self.assertEqual(second["status"], "written")
            self.assertEqual(
                second["result"]["cities"][0]["measurement_count"],
                first["cities"][0]["measurement_count"] + 1,
            )

    def test_municipalities_are_named_in_their_own_language(self):
        municipalities = Municipalities(REFERENCE)
        self.assertEqual(municipalities.find(5.5797, 50.6326), ("Liège", "62063"))
        self.assertEqual(municipalities.find(3.7250, 51.0543), ("Gent", "44021"))
        names = {
            str(properties["nis_code"]): local_name(properties)
            for properties in municipalities.properties
        }
        self.assertEqual(names["55004"], "Braine-le-Comte")
        self.assertEqual(names["63040"], "Kelmis")
        self.assertEqual(names["21004"], "Bruxelles / Brussel")
        self.assertEqual(names["21001"], "Anderlecht")

    def test_offset_timestamps_are_converted_to_utc(self):
        self.assertEqual(
            parse_time("2026-09-17T06:13:00+02:00"),
            datetime(2026, 9, 17, 4, 13, tzinfo=UTC),
        )


if __name__ == "__main__":
    unittest.main()
