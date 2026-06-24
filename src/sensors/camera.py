import time
from pathlib import Path
from typing import Optional, Dict, Tuple

from src.sensors.base_sensor import SensorDriver

cv2 = None  # Lazy-imported in start() so mock-only environments don't need OpenCV.


class CameraDriver(SensorDriver):
    """USB camera driver — captures frames via OpenCV, with a mock fallback."""

    def __init__(
        self,
        device_id: int = 0,
        resolution: Tuple[int, int] = (1280, 720),
        fps: int = 30,
        codec: str = "MJPEG",
        jpeg_quality: int = 90,
        use_mock: bool = True,
        autofocus: Optional[bool] = None,
        focus: Optional[int] = None,
        sharpness: Optional[int] = None,
    ):
        super().__init__()
        self.device_id = device_id
        self.resolution = resolution
        self.fps = fps
        self.codec = codec
        self.jpeg_quality = int(jpeg_quality)
        self.use_mock = use_mock
        # V4L2 lens / image-quality knobs. None = don't override the camera's
        # current value; an int/bool = apply it after the cv2.VideoCapture open.
        self.autofocus = autofocus
        self.focus = focus
        self.sharpness = sharpness
        self.frame_count = 0
        self._cap = None  # cv2.VideoCapture, set in start()
        self._mock_period = 1.0 / max(1, int(fps))  # used to pace mock get_frame()
        self._last_mock_t = 0.0

    def start(self) -> bool:
        if self.use_mock:
            self._is_running = True
            print("CameraDriver started (mock mode).")
            return True

        global cv2
        if cv2 is None:
            import cv2 as _cv2
            cv2 = _cv2

        cap = cv2.VideoCapture(self.device_id)
        if not cap.isOpened():
            print(f"CameraDriver: failed to open device {self.device_id}")
            return False

        codec_str = (self.codec or "").upper().replace("MJPEG", "MJPG")
        if len(codec_str) >= 4:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*codec_str[:4]))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
        cap.set(cv2.CAP_PROP_FPS, self.fps)

        # Apply optional V4L2 lens / image controls. Order matters: turn
        # autofocus off *before* setting a manual focus value, otherwise the
        # camera ignores the focus write.
        if self.autofocus is not None:
            cap.set(cv2.CAP_PROP_AUTOFOCUS, 1 if self.autofocus else 0)
        if self.focus is not None:
            cap.set(cv2.CAP_PROP_FOCUS, int(self.focus))
        if self.sharpness is not None:
            cap.set(cv2.CAP_PROP_SHARPNESS, int(self.sharpness))

        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = cap.get(cv2.CAP_PROP_FPS)
        actual_af = int(cap.get(cv2.CAP_PROP_AUTOFOCUS))
        actual_focus = int(cap.get(cv2.CAP_PROP_FOCUS))
        actual_sharp = int(cap.get(cv2.CAP_PROP_SHARPNESS))
        print(
            f"CameraDriver opened device {self.device_id}: "
            f"{actual_w}x{actual_h} @ {actual_fps:.1f} fps "
            f"(requested {self.resolution[0]}x{self.resolution[1]} @ {self.fps}), "
            f"autofocus={actual_af}, focus={actual_focus}, sharpness={actual_sharp}"
        )

        self._cap = cap
        self._is_running = True
        return True

    def stop(self):
        self._is_running = False
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        print("CameraDriver stopped.")

    def get_data(self) -> Optional[Dict]:
        frame = self.get_frame()
        if frame is None:
            return None
        timestamp, payload = frame
        return {"timestamp": timestamp, **payload}

    def get_frame(self) -> Optional[Tuple[float, Dict]]:
        if not self._is_running:
            return None

        if self.use_mock:
            # Pace the mock at the configured FPS so partial-real recordings
            # (--real-gps without --real-camera, etc.) don't run the main loop
            # at full CPU speed and produce 100k placeholder files in a minute.
            now = time.time()
            wait = self._mock_period - (now - self._last_mock_t)
            if wait > 0:
                time.sleep(wait)
            timestamp = time.time()
            self._last_mock_t = timestamp
            self.frame_count += 1
            return (
                timestamp,
                {
                    "width": self.resolution[0],
                    "height": self.resolution[1],
                    "data": None,
                    "mock": True,
                },
            )

        ok, image = self._cap.read()
        if not ok or image is None:
            return None
        timestamp = time.time()
        self.frame_count += 1
        h, w = image.shape[:2]
        return (timestamp, {"width": w, "height": h, "data": image})

    def save_frame(self, frame: Dict, timestamp: float, images_dir) -> Optional[str]:
        images_dir = Path(images_dir)
        images_dir.mkdir(parents=True, exist_ok=True)
        filename = f"frame_{int(timestamp * 1000)}.jpg"
        out_path = images_dir / filename

        image = frame.get("data") if isinstance(frame, dict) else None
        if self.use_mock or image is None:
            out_path.write_bytes(b"MOCK_FRAME")
            return filename

        params = [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
        if not cv2.imwrite(str(out_path), image, params):
            print(f"CameraDriver: failed to write {out_path}")
            return None
        return filename

    def get_frame_count(self) -> int:
        return self.frame_count
