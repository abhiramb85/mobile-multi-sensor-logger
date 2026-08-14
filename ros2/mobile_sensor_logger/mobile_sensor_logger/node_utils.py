"""Small rclpy-side helpers shared by the sensor nodes.

Unlike `src/tools/ros2_common.py` (which stays ROS-free for the offline
exporter), this module DOES import ROS message types, so it only imports on a
machine with ROS 2 installed.
"""

from builtin_interfaces.msg import Time
from std_msgs.msg import Header

from src.tools.ros2_common import to_ros_time


def header_from_epoch(epoch_seconds: float, frame_id: str) -> Header:
    """Build a std_msgs/Header stamped with the sensor's own reading time.

    Stamping with the driver timestamp (not receive time) keeps the live bag
    aligned the same way the CSV synchronizer and the offline exporter align
    things — all downstream tooling then agrees on when a sample happened.
    """
    parts = to_ros_time(epoch_seconds)
    header = Header()
    header.stamp = Time(sec=parts["sec"], nanosec=parts["nanosec"])
    header.frame_id = frame_id
    return header
