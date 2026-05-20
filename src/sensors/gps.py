import time
import random
from typing import Optional, Dict

from src.sensors.base_sensor import SensorDriver


class GPSDriver(SensorDriver):
    """Mock GPS driver — simulates movement around a fixed location."""

    def __init__(self):
        super().__init__()
        self.fix_count = 0

    def start(self) -> bool:
        self._is_running = True
        print("Mock GPSDriver started.")
        return True

    def stop(self):
        self._is_running = False
        print("Mock GPSDriver stopped.")

    def get_data(self) -> Optional[Dict]:
        if not self._is_running:
            return None
        timestamp = time.time()
        lat = 34.0522 + random.uniform(-0.01, 0.01)
        lon = -118.2437 + random.uniform(-0.01, 0.01)
        data = {"timestamp": timestamp, "latitude": lat, "longitude": lon}
        self.fix_count += 1
        try:
            self.data_queue.put_nowait(data)
        except Exception:
            pass
        return data

    def get_fix_count(self) -> int:
        return self.fix_count
