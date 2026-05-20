"""Unit tests for data logger module."""

import unittest
import tempfile
import json
import csv
from pathlib import Path
from src.core.logger import DataLogger


class TestDataLogger(unittest.TestCase):
    """Tests for DataLogger."""
    
    def setUp(self):
        """Create temporary directory for test output."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_path = Path(self.temp_dir.name)
    
    def tearDown(self):
        """Clean up temporary directory."""
        self.temp_dir.cleanup()
    
    def test_initialization(self):
        """Test logger initialization."""
        config = {"camera": {"device_id": 0}}
        logger = DataLogger(self.output_path, config)
        
        # Check directories created
        self.assertTrue((self.output_path / "images").exists())
        
        # Check files created
        self.assertTrue((self.output_path / "data.csv").exists())
        self.assertTrue((self.output_path / "metadata.json").exists())
        
        logger.finalize()
    
    def test_csv_headers(self):
        """Test CSV headers are correct."""
        logger = DataLogger(self.output_path)
        logger.csv_file.flush()  # Ensure headers are written
        
        with open(self.output_path / "data.csv", 'r') as f:
            reader = csv.DictReader(f)
            expected_fields = [
                'timestamp', 'latitude', 'longitude', 'image_path',
                'ax', 'ay', 'az', 'gx', 'gy', 'gz'
            ]
            self.assertEqual(reader.fieldnames, expected_fields)
        
        logger.finalize()
    
    def test_metadata_json(self):
        """Test metadata JSON is valid."""
        config = {"test": "value"}
        logger = DataLogger(self.output_path, config)
        
        with open(self.output_path / "metadata.json", 'r') as f:
            metadata = json.load(f)
        
        self.assertIn("recording_start", metadata)
        self.assertIn("sensor_configuration", metadata)
        self.assertEqual(metadata["sensor_configuration"]["test"], "value")
        
        logger.finalize()
    
    def test_log_record(self):
        """Test logging a single record."""
        logger = DataLogger(self.output_path)
        
        record = {
            "timestamp": 1234567890.123,
            "latitude": 52.5200,
            "longitude": 13.4050,
            "image_path": "images/frame_1234567890123.jpg",
            "ax": 0.05,
            "ay": -0.02,
            "az": 9.81,
            "gx": 0.01,
            "gy": 0.02,
            "gz": -0.01
        }
        
        result = logger.log_record(record)
        self.assertTrue(result)
        self.assertEqual(logger.get_record_count(), 1)
        
        logger.finalize()
    
    def test_log_record_with_nulls(self):
        """Test logging record with null IMU values."""
        logger = DataLogger(self.output_path)
        
        record = {
            "timestamp": 1234567890.123,
            "latitude": 52.5200,
            "longitude": 13.4050,
            "image_path": "images/frame_1234567890123.jpg",
            "ax": None,
            "ay": None,
            "az": None,
            "gx": None,
            "gy": None,
            "gz": None
        }
        
        result = logger.log_record(record)
        self.assertTrue(result)
        self.assertEqual(logger.get_record_count(), 1)
        
        # Verify CSV contains record
        with open(self.output_path / "data.csv", 'r') as f:
            lines = f.readlines()
            self.assertEqual(len(lines), 2)  # Header + 1 record
        
        logger.finalize()
    
    def test_log_batch(self):
        """Test logging multiple records."""
        logger = DataLogger(self.output_path)
        
        records = [
            {
                "timestamp": 1234567890.0 + i,
                "latitude": 52.5200 + i * 0.001,
                "longitude": 13.4050 + i * 0.001,
                "image_path": f"images/frame_{i}.jpg",
                "ax": 0.0, "ay": 0.0, "az": 9.81,
                "gx": 0.0, "gy": 0.0, "gz": 0.0
            }
            for i in range(5)
        ]
        
        count = logger.log_batch(records)
        self.assertEqual(count, 5)
        self.assertEqual(logger.get_record_count(), 5)
        
        logger.finalize()
    
    def test_finalize_updates_metadata(self):
        """Test that finalize updates metadata with stats."""
        logger = DataLogger(self.output_path)
        
        # Log some records
        for i in range(3):
            record = {
                "timestamp": 1234567890.0 + i,
                "latitude": 52.5200, "longitude": 13.4050,
                "image_path": f"images/frame_{i}.jpg",
                "ax": 0.0, "ay": 0.0, "az": 9.81,
                "gx": 0.0, "gy": 0.0, "gz": 0.0
            }
            logger.log_record(record)
        
        logger.finalize()
        
        # Check metadata has final stats
        with open(self.output_path / "metadata.json", 'r') as f:
            metadata = json.load(f)
        
        self.assertIn("recording_end", metadata)
        self.assertIn("recording_duration_seconds", metadata)
        self.assertEqual(metadata["total_records"], 3)
    
    def test_elapsed_time(self):
        """Test elapsed time tracking."""
        import time
        logger = DataLogger(self.output_path)
        
        initial_elapsed = logger.get_elapsed_time()
        self.assertGreaterEqual(initial_elapsed, 0)
        
        time.sleep(0.1)
        elapsed = logger.get_elapsed_time()
        self.assertGreater(elapsed, initial_elapsed)
        
        logger.finalize()


if __name__ == '__main__':
    unittest.main()
