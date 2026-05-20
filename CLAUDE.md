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

## Configuration

All configuration lives in dataclasses in `src/core/config.py`. The `SystemConfig` root aggregates `CameraConfig`, `GPSConfig`, `IMUConfig`, and `SyncConfig`. Defaults are sensible for Raspberry Pi 4; override via constructor kwargs in `src/main.py`.

## Development phases

Per `docs/DEVELOPMENT.md`:
- **Phase 1–2**: Core framework and mock drivers — complete
- **Phase 3**: Integration testing and Kalman-filter sync — in progress
- **Phase 4–5**: Web replay UI and real-time monitoring dashboard — pending

## Hardware notes

Target: Raspberry Pi 4 (4 GB), USB webcam (Logitech C920), u-blox NEO-6M GPS via serial, optional MPU-6050 IMU via I2C. RPi 4 may bottleneck above 20 fps at full resolution. GPS cold start takes 30+ seconds outdoors. See `docs/HARDWARE_SETUP.md` for wiring details.
