"""Unit tests for the rosbag2 exporter."""

import math
import tempfile
import unittest
from pathlib import Path

from src.core.logger import DataLogger
from src.tools import ros2_msgs, to_rosbag

try:
    from mcap_ros2.reader import read_ros2_messages
    MCAP_AVAILABLE = True
except ImportError:
    MCAP_AVAILABLE = False

FRAMES = {"camera": "camera_link", "gps": "gps_link", "imu": "imu_link"}


class TestTimestampParsing(unittest.TestCase):
    """Both timestamp encodings found in ./data must convert."""

    def test_parses_iso8601(self):
        epoch = to_rosbag.parse_timestamp("2026-06-24T14:39:29.903236+00:00")
        self.assertAlmostEqual(epoch, 1782311969.903236, places=5)

    def test_parses_bare_epoch_float(self):
        self.assertAlmostEqual(
            to_rosbag.parse_timestamp("1778834626.1902351"), 1778834626.1902351)

    def test_rejects_empty_and_garbage(self):
        self.assertIsNone(to_rosbag.parse_timestamp(""))
        self.assertIsNone(to_rosbag.parse_timestamp(None))
        self.assertIsNone(to_rosbag.parse_timestamp("not-a-time"))

    def test_ros_time_split(self):
        self.assertEqual(to_rosbag.to_ros_time(12.5), {"sec": 12, "nanosec": 500000000})


class TestMessageBuilders(unittest.TestCase):
    """Field-level checks that don't need the MCAP writer."""

    stamp = {"sec": 1, "nanosec": 0}

    def test_gyro_converted_to_radians(self):
        record = {"ax": "0", "ay": "0", "az": "9.81",
                  "gx": "180", "gy": "0", "gz": "-90"}
        imu = to_rosbag.build_imu(record, self.stamp, "imu_link")
        self.assertAlmostEqual(imu["angular_velocity"]["x"], math.pi)
        self.assertAlmostEqual(imu["angular_velocity"]["z"], -math.pi / 2)
        self.assertAlmostEqual(imu["linear_acceleration"]["z"], 9.81)

    def test_orientation_marked_unavailable(self):
        record = {k: "0" for k in ("ax", "ay", "az", "gx", "gy", "gz")}
        imu = to_rosbag.build_imu(record, self.stamp, "imu_link")
        self.assertEqual(imu["orientation_covariance"][0], -1.0)
        self.assertEqual(imu["orientation"], {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0})

    def test_orientation_uses_recorded_quaternion(self):
        record = {k: "0" for k in ("ax", "ay", "az", "gx", "gy", "gz")}
        record.update(qx="0", qy="0", qz="0.7071", qw="0.7071")
        imu = to_rosbag.build_imu(record, self.stamp, "imu_link")
        self.assertEqual(imu["orientation"], {"x": 0.0, "y": 0.0, "z": 0.7071, "w": 0.7071})
        self.assertEqual(imu["orientation_covariance"], [0.0] * 9)

    def test_missing_imu_columns_yield_no_message(self):
        record = {"ax": "", "ay": "", "az": "", "gx": "", "gy": "", "gz": ""}
        self.assertIsNone(to_rosbag.build_imu(record, self.stamp, "imu_link"))

    def test_missing_gps_columns_yield_no_message(self):
        self.assertIsNone(
            to_rosbag.build_navsatfix({"latitude": ""}, self.stamp, "gps_link"))

    def test_navsatfix_altitude_is_nan_when_unknown(self):
        fix = to_rosbag.build_navsatfix(
            {"latitude": "34.0", "longitude": "-118.0"}, self.stamp, "gps_link")
        self.assertTrue(math.isnan(fix["altitude"]))
        self.assertEqual(fix["position_covariance_type"],
                         ros2_msgs.COVARIANCE_TYPE_UNKNOWN)


