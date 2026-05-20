import time
from typing import Optional, Dict, Any
from queue import Queue
import random

class MockSensorBase:
    """Abstract base class for mocking sensor behavior."""
    def __init__(self):
        self.is_running = False
        self.data_queue = Queue(maxsize=10)
        self.sample_count = 0

    def start(self) -> bool:
        """Starts the mock data generation loop."""
        print(f"Mock sensor started.")
        self.is_running = True
        # In a real scenario, this would start a thread. For mocks, we simulate data on demand or in a simple loop.
        return True

    def stop(self):
        """Stops the mock data generation."""
        print("Mock sensor stopped.")
        self.is_running = False

    def get_data(self) -> Optional[Dict]:
        """Retrieves simulated data from the queue."""
        try:
            return self.data_queue.get_nowait()
        except Exception:
            return None

class MockCameraDriver(MockSensorBase):
    """Mocks camera frame capture."""
    def __init__(self, mock_resolution: tuple = (1280, 720)):
        super().__init__()
        self.mock_resolution = mock_resolution
        self.frame_count = 0

    def start(self) -> bool:
        """Starts the mock data generation loop."""
        super().start()
        print("Mock CameraDriver started.")
        return True

    def get_frame(self) -> Optional[tuple]:
        """Returns a simulated (timestamp, frame) tuple. Frame is just a placeholder object/dict."""
        if not self.is_running:
            return None
        
        # Simulate data generation
        timestamp = time.time()
        mock_frame = {"width": self.mock_resolution[0], "height": self.mock_resolution[1], "data": f"MockFrame_{self.frame_count}"}
        self.frame_count += 1

        # Put data into the queue (simulating a captured frame)
        try:
            self.data_queue.put_nowait((timestamp, mock_frame))
        except Exception:
            pass # Queue full

        return self.get_data()

    def save_frame(self, frame, timestamp: float, output_dir: str) -> Optional[str]:
        """Mocks saving a frame."""
        print(f"Mock saving frame to {output_dir} at {timestamp}")
        return "mock_file.jpg"


class MockGPSDriver(MockSensorBase):
    """Mocks GPS position data acquisition."""
    def __init__(self):
        super().__init__()
        self.fix_count = 0

    def start(self) -> bool:
        """Starts the mock data generation loop."""
        super().start()
        print("Mock GPSDriver started.")
        return True

    def get_position(self) -> Optional[Dict]:
        """Returns a simulated position dictionary."""
        if not self.is_running:
            return None
        
        # Simulate slight movement around a central point (e.g., 34.0522, -118.2437)
        timestamp = time.time()
        lat = 34.0 + random.uniform(-0.01, 0.01)
        lon = -118.0 + random.uniform(-0.01, 0.01)

        data = {
            "timestamp": timestamp,
            "latitude": lat,
            "longitude": lon
        }
        self.fix_count += 1
        try:
            self.data_queue.put_nowait(data)
        except Exception:
            pass # Queue full

        return self.get_data()

    def get_last_fix(self) -> Optional[Dict]:
        """Returns the last simulated fix."""
        # For mocks, we just return a recent mock data point if available
        if self.data_queue.qsize() > 0:
            return self.get_data()
        return None


class MockIMUDriver(MockSensorBase):
    """Mocks IMU measurement acquisition."""
    def __init__(self):
        super().__init__()

    def start(self) -> bool:
        """Starts the mock data generation loop."""
        super().start()
        print("Mock IMUDriver started.")
        return True

    def get_measurement(self) -> Optional[Dict]:
        """Returns a simulated 6-DOF measurement dictionary."""
        if not self.is_running:
            return None
        
        # Simulate typical values (e.g., gravity pointing down, small random noise for rotation)
        timestamp = time.time()
        data = {
            "timestamp": timestamp,
            "ax": 0.1 + random.uniform(-0.5, 0.5),  # m/s²
            "ay": 0.2 + random.uniform(-0.5, 0.5),
            "az": 9.81 + random.uniform(-0.5, 0.5), # Gravity component
            "gx": random.uniform(-10, 10),  # °/s
            "gy": random.uniform(-10, 10),
            "gz": random.uniform(-10, 10)
        }
        self.sample_count += 1

        try:
            self.data_queue.put_nowait(data)
        except Exception:
            pass # Queue full
            
        return self.get_data()