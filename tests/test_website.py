import json
import tempfile
import unittest
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

from airmax_ingestion.adapters.local_writer import LocalWriter
from airmax_ingestion.handler import lambda_handler as ingest
from airmax_transformation.adapters.local_store import LocalStore
from airmax_transformation.handler import lambda_handler as calculate
from airmax_website.app.presenter import dashboard_view
from airmax_website.handler import lambda_handler

FIXTURES = Path(__file__).parent / "fixtures"


class Reader:
    def __init__(self, result=b'{"cities":[]}'):
        self._result = result

    def result(self):
        return self._result

    def municipalities(self):
        return b'{"type":"FeatureCollection","features":[]}'


class ServingTest(unittest.TestCase):
    def test_transformation_result_matches_dashboard_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event = json.loads(
                (FIXTURES / "burst-2026-09-17T04-13Z/sqs-event.json").read_text(
                    encoding="utf-8"
                )
            )
            ingest(event, writer=LocalWriter(root))
            calculate(store=LocalStore(root), now=datetime(2026, 9, 17, 5, tzinfo=UTC))

            response = lambda_handler(
                {"rawPath": "/api/current"},
                reader=Reader((root / "results/latest.json").read_bytes()),
            )
            body = json.loads(response["body"])
            gent = next(city for city in body["cities"] if city["nis_code"] == "44021")
            pm25 = gent["values"]["pm25_ug_m3"]

            self.assertEqual(response["statusCode"], 200)
            self.assertEqual(pm25["average"], 13.6474010878)
            self.assertEqual(pm25["measurement_count"], 6)
            self.assertEqual(pm25["station_count"], 5)
            self.assertNotIn("quality", body)

    def test_routes(self):
        reader = Reader()
        page = lambda_handler({"rawPath": "/"}, reader=reader)
        self.assertEqual(page["statusCode"], 200)
        self.assertIn("Belgian air quality", page["body"])
        self.assertIn('id="municipalityDataOnly"', page["body"])
        self.assertIn(
            "allPlaces.filter(hasData)",
            lambda_handler({"rawPath": "/app.js"}, reader=reader)["body"],
        )

        data = lambda_handler({"rawPath": "/data.json"}, reader=reader)
        self.assertEqual(json.loads(data["body"]), {"cities": []})
        dashboard = lambda_handler({"rawPath": "/api/current"}, reader=reader)
        dashboard_body = json.loads(dashboard["body"])
        self.assertEqual(dashboard_body["cities"], [])
        self.assertEqual(
            next(
                item
                for item in dashboard_body["guidelines"]
                if item["pollutant"] == "o3"
            ),
            {
                "pollutant": "o3",
                "guideline": 100,
                "unit": "µg/m³",
                "period_hours": 8,
                "source": "https://www.who.int/publications/i/item/9789240034228",
            },
        )
        self.assertIn(
            "maplibre", lambda_handler({"rawPath": "/app.js"}, reader=reader)["body"]
        )
        self.assertEqual(
            lambda_handler({"rawPath": "/vendor/maplibre-gl.js"}, reader=reader)[
                "statusCode"
            ],
            200,
        )
        static = files("airmax_website").joinpath("app/static")
        for name in ("index.html", "app.js", "styles.css"):
            text = (static / name).read_text(encoding="utf-8")
            self.assertNotRegex(
                text,
                r"(src|href)=\"https?://(?!(openaq\.org|www\.who\.int))|url\('https?:|style: 'https?:",
                f"{name} must not load third-party resources",
            )

        self.assertEqual(
            lambda_handler({"rawPath": "/missing"}, reader=reader)["statusCode"], 404
        )

    def test_who_24_hour_comparison(self):
        city = {
            "municipality": "Gent",
            "nis": "44021",
            "pollutant": "pm25",
            "unit": "µg/m³",
            "average": 12,
            "measurement_count": 6,
            "location_count": 5,
            "distinct_sites": 5,
            "latitude": 51.05,
            "longitude": 3.72,
            "earliest_observation": "2026-09-17T01:00:00Z",
            "latest_observation": "2026-09-17T04:00:00Z",
        }
        daily = {
            **city,
            "average": 18,
            "measurement_count": 24,
            "distinct_sites": 5,
            "observation_count": 20,
            "observation_hour_count": 19,
            "required_hour_count": 18,
            "earliest_observation": "2026-09-16T04:00:00Z",
        }
        result = {
            "window": {
                "start": "2026-09-17T01:00:00Z",
                "end_t": "2026-09-17T04:00:00Z",
                "hours": 3,
            },
            "source": {"name": "OpenAQ", "url": "https://openaq.org"},
            "cities": [city],
            "who_24h": {
                "generated_at": "2026-09-17T04:05:00Z",
                "window": {"history_complete": True},
                "cities": [daily],
            },
        }
        view = dashboard_view(
            result, stale_hours=8, now=datetime(2026, 9, 17, 5, tzinfo=UTC)
        )
        comparison = view["cities"][0]["who_values"]["pm25_ug_m3"]["comparison"]
        self.assertEqual(comparison["guideline"], 15)
        self.assertEqual(comparison["difference"], 3)
        self.assertEqual(comparison["observation_count"], 20)
        self.assertEqual(comparison["observation_hour_count"], 19)
        self.assertEqual(comparison["status"], "above_guideline_value")

        result["who_24h"]["window"]["history_complete"] = False
        incomplete = dashboard_view(result, stale_hours=8)["cities"][0]["who_values"][
            "pm25_ug_m3"
        ]["comparison"]
        self.assertEqual(incomplete["status"], "insufficient_coverage")

        result["who_24h"]["window"]["history_complete"] = True
        daily["observation_hour_count"] = 17
        low_coverage = dashboard_view(result, stale_hours=8)["cities"][0]["who_values"][
            "pm25_ug_m3"
        ]["comparison"]
        self.assertEqual(low_coverage["status"], "insufficient_coverage")

        result["cities"] = []
        who_only = dashboard_view(result, stale_hours=8)["cities"][0]
        self.assertEqual(who_only["values"], {})
        self.assertEqual(
            who_only["who_values"]["pm25_ug_m3"]["comparison"]["average"],
            18,
        )


if __name__ == "__main__":
    unittest.main()
