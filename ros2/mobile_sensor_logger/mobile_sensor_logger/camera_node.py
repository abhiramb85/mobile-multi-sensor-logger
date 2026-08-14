"""Publish CameraDriver frames as sensor_msgs/CompressedImage (+ CameraInfo).

The driver hands back a raw BGR ndarray; ROS carries video as an image stream,
so this node JPEG-encodes each frame into a CompressedImage (the ROS-native
equivalent of the recorded JPEGs). CameraInfo rides alongside on every frame so
consumers can associate intrinsics — zeroed here, since the logger captures no
calibration. Pass publish_raw:=true to also emit an uncompressed Image.
"""

import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, CompressedImage, Image, RegionOfInterest

from .driver_loader import ensure_drivers_importable

ensure_drivers_importable()

from src.sensors.camera import CameraDriver  # noqa: E402
from src.tools.ros2_common import (  # noqa: E402
    FRAME_CAMERA,
    TOPIC_CAMERA_INFO,
    TOPIC_IMAGE_COMPRESSED,
    TOPIC_IMAGE_RAW,
    ZERO_COV_9,
)
from .node_utils import header_from_epoch  # noqa: E402

import cv2  # noqa: E402  (imported after driver_loader for symmetry; always present on the Pi)


class CameraPublisher(Node):
    """Wraps the existing OpenCV CameraDriver in a ROS 2 publisher node."""

    def __init__(self):
        super().__init__("camera_publisher")
        self.declare_parameter("use_mock", True)
        self.declare_parameter("device_id", 0)
        self.declare_parameter("width", 1280)
        self.declare_parameter("height", 720)
        self.declare_parameter("fps", 30)
        self.declare_parameter("jpeg_quality", 90)
        self.declare_parameter("frame_id", FRAME_CAMERA)
        self.declare_parameter("publish_raw", False)

        self.frame_id = self.get_parameter("frame_id").value
        self.width = int(self.get_parameter("width").value)
        self.height = int(self.get_parameter("height").value)
        self.jpeg_quality = int(self.get_parameter("jpeg_quality").value)
        self.publish_raw = bool(self.get_parameter("publish_raw").value)
        use_mock = self.get_parameter("use_mock").value
        fps = int(self.get_parameter("fps").value)

        self._driver = CameraDriver(
            device_id=int(self.get_parameter("device_id").value),
            resolution=(self.width, self.height),
            fps=fps,
            jpeg_quality=self.jpeg_quality,
            use_mock=use_mock,
        )
        if not self._driver.start():
            raise RuntimeError("CameraDriver failed to start")

        self._compressed_pub = self.create_publisher(
            CompressedImage, TOPIC_IMAGE_COMPRESSED, 5)
        self._info_pub = self.create_publisher(CameraInfo, TOPIC_CAMERA_INFO, 5)
        self._raw_pub = (
            self.create_publisher(Image, TOPIC_IMAGE_RAW, 5) if self.publish_raw else None)

        self._timer = self.create_timer(1.0 / max(1, fps), self._tick)
        self.get_logger().info(
            f"camera_publisher up ({'mock' if use_mock else 'real'}) -> "
            f"{TOPIC_IMAGE_COMPRESSED} @ {fps} fps"
            + (" (+ raw)" if self.publish_raw else ""))

    def _tick(self):
        frame = self._driver.get_frame()
        if frame is None:
            return
        timestamp, payload = frame
        image = payload.get("data")
        if image is None:
            # Mock mode has no real pixels; synthesize a mid-gray frame so the
            # topics stay live for pipeline testing without hardware.
            image = np.full((self.height, self.width, 3), 128, dtype=np.uint8)

        header = header_from_epoch(timestamp, self.frame_id)

        ok, encoded = cv2.imencode(
            ".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality])
        if ok:
            comp = CompressedImage()
            comp.header = header
            comp.format = "jpeg"
            comp.data = encoded.tobytes()
            self._compressed_pub.publish(comp)

        self._info_pub.publish(self._camera_info(header, image.shape[1], image.shape[0]))

        if self._raw_pub is not None:
            h, w = image.shape[:2]
            raw = Image()
            raw.header = header
            raw.height = h
            raw.width = w
            raw.encoding = "bgr8"
            raw.is_bigendian = 0
            raw.step = w * 3
            raw.data = image.tobytes()
            self._raw_pub.publish(raw)

    def _camera_info(self, header, width, height) -> CameraInfo:
        info = CameraInfo()
        info.header = header
        info.height = height
        info.width = width
        info.distortion_model = "plumb_bob"
        info.d = [0.0] * 5
        info.k = list(ZERO_COV_9)
        info.r = list(ZERO_COV_9)
        info.p = [0.0] * 12
        info.roi = RegionOfInterest()
        return info

    def destroy_node(self):
        self._driver.stop()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = CameraPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
