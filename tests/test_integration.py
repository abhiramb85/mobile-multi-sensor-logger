"""Integration tests for the full mock-pipeline: drivers + synchronizer + logger."""

import time
import unittest
from pathlib import Path

from src.sensors.camera import CameraDriver
from src.sensors.gps import GPSDriver
from src.sensors.imu import IMUDriver
from src.core.sync import TimestampSynchronizer
from src.core.logger import DataLogger


class SensorIntegrationTests(unittest.TestCase):
    """Exercise the camera + GPS + IMU + sync + logger pipeline in mock mode."""

    @classmethod
    def setUpClass(cls):
        cls.camera = CameraDriver()
        cls.gps = GPSDriver()
        cls.imu = IMUDriver()
        cls.camera.start()
        cls.gps.start()
        cls.imu.start()

    @classmethod
    def tearDownClass(cls):
        cls.camera.stop()
        cls.gps.stop()
        cls.imu.stop()

    def test_full_logging_cycle(self):
        """Acquisition -> synchronization -> logging round trip writes at least one record."""
        synchronizer = TimestampSynchronizer(reference_source="gps")
        logger = DataLogger(output_dir=Path("./data/test_logs"))

        try:
            duration = 1.0
            end_time = time.time() + duration

            while time.time() < end_time:
                camera_data = self.camera.get_frame()
                gps_data = self.gps.get_data()
                imu_data = self.imu.get_measurement()

                if not camera_data:
                    time.sleep(0.01)
                    continue

                camera_ts = camera_data[0]
                camera_record = {
                    "timestamp": camera_ts,
                    "image_path": f"mock/img_{self.camera.get_frame_count()}.jpg",
                }
                synchronizer.add_gps_data(gps_data)
                synchronizer.add_imu_measurement(imu_data)
                synchronizer.add_camera_frame(camera_ts, camera_record)

                sync_record = synchronizer.synchronize_frame(camera_record)
                if sync_record:
                    logger.log_record(sync_record)

            self.assertGreater(
                logger.get_record_count(), 0,
                "Expected at least one record to be logged in a 1-second mock run.",
            )
        finally:
            logger.finalize()

    def test_synchronizer_drift_detection(self):
        """Populating buffers with an IMU-vs-GPS offset should be detectable."""
        synchronizer = TimestampSynchronizer(reference_source="gps")

        for _ in range(50):
            camera_ts = time.time() - 0.1  # camera slightly behind GPS
            synchronizer.add_gps_data(self.gps.get_data())
            synchronizer.add_imu_measurement(self.imu.get_measurement())
            synchronizer.add_camera_frame(camera_ts, {"image_path": "mock"})

        drift = synchronizer.detect_drift()
        self.assertIn("imu", drift, "IMU drift should be detectable when buffers contain offset data.")


class LoggerNullHandlingTests(unittest.TestCase):
    """The logger must accept records with null GPS or null IMU fields without crashing."""

    def test_log_record_with_missing_gps(self):
        logger = DataLogger(output_dir=Path("./data/test_logs"))
        record = {
            "timestamp": time.time(),
            "latitude": None, "longitude": None,
            "image_path": "mock",
            "ax": 1.0, "ay": 2.0, "az": 9.81,
            "gx": 0.0, "gy": 0.0, "gz": 0.0,
        }
        self.assertTrue(logger.log_record(record))
        logger.finalize()

    def test_log_record_with_missing_imu(self):
        logger = DataLogger(output_dir=Path("./data/test_logs"))
        record = {
            "timestamp": time.time(),
            "latitude": 34.0, "longitude": -118.0,
            "image_path": "mock",
            "ax": None, "ay": None, "az": None,
            "gx": None, "gy": None, "gz": None,
        }
        self.assertTrue(logger.log_record(record))
        logger.finalize()


if __name__ == "__main__":
    unittest.main()
