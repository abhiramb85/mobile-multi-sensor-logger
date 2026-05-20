import time
import random
from typing import Optional, Dict

from src.sensors.base_sensor import SensorDriver


class IMUDriver(SensorDriver):
    """Mock IMU driver — simulates 6-DOF accelerometer + gyroscope data."""

    def __init__(self):
        super().__init__()
        self.sample_count = 0

    def start(self) -> bool:
        self._is_running = True
        print("Mock IMUDriver started.")
        return True

    def stop(self):
        self._is_running = False
        print("Mock IMUDriver stopped.")

    def get_data(self) -> Optional[Dict]:
        if not self._is_running:
            return None
        timestamp = time.time()
        data = {
            "timestamp": timestamp,
            "ax": 0.1 + random.uniform(-0.5, 0.5),
            "ay": 0.2 + random.uniform(-0.5, 0.5),
            "az": 9.81 + random.uniform(-0.5, 0.5),
            "gx": random.uniform(-10, 10),
            "gy": random.uniform(-10, 10),
            "gz": random.uniform(-10, 10),
        }
        self.sample_count += 1
        try:
            self.data_queue.put_nowait(data)
        except Exception:
            pass
        return data

    def get_measurement(self) -> Optional[Dict]:
        """Alias for get_data() — kept for compatibility with main.py."""
        return self.get_data()
