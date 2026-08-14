"""Publish GPSDriver fixes as sensor_msgs/NavSatFix on /gps/fix."""

import math

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix, NavSatStatus

from .driver_loader import ensure_drivers_importable

ensure_drivers_importable()

from src.sensors.gps import GPSDriver  # noqa: E402
from src.tools.ros2_common import (  # noqa: E402
    COVARIANCE_TYPE_UNKNOWN,
    FRAME_GPS,
    SERVICE_GPS,
    STATUS_FIX,
    TOPIC_GPS,
    ZERO_COV_9,
)
from .node_utils import header_from_epoch  # noqa: E402


class GpsPublisher(Node):
    """Wraps the existing NMEA GPSDriver in a ROS 2 publisher node."""

    def __init__(self):
        super().__init__("gps_publisher")
        self.declare_parameter("use_mock", True)
        self.declare_parameter("port", "/dev/ttyACM0")
        self.declare_parameter("baudrate", 9600)
        self.declare_parameter("frame_id", FRAME_GPS)
        self.declare_parameter("publish_rate_hz", 5.0)

        self.frame_id = self.get_parameter("frame_id").value
        use_mock = self.get_parameter("use_mock").value
        rate = float(self.get_parameter("publish_rate_hz").value)

        self._driver = GPSDriver(
            port=self.get_parameter("port").value,
            baudrate=int(self.get_parameter("baudrate").value),
            use_mock=use_mock,
        )
        if not self._driver.start():
            raise RuntimeError("GPSDriver failed to start")

        self._pub = self.create_publisher(NavSatFix, TOPIC_GPS, 10)
        self._timer = self.create_timer(1.0 / max(0.1, rate), self._tick)
        self.get_logger().info(
            f"gps_publisher up ({'mock' if use_mock else 'real'}) -> {TOPIC_GPS} @ {rate} Hz")

    def _tick(self):
        fix = self._driver.get_data()
        if not fix:
            return
        msg = NavSatFix()
        msg.header = header_from_epoch(fix["timestamp"], self.frame_id)
        # NMEA driver reports position only, with no accuracy estimate.
        msg.status.status = STATUS_FIX
        msg.status.service = SERVICE_GPS
        msg.latitude = float(fix["latitude"])
        msg.longitude = float(fix["longitude"])
        msg.altitude = math.nan
        msg.position_covariance = list(ZERO_COV_9)
        msg.position_covariance_type = COVARIANCE_TYPE_UNKNOWN
        self._pub.publish(msg)

    def destroy_node(self):
        self._driver.stop()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = GpsPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
