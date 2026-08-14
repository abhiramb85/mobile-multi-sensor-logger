# mobile_sensor_logger (ROS 2 package)

Live ROS 2 publisher nodes wrapping the mobile multi-sensor logger's camera /
GPS / IMU drivers. The nodes reuse the drivers in `../../src/sensors/`
unchanged, so mock/real behavior is identical to the CSV recorder. The CSV
acquisition pipeline stays ROS-free; this package is an **additional** live
frontend, not a replacement.

## Nodes and topics

| Executable | Node | Topic(s) | Type |
|---|---|---|---|
| `gps_node` | `gps_publisher` | `/gps/fix` | `sensor_msgs/msg/NavSatFix` |
| `imu_node` | `imu_publisher` | `/imu/data_raw` | `sensor_msgs/msg/Imu` |
| `camera_node` | `camera_publisher` | `/camera/image_raw/compressed`, `/camera/camera_info` | `sensor_msgs/msg/CompressedImage`, `CameraInfo` |
| | | `/camera/image_raw` (with `publish_raw:=true`) | `sensor_msgs/msg/Image` |

Message types, frame ids, and unit conventions (gyro in rad/s per REP-103,
`NaN` altitude, `-1` orientation covariance, zeroed uncalibrated intrinsics)
match the offline exporter `src/tools/to_rosbag.py` — both import the shared
conversions in `src/tools/ros2_common.py`.

## Prerequisites (Raspberry Pi)

Recommended: **Ubuntu Server 22.04 (64-bit) + ROS 2 Humble** (LTS, best-tested
on the Pi). Ubuntu 24.04 + Jazzy also works — the code is distro-agnostic.

```bash
# ROS 2 base (see the official install docs for the apt key/source setup)
sudo apt install ros-humble-ros-base ros-humble-rosbag2-storage-mcap \
                 python3-colcon-common-extensions

# Python deps the drivers need (already in the repo's requirements.txt, but on
# the Pi install the hardware-facing ones too):
pip install adafruit-circuitpython-bno08x adafruit-blinka lgpio pyserial
sudo apt install python3-opencv python3-numpy
```

## Build

The nodes import the drivers from the repo via `driver_loader.py`, which finds
the repo root by walking up from the (symlinked) node files — so build with
`--symlink-install`:

```bash
mkdir -p ~/ros2_ws/src
ln -s ~/mobile-multi-sensor-logger/ros2/mobile_sensor_logger ~/ros2_ws/src/
cd ~/ros2_ws
colcon build --symlink-install
source install/setup.bash
```

If your repo is somewhere the walk-up can't reach, set the override:

```bash
export SENSOR_LOGGER_ROOT=~/mobile-multi-sensor-logger
```

## Run

```bash
# Everything mocked — verify the graph with no hardware:
ros2 launch mobile_sensor_logger sensors.launch.py

# Inspect:
ros2 topic hz /gps/fix
ros2 topic echo /imu/data_raw --once

# Real hardware:
ros2 launch mobile_sensor_logger sensors.launch.py \
    camera_mock:=false gps_mock:=false imu_enabled:=true imu_mock:=false
```

Individual nodes (each takes parameters, see the `declare_parameter` calls):

```bash
ros2 run mobile_sensor_logger gps_node --ros-args -p use_mock:=false -p port:=/dev/ttyACM0
ros2 run mobile_sensor_logger imu_node --ros-args -p use_mock:=false
ros2 run mobile_sensor_logger camera_node --ros-args -p use_mock:=false -p publish_raw:=true
```

## Record and play back

```bash
ros2 bag record -s mcap -o ride_001 \
    /gps/fix /imu/data_raw /camera/image_raw/compressed /camera/camera_info

ros2 bag info ride_001
ros2 bag play ride_001
```

The recorded bag uses the same MCAP storage and message types as a bag produced
offline by `to_rosbag.py`, so downstream tooling can't tell which path made it.

## Launch arguments

| Argument | Default | Meaning |
|---|---|---|
| `camera_mock` / `gps_mock` / `imu_mock` | `true` | Per-sensor mock vs real hardware |
| `imu_enabled` | `false` | IMU node only launches when true (mirrors `IMUConfig.enabled`) |
| `camera_fps` | `30` | Camera publish rate |
| `camera_device_id` | `0` | OpenCV device index |
| `gps_port` | `/dev/ttyACM0` | NMEA serial port |
| `publish_raw` | `false` | Also publish uncompressed `sensor_msgs/Image` |
