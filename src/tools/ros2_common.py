"""Shared boundary logic for turning dataset/driver values into ROS 2 quantities.

Imported by BOTH the offline exporter (`to_rosbag.py`, which builds plain dicts
for the pure-Python MCAP writer) and the live ROS 2 nodes (`ros2/`, which fill
real `sensor_msgs` message objects). Keeping the unit conversions, covariance
sentinels, timestamp splitting, and topic/frame names in one ROS-free module is
what stops the recorded-then-converted bag and the live-published bag from
disagreeing.

This module must not import rclpy or any ROS package — it has to stay importable
on the plain-Python side (e.g. a Windows laptop running the exporter).
"""

import math
from datetime import datetime
from typing import Dict, Optional, Sequence, Tuple

DEG_TO_RAD = math.pi / 180.0

# Topic names — shared so `ros2 bag record` output and `to_rosbag.py` output
# land on identical topics.
TOPIC_GPS = "/gps/fix"
TOPIC_IMU = "/imu/data_raw"
TOPIC_IMAGE_COMPRESSED = "/camera/image_raw/compressed"
TOPIC_IMAGE_RAW = "/camera/image_raw"
TOPIC_CAMERA_INFO = "/camera/camera_info"

# Default REP-105 frame ids.
FRAME_GPS = "gps_link"
FRAME_IMU = "imu_link"
FRAME_CAMERA = "camera_link"

# sensor_msgs sentinels.
COVARIANCE_TYPE_UNKNOWN = 0        # NavSatFix.position_covariance_type
STATUS_FIX = 0                     # NavSatStatus.status (STATUS_FIX)
SERVICE_GPS = 1                    # NavSatStatus.service (SERVICE_GPS)
ORIENTATION_UNAVAILABLE = -1.0     # Imu.orientation_covariance[0] per the msg docs

ZERO_COV_9 = [0.0] * 9


def parse_timestamp(value) -> Optional[float]:
    """Parse a CSV timestamp into a Unix epoch float.

    Datasets carry either an ISO 8601 UTC string (current logger) or a bare
    epoch float (older recordings); both appear in ./data.
    """
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except ValueError:
        return None


def to_ros_time(epoch_seconds: float) -> Dict[str, int]:
    """Split a Unix epoch float into builtin_interfaces/Time fields."""
    nanos = int(round(epoch_seconds * 1e9))
    return {"sec": nanos // 1_000_000_000, "nanosec": nanos % 1_000_000_000}


def to_nanoseconds(epoch_seconds: float) -> int:
    return int(round(epoch_seconds * 1e9))


def gyro_dps_to_rads(gyro: Sequence[float]) -> Tuple[float, float, float]:
    """Convert an angular-velocity triple from deg/s (CSV / driver units) to
    rad/s, which is what sensor_msgs/Imu requires under REP-103."""
    gx, gy, gz = gyro
    return (gx * DEG_TO_RAD, gy * DEG_TO_RAD, gz * DEG_TO_RAD)


def orientation_from_quaternion(
    qx: Optional[float], qy: Optional[float], qz: Optional[float], qw: Optional[float]
) -> Tuple[Tuple[float, float, float, float], list]:
    """Build (x, y, z, w) + orientation_covariance for sensor_msgs/Imu.

    All four components must be present (the BNO085's on-chip rotation-vector
    fusion report); otherwise orientation is unavailable and covariance[0] is
    set to -1, per the msg docs, rather than publishing a fabricated identity
    reading as if it were real.
    """
    if None in (qx, qy, qz, qw):
        return (0.0, 0.0, 0.0, 1.0), [ORIENTATION_UNAVAILABLE] + [0.0] * 8
    return (qx, qy, qz, qw), list(ZERO_COV_9)
