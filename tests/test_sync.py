"""Unit tests for synchronization module."""

import unittest
from src.core.sync import TimestampSynchronizer


class TestTimestampSynchronizer(unittest.TestCase):
    """Tests for TimestampSynchronizer."""
    
    def setUp(self):
        """Initialize synchronizer."""
        self.sync = TimestampSynchronizer(reference_source="gps", max_drift_ms=100.0)
    
    def test_initialization(self):
        """Test synchronizer initialization."""
        self.assertEqual(self.sync.reference_source, "gps")
        self.assertEqual(self.sync.max_drift_ms, 100.0)
        self.assertEqual(len(self.sync.buffers), 3)  # camera, gps, imu
    
    def test_add_gps_data(self):
        """Test adding GPS data."""
        gps_data = {"timestamp": 1000.0, "latitude": 52.5, "longitude": 13.4}
        self.sync.add_gps_data(gps_data)
        
        self.assertEqual(len(self.sync.buffers["gps"]), 1)
        self.assertEqual(self.sync.buffers["gps"][0]["timestamp"], 1000.0)
    
    def test_add_camera_frame(self):
        """Test adding camera frame."""
        frame_data = {"image_path": "frame.jpg"}
        self.sync.add_camera_frame(1000.0, frame_data)
        
        self.assertEqual(len(self.sync.buffers["camera"]), 1)
        self.assertEqual(self.sync.buffers["camera"][0]["timestamp"], 1000.0)
    
    def test_add_imu_measurement(self):
        """Test adding IMU measurement."""
        imu_data = {
            "timestamp": 1000.0,
            "ax": 0.05, "ay": -0.02, "az": 9.81,
            "gx": 0.01, "gy": 0.02, "gz": -0.01
        }
        self.sync.add_imu_measurement(imu_data)
        
        self.assertEqual(len(self.sync.buffers["imu"]), 1)
    
    def test_nearest_neighbor_match_exact(self):
        """Test nearest neighbor matching with exact timestamp."""
        self.sync.add_gps_data({"timestamp": 1000.0, "latitude": 52.5, "longitude": 13.4})
        
        match = self.sync._nearest_neighbor_match(1000.0, self.sync.buffers["gps"])
        
        self.assertIsNotNone(match)
        self.assertEqual(match["timestamp"], 1000.0)
    
    def test_nearest_neighbor_match_closest(self):
        """Test nearest neighbor finds closest match."""
        for i in range(5):
            self.sync.add_gps_data({"timestamp": 1000.0 + i * 0.1, "latitude": 52.5, "longitude": 13.4})
        
        # Query for timestamp between two samples
        match = self.sync._nearest_neighbor_match(1000.15, self.sync.buffers["gps"])
        
        self.assertIsNotNone(match)
        # Should match either 1000.1 or 1000.2 (closest)
        self.assertIn(match["timestamp"], [1000.1, 1000.2])
    
    def test_nearest_neighbor_max_distance(self):
        """Test nearest neighbor respects max distance."""
        self.sync.add_gps_data({"timestamp": 1000.0, "latitude": 52.5, "longitude": 13.4})
        
        # Query with target far from sample
        match = self.sync._nearest_neighbor_match(2000.0, self.sync.buffers["gps"], max_distance_s=0.5)
        
        # Should return None because distance exceeds max
        self.assertIsNone(match)
    
    def test_synchronize_frame_no_gps(self):
        """Test frame synchronization without GPS data."""
        camera_data = {"timestamp": 1000.0, "image_path": "frame.jpg"}
        
        record = self.sync.synchronize_frame(camera_data)
        
        self.assertEqual(record["timestamp"], 1000.0)
        self.assertEqual(record["image_path"], "frame.jpg")
        self.assertIsNone(record["latitude"])
        self.assertIsNone(record["longitude"])
    
    def test_synchronize_frame_with_gps_and_imu(self):
        """Test frame synchronization with GPS and IMU data."""
        # Add GPS data
        self.sync.add_gps_data({"timestamp": 1000.0, "latitude": 52.5, "longitude": 13.4})
        
        # Add IMU data
        self.sync.add_imu_measurement({
            "timestamp": 1000.0,
            "ax": 0.05, "ay": -0.02, "az": 9.81,
            "gx": 0.01, "gy": 0.02, "gz": -0.01
        })
        
        # Synchronize camera frame
        camera_data = {"timestamp": 1000.0, "image_path": "frame.jpg"}
        record = self.sync.synchronize_frame(camera_data)
        
        self.assertEqual(record["timestamp"], 1000.0)
        self.assertEqual(record["latitude"], 52.5)
        self.assertEqual(record["longitude"], 13.4)
        self.assertEqual(record["ax"], 0.05)
        self.assertEqual(record["az"], 9.81)
    
    def test_estimate_clock_offset_reference_source(self):
        """Test clock offset for reference source is always 0."""
        offset = self.sync.estimate_clock_offset("gps")
        self.assertEqual(offset, 0.0)
    
    def test_estimate_clock_offset_insufficient_data(self):
        """Test clock offset with insufficient samples."""
        # Add only 1 sample, need at least 10
        self.sync.add_gps_data({"timestamp": 1000.0, "latitude": 52.5, "longitude": 13.4})
        
        offset = self.sync.estimate_clock_offset("camera", reference_samples=10)
        self.assertIsNone(offset)
    
    def test_detect_drift(self):
        """Test drift detection."""
        # Add camera frames with some spacing
        for i in range(10):
            self.sync.add_camera_frame(1000.0 + i * 0.033, {"image_path": f"frame_{i}.jpg"})
        
        drift_report = self.sync.detect_drift()
        
        self.assertIn("camera", drift_report)
        # Should detect minimal drift for sequential frames
        self.assertIsInstance(drift_report["camera"], float)
    
    def test_get_statistics(self):
        """Test statistics retrieval."""
        self.sync.add_gps_data({"timestamp": 1000.0, "latitude": 52.5, "longitude": 13.4})
        self.sync.add_camera_frame(1000.0, {"image_path": "frame.jpg"})
        
        stats = self.sync.get_statistics()
        
        self.assertIn("clock_offsets", stats)
        self.assertIn("buffer_sizes", stats)
        self.assertIn("drift_detection", stats)
        
        self.assertEqual(stats["buffer_sizes"]["gps"], 1)
        self.assertEqual(stats["buffer_sizes"]["camera"], 1)


if __name__ == '__main__':
    unittest.main()
