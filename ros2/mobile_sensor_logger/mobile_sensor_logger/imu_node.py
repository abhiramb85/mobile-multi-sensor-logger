"""Publish IMUDriver samples as sensor_msgs/Imu on /imu/data_raw."""

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Imu

from .driver_loader import ensure_drivers_importable

ensure_drivers_importable()

from src.sensors.imu import IMUDriver  # noqa: E402
from src.tools.ros2_common import (  # noqa: E402
    FRAME_IMU,
    ORIENTATION_UNAVAILABLE,
    TOPIC_IMU,
    ZERO_COV_9,
    gyro_dps_to_rads,
)
from .node_utils import header_from_epoch  # noqa: E402


class ImuPublisher(Node):
    """Wraps the existing BNO085 IMUDriver in a ROS 2 publisher node."""

    def __init__(self):
        super().__init__("imu_publisher")
        self.declare_parameter("use_mock", True)
        self.declare_parameter("i2c_address", 0x4A)
        self.declare_parameter("sample_rate_hz", 100)
        self.declare_parameter("frame_id", FRAME_IMU)
        self.declare_parameter("publish_rate_hz", 100.0)

        self.frame_id = self.get_parameter("frame_id").value
        use_mock = self.get_parameter("use_mock").value
        rate = float(self.get_parameter("publish_rate_hz").value)

        self._driver = IMUDriver(
            i2c_address=int(self.get_parameter("i2c_address").value),
            sample_rate_hz=int(self.get_parameter("sample_rate_hz").value),
            use_mock=use_mock,
        )
        if not self._driver.start():
            raise RuntimeError("IMUDriver failed to start")

        self._pub = self.create_publisher(Imu, TOPIC_IMU, 50)
        self._timer = self.create_timer(1.0 / max(0.1, rate), self._tick)
        self.get_logger().info(
            f"imu_publisher up ({'mock' if use_mock else 'real'}) -> {TOPIC_IMU} @ {rate} Hz")

    def _tick(self):
        sample = self._driver.get_measurement()
        if not sample:
            return
        msg = Imu()
        msg.header = header_from_epoch(sample["timestamp"], self.frame_id)
        # The driver logs raw accel/gyro only; leading -1 marks orientation as
        # not supplied, per the sensor_msgs/Imu convention.
        msg.orientation.w = 1.0
        msg.orientation_covariance = [ORIENTATION_UNAVAILABLE] + [0.0] * 8
        # Driver reports gyro in deg/s; sensor_msgs/Imu requires rad/s (REP-103).
        wx, wy, wz = gyro_dps_to_rads((sample["gx"], sample["gy"], sample["gz"]))
        msg.angular_velocity.x = wx
        msg.angular_velocity.y = wy
        msg.angular_velocity.z = wz
        msg.angular_velocity_covariance = list(ZERO_COV_9)
        msg.linear_acceleration.x = float(sample["ax"])
        msg.linear_acceleration.y = float(sample["ay"])
        msg.linear_acceleration.z = float(sample["az"])
        msg.linear_acceleration_covariance = list(ZERO_COV_9)
        self._pub.publish(msg)

    def destroy_node(self):
        self._driver.stop()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = ImuPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
