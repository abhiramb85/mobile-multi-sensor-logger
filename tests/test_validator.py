"""Tests for the dataset validator's pure-Python helpers."""

import sys
import unittest
from pathlib import Path

# scripts/ isn't a package, so make it importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from validate_dataset import haversine_m  # noqa: E402


class HaversineDistanceTests(unittest.TestCase):

    def test_zero_distance(self):
        # Same point -> 0 m.
        self.assertAlmostEqual(haversine_m(52.5200, 13.4050, 52.5200, 13.4050), 0.0)

    def test_one_arc_minute_of_latitude_is_about_1852_metres(self):
        # 1' of latitude is the nautical mile by definition (1852 m).
        d = haversine_m(52.0, 13.0, 52.0 + 1 / 60, 13.0)
        self.assertAlmostEqual(d, 1852, delta=2)

    def test_berlin_to_munich_about_504km(self):
        # Real-world sanity check: Berlin -> Munich great-circle ~504 km.
        berlin = (52.5200, 13.4050)
        munich = (48.1351, 11.5820)
        d_km = haversine_m(*berlin, *munich) / 1000
        self.assertAlmostEqual(d_km, 504, delta=3)

    def test_symmetric(self):
        a = haversine_m(52.5200, 13.4050, 48.1351, 11.5820)
        b = haversine_m(48.1351, 11.5820, 52.5200, 13.4050)
        self.assertAlmostEqual(a, b)


if __name__ == "__main__":
    unittest.main()
