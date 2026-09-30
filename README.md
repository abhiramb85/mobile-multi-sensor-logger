# Mobile Multi-Sensor Data Logging System

A robust Python-based system for acquiring synchronized multi-sensor data from mobile platforms (bicycles, robots) for outdoor infrastructure monitoring.

## Overview

This project integrates camera, GPS, and optional IMU sensors to collect geo-referenced, time-synchronized datasets. The system logs images and sensor telemetry in a structured format with a replay tool for synchronized visualization.

## Features

- **Multi-sensor acquisition**: USB camera via OpenCV, NMEA-0183 GPS via pyserial, BNO085 IMU via I2C (optional)
- **Mock fallbacks**: Every sensor driver runs in mock mode by default; opt-in to real hardware with `--real-camera`, `--real-gps`, `--real-imu`
- **Hardware time synchronization**: GPS as reference clock with nearest-neighbor interpolation
- **Structured dataset output**: Images directory + CSV log + metadata JSON
- **Replay tool**: Synchronized video playback with GPS map overlay and IMU telemetry
- **Robust error handling**: GPS outages, frame drops, clock drift detection
- **Real-time buffering**: Async writes to prevent data loss on resource-constrained hardware

## Requirements

- Python 3.8+
- Linux or Raspberry Pi OS (camera/GPS integration optimized for Linux)
- USB camera with OpenCV support
- GPS module (USB or serial NMEA stream)
- Optional: IMU sensor (I2C or SPI)

## Installation

1. Clone or download this repository:
   ```bash
   git clone <repo-url>
   cd mobile-multi-sensor-logger
   ```

2. Create a Python virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Hardware Setup

Refer to `docs/HARDWARE_SETUP.md` for detailed wiring and assembly instructions.

### Supported Components

- **Camera**: Any USB UVC camera supported by OpenCV (tested on a 12 MP USB webcam at 1280×720)
- **GPS**: Any NMEA-0183 module over USB or UART. Default port `/dev/ttyACM0` matches native-USB modules like the Navilock NL-852EUSB (u-blox 8). Pass `--gps-port /dev/ttyUSB0` for USB-to-serial bridges.
- **IMU**: Optional Bosch BNO085 over I2C with SH-2 protocol (9-DOF with onboard sensor fusion). Default address `0x4a`.
- **Compute**: Raspberry Pi 4 or 5; Python 3.8+

## Usage

### Data Acquisition

Run as a module from the project root so the `src` package resolves:

```bash
python -m src.main --output-dir ./data/run001 --duration 600 --camera-id 0
```

By default everything runs in mock mode (synthetic data, no hardware needed). Add the `--real-*` flags per sensor to use real hardware:

```bash
python -m src.main \
  --real-camera --real-gps --enable-imu --real-imu \
  --output-dir ./data/run001 --duration 600
```

Options:
- `--output-dir`: Directory to store dataset
- `--duration`: Recording duration in seconds (0 = infinite)
- `--camera-id`: USB camera device ID (default: 0)
- `--gps-port`: Serial port for GPS (default: `/dev/ttyACM0`)
- `--enable-imu`: Include the IMU in this run (off by default — CSV columns are optional)
- `--real-camera`: Capture from a real USB camera via OpenCV instead of mock frames
- `--real-gps`: Read real NMEA sentences from the GPS port instead of mock data
- `--real-imu`: Read from a real BNO085 over I2C instead of mock data (also needs `--enable-imu`)
- `--fps`: Camera frames per second (default: 30)

Output structure:
```
data/run001/
├── images/              # Timestamped frame captures
├── data.csv             # Synchronized sensor log
└── metadata.json        # Sensor configuration and hardware info
```

### CSV Format

```
timestamp,latitude,longitude,image_path,ax,ay,az,gx,gy,gz,qx,qy,qz,qw
1651316400.123,52.5200,13.4050,images/frame_1651316400123.jpg,0.05,-0.02,9.81,0.01,0.02,-0.01,0.0,0.0,0.01,0.9999
```

