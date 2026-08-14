# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python-based multi-sensor data logging system for mobile platforms (bicycles, robots) targeting Raspberry Pi. Captures synchronized camera frames, GPS positions, and IMU measurements for outdoor infrastructure monitoring and research.

## Commands

```bash
# Setup
python3 -m venv venv
source venv/bin/activate        # Linux/macOS
pip install -r requirements.txt

# Run data acquisition
python src/main.py --output-dir ./data/test --duration 300 --camera-id 0 --fps 30

# Replay a recorded dataset
python src/tools/replay.py --dataset-dir ./data/run_001 --map --telemetry

# Export a dataset to a rosbag2 bag (readable by `ros2 bag info/play/read`)
python src/tools/to_rosbag.py --dataset-dir ./data/run_001

# Tests
python -m unittest discover -s tests -p "test_*.py"
pytest tests/

# Run a single test file
pytest tests/test_sync.py
```

## Architecture

The pipeline flows: **Hardware → Sensor Drivers → Synchronizer → Logger → Dataset**

```
src/sensors/         Thin drivers around each physical sensor
src/core/sync.py     TimestampSynchronizer — aligns readings across sensors
src/core/logger.py   DataLogger — writes CSV, metadata.json, JPEG frames
src/core/config.py   Dataclass config hierarchy (System → Camera/GPS/IMU/Sync)
src/main.py          DataAcquisitionSystem orchestrator, SIGINT shutdown
src/tools/replay.py  Dataset replay with video, folium map, matplotlib telemetry
src/tools/to_rosbag.py  Dataset → rosbag2 (MCAP) exporter
src/tools/ros2_msgs.py  Embedded sensor_msgs .msg definitions for the exporter
src/tools/ros2_common.py  ROS-free shared conversions/constants (exporter + live nodes)
ros2/mobile_sensor_logger/  ament_python package: live ROS 2 publisher nodes (Pi only)
tests/               unittest + pytest; mock sensors for fully offline testing
```

### Synchronization strategy

GPS is the reference clock. The `TimestampSynchronizer` (`src/core/sync.py`) buffers readings from all sensors in deques, uses nearest-neighbor interpolation to align camera and IMU data to GPS timestamps, and tracks clock drift. `max_drift_ms` (default 100 ms) triggers a warning; readings outside that window are discarded.

### Sensor drivers

`src/sensors/base_sensor.py` defines the abstract `SensorDriver` interface. All three drivers (`camera.py`, `gps.py`, `imu.py`) currently use mock implementations that generate realistic synthetic data. Real hardware implementations (NMEA serial parsing, I2C/SPI IMU init) are the primary pending work (Phase 2 in `docs/DEVELOPMENT.md`).

### Output format

Each recording produces a directory with:
- `images/frame_<unix_ms>.jpg` — JPEG frames
- `data.csv` — 10 columns: `timestamp, latitude, longitude, image_path, ax, ay, az, gx, gy, gz` (IMU/GPS columns nullable)
- `metadata.json` — sensor config snapshot + recording stats

### ROS 2 compatibility

The acquisition pipeline deliberately has no ROS dependency — the Pi records plain CSV + JPEG. ROS compatibility is a *post-hoc conversion*: `src/tools/to_rosbag.py` turns a dataset into a rosbag2 bag (MCAP storage, CDR serialization) carrying `NavSatFix` on `/gps/fix`, `Imu` on `/imu/data_raw`, `CompressedImage` on `/camera/image_raw/compressed`, and `CameraInfo` on `/camera/camera_info`.

Serialization uses the pure-Python `mcap` + `mcap-ros2-support` packages, so no ROS 2 install is required to write a bag. Message schemas are embedded as .msg text in `src/tools/ros2_msgs.py`; **CDR is positional, so field order there must match upstream `sensor_msgs` exactly** or consumers decode garbage.

Two unit conversions happen at the boundary: `data.csv` stores gyro in °/s but `sensor_msgs/Imu` requires rad/s (REP-103), and the CSV's ISO 8601 timestamp becomes a `builtin_interfaces/Time`. Older datasets store a bare epoch float instead of ISO 8601 — `parse_timestamp` handles both.

For *live* ROS use, `ros2/mobile_sensor_logger/` is an `ament_python` package whose nodes wrap the existing drivers (`src/sensors/`) and publish the same topics/types in real time; record with `ros2 bag record`. It runs alongside the CSV pipeline, not instead of it, and needs a real ROS 2 install (Linux/Pi) — `rclpy` is not pip-installable, so it can't be exercised from the Windows dev box. The nodes import the drivers via `driver_loader.py` (walks up to the repo root, or `$SENSOR_LOGGER_ROOT`), so build with `colcon build --symlink-install`. The boundary conversions/constants/topic names live once in `src/tools/ros2_common.py` (ROS-free) and are imported by both the exporter and the nodes so the recorded-then-converted bag and the live bag can't disagree.

## Configuration

All configuration lives in dataclasses in `src/core/config.py`. The `SystemConfig` root aggregates `CameraConfig`, `GPSConfig`, `IMUConfig`, and `SyncConfig`. Defaults are sensible for Raspberry Pi 4; override via constructor kwargs in `src/main.py`.

## Development phases

Per `docs/DEVELOPMENT.md`:
- **Phase 1–2**: Core framework and mock drivers — complete
- **Phase 3**: Integration testing and Kalman-filter sync — in progress
- **Phase 4–5**: Web replay UI and real-time monitoring dashboard — pending

## Hardware notes

Target: Raspberry Pi 4 (4 GB), USB webcam (Logitech C920), u-blox NEO-6M GPS via serial, optional MPU-6050 IMU via I2C. RPi 4 may bottleneck above 20 fps at full resolution. GPS cold start takes 30+ seconds outdoors. See `docs/HARDWARE_SETUP.md` for wiring details.
