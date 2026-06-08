# Hardware Setup Guide

## Supported Components

### Camera
- **Any USB UVC webcam**: works out-of-the-box via OpenCV (`cv2.VideoCapture`). Tested target: a 12 MP USB camera at 1280×720.
- **Logitech C920 HD**: USB, 1080p, well-known reference.
- **Raspberry Pi Camera Module (CSI ribbon)**: NOT supported by the current driver on Pi 5 — would need a separate picamera2/libcamera code path.

### GPS Module
- **Navilock NL-852EUSB** (u-blox 8 UBX-M8030-KT): native USB CDC, shows up as `/dev/ttyACM0`. Multi-GNSS (GPS+GLONASS+BeiDou+Galileo+QZSS), 2.5 m CEP, ~26 s cold start. This is the tested module.
- **u-blox NEO-6M/7M/8M USB**: equivalent; same driver works.
- **Any NMEA-0183 module** (USB or UART): the driver parses RMC + GGA from any talker ID (`$GP`, `$GN`, `$GL`, `$GA`, …) and verifies the `*XX` checksum.

### IMU (Optional)
- **Bosch BNO085** (9-DOF with onboard sensor fusion, SH-2 protocol): I2C, default address `0x4a` (Adafruit breakouts). Outputs accel/gyro/mag plus quaternion, game-rotation, linear acceleration, gravity, and calibration status. This is the tested module.
- Other I2C IMUs (MPU-6050, ICM-20948, LSM6DSL) are not currently supported — would need a new driver in `src/sensors/imu.py`.

### Compute Platform
- **Raspberry Pi 5**: tested target; USB 3.0 gives plenty of headroom for camera + GPS over USB.
- **Raspberry Pi 4B** (4GB+): also works; may bottleneck above ~20 fps at full resolution.
- **Raspberry Pi 3B+**: slower, may struggle with 30+ fps capture.
- Any Linux system with USB and I2C support.

## Raspberry Pi Assembly

### Required
- Raspberry Pi 4 (4GB+) or Raspberry Pi 5
- Fast storage (64GB+ microSD class 10, or USB SSD on Pi 5 — strongly recommended for sustained 30 fps recording)
- USB power adapter (5V 3A for Pi 4; 5V 5A USB-C for Pi 5)
- USB UVC camera (12 MP USB camera, Logitech C920, etc.)
- USB GPS module (Navilock NL-852EUSB recommended)

### Optional
- BNO085 IMU breakout board (Adafruit or equivalent)
- (Recommended) STEMMA QT JST-SH-to-Dupont cable (Adafruit 4397) for one-step wiring
- Breadboard and jumper wires (for I2C)
- USB hub (if > 3 USB devices)
- Weatherproof enclosure

### Wiring

#### USB Connections
- Camera → USB port (prefer USB 3.0 / blue on Pi 4; either port on Pi 5)
- GPS (Navilock NL-852EUSB) → any USB port → enumerates as `/dev/ttyACM0`
- Power → USB-C (Pi 5) or USB-C/micro-USB (Pi 4)

#### I2C Connections (for BNO085 IMU)
Easiest path: an Adafruit STEMMA QT cable (part 4397) — plug the JST-SH end into either STEMMA QT port on the breakout and the four Dupont ends onto pins 1, 3, 5, 6 on the Pi header.

Manual wiring (4 wires):
- BNO085 VIN → RPi 3.3V (pin 1)  *(stick to 3.3 V; the chip itself is 3.3 V even though Adafruit breakouts have a regulator)*
- BNO085 GND → RPi GND (pin 6)
- BNO085 SDA → RPi GPIO 2 (pin 3)
- BNO085 SCL → RPi GPIO 3 (pin 5)

For Pi 5, set I2C to 400 kHz in `/boot/firmware/config.txt` (the BNO085 SH-2 protocol works much more reliably at higher I2C speeds):
```
dtparam=i2c_arm=on,i2c_arm_baudrate=400000
```

#### Serial Connections (only if using a UART GPS instead of USB)
- GPS TX → RPi RX (GPIO 15, pin 10)
- GPS RX → RPi TX (GPIO 14, pin 8)
- GPS GND → RPi GND (pin 6)
- Note: on Pi 5 the UART overlay is enabled via `/boot/firmware/config.txt` (not `/boot/config.txt`).

### Software Setup

1. **Raspberry Pi OS Installation**
   ```bash
   # Use Raspberry Pi Imager to flash 64-bit Raspberry Pi OS Lite
   # Enable SSH in imager settings
   ```

2. **System Configuration**
   ```bash
   sudo apt update
   sudo apt upgrade -y
   
   # Enable I2C (if using IMU)
   sudo raspi-config
   # Navigate to Interface Options → I2C → Enable
   
   # Enable Serial (if using serial GPS)
   sudo raspi-config
   # Navigate to Interface Options → Serial → Enable
   ```