- `timestamp`: Unix epoch (seconds.milliseconds)
- `latitude`, `longitude`: GPS position in decimal degrees
- `image_path`: Path to the image as written at recording time (often absolute, tied to the machine/`--output-dir` used); consumers should join on the basename against their own `images/` dir, as `scripts/validate_dataset.py` and `src/tools/replay.py` do, rather than use the stored path directly
- `ax, ay, az`: Acceleration in m/s² (or null if no IMU)
- `gx, gy, gz`: Angular velocity in °/s (or null if no IMU)
- `qx, qy, qz, qw`: Orientation quaternion from the IMU's on-chip sensor fusion (or null if the IMU doesn't report one)

### Replay Tool (CLI)

```bash
python -m src.tools.replay --dataset-dir ./data/run001 --speed 1.0
```

Displays:
- Synchronized video playback
- GPS trajectory map (folium HTML)
- IMU telemetry graphs (matplotlib)
- Optional MP4 export with `--export-video` (works headless on the Pi)

### ROS 2 Export (`ros2 bag`)

Datasets convert to a [rosbag2](https://github.com/ros2/rosbag2) bag on the MCAP storage backend. The exporter is pure Python — **no ROS 2 install is needed to produce a bag**, only to play one back — so the Pi stays ROS-free while a ROS workstation reads the result.

```bash
python src/tools/to_rosbag.py --dataset-dir ./data/run_001
# -> ./data/run_001_rosbag/{run_001_rosbag_0.mcap, metadata.yaml}

# on the ROS 2 machine (Humble or newer):
ros2 bag info ./data/run_001_rosbag
ros2 bag play ./data/run_001_rosbag
```

| Topic | Type | Notes |
|---|---|---|
| `/gps/fix` | `sensor_msgs/msg/NavSatFix` | `frame_id: gps_link`, altitude `NaN`, covariance type `UNKNOWN` |
| `/imu/data_raw` | `sensor_msgs/msg/Imu` | `frame_id: imu_link`, gyro converted to rad/s per REP-103; `orientation` set from the recorded quaternion when present, else `orientation_covariance[0] = -1` (no orientation) |
| `/camera/image_raw/compressed` | `sensor_msgs/msg/CompressedImage` | `format: jpeg`, JPEG bytes passed through unmodified |
| `/camera/camera_info` | `sensor_msgs/msg/CameraInfo` | Resolution from `metadata.json`; intrinsics zeroed (uncalibrated) |
| `/camera/image_raw` | `sensor_msgs/msg/Image` | `bgr8`, only with `--raw-images` (produces much larger bags) |

Notes:
- All messages on a row share the synchronizer's GPS-referenced timestamp, so the bag preserves the alignment `TimestampSynchronizer` computed.
- ROS carries video as an image stream, not a container file — `/camera/image_raw/compressed` is the ROS-native form of the recording. The MP4 export remains a convenience artifact for humans, not for `ros2 bag`.
- Frame IDs are overridable: `--camera-frame`, `--gps-frame`, `--imu-frame`.
- Camera intrinsics are not captured by the logger; run `camera_calibration` and republish `CameraInfo` if you need rectified images.

### Live ROS 2 Nodes (on the Pi)

For *live* ROS 2 use, the sensor drivers are wrapped in publisher nodes so the sensors stream onto the ROS graph in real time — record with `ros2 bag record`, or feed any ROS consumer directly. This runs **alongside** the CSV pipeline, which stays ROS-free; it does not replace it.

Unlike the offline exporter, live nodes need an actual ROS 2 install (Linux). The package lives in [ros2/mobile_sensor_logger/](ros2/mobile_sensor_logger/) as a standard `ament_python` package and reuses the exact same drivers in [src/sensors/](src/sensors/), so mock/real behavior matches the recorder. See [ros2/mobile_sensor_logger/README.md](ros2/mobile_sensor_logger/README.md) for full Pi setup; the short version:

```bash
# On the Pi (Ubuntu + ROS 2 Humble/Jazzy), with this repo cloned:
mkdir -p ~/ros2_ws/src && ln -s ~/mobile-multi-sensor-logger/ros2/mobile_sensor_logger ~/ros2_ws/src/
cd ~/ros2_ws && colcon build --symlink-install && source install/setup.bash

# All sensors mocked — brings the graph up with no hardware:
ros2 launch mobile_sensor_logger sensors.launch.py

# Real hardware + live recording to an MCAP bag:
ros2 launch mobile_sensor_logger sensors.launch.py \
    camera_mock:=false gps_mock:=false imu_enabled:=true imu_mock:=false
ros2 bag record -s mcap -o ride_001 \
    /gps/fix /imu/data_raw /camera/image_raw/compressed /camera/camera_info
```

Nodes → topics: `gps_node` → `/gps/fix`, `imu_node` → `/imu/data_raw`, `camera_node` → `/camera/image_raw/compressed` + `/camera/camera_info` (add `publish_raw:=true` for `/camera/image_raw`). Same message types, frames, and unit conventions as the offline exporter above.

### Web Viewer + Control Panel

A local browser-based UI for recording, reviewing, and visualizing datasets — usable from any phone or laptop on the same network as the Pi. No SSH needed for normal operation.

```bash
python -m src.web.server --data-dir ./data
# then open http://<pi-ip>:5000 (or http://raspberrypi.local:5000) in any browser
```

**Record panel** (top of page):
- Toggle which sensors run real vs mock (camera / GPS / IMU)
- FPS slider (1–60)
- Duration field with quick presets (30 s, 5 min, 30 min)
- Optional output-name field (auto-generates `ride_YYYYMMDD_HHMMSS` if blank)
- Start button spawns the acquisition subprocess; recording survives even if you close the browser or kill the web server
- Live status during recording: pulsing indicator, elapsed time, frame/record counts, progress bar, last 30 log lines
- Stop button sends SIGINT so `metadata.json` and `data.csv` are finalized cleanly

**Review panel** (below):
- Run selector dropdown with size
- Current frame with sensor overlay
- GPS track on a Leaflet map with moving marker
- Accel + gyro plots (Chart.js) with a "now" cursor
- Play / pause / scrub through the recording

When a recording finishes, the run dropdown auto-refreshes and selects the new dataset so you can immediately review it.

## Project Structure

```
src/
├── sensors/          # Hardware drivers
│   ├── camera.py
│   ├── gps.py
│   └── imu.py
├── core/             # System core
│   ├── sync.py       # Timestamp synchronization
│   ├── logger.py     # Data logging formatter
│   └── config.py     # Configuration schemas
├── tools/            # Utilities
│   ├── replay.py     # Replay and visualization
│   ├── to_rosbag.py  # rosbag2 (MCAP) exporter
│   └── ros2_msgs.py  # Embedded sensor_msgs definitions
└── main.py           # Main acquisition orchestrator

tests/                # Unit and integration tests
docs/                 # Documentation and guides
data/                 # Default data storage location
```

## Development Status

- [x] Project structure
- [x] Sensor drivers (camera via OpenCV, GPS via pyserial NMEA, BNO085 IMU via Adafruit Blinka — all with mock fallbacks)
- [x] Timestamp synchronization (GPS-referenced, nearest-neighbor)
- [x] CSV logging + metadata.json
- [x] Replay tool (video + folium map + matplotlib telemetry)
- [ ] Real-world validation on bicycle/robot platform

See `docs/DEVELOPMENT.md` for detailed roadmap.

## Known Limitations

1. **Camera timestamps**: USB camera timestamps may drift. RPi CSI camera recommended for better synchronization.
2. **GPS cold start**: 30+ seconds to first fix in outdoor open sky; longer in urban canyons.
3. **Compute constraints**: Raspberry Pi 4 may struggle with >20 fps at full resolution. Use buffering and async writes.
4. **IMU optional**: IMU integration depends on availability; system works with camera + GPS alone.

## Troubleshooting

- **No camera detected**: Check USB device ID with `ls /dev/video*` and adjust `--camera-id`
- **GPS no fix**: Ensure antenna is outdoors, verify serial port with `dmesg`
- **Frame drops**: Enable buffering, reduce resolution, or profile CPU load with `top`

See `docs/TROUBLESHOOTING.md` for more issues.

## License

[License information to be determined]

## References

- Master Thesis: "Development of a Mobile Multi-Sensor Data Logging System for Outdoor Infrastructure Monitoring"
- Dataset format specification: See `docs/DATASET_FORMAT.md`

## Contact

[Contact information to be added]
