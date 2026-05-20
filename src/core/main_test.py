import time
from typing import List, Dict
from src.sensors.camera import CameraDriver
from src.sensors.gps import GPSDriver
from src.sensors.imu import IMUDriver
from src.core.sync import TimestampSynchronizer
from src.core.logger import DataLogger

def run_mock_simulation(duration_seconds: float = 5):
    """
    Simulates the full data logging cycle using mock sensor drivers.
    This function addresses Task 2 (Updating core logic for testing).
    """
    print("--- Starting Multi-Sensor Mock Simulation ---")

    # 1. Initialize Mock Sensors (Task 1 is complete)
    camera = CameraDriver()
    gps = GPSDriver()
    imu = IMUDriver()

    if not all([camera.start(), gps.start(), imu.start()]):
        print("Failed to start one or more mock sensors. Exiting simulation.")
        return

    # 2. Initialize Synchronizer and Logger
    synchronizer = TimestampSynchronizer(reference_source="gps")
    logger = DataLogger(output_dir="./data", sensor_config={
        "camera": {"resolution": (1280, 720), "fps": 30},
        "gps": {"port": "/dev/ttyUSB0", "baudrate": 9600},
        "imu": {"sensor_type": "MPU6050"}
    })

    start_time = time.time()
    end_time = start_time + duration_seconds
    frame_count = 0
    log_records: List[Dict] = []

    try:
        while time.time() < end_time and camera.is_running():
            # --- Data Acquisition Cycle (Simulated Loop) ---
            
            # Get latest data from all sensors
            camera_data = camera.get_frame()
            gps_data = gps.get_position()
            imu_data = imu.get_measurement()

            if not camera_data and not gps_data and not imu_data:
                time.sleep(0.1)
                continue

            # 3. Synchronization (Task 2 implementation)
            sync_record = None
            if camera_data:
                # Use the camera timestamp as the primary reference for synchronization attempt
                camera_ts = camera_data[0] # Assuming get_frame returns a tuple/list where index 0 is timestamp
                
                # Update synchronizer buffers with latest data points
                synchronizer.add_gps_data(gps_data)
                synchronizer.add_imu_measurement(imu_data)
                synchronizer.add_camera_frame(camera_ts, {"image_path": f"mock/img_{camera.get_frame_count()}.jpg"})

                # Synchronize and get the aligned record
                sync_record = synchronizer.synchronize_frame(camera_data)
            else:
                print("Waiting for camera frame to start synchronization.")
                time.sleep(0.1)
                continue


            if sync_record:
                # 4. Logging (Task 2/4 integration)
                log_records.append(sync_record)
                logger.log_record(sync_record)
                frame_count += 1

            time.sleep(0.05) # Simulate processing time between frames

    except KeyboardInterrupt:
        print("\nSimulation interrupted by user.")
    finally:
        # Cleanup
        camera.stop()
        gps.stop()
        imu.stop()
        logger.finalize()
        print("--- Simulation Finished ---")


if __name__ == "__main__":
    # Run the simulation for 10 seconds to generate data
    run_mock_simulation(duration_seconds=10)