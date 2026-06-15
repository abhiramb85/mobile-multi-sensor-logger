# Dataset Format Specification

## Overview

A valid dataset consists of three components:
1. `data.csv` - Synchronized sensor log (timestamps, GPS, IMU)
2. `images/` directory - Timestamped image frames
3. `metadata.json` - Sensor configuration and recording metadata

## Directory Structure

```
dataset_root/
├── images/
│   ├── frame_1651316400123.jpg
│   ├── frame_1651316400160.jpg
│   └── ... (more frames)
├── data.csv
└── metadata.json
```

## CSV Format

### File: `data.csv`

**Delimiter**: Comma (`,`)
**Encoding**: UTF-8
**Line ending**: LF (`\n`)

### Column Specifications

| Column | Type | Required | Format | Notes |
|--------|------|----------|--------|-------|
| timestamp | String | Yes | ISO 8601 UTC, microsecond precision | E.g., `2026-06-14T06:24:02.040558+00:00` |
| latitude | Float | Optional | Decimal degrees | Range: -90 to +90; Null if no GPS fix |
| longitude | Float | Optional | Decimal degrees | Range: -180 to +180; Null if no GPS fix |
| image_path | String | Yes | Relative path from dataset root | E.g., `images/frame_1651316400123.jpg` |
| ax | Float | Optional | m/s² | X-axis acceleration; Null if no IMU |
| ay | Float | Optional | m/s² | Y-axis acceleration; Null if no IMU |
| az | Float | Optional | m/s² | Z-axis acceleration; Null if no IMU |
| gx | Float | Optional | °/s | X-axis angular velocity; Null if no IMU |
| gy | Float | Optional | °/s | Y-axis angular velocity; Null if no IMU |
| gz | Float | Optional | °/s | Z-axis angular velocity; Null if no IMU |

### Example Row

```csv
2026-06-14T06:24:02.040558+00:00,52.52001,13.40500,images/frame_1781475842040.jpg,0.05,-0.02,9.81,0.01,0.02,-0.01
2026-06-14T06:24:02.073891+00:00,52.52002,13.40501,images/frame_1781475842073.jpg,0.04,-0.01,9.82,0.00,0.03,-0.01
2026-06-14T06:24:02.107224+00:00,,,images/frame_1781475842107.jpg,,,,,,
```

### Null Value Representation

- GPS outage: Empty cell (no value between commas)
- No IMU: Entire columns may be empty or null

## Image Files

### Naming Convention

**Format**: `frame_<timestamp_ms>.jpg`

- `timestamp_ms`: Milliseconds since Unix epoch (integer)
- Example: `frame_1651316400123.jpg` (captured at 2022-04-29 10:00:00.123 UTC)

### File Format

- **Codec**: JPEG (preferred) or PNG
- **Resolution**: 640x480 to 1920x1080 (depends on hardware)
- **Color space**: RGB (8-bit per channel)
- **Size**: ~50-500 KB per frame (typical for JPEG)

## Metadata JSON

### File: `metadata.json`

```json
{
  "recording_start": "2026-05-01T10:00:00",
  "recording_start_unix": 1746086400.0,
  "recording_end": "2026-05-01T10:10:00",
  "recording_end_unix": 1746086400.600,
  "recording_duration_seconds": 600.0,
  "total_records": 18000,
  "sensor_configuration": {
    "camera": {
      "device_id": 0,
      "resolution_width": 1280,
      "resolution_height": 720,
      "fps": 30,
      "codec": "MJPEG"
    },
    "gps": {
      "port": "/dev/ttyACM0",
      "baudrate": 9600,
      "type": "NMEA"
    },
    "imu": {
      "enabled": false,
      "sensor_type": "BNO085",
      "i2c_bus": 1,
      "i2c_address": 74,
      "sample_rate_hz": 100
    }
  },
  "synchronization": {
    "reference_source": "gps",
    "max_drift_ms": 100.0,
    "interpolation_method": "nearest_neighbor"
  },
  "notes": "Field test on bicycle path, moderate GPS signal"
}
```

## Validation Rules

### Required Fields
- Every row must have a valid `timestamp`
- Every row must have a valid `image_path`
- Image files must exist and be readable

### Consistency Checks
- Timestamps must be monotonically increasing
- Image filenames must match timestamps in CSV
- No duplicate timestamps

### Data Range Checks
- Latitude: -90 ≤ lat ≤ +90
- Longitude: -180 ≤ lon ≤ +180
- Acceleration: typically |a| < 20 m/s²
- Angular velocity: typically |ω| < 360 °/s

## Validation Tool

```bash
python scripts/validate_dataset.py --dataset-dir ./data/run_001

# Output:
# ✓ CSV valid: 18000 rows
# ✓ Images: 18000 files found
# ✓ Timestamps: monotonically increasing
# ✓ GPS coverage: 17950/18000 (99.7%)
# ✓ IMU coverage: 0/18000 (not enabled)
```

## Archival

### Recommended Format
- **Archive tool**: TAR with gzip compression
- **Command**: `tar -czf run_001.tar.gz data/run_001/`
- **Size reduction**: ~60-70% (JPEG not compressible, CSV highly compressible)

### Storage
- **Local**: SSD for speed (~50-100 MB/min at 30 fps, 1280x720)
- **Cloud**: Upload to S3, Google Cloud, or university storage
- **Backup**: Keep redundant copies; datasets are irreplaceable

## Example Processing

```python
import pandas as pd
import cv2
from pathlib import Path

# Load dataset
dataset_dir = Path("data/run_001")
df = pd.read_csv(dataset_dir / "data.csv")

# Print statistics
print(f"Total records: {len(df)}")
print(f"Duration: {df['timestamp'].max() - df['timestamp'].min():.1f}s")
print(f"GPS coverage: {(df['latitude'].notna().sum() / len(df) * 100):.1f}%")

# Load first frame
first_image = cv2.imread(str(dataset_dir / df['image_path'].iloc[0]))
print(f"Image shape: {first_image.shape}")
```
