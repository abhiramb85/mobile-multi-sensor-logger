# Mobile Multi-Sensor Data Logging System

A robust Python-based system for acquiring synchronized multi-sensor data from mobile platforms (bicycles, robots) for outdoor infrastructure monitoring.

## Overview

This project integrates camera, GPS, and optional IMU sensors to collect geo-referenced, time-synchronized datasets. The system logs images and sensor telemetry in a structured format with a replay tool for synchronized visualization.

## Features

- **Multi-sensor acquisition**: USB camera via OpenCV, NMEA-0183 GPS via pyserial, BNO055 IMU via I2C (optional)
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
- **IMU**: Optional Bosch BNO055 over I2C (9-DOF with onboard sensor fusion). Default address `0x28`.
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
- `--real-imu`: Read from a real BNO055 over I2C instead of mock data (also needs `--enable-imu`)
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
timestamp,latitude,longitude,image_path,ax,ay,az,gx,gy,gz
1651316400.123,52.5200,13.4050,images/frame_1651316400123.jpg,0.05,-0.02,9.81,0.01,0.02,-0.01
```

- `timestamp`: Unix epoch (seconds.milliseconds)
- `latitude`, `longitude`: GPS position in decimal degrees
- `image_path`: Relative path to image file
- `ax, ay, az`: Acceleration in m/s² (or null if no IMU)
- `gx, gy, gz`: Angular velocity in °/s (or null if no IMU)

### Replay Tool

```bash
python -m src.tools.replay --dataset-dir ./data/run001 --speed 1.0
```

Displays:
- Synchronized video playback
- GPS trajectory map
- IMU telemetry graphs (if available)

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
│   └── replay.py     # Replay and visualization
└── main.py           # Main acquisition orchestrator

tests/                # Unit and integration tests
docs/                 # Documentation and guides
data/                 # Default data storage location
```

## Development Status

- [x] Project structure
- [x] Sensor drivers (camera via OpenCV, GPS via pyserial NMEA, BNO055 IMU via Adafruit Blinka — all with mock fallbacks)
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
