"""Configuration schemas for sensor and system settings."""

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class CameraConfig:
    """Camera hardware configuration."""
    device_id: int = 0
    resolution_width: int = 1280
    resolution_height: int = 720
    fps: int = 30
    codec: str = "MJPEG"


@dataclass
class GPSConfig:
    """GPS module configuration."""
    port: str = "/dev/ttyACM0"
    baudrate: int = 9600
    type: str = "NMEA"


@dataclass
class IMUConfig:
    """IMU sensor configuration."""
    enabled: bool = False
    sensor_type: str = "BNO085"
    i2c_bus: int = 1
    i2c_address: int = 0x4A
    sample_rate_hz: int = 100


@dataclass
class SyncConfig:
    """Synchronization settings."""
    reference_source: str = "gps"
    max_drift_ms: float = 100.0
    interpolation_method: str = "nearest_neighbor"


@dataclass
class SystemConfig:
    """Overall system configuration."""
    camera: CameraConfig = None
    gps: GPSConfig = None
    imu: IMUConfig = None
    sync: SyncConfig = None
    
    def __post_init__(self):
        """Initialize defaults and validate required components."""
        # Initialize all sub-configs if they are None
        if self.camera is None:
            self.camera = CameraConfig()
        if self.gps is None:
            self.gps = GPSConfig()
        if self.imu is None:
            self.imu = IMUConfig()
        if self.sync is None:
            self.sync = SyncConfig()

        # Basic validation check (Example: Ensure required fields are set)
        if self.camera.resolution_width <= 0 or self.camera.resolution_height <= 0:
             raise ValueError("Camera resolution must be positive.")
    
    def to_dict(self):
        """Convert to dictionary (for JSON serialization)."""
        return asdict(self)
