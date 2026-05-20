"""Timestamp synchronization engine for multi-sensor alignment."""

import time
from typing import Dict, Optional, List
from collections import deque
from src.sensors.base_sensor import SensorDriver
from src.sensors.base_sensor import SensorDriver
from src.sensors.camera import CameraDriver
from src.sensors.gps import GPSDriver
from src.sensors.imu import IMUDriver


class TimestampSynchronizer:
    """
    Aligns timestamps across multiple asynchronous sensor streams.
    
    Strategy: GPS as reference clock, nearest-neighbor interpolation for camera and IMU.
    Detects hardware clock offsets and maintains sync statistics.
    """
    
    def __init__(self, reference_source: str = "gps", max_drift_ms: float = 100.0):
        """
        Initialize synchronizer.
        
        Args:
            reference_source: Primary time source (gps, camera, imu)
            max_drift_ms: Maximum acceptable timestamp drift in milliseconds
        """
        self.reference_source = reference_source
        self.max_drift_ms = max_drift_ms
        
        # Clock offset tracking (source -> estimated offset in seconds)
        self.clock_offsets = {}
        
        # Sensor data buffers (source -> deque of timestamped data)
        self.buffers = {
            "camera": deque(maxlen=300),
            "gps": deque(maxlen=100),
            "imu": deque(maxlen=1000)
        }
        
        # Statistics
        self.sync_events = []
        
    def add_gps_data(self, gps_data: Optional[Dict]):
        """Add GPS position data with timestamp."""
        if gps_data and isinstance(gps_data, dict) and "timestamp" in gps_data:
            self.buffers["gps"].append(gps_data)

    def add_camera_frame(self, timestamp: float, frame_data: Dict):
        """Add camera frame metadata with timestamp."""
        # Ensure the structure is consistent for synchronization
        self.buffers["camera"].append({
            "timestamp": timestamp,
            **frame_data
        })

    def add_imu_measurement(self, imu_data: Optional[Dict]):
        """Add IMU measurement with timestamp."""
        if imu_data and isinstance(imu_data, dict) and "timestamp" in imu_data:
            self.buffers["imu"].append(imu_data)
    
    def estimate_clock_offset(self, source: str, reference_samples: int = 10) -> Optional[float]:
        """
        Estimate clock offset between source and reference.
        
        Args:
            source: Sensor source to calibrate
            reference_samples: Number of samples to use for estimation
            
        Returns:
            Estimated offset in seconds or None if insufficient data
        """
        if source == self.reference_source:
            return 0.0
        
        buffer = self.buffers[source]
        if len(buffer) < reference_samples:
            return None
        
        # Compute offset between source and reference (GPS) timestamps
        # If source timestamp is ahead of reference, offset is positive
        if not self.buffers[self.reference_source]:
            return None
        
        offsets = []
        source_samples = list(buffer)[-reference_samples:]
        reference_samples_list = list(self.buffers[self.reference_source])[-reference_samples:]
        
        # Compare paired samples
        for src_sample in source_samples:
            src_ts = src_sample.get("timestamp", 0)
            # Find nearest reference sample
            best_ref_ts = None
            best_distance = float('inf')
            for ref_sample in reference_samples_list:
                ref_ts = ref_sample.get("timestamp", 0)
                distance = abs(src_ts - ref_ts)
                if distance < best_distance:
                    best_distance = distance
                    best_ref_ts = ref_ts
            
            if best_ref_ts is not None:
                offsets.append(src_ts - best_ref_ts)
        
        mean_offset = sum(offsets) / len(offsets) if offsets else 0.0
        self.clock_offsets[source] = mean_offset
        
        return mean_offset
    
    def synchronize_frame(self, camera_data: Dict) -> Dict:
        """
        Synchronize camera frame with GPS and optional IMU.
        
        Returns:
            Synchronized record: {timestamp, lat, lon, image_path, ax, ay, az, gx, gy, gz}
        """
        camera_ts = camera_data.get("timestamp")
        
        # Find nearest GPS fix
        gps_match = self._nearest_neighbor_match(
            camera_ts, 
            self.buffers["gps"], 
            max_distance_s=1.0
        )
        
        # Find nearest IMU measurement(s) if available
        imu_match = self._nearest_neighbor_match(
            camera_ts,
            self.buffers["imu"],
            max_distance_s=0.1
        )
        
        # Build synchronized record
        record = {
            "timestamp": camera_ts,
            "latitude": gps_match.get("latitude") if gps_match else None,
            "longitude": gps_match.get("longitude") if gps_match else None,
            "image_path": camera_data.get("image_path"),
            "ax": imu_match.get("ax") if imu_match else None,
            "ay": imu_match.get("ay") if imu_match else None,
            "az": imu_match.get("az") if imu_match else None,
            "gx": imu_match.get("gx") if imu_match else None,
            "gy": imu_match.get("gy") if imu_match else None,
            "gz": imu_match.get("gz") if imu_match else None,
        }
        
        return record
    
    def _nearest_neighbor_match(self, target_ts: float, buffer: deque, 
                               max_distance_s: float = 1.0) -> Optional[Dict]:
        """Find buffer item with timestamp nearest to target."""
        if not buffer:
            return None
        
        best_item = None
        best_distance = float('inf')
        
        for item in buffer:
            distance = abs(item.get("timestamp", 0) - target_ts)
            if distance < best_distance and distance <= max_distance_s:
                best_distance = distance
                best_item = item
        
        return best_item
    
    def detect_drift(self) -> Dict:
        """Detect and report timestamp drift across sensors."""
        drift_report = {}
        
        for source, buffer in self.buffers.items():
            if len(buffer) < 2:
                continue
            
            items = list(buffer)
            first_ts = items[0].get("timestamp")
            last_ts = items[-1].get("timestamp")
            
            if first_ts and last_ts:
                observed_duration = last_ts - first_ts
                expected_count = len(buffer)
                expected_duration = expected_count / 30.0 if source == "camera" else expected_count / 1.0
                
                drift_ms = abs(observed_duration - expected_duration) * 1000
                drift_report[source] = drift_ms
        
        return drift_report
    
    def get_statistics(self) -> Dict:
        """Get synchronization statistics."""
        return {
            "clock_offsets": self.clock_offsets.copy(),
            "buffer_sizes": {s: len(b) for s, b in self.buffers.items()},
            "drift_detection": self.detect_drift()
        }