class TestImageResolution(unittest.TestCase):
    """data.csv paths come from other machines; the basename must still resolve."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dataset = Path(self.temp_dir.name)
        (self.dataset / "images").mkdir()
        (self.dataset / "images" / "frame_1.jpg").write_bytes(b"JPEG")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_resolves_windows_style_path_by_basename(self):
        found = to_rosbag.resolve_image(
            self.dataset, r"D:\other\machine\images\frame_1.jpg")
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "frame_1.jpg")

    def test_missing_image_returns_none(self):
        self.assertIsNone(to_rosbag.resolve_image(self.dataset, "images/nope.jpg"))
        self.assertIsNone(to_rosbag.resolve_image(self.dataset, ""))


@unittest.skipUnless(MCAP_AVAILABLE, "requires mcap and mcap-ros2-support")
class TestBagConversion(unittest.TestCase):
    """End-to-end: log a dataset, export it, decode it back through CDR."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.dataset = root / "run"
        self.bag_dir = root / "run_rosbag"

        logger = DataLogger(self.dataset, {"camera": {"resolution_width": 640,
                                                      "resolution_height": 480}})
        for i in range(3):
            frame = self.dataset / "images" / f"frame_{i}.jpg"
            frame.write_bytes(b"JPEGDATA")
            logger.log_record({
                "timestamp": 1700000000.0 + i * 0.1,
                "latitude": 34.0 + i, "longitude": -118.0 - i,
                "image_path": str(frame),
                "ax": 0.0, "ay": 0.0, "az": 9.81,
                "gx": 180.0, "gy": 0.0, "gz": 0.0,
            })
        logger.finalize()

        self.counts = to_rosbag.convert(self.dataset, self.bag_dir, FRAMES)
        self.messages = list(read_ros2_messages(
            self.bag_dir / f"{self.bag_dir.name}_0.mcap"))

    def tearDown(self):
        self.temp_dir.cleanup()

    def _by_topic(self, topic):
        return [m for m in self.messages if m.channel.topic == topic]

    def test_all_topics_present_with_expected_counts(self):
        for topic in (to_rosbag.TOPIC_GPS, to_rosbag.TOPIC_IMU,
                      to_rosbag.TOPIC_IMAGE_COMPRESSED, to_rosbag.TOPIC_CAMERA_INFO):
            self.assertEqual(self.counts[topic], 3, topic)
            self.assertEqual(len(self._by_topic(topic)), 3, topic)

    def test_navsatfix_decodes_with_original_values(self):
        fix = self._by_topic(to_rosbag.TOPIC_GPS)[0].ros_msg
        self.assertAlmostEqual(fix.latitude, 34.0)
        self.assertAlmostEqual(fix.longitude, -118.0)
        self.assertEqual(fix.header.frame_id, "gps_link")
        self.assertEqual(fix.header.stamp.sec, 1700000000)

    def test_imu_decodes_in_radians_per_second(self):
        imu = self._by_topic(to_rosbag.TOPIC_IMU)[0].ros_msg
        self.assertAlmostEqual(imu.angular_velocity.x, math.pi, places=6)
        self.assertAlmostEqual(imu.linear_acceleration.z, 9.81, places=6)

    def test_compressed_image_carries_jpeg_bytes(self):
        image = self._by_topic(to_rosbag.TOPIC_IMAGE_COMPRESSED)[0].ros_msg
        self.assertEqual(image.format, "jpeg")
        self.assertEqual(bytes(image.data), b"JPEGDATA")

    def test_camera_info_uses_recorded_resolution(self):
        info = self._by_topic(to_rosbag.TOPIC_CAMERA_INFO)[0].ros_msg
        self.assertEqual((info.width, info.height), (640, 480))

    def test_metadata_yaml_describes_the_bag(self):
        text = (self.bag_dir / "metadata.yaml").read_text()
        self.assertIn("storage_identifier: mcap", text)
        self.assertIn("sensor_msgs/msg/NavSatFix", text)
        self.assertIn("serialization_format: cdr", text)
        self.assertIn(f"{self.bag_dir.name}_0.mcap", text)

    def test_repeated_image_path_is_written_once(self):
        """Rows sharing a frame must not inflate the camera rate."""
        duplicated = self.dataset.parent / "dup_rosbag"
        csv_path = self.dataset / "data.csv"
        rows = csv_path.read_text().splitlines()
        csv_path.write_text("\n".join(rows + [rows[-1]]) + "\n")

        counts = to_rosbag.convert(self.dataset, duplicated, FRAMES)
        self.assertEqual(counts[to_rosbag.TOPIC_GPS], 4)
        self.assertEqual(counts[to_rosbag.TOPIC_IMAGE_COMPRESSED], 3)


if __name__ == "__main__":
    unittest.main()
