import pytest
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Import mock drivers and core components
from src.sensors.camera import CameraDriver
from src.sensors.gps import GPSDriver
from src.sensors.imu import IMUDriver
from src.core.sync import TimestampSynchronizer
from src.core.logger import DataLogger


@pytest.fixture(scope="module")
def mock_sensors():
    """Fixture to provide initialized and started mock sensor drivers."""
    camera = CameraDriver()
    gps = GPSDriver()
    imu = IMUDriver()

    # Start all mocks
    camera.start()
    gps.start()
    imu.start()

    yield camera, gps, imu

    # Teardown: Stop all mocks after tests run
    camera.stop()
    gps.stop()
    imu.stop()


def test_full_logging_cycle(mock_sensors):
    """
    Tests the entire data pipeline: Acquisition -> Synchronization -> Logging.
    This simulates a full logging cycle using mock sensors.
    """
    camera, gps, imu = mock_sensors

    # 1. Setup Synchronizer and Logger
    synchronizer = TimestampSynchronizer(reference_source="gps")
    logger = DataLogger(output_dir=Path("./data/test_logs")) # Use a dedicated test directory

    try:
        # Simulate data acquisition for a short period (e.g., 2 seconds)
        SIMULATION_DURATION = 2.0
        start_time = time.time()
        end_time = start_time + SIMULATION_DURATION
        frame_count = 0

        while time.time() < end_time:
            # --- Data Acquisition Cycle ---
            camera_data = camera.get_frame()
            gps_data = gps.get_position()
            imu_data = imu.get_measurement()

            if not camera_data and not gps_data and not imu_data:
                time.sleep(0.1)
                continue

            # 2. Synchronization (Core Logic Test)
            sync_record = None
            if camera_data:
                camera_ts = camera_data[0] # Assuming get_frame returns a tuple/list where index 0 is timestamp
                
                # Update synchronizer buffers with latest data points
                synchronizer.add_gps_data(gps_data)
                synchronizer.add_imu_measurement(imu_data)
                synchronizer.add_camera_frame(camera_ts, {"image_path": f"mock/img_{camera.get_frame_count()}.jpg"})

                # Synchronize and get the aligned record
                sync_record = synchronizer.synchronize_frame(camera_data)

            if sync_record:
                # 3. Logging (Logger Test)
                logger.log_record(sync_record)
                frame_count += 1
            
            time.sleep(0.05) # Simulate processing time

        # Finalize logging and check statistics
        assert logger.get_record_count() > 0, "Expected at least one record to be logged."
        logger.finalize()

    finally:
        # Cleanup is handled by the fixture teardown
        pass

def test_synchronizer_drift_detection(mock_sensors):
    """Tests if the synchronizer can detect significant time drift."""
    camera, gps, imu = mock_sensors
    synchronizer = TimestampSynchronizer(reference_source="gps")

    # 1. Populate buffers with data that has a known offset (e.g., IMU is running fast)
    print("Populating buffers for drift test...")
    for _ in range(50):
        camera_ts = time.time() - 0.1 # Simulate camera being slightly delayed relative to GPS
        synchronizer.add_gps_data(gps.get_position())
        synchronizer.add_imu_measurement(imu.get_measurement())
        synchronizer.add_camera_frame(camera_ts, {"image_path": "mock"})

    # 2. Check for drift detection
    drift = synchronizer.detect_drift()
    assert 'imu' in drift, "IMU drift should be detectable."
    print(f"Detected IMU Drift: {drift['imu']:.2f} ms")


def test_logger_data_validation():
    """Tests the logger's ability to handle missing or invalid data."""
    # Setup a mock logger instance without actual file writing for testing purposes
    mock_logger = DataLogger(output_dir=Path("./data/test_logs"))

    # Test 1: Missing GPS data (should log None)
    record_no_gps = {
        "timestamp": time.time(), "latitude": None, "longitude": None, 
        "image_path": "mock", "ax": 1.0, "ay": 2.0, "az": 9.81, "gx": 0.0, "gy": 0.0, "gz": 0.0
    }
    assert mock_logger.log_record(record_no_gps) == True

    # Test 2: Missing IMU data (should log None)
    record_no_imu = {
        "timestamp": time.time(), "latitude": 34.0, "longitude": -118.0, 
        "image_path": "mock", "ax": None, "ay": None, "az": None, "gx": None, "gy": None, "gz": None
    }
    assert mock_logger.log_record(record_no_imu) == True

    # Finalize to ensure cleanup logic runs
    mock_logger.finalize()