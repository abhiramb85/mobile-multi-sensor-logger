"""Unit tests for the ROS-free shared boundary logic.

These cover the conversions the live nodes and the offline exporter both rely
on, so they run without ROS 2 installed.
"""

import math
import unittest

from src.tools import ros2_common as rc


class TestTimestamps(unittest.TestCase):
    def test_parses_iso8601(self):
        self.assertAlmostEqual(
            rc.parse_timestamp("2026-06-24T14:39:29.903236+00:00"),
            1782311969.903236, places=5)

    def test_parses_bare_epoch(self):
        self.assertAlmostEqual(rc.parse_timestamp("1778834626.19"), 1778834626.19)

    def test_rejects_junk(self):
        for bad in ("", None, "not-a-time"):
            self.assertIsNone(rc.parse_timestamp(bad))

    def test_to_ros_time_splits_seconds_and_nanos(self):
        self.assertEqual(rc.to_ros_time(12.5), {"sec": 12, "nanosec": 500000000})

    def test_to_nanoseconds_round_trips_with_to_ros_time(self):
        epoch = 1700000000.123456
        parts = rc.to_ros_time(epoch)
        self.assertEqual(rc.to_nanoseconds(epoch),
                         parts["sec"] * 1_000_000_000 + parts["nanosec"])


class TestGyroConversion(unittest.TestCase):
    def test_degrees_to_radians(self):
        wx, wy, wz = rc.gyro_dps_to_rads((180.0, 0.0, -90.0))
        self.assertAlmostEqual(wx, math.pi)
        self.assertAlmostEqual(wy, 0.0)
        self.assertAlmostEqual(wz, -math.pi / 2)


class TestSharedConstants(unittest.TestCase):
    def test_ros2_msgs_reexports_same_objects(self):
        # ros2_msgs must not carry a second copy of these sentinels.
        from src.tools import ros2_msgs
        self.assertIs(ros2_msgs.COVARIANCE_TYPE_UNKNOWN, rc.COVARIANCE_TYPE_UNKNOWN)
        self.assertIs(ros2_msgs.STATUS_FIX, rc.STATUS_FIX)
        self.assertIs(ros2_msgs.SERVICE_GPS, rc.SERVICE_GPS)

    def test_to_rosbag_shares_the_same_topic_names(self):
        from src.tools import to_rosbag
        self.assertEqual(to_rosbag.TOPIC_GPS, rc.TOPIC_GPS)
        self.assertEqual(to_rosbag.TOPIC_IMU, rc.TOPIC_IMU)
        self.assertEqual(to_rosbag.TOPIC_IMAGE_COMPRESSED, rc.TOPIC_IMAGE_COMPRESSED)


if __name__ == "__main__":
    unittest.main()
