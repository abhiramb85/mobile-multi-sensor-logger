import random
import threading
import time
from typing import Optional, Dict

from src.sensors.base_sensor import SensorDriver

serial = None  # Lazy-imported in start() so mock-only environments don't need pyserial.


def _nmea_to_decimal(value: str, hemisphere: str) -> Optional[float]:
    """Convert NMEA ddmm.mmmm / dddmm.mmmm + N/S/E/W to signed decimal degrees."""
    if not value or not hemisphere:
        return None
    try:
        dot = value.index(".")
    except ValueError:
        return None
    deg_digits = dot - 2
    if deg_digits < 1:
        return None
    try:
        degrees = int(value[:deg_digits])
        minutes = float(value[deg_digits:])
    except ValueError:
        return None
    decimal = degrees + minutes / 60.0
    if hemisphere in ("S", "W"):
        decimal = -decimal
    return decimal


def _verify_checksum(sentence: str) -> bool:
    """Validate the trailing *XX NMEA checksum."""
    if "*" not in sentence:
        return False
    body, _, csum = sentence.partition("*")
    if body.startswith("$"):
        body = body[1:]
    try:
        expected = int(csum[:2], 16)
    except ValueError:
        return False
    actual = 0
    for ch in body:
        actual ^= ord(ch)
    return actual == expected


class GPSDriver(SensorDriver):
    """u-blox / NMEA-0183 GPS driver — pyserial-based, with mock fallback."""

    def __init__(
        self,
        port: str = "/dev/ttyACM0",
        baudrate: int = 9600,
        read_timeout: float = 1.0,
        use_mock: bool = True,
    ):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.read_timeout = read_timeout
        self.use_mock = use_mock

        self._serial = None
        self._thread = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._latest_fix: Optional[Dict] = None
        self.fix_count = 0

    def start(self) -> bool:
        if self.use_mock:
            self._is_running = True
            print("GPSDriver started (mock mode).")
            return True

        global serial
        if serial is None:
            import serial as _serial
            serial = _serial

        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.read_timeout,
            )
        except Exception as e:
            print(f"GPSDriver: failed to open {self.port}: {e}")
            return False

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._read_loop, name="gps-reader", daemon=True)
        self._thread.start()
        self._is_running = True
        print(f"GPSDriver opened {self.port} @ {self.baudrate} baud (waiting for first fix)...")
        return True

    def stop(self):
        self._is_running = False
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None
        print("GPSDriver stopped.")

    def get_data(self) -> Optional[Dict]:
        if not self._is_running:
            return None
        if self.use_mock:
            timestamp = time.time()
            lat = 34.0522 + random.uniform(-0.01, 0.01)
            lon = -118.2437 + random.uniform(-0.01, 0.01)
            self.fix_count += 1
            return {"timestamp": timestamp, "latitude": lat, "longitude": lon}
        with self._lock:
            return dict(self._latest_fix) if self._latest_fix else None

    def get_fix_count(self) -> int:
        return self.fix_count

    def _read_loop(self):
        buf = b""
        while not self._stop_event.is_set():
            try:
                chunk = self._serial.read(256)
            except Exception as e:
                print(f"GPSDriver: read error: {e}")
                break
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                line, _, buf = buf.partition(b"\n")
                self._process_line(line.decode("ascii", errors="ignore").strip())

    def _process_line(self, line: str):
        if not line.startswith("$") or "*" not in line:
            return
        if not _verify_checksum(line):
            return
        body = line[1:line.index("*")]
        fields = body.split(",")
        if len(fields) < 2:
            return
        # Accept any talker ID (GP, GN, GL, GA, BD, GB, QZ, ...).
        msg = fields[0][-3:]
        if msg == "RMC":
            self._handle_rmc(fields)
        elif msg == "GGA":
            self._handle_gga(fields)

    def _handle_rmc(self, fields):
        # $..RMC,time,status,lat,N/S,lon,E/W,sog,cog,date,...
        if len(fields) < 7 or fields[2] != "A":
            return
        lat = _nmea_to_decimal(fields[3], fields[4])
        lon = _nmea_to_decimal(fields[5], fields[6])
        if lat is None or lon is None:
            return
        self._update_fix(lat, lon)

    def _handle_gga(self, fields):
        # $..GGA,time,lat,N/S,lon,E/W,fix_quality,nsats,hdop,alt,M,...
        if len(fields) < 7:
            return
        try:
            quality = int(fields[6]) if fields[6] else 0
        except ValueError:
            quality = 0
        if quality == 0:
            return
        lat = _nmea_to_decimal(fields[2], fields[3])
        lon = _nmea_to_decimal(fields[4], fields[5])
        if lat is None or lon is None:
            return
        self._update_fix(lat, lon)

    def _update_fix(self, lat: float, lon: float):
        data = {"timestamp": time.time(), "latitude": lat, "longitude": lon}
        with self._lock:
            self._latest_fix = data
            self.fix_count += 1
