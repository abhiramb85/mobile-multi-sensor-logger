"""Unit tests for configuration module."""

import unittest
from src.core.config import (
    CameraConfig, GPSConfig, IMUConfig, SyncConfig, SystemConfig
)


class TestCameraConfig(unittest.TestCase):
    """Tests for CameraConfig."""
    
    def test_defaults(self):
        """Test default values."""
        config = CameraConfig()
        self.assertEqual(config.device_id, 0)
        self.assertEqual(config.fps, 30)
        self.assertEqual(config.resolution_width, 1280)
        self.assertEqual(config.resolution_height, 720)
    
    def test_custom_values(self):
        """Test with custom values."""
        config = CameraConfig(device_id=1, fps=60, resolution_width=1920, resolution_height=1080)
        self.assertEqual(config.device_id, 1)
        self.assertEqual(config.fps, 60)
        self.assertEqual(config.resolution_width, 1920)


class TestGPSConfig(unittest.TestCase):
    """Tests for GPSConfig."""
    
    def test_defaults(self):
        """Test default values."""
        config = GPSConfig()
        self.assertEqual(config.port, "/dev/ttyACM0")
        self.assertEqual(config.baudrate, 9600)
        self.assertEqual(config.type, "NMEA")


class TestIMUConfig(unittest.TestCase):
    """Tests for IMUConfig."""
    
    def test_defaults(self):
        """Test default values."""
        config = IMUConfig()
        self.assertFalse(config.enabled)
        self.assertEqual(config.sensor_type, "BNO055")
        self.assertEqual(config.i2c_bus, 1)
        self.assertEqual(config.i2c_address, 0x28)
    
    def test_enabled(self):
        """Test enabling IMU."""
        config = IMUConfig(enabled=True)
        self.assertTrue(config.enabled)


class TestSyncConfig(unittest.TestCase):
    """Tests for SyncConfig."""
    
    def test_defaults(self):
        """Test default values."""
        config = SyncConfig()
        self.assertEqual(config.reference_source, "gps")
        self.assertEqual(config.max_drift_ms, 100.0)
        self.assertEqual(config.interpolation_method, "nearest_neighbor")


class TestSystemConfig(unittest.TestCase):
    """Tests for SystemConfig."""
    
    def test_post_init_creates_defaults(self):
        """Test that __post_init__ creates default sub-configs."""
        config = SystemConfig()
        self.assertIsNotNone(config.camera)
        self.assertIsNotNone(config.gps)
        self.assertIsNotNone(config.imu)
        self.assertIsNotNone(config.sync)
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        config = SystemConfig()
        config_dict = config.to_dict()
        self.assertIn('camera', config_dict)
        self.assertIn('gps', config_dict)
        self.assertIn('imu', config_dict)
        self.assertIn('sync', config_dict)
    
    def test_custom_components(self):
        """Test with custom sub-components."""
        camera = CameraConfig(device_id=2, fps=60)
        config = SystemConfig(camera=camera)
        self.assertEqual(config.camera.device_id, 2)
        self.assertEqual(config.camera.fps, 60)


if __name__ == '__main__':
    unittest.main()
