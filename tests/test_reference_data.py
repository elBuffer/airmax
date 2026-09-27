import unittest
from importlib.resources import files


class ReferenceDataTest(unittest.TestCase):
    def test_services_share_identical_boundaries(self):
        # Transformation maps readings to these polygons and the website draws them; each service
        # ships its own copy so it builds on its own, and the copies must never drift apart.
        transformation = files("airmax_transformation").joinpath(
            "reference/municipalities.geojson"
        )
        website = files("airmax_website").joinpath("reference/municipalities.geojson")
        self.assertEqual(transformation.read_bytes(), website.read_bytes())


if __name__ == "__main__":
    unittest.main()
