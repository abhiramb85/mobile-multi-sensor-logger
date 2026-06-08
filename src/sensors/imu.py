import math
import random
import threading
import time
from typing import Optional, Dict

from src.sensors.base_sensor import SensorDriver

# Lazy-imported in start() so mock-only environments don't need Blinka/BNO08x libs.
board = None
busio = None
BNO08X_I2C = None
BNO_REPORT_ACCELEROMETER = None
BNO_REPORT_GYROSCOPE = None

_RAD_TO_DEG = 180.0 / math.pi


class IMUDriver(SensorDriver):
    """Bosch BNO085 9-DOF IMU driver — I2C via Adafruit Blinka, with mock fallback."""

    def __init__(
        self,
        i2c_address: int = 0x4A,
        sample_rate_hz: int = 100,
        use_mock: bool = True,
    ):
        super().__init__()
        self.i2c_address = i2c_address
        self.sample_rate_hz = max(1, sample_rate_hz)
        self.use_mock = use_mock

        self._sensor = None
        self._thread = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._latest_measurement: Optional[Dict] = None
        self.sample_count = 0

    def start(self) -> bool:
        if self.use_mock:
            self._is_running = True
            print("IMUDriver started (mock mode).")
            return True

        global board, busio, BNO08X_I2C, BNO_REPORT_ACCELEROMETER, BNO_REPORT_GYROSCOPE
        if BNO08X_I2C is None:
            try:
                import board as _board
                import busio as _busio
                from adafruit_bno08x.i2c import BNO08X_I2C as _BNO08X_I2C
                from adafruit_bno08x import (
                    BNO_REPORT_ACCELEROMETER as _ACCEL,
                    BNO_REPORT_GYROSCOPE as _GYRO,
                )
            except ImportError as e:
                print(f"IMUDriver: missing BNO085 deps ({e}). "
                      f"Install: pip install adafruit-circuitpython-bno08x adafruit-blinka")
                return False
            board, busio = _board, _busio
            BNO08X_I2C = _BNO08X_I2C
            BNO_REPORT_ACCELEROMETER = _ACCEL
            BNO_REPORT_GYROSCOPE = _GYRO

        try:
            i2c = busio.I2C(board.SCL, board.SDA, frequency=400_000)
            self._sensor = BNO08X_I2C(i2c, address=self.i2c_address)
            self._sensor.enable_feature(BNO_REPORT_ACCELEROMETER)
            self._sensor.enable_feature(BNO_REPORT_GYROSCOPE)
            time.sleep(0.2)  # SH-2 needs a moment before the first reports stream
        except Exception as e:
            print(f"IMUDriver: failed to init BNO085 at 0x{self.i2c_address:02X}: {e}")
            return False

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._sample_loop, name="imu-sampler", daemon=True
        )
        self._thread.start()
        self._is_running = True
        print(f"IMUDriver opened BNO085 at 0x{self.i2c_address:02X} "
              f"@ {self.sample_rate_hz} Hz (SH-2 protocol, 400 kHz I2C).")
        return True

    def stop(self):
        self._is_running = False
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._sensor = None
        print("IMUDriver stopped.")

    def get_data(self) -> Optional[Dict]:
        return self.get_measurement()

    def get_measurement(self) -> Optional[Dict]:
        if not self._is_running:
            return None
        if self.use_mock:
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
            return data
        with self._lock:
            return dict(self._latest_measurement) if self._latest_measurement else None

    def get_sample_count(self) -> int:
        return self.sample_count

    def _sample_loop(self):
        period = 1.0 / self.sample_rate_hz
        while not self._stop_event.is_set():
            t_start = time.time()
            sample = self._read_sensor(t_start)
            if sample is not None:
                with self._lock:
                    self._latest_measurement = sample
                    self.sample_count += 1
            elapsed = time.time() - t_start
            sleep_for = period - elapsed
            if sleep_for > 0:
                self._stop_event.wait(sleep_for)

    def _read_sensor(self, timestamp: float) -> Optional[Dict]:
        try:
            accel = self._sensor.acceleration   # (ax, ay, az) m/s^2
            gyro = self._sensor.gyro            # (gx, gy, gz) rad/s
        except Exception:
            # BNO085 SH-2 reports can occasionally fail; main loop sees a stale value.
            return None
        if accel is None or gyro is None:
            return None
        if any(v is None for v in tuple(accel) + tuple(gyro)):
            return None
        ax, ay, az = accel
        gx, gy, gz = gyro
        return {
            "timestamp": timestamp,
            "ax": float(ax), "ay": float(ay), "az": float(az),
            # Convert rad/s -> deg/s so the schema stays human-friendly and consistent
            # with mock-mode magnitudes.
            "gx": float(gx) * _RAD_TO_DEG,
            "gy": float(gy) * _RAD_TO_DEG,
            "gz": float(gz) * _RAD_TO_DEG,
        }
