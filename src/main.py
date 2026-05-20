"""Main data acquisition orchestrator."""

import argparse
import signal
import sys
import time
from pathlib import Path

from src.sensors.camera import CameraDriver
from src.sensors.gps import GPSDriver
from src.sensors.imu import IMUDriver
from src.core.sync import TimestampSynchronizer
from src.core.logger import DataLogger
from src.core.config import SystemConfig, CameraConfig, GPSConfig, IMUConfig, SyncConfig


class DataAcquisitionSystem:
    """Main orchestrator for multi-sensor data acquisition."""
    
    def __init__(self, config: SystemConfig, output_dir: Path):
        """
        Initialize acquisition system.
        
        Args:
            config: System configuration
            output_dir: Base output directory for dataset
        """
        self.config = config
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.camera = None
        self.gps = None
        self.imu = None
        self.sync = TimestampSynchronizer(
            reference_source=config.sync.reference_source,
            max_drift_ms=config.sync.max_drift_ms
        )
        self.logger = DataLogger(self.output_dir, config.to_dict())
        
        self.is_running = False
        self.acquisition_start = None
    
    def initialize(self, mock_camera: bool = True, mock_gps: bool = True) -> bool:
        """Initialize sensor drivers. IMU is still mock; camera and GPS are configurable."""
        try:
            self.camera = CameraDriver(
                device_id=self.config.camera.device_id,
                resolution=(
                    self.config.camera.resolution_width,
                    self.config.camera.resolution_height,
                ),
                fps=self.config.camera.fps,
                codec=self.config.camera.codec,
                use_mock=mock_camera,
            )
            if not self.camera.start():
                print(f"Failed to start camera ({'mock' if mock_camera else 'real'})")
                return False

            self.gps = GPSDriver(
                port=self.config.gps.port,
                baudrate=self.config.gps.baudrate,
                use_mock=mock_gps,
            )
            if not self.gps.start():
                print(f"Failed to start GPS ({'mock' if mock_gps else 'real'}) (continuing without GPS)")
                self.gps = None

            if self.config.imu.enabled:
                self.imu = IMUDriver()
                if not self.imu.start():
                    print("Failed to start mock IMU (continuing without IMU)")
                    self.imu = None

            cam_mode = "MOCK" if mock_camera else "REAL"
            gps_mode = "MOCK" if mock_gps else "REAL"
            print(f"System initialized successfully ({cam_mode} camera, {gps_mode} GPS, mock IMU).")
            return True
        except Exception as e:
            print(f"Error during system initialization: {e}")
            self.camera = None
            self.gps = None
            self.imu = None
            return False

    def initialize_mock(self) -> bool:
        """Backwards-compatible entry point — all sensors mocked."""
        return self.initialize(mock_camera=True, mock_gps=True)
    
    def start(self):
        """Start data acquisition loop."""
        self.is_running = True
        self.acquisition_start = time.time()
        
        print("Data acquisition started")
        print(f"Output directory: {self.output_dir}")
        
        duration = getattr(self, '_duration', 0)

        try:
            while self.is_running:
                if duration > 0 and (time.time() - self.acquisition_start) >= duration:
                    print(f"\nDuration limit ({duration}s) reached.")
                    break

                # Get camera frame
                frame_data = self.camera.get_frame()
                if not frame_data:
                    time.sleep(0.01)
                    continue
                
                timestamp, frame = frame_data
                
                # Save frame to disk
                image_path = self.camera.save_frame(frame, timestamp, self.output_dir / "images")
                if not image_path:
                    continue
                
                # Get GPS data
                gps_data = None
                if self.gps:
                    gps_data = self.gps.get_data() # Use get_data for mock consistency
                    if gps_data:
                        self.sync.add_gps_data(gps_data)
                
                # Get IMU data
                imu_data = None
                if self.imu:
                    imu_data = self.imu.get_measurement()
                    if imu_data:
                        self.sync.add_imu_measurement(imu_data)
                
                # Synchronize and log
                camera_record = {
                    "timestamp": timestamp,
                    "image_path": str(self.output_dir / "images" / image_path)
                }
                self.sync.add_camera_frame(timestamp, camera_record)
                
                # Create synchronized record
                sync_record = self.sync.synchronize_frame(camera_record)
                
                # Log to CSV
                self.logger.log_record(sync_record)
                
                # Progress indication every 100 frames
                if self.camera.get_frame_count() % 100 == 0:
                    elapsed = self.logger.get_elapsed_time()
                    print(f"[{elapsed:.1f}s] Frames: {self.camera.get_frame_count()}, "
                          f"Records: {self.logger.get_record_count()}")
                
        except KeyboardInterrupt:
            print("\nAcquisition interrupted by user")
        except Exception as e:
            print(f"Error during acquisition: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """Stop all sensors and finalize logging."""
        self.is_running = False
        
        print("\nStopping sensors...")
        
        if self.camera:
            self.camera.stop()
        if self.gps:
            self.gps.stop()
        if self.imu:
            self.imu.stop()
        
        self.logger.finalize()
        
        elapsed = self.logger.get_elapsed_time()
        print(f"\nAcquisition complete:")
        print(f"  Duration: {elapsed:.1f}s")
        print(f"  Frames: {self.camera.get_frame_count() if self.camera else 0}")
        print(f"  Records: {self.logger.get_record_count()}")
        print(f"  Output: {self.output_dir}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Mobile Multi-Sensor Data Logging System"
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default="./data/run_001",
        help="Output directory for dataset"
    )
    parser.add_argument(
        "--duration", "-d",
        type=int,
        default=0,
        help="Recording duration in seconds (0=infinite)"
    )
    parser.add_argument(
        "--camera-id", "-c",
        type=int,
        default=0,
        help="USB camera device ID"
    )
    parser.add_argument(
        "--gps-port", "-g",
        type=str,
        default="/dev/ttyUSB0",
        help="GPS serial port"
    )
    parser.add_argument(
        "--enable-imu",
        action="store_true",
        help="Enable IMU acquisition"
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="Camera frames per second"
    )
    parser.add_argument(
        "--real-camera",
        action="store_true",
        help="Capture from a real USB camera via OpenCV (default: mock frames)"
    )
    parser.add_argument(
        "--real-gps",
        action="store_true",
        help="Read from a real NMEA GPS over serial via pyserial (default: mock data)"
    )
    
    args = parser.parse_args()
    
    # Create system configuration
    config = SystemConfig(
        camera=CameraConfig(device_id=args.camera_id, fps=args.fps),
        gps=GPSConfig(port=args.gps_port),
        imu=IMUConfig(enabled=args.enable_imu),
        sync=SyncConfig()
    )
    
    # Create and run system
    system = DataAcquisitionSystem(config, args.output_dir)
    system._duration = args.duration

    # Handle graceful shutdown
    def signal_handler(sig, frame):
        system.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    if system.initialize(mock_camera=not args.real_camera, mock_gps=not args.real_gps):
        system.start()
    else:
        print("Failed to initialize system")
        sys.exit(1)


if __name__ == "__main__":
    main()
