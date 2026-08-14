"""Bring up all three sensor publisher nodes.

All sensors default to mock so the graph comes up with no hardware attached:

    ros2 launch mobile_sensor_logger sensors.launch.py

Flip individual sensors to real hardware, and record live:

    ros2 launch mobile_sensor_logger sensors.launch.py \\
        gps_mock:=false imu_enabled:=true imu_mock:=false camera_mock:=false
    ros2 bag record -s mcap -o ride_001 /gps/fix /imu/data_raw \\
        /camera/image_raw/compressed /camera/camera_info
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    args = [
        DeclareLaunchArgument("camera_mock", default_value="true"),
        DeclareLaunchArgument("gps_mock", default_value="true"),
        DeclareLaunchArgument("imu_mock", default_value="true"),
        # IMU is off by default, mirroring IMUConfig.enabled in the CSV pipeline.
        DeclareLaunchArgument("imu_enabled", default_value="false"),
        DeclareLaunchArgument("camera_fps", default_value="30"),
        DeclareLaunchArgument("camera_device_id", default_value="0"),
        DeclareLaunchArgument("gps_port", default_value="/dev/ttyACM0"),
        DeclareLaunchArgument("publish_raw", default_value="false"),
    ]

    camera = Node(
        package="mobile_sensor_logger",
        executable="camera_node",
        name="camera_publisher",
        output="screen",
        parameters=[{
            "use_mock": LaunchConfiguration("camera_mock"),
            "device_id": LaunchConfiguration("camera_device_id"),
            "fps": LaunchConfiguration("camera_fps"),
            "publish_raw": LaunchConfiguration("publish_raw"),
        }],
    )

    gps = Node(
        package="mobile_sensor_logger",
        executable="gps_node",
        name="gps_publisher",
        output="screen",
        parameters=[{
            "use_mock": LaunchConfiguration("gps_mock"),
            "port": LaunchConfiguration("gps_port"),
        }],
    )

    imu = Node(
        package="mobile_sensor_logger",
        executable="imu_node",
        name="imu_publisher",
        output="screen",
        condition=IfCondition(LaunchConfiguration("imu_enabled")),
        parameters=[{
            "use_mock": LaunchConfiguration("imu_mock"),
        }],
    )

    return LaunchDescription(args + [camera, gps, imu])
