"""ROS 2 message definitions used by the rosbag2 exporter.

These are the concatenated .msg texts (the same format `ros2 interface show`
emits, with `MSG:` separators for dependencies) that `mcap_ros2` needs to
register a schema. Embedding them here keeps the exporter runnable on machines
without a ROS 2 installation — a laptop or the Pi itself can produce a bag that
a ROS workstation reads back with `ros2 bag play`.

Field order and types must match the upstream sensor_msgs definitions exactly:
CDR is positional, so a reordered field silently corrupts the decode.
"""

SEP = "=" * 80

_TIME = """int32 sec
uint32 nanosec
"""

_HEADER = """builtin_interfaces/Time stamp
string frame_id
"""

_VECTOR3 = """float64 x
float64 y
float64 z
"""

_QUATERNION = """float64 x
float64 y
float64 z
float64 w
"""

_NAVSAT_STATUS = """int8 status
uint16 service
"""

_ROI = """uint32 x_offset
uint32 y_offset
uint32 height
uint32 width
bool do_rectify
"""


def _bundle(root: str, *deps: tuple) -> str:
    """Join a root definition with its dependencies in gendeps format."""
    parts = [root]
    for name, text in deps:
        parts.append(f"{SEP}\nMSG: {name}\n{text}")
    return "\n".join(parts)


NAVSATFIX = _bundle(
    """std_msgs/Header header
sensor_msgs/NavSatStatus status
float64 latitude
float64 longitude
float64 altitude
float64[9] position_covariance
uint8 position_covariance_type
""",
    ("std_msgs/Header", _HEADER),
    ("builtin_interfaces/Time", _TIME),
    ("sensor_msgs/NavSatStatus", _NAVSAT_STATUS),
)

IMU = _bundle(
    """std_msgs/Header header
geometry_msgs/Quaternion orientation
float64[9] orientation_covariance
geometry_msgs/Vector3 angular_velocity
float64[9] angular_velocity_covariance
geometry_msgs/Vector3 linear_acceleration
float64[9] linear_acceleration_covariance
""",
    ("std_msgs/Header", _HEADER),
    ("builtin_interfaces/Time", _TIME),
    ("geometry_msgs/Quaternion", _QUATERNION),
    ("geometry_msgs/Vector3", _VECTOR3),
)

COMPRESSED_IMAGE = _bundle(
    """std_msgs/Header header
string format
uint8[] data
""",
    ("std_msgs/Header", _HEADER),
    ("builtin_interfaces/Time", _TIME),
)

IMAGE = _bundle(
    """std_msgs/Header header
uint32 height
uint32 width
string encoding
uint8 is_bigendian
uint32 step
uint8[] data
""",
    ("std_msgs/Header", _HEADER),
    ("builtin_interfaces/Time", _TIME),
)

CAMERA_INFO = _bundle(
    """std_msgs/Header header
uint32 height
uint32 width
string distortion_model
float64[] d
float64[9] k
float64[9] r
float64[12] p
uint32 binning_x
uint32 binning_y
sensor_msgs/RegionOfInterest roi
""",
    ("std_msgs/Header", _HEADER),
    ("builtin_interfaces/Time", _TIME),
    ("sensor_msgs/RegionOfInterest", _ROI),
)


# Covariance / status sentinels from the upstream message docs. Re-exported from
# ros2_common so the exporter and the live nodes share one definition.
from src.tools.ros2_common import (  # noqa: E402
    COVARIANCE_TYPE_UNKNOWN,
    STATUS_FIX,
    SERVICE_GPS,
)
