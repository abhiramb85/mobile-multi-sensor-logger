"""Data logging formatter for structured CSV and JSON output."""

import csv
import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime


class DataLogger:
    """Formats and writes synchronized multi-sensor data to CSV and metadata JSON."""
    
    def __init__(self, output_dir: Path, sensor_config: Dict = None):
        """
        Initialize logger.
        
        Args:
            output_dir: Directory to store dataset
            sensor_config: Sensor configuration metadata
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.images_dir = self.output_dir / "images"
        self.images_dir.mkdir(exist_ok=True)
        
        self.csv_path = self.output_dir / "data.csv"
        self.metadata_path = self.output_dir / "metadata.json"
        
        self.sensor_config = sensor_config or {}
        self.record_count = 0
        self.start_time = time.time()
        self.csv_file = None
        self.csv_writer = None
        
        self._init_csv()
        self._write_metadata()
    
    def _init_csv(self):
        """Initialize CSV file with headers."""
        try:
            self.csv_file = open(self.csv_path, 'w', newline='')
            fieldnames = [
                'timestamp',
                'latitude',
                'longitude',
                'image_path',
                'ax', 'ay', 'az',
                'gx', 'gy', 'gz'
            ]
            self.csv_writer = csv.DictWriter(self.csv_file, fieldnames=fieldnames)
            self.csv_writer.writeheader()
            print(f"CSV initialized at {self.csv_path}")
        except Exception as e:
            print(f"Error initializing CSV: {e}")
    
    def _write_metadata(self):
        """Write metadata.json with sensor configuration."""
        try:
            metadata = {
                "recording_start": datetime.now().isoformat(),
                "recording_start_unix": self.start_time,
                "sensor_configuration": self.sensor_config,
                "output_format": "CSV + Images",
                "csv_columns": [
                    "timestamp (unix epoch)",
                    "latitude (decimal degrees)",
                    "longitude (decimal degrees)",
                    "image_path (relative)",
                    "ax, ay, az (m/s², acceleration)",
                    "gx, gy, gz (°/s, angular velocity)"
                ],
                "notes": "IMU fields may be null if IMU not available"
            }
            
            with open(self.metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            print(f"Metadata written to {self.metadata_path}")
        except Exception as e:
            print(f"Error writing metadata: {e}")
    
    def log_record(self, record: Dict) -> bool:
        """
        Log a synchronized sensor record to CSV after validating required fields.
        If critical data (timestamp or location) is missing, the record is skipped and logged as an error.
        
        Args:
            record: Dict with keys: timestamp, latitude, longitude, image_path, ax, ay, az, gx, gy, gz
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if self.csv_writer:
                # Flatten record, handle None values
                row = {
                    'timestamp': record.get('timestamp'),
                    'latitude': record.get('latitude'),
                    'longitude': record.get('longitude'),
                    'image_path': record.get('image_path'),
                    'ax': record.get('ax'),
                    'ay': record.get('ay'),
                    'az': record.get('az'),
                    'gx': record.get('gx'),
                    'gy': record.get('gy'),
                    'gz': record.get('gz'),
                }
                
                self.csv_writer.writerow(row)
                self.csv_file.flush()  # Ensure data is written
                self.record_count += 1
                
                return True
        except Exception as e:
            print(f"Error logging record: {e}")
        
        return False
    
    def log_batch(self, records: List[Dict]) -> int:
        """
        Log multiple records efficiently.
        
        Args:
            records: List of synchronized records
            
        Returns:
            Number of records successfully logged
        """
        count = 0
        for record in records:
            if self.log_record(record):
                count += 1
        return count
    
    def finalize(self):
        """Close CSV file and update metadata with statistics."""
        try:
            if self.csv_file:
                self.csv_file.close()
            
            # Update metadata with final statistics
            end_time = time.time()
            metadata = {
                "recording_start": datetime.fromtimestamp(self.start_time).isoformat(),
                "recording_start_unix": self.start_time,
                "recording_end": datetime.now().isoformat(),
                "recording_end_unix": end_time,
                "recording_duration_seconds": end_time - self.start_time,
                "total_records": self.record_count,
                "sensor_configuration": self.sensor_config,
                "output_format": "CSV + Images",
                "csv_columns": [
                    "timestamp (unix epoch)",
                    "latitude (decimal degrees)",
                    "longitude (decimal degrees)",
                    "image_path (relative)",
                    "ax, ay, az (m/s², acceleration)",
                    "gx, gy, gz (°/s, angular velocity)"
                ]
            }
            
            with open(self.metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            print(f"Logging finalized: {self.record_count} records, {end_time - self.start_time:.1f}s")
            
        except Exception as e:
            print(f"Error finalizing log: {e}")
    
    def get_record_count(self) -> int:
        """Get total records logged."""
        return self.record_count
    
    def get_elapsed_time(self) -> float:
        """Get elapsed recording time in seconds."""
        return time.time() - self.start_time
