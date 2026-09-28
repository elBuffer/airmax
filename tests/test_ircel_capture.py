import tempfile
import unittest
from argparse import ArgumentTypeError
from pathlib import Path

from airmax_ingestion.adapters.local_writer import LocalWriter
from airmax_transformation.adapters.local_store import LocalStore
from airmax_transformation.handler import lambda_handler as calculate

from tools.capture_ircel import _rows, _time


class IrcelCaptureTest(unittest.TestCase):
    def test_normalizes_co_and_skips_missing_values(self):
        series = {
            "id": "42",
            "uom": "µg/m³",
            "station": {
                "properties": {"id": 7, "label": "Station"},
                "geometry": {"coordinates": [4.4, 50.8, "NaN"]},
            },
        }

        rows = list(
            _rows(
                series,
                "co",
                [
                    {"timestamp": 1_789_603_200_000, "value": 750.0},
                    {"timestamp": 1_789_606_800_000, "value": None},
                ],
            )
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "IRCEL-CELINE")
        self.assertEqual(rows[0]["value"], 0.75)
        self.assertEqual(rows[0]["unit"], "mg/m³")
        self.assertEqual(rows[0]["observed_at"], "2026-09-17T00:00:00Z")
        self.assertEqual(rows[0]["coordinates"], {"latitude": 50.8, "longitude": 4.4})

    def test_requires_explicit_timezone(self):
        with self.assertRaises(ArgumentTypeError):
            _time("2026-09-17T00:00:00")

    def test_ircel_record_runs_through_transformation(self):
        record = {
            "source": "IRCEL-CELINE",
            "timeseries_id": "42",
            "station_id": "7",
            "station": "Gent",
            "pollutant": "pm25",
            "unit": "µg/m³",
            "value": 12.5,
            "observed_at": "2026-09-17T04:00:00Z",
            "coordinates": {"latitude": 51.0543, "longitude": 3.725},
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            LocalWriter(root).write(
                "raw/2026/09/17/04/ircel.json", {"Records": [record]}
            )

            result = calculate(store=LocalStore(root))["result"]

        self.assertEqual(
            result["source"],
            {"name": "IRCEL-CELINE", "url": "https://www.irceline.be/en/"},
        )
        self.assertEqual(result["cities"][0]["municipality"], "Gent")
        self.assertEqual(result["cities"][0]["average"], 12.5)


if __name__ == "__main__":
    unittest.main()