3. **Install Python Dependencies**
   ```bash
   sudo apt install -y python3-pip python3-venv python3-dev libgl1 i2c-tools
   
   # Create virtual environment
   cd /path/to/mobile-multi-sensor-logger
   python3 -m venv venv
   source venv/bin/activate
   
   # Install project dependencies (includes opencv-python, pyserial,
   # adafruit-circuitpython-bno08x, adafruit-blinka, and lgpio)
   pip install -r requirements.txt
   ```

## Testing Sensors

### Test Camera
```bash
# Grab one frame and print its shape — proves the camera works end-to-end.
python3 -c "import cv2; c=cv2.VideoCapture(0); ok,f=c.read(); print('ok=',ok,'shape=',None if f is None else f.shape); c.release()"
```

### Test GPS
```bash
# Native-USB GPS modules (Navilock NL-852EUSB, most u-blox 7/8 USB)
cat /dev/ttyACM0
# USB-to-serial bridge modules (FTDI, CP2102, PL2303)
cat /dev/ttyUSB0
# UART-connected GPS (Pi GPIO 14/15)
cat /dev/serial0
# Should show NMEA sentences. Multi-GNSS modules use $GN prefix:
#   $GNRMC,hhmmss.ss,A,ddmm.mmmm,N,dddmm.mmmm,E,...
# Status 'A' = active fix, 'V' = void (no fix yet). Outdoors, expect 'V' for the first ~30 s.
# Press Ctrl+C to stop.
```

### Test IMU (BNO085)
```bash
# First confirm the chip is on the bus
i2cdetect -y 1
# Expect "4a" in the grid. "UU" means a kernel driver has claimed the address — fine,
# the userspace library still works.
```
```python
import board, busio
from adafruit_bno08x.i2c import BNO08X_I2C
from adafruit_bno08x import BNO_REPORT_ACCELEROMETER, BNO_REPORT_GYROSCOPE

i2c = busio.I2C(board.SCL, board.SDA, frequency=400_000)
sensor = BNO08X_I2C(i2c)                          # default address 0x4a
sensor.enable_feature(BNO_REPORT_ACCELEROMETER)
sensor.enable_feature(BNO_REPORT_GYROSCOPE)

import time; time.sleep(0.5)                       # SH-2 needs a moment to start reports
print("accel:", sensor.acceleration)               # m/s^2, includes gravity
print("gyro:",  sensor.gyro)                       # rad/s — convert *180/π for deg/s
```

## Outdoor Testing

### Location Recommendations
- **Open field**: Best GPS fix, 2-5 meters accuracy
- **Urban park**: Moderate GPS, some multipath interference
- **Bicycle path**: Good for testing along linear routes
- **Avoid**: Tunnels, dense trees, tall buildings (GPS won't fix)

### Pre-Test Checklist
- [ ] All USB devices detected: `lsusb`
- [ ] Camera accessible: `ls /dev/video*`
- [ ] GPS getting fixes: `cat /dev/ttyACM0` (watch for `$GNRMC`/`$GNGGA` sentences with status `A` = active)
- [ ] IMU responding (if enabled): `i2cdetect -y 1` (should show `28`, or `29` if ADR high)
- [ ] Storage space: `df -h` (ensure >50GB free)
- [ ] Battery/power: Adequate for planned duration
- [ ] Network connectivity: Not required for logging, but helpful for monitoring

## Troubleshooting

### Camera Not Found
```bash
# List devices
ls /dev/video*

# Adjust --camera-id to match (usually 0 or 1)
python -m src.main --real-camera --camera-id 0
```

### GPS Not Getting Fix
- Ensure antenna is outdoors and away from metal
- Wait 30-60 seconds (cold start; Navilock NL-852EUSB spec is ~26 s)
- Check NMEA output: `cat /dev/ttyACM0` should show `$GNRMC` or `$GNGGA` with status `A` (active)
- Wrong port? Try `cat /dev/ttyUSB0` or `cat /dev/serial0`
- For USB CDC modules (like the Navilock) the baud rate setting is mostly cosmetic — USB is packet-based

### Low Frame Rate / Dropped Frames
- Reduce resolution: `--fps 15` or adjust in `src/core/config.py`
- Monitor CPU: `top` or `htop`
- Consider USB hub if multiple devices compete for bandwidth

### I2C Device Not Found
```bash
i2cdetect -y 1
# Should show "4a" for BNO085
# If not found: check wiring, ensure VIN→3.3V not 5V, run `sudo i2cdetect -r 1` to retry
```

## Performance Tips

1. **Use buffering**: Enable async writes to prevent data loss
2. **Reduce resolution**: 640x480 @ 15 fps often better than 1280x720 @ 30 fps on RPi
3. **SSD vs microSD**: Fast storage critical; consider USB 3.0 external SSD
4. **Dedicated power**: Use quality USB adapter, avoid underpowering RPi
5. **Thermal management**: Consider heatsinks/fan for long runs in hot weather
