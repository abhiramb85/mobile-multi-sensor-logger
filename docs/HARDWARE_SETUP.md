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
- **Bosch BNO055** (9-DOF with onboard sensor fusion): I2C, default address `0x28` (Adafruit breakouts), alt `0x29` if ADR pin tied high. Outputs accel/gyro/mag plus quaternion/Euler/calibration status from hardware fusion (NDOF mode). This is the tested module.
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
- BNO055 IMU breakout board (Adafruit or equivalent)
- Breadboard and jumper wires (for I2C)
- USB hub (if > 3 USB devices)
- Weatherproof enclosure

### Wiring

#### USB Connections
- Camera → USB port (prefer USB 3.0 / blue on Pi 4; either port on Pi 5)
- GPS (Navilock NL-852EUSB) → any USB port → enumerates as `/dev/ttyACM0`
- Power → USB-C (Pi 5) or USB-C/micro-USB (Pi 4)

#### I2C Connections (for BNO055 IMU)
- BNO055 VIN → RPi 3.3V (pin 1)  *(do NOT use 5V — the BNO055 chip itself is 3.3 V; Adafruit breakouts have a regulator but 3.3 V is safe everywhere)*
- BNO055 GND → RPi GND (pin 6)
- BNO055 SDA → RPi GPIO 2 (pin 3)
- BNO055 SCL → RPi GPIO 3 (pin 5)
- (Optional) BNO055 ADR → GND for `0x28` (default), or 3.3V for `0x29`

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
   # adafruit-circuitpython-bno055, and adafruit-blinka)
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

### Test IMU (BNO055)
```bash
# First confirm the chip is on the bus
i2cdetect -y 1
# Expect "28" in the grid (or "29" if ADR is high). "UU" means a kernel driver
# has claimed the address — fine, the userspace library still works.
```
```python
import board, busio, adafruit_bno055
i2c = busio.I2C(board.SCL, board.SDA)
sensor = adafruit_bno055.BNO055_I2C(i2c)  # add address=0x29 if you tied ADR high
print("accel:", sensor.acceleration)        # m/s^2, includes gravity
print("gyro:", sensor.gyro)                  # deg/s
print("euler:", sensor.euler)                # heading, roll, pitch (deg)
print("calibration:", sensor.calibration_status)  # (sys, gyro, accel, mag), each 0-3
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
# Should show "28" for BNO055 (or "29" if ADR pin tied high)
# If not found: check wiring, ensure VIN→3.3V not 5V, run `sudo i2cdetect -r 1` to retry
```

## Performance Tips

1. **Use buffering**: Enable async writes to prevent data loss
2. **Reduce resolution**: 640x480 @ 15 fps often better than 1280x720 @ 30 fps on RPi
3. **SSD vs microSD**: Fast storage critical; consider USB 3.0 external SSD
4. **Dedicated power**: Use quality USB adapter, avoid underpowering RPi
5. **Thermal management**: Consider heatsinks/fan for long runs in hot weather
