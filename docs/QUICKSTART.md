# Quick Start Guide

## 5-Minute Setup

### 1. Clone and Install
```bash
cd ~/projects
git clone <repo-url> mobile-multi-sensor-logger
cd mobile-multi-sensor-logger

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Hardware Check
```bash
# List USB devices
lsusb

# Find camera
ls /dev/video*

# Test GPS (if connected)
cat /dev/ttyUSB0 115200
```

### 3. First Recording (5 minutes)
```bash
python src/main.py \
  --output-dir ./data/test_run \
  --duration 300 \
  --camera-id 0 \
  --fps 30

# Output goes to ./data/test_run/
```

### 4. Replay Dataset
```bash
python src/tools/replay.py \
  --dataset-dir ./data/test_run \
  --speed 1.0 \
  --map \
  --telemetry
```

## Hardware Quick Setup

### Minimal Setup (Camera + USB Power)
- USB camera connected to RPi USB port
- Power adapter connected to micro USB

### With GPS
- USB GPS module → RPi USB port 2
- Or serial GPS → GPIO 14/15

### With IMU (Optional)
- SDA → GPIO 2, SCL → GPIO 3, VCC → 3.3V, GND → GND

## Command Reference

### Recording Options

```bash
# Basic recording
python src/main.py

# Specify camera and GPS port
python src/main.py --camera-id 0 --gps-port /dev/ttyUSB0

# Limit duration (300 seconds = 5 minutes)
python src/main.py --duration 300

# Enable IMU
python src/main.py --enable-imu

# Reduce framerate to save CPU/storage
python src/main.py --fps 15

# Full example
python src/main.py \
  --output-dir ./data/bike_ride_001 \
  --duration 1800 \
  --camera-id 0 \
  --gps-port /dev/ttyUSB0 \
  --fps 30 \
  --enable-imu
```

### Replay Options

```bash
# Basic replay
python src/tools/replay.py --dataset-dir ./data/test_run

# Fast playback
python src/tools/replay.py --dataset-dir ./data/test_run --speed 2.0

# Generate map and telemetry
python src/tools/replay.py --dataset-dir ./data/test_run --map --telemetry

# Replay on different machine
# Copy entire ./data/test_run directory and run replay
```

## Keyboard Controls (Replay)

- **SPACE**: Pause/Resume
- **ESC**: Quit
- **LEFT arrow**: Seek back 10 frames
- **RIGHT arrow**: Seek forward 10 frames

## Output Files

After recording `./data/test_run/`:

```
test_run/
├── images/
│   ├── frame_1234567890123.jpg
│   ├── frame_1234567890160.jpg
│   └── ... (1800 frames for 60s @ 30fps)
├── data.csv          # Synchronized log
└── metadata.json     # Configuration and stats
```

## Next Steps

1. **Review** [HARDWARE_SETUP.md](docs/HARDWARE_SETUP.md) for detailed hardware assembly
2. **Check** [DATASET_FORMAT.md](docs/DATASET_FORMAT.md) for CSV/image specifications
3. **Debug** [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) if issues arise
4. **Read** [DEVELOPMENT.md](docs/DEVELOPMENT.md) for roadmap and testing

## Performance Expectations

### Typical Performance (Raspberry Pi 4, 1280x720, 30 fps)
- **Frame capture**: 30+ fps sustained
- **CSV writes**: Real-time with buffering
- **Storage**: ~4.5 MB/sec (~270 MB/min)
- **GPS updates**: 1 Hz (if available)
- **IMU samples**: 100 Hz (if available)

### Limitations
- **CPU**: Single-core can saturate; multi-core needed for >20 fps
- **Storage**: microSD slow; external SSD recommended for long runs
- **GPS**: 30-60 second cold start, ±5-10m accuracy typical
- **Sync**: ±100ms drift acceptable, noted in metadata

## Tips

1. **Test before field deployment**: 5-minute lab run to verify all systems
2. **Check storage**: `df -h` before long recordings
3. **Monitor GPS**: Ensure outdoor antenna placement, wait for fix before moving
4. **Thermal**: Consider heatsinks for >2 hour continuous runs
5. **Power**: Use quality 5V 3A adapter, not cheap phone chargers
6. **Backup**: Keep redundant copies of unique datasets

## Common Commands

```bash
# Check free space
df -h

# Monitor during recording
top -p <PID>

# List USB devices
lsusb

# Check camera
v4l2-ctl --list-devices

# Find GPS port
dmesg | grep ttyUSB
```

## Troubleshooting Quick Links

- **Camera issues**: See [TROUBLESHOOTING.md#1-camera-not-detected](docs/TROUBLESHOOTING.md#1-camera-not-detected)
- **GPS issues**: See [TROUBLESHOOTING.md#2-gps-not-getting-fix](docs/TROUBLESHOOTING.md#2-gps-not-getting-fix)
- **Performance issues**: See [TROUBLESHOOTING.md#3-low-frame-rate--frame-drops](docs/TROUBLESHOOTING.md#3-low-frame-rate--frame-drops)

## Support

For detailed help:
1. Check relevant doc files in `docs/`
2. Review error messages (often in metadata.json)
3. Enable debug logging in src/main.py
4. Report issues with hardware config, error output, and metadata.json

**Ready to start? Run your first recording:**
```bash
python src/main.py --output-dir ./data/test_run --duration 60
```
