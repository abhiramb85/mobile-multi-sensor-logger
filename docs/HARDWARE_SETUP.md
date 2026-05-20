# Hardware Setup Guide

## Supported Components

### Camera
- **Logitech C920 HD**: USB, 1080p, stable, recommended for development
- **Raspberry Pi Camera v2**: CSI, 8MP, requires RPi; better for timestamp sync
- Other USB cameras supported by OpenCV

### GPS Module
- **u-blox NEO-6M**: USB or serial UART, NMEA protocol, commonly available
- **u-blox NEO-7M/8M**: Newer versions, higher accuracy (±2.5m)
- Any NMEA-compatible GPS module

### IMU (Optional)
- **MPU-6050**: I2C, 6-DOF, cheap, common
- **LSM6DSL**: I2C/SPI, 6-DOF, lower power
- **ICM-20689**: SPI, high-performance alternative

### Compute Platform
- **Raspberry Pi 4B** (4GB+): Recommended, tested, plug-and-play USB support
- **Raspberry Pi 3B+**: Slower, may struggle with 30+ fps capture
- **Jetson Nano**: Overkill for logging, good if adding ML later
- Any Linux system with USB support (Intel NUC, laptop, etc.)

## Raspberry Pi 4 Assembly

### Required
- Raspberry Pi 4 (4GB or 8GB)
- 64GB microSD card (class 10, fast)
- USB power adapter (5V 3A minimum)
- Logitech C920 USB camera
- u-blox NEO-6M GPS module (USB version)

### Optional
- MPU-6050 IMU breakout board
- Breadboard and jumper wires (for I2C)
- USB hub (if > 3 USB devices)
- Weatherproof enclosure

### Wiring

#### USB Connections
- Camera → USB port 1
- GPS (if USB) → USB port 2
- Power → Micro USB

#### I2C Connections (for IMU)
- MPU-6050 VCC → RPi 3.3V (pin 1)
- MPU-6050 GND → RPi GND (pin 6)
- MPU-6050 SDA → RPi GPIO 2 (pin 3)
- MPU-6050 SCL → RPi GPIO 3 (pin 5)

#### Serial Connections (if using serial GPS)
- GPS TX → RPi RX (GPIO 15, pin 10)
- GPS RX → RPi TX (GPIO 14, pin 8)
- GPS GND → RPi GND (pin 6)

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
   sudo apt install -y python3-pip python3-venv python3-dev
   
   # Create virtual environment
   python3 -m venv /path/to/mobile-multi-sensor-logger/venv
   source venv/bin/activate
   
   # Install project dependencies
   pip install -r requirements.txt
   
   # Optional: IMU libraries (if using IMU)
   pip install adafruit-circuitpython-mpu6050
   ```

## Testing Sensors

### Test Camera
```bash
python3 -c "import cv2; cap = cv2.VideoCapture(0); print(cap.get(cv2.CAP_PROP_FRAME_COUNT))"
```

### Test GPS
```bash
# If USB connection
cat /dev/ttyUSB0 115200
# Should show NMEA sentences starting with $G

# If serial connection (RPi)
minicom -D /dev/ttyAMA0 -b 9600
```

### Test IMU (if enabled)
```python
from adafruit_mpu6050 import Adafruit_MPU6050
import board
import busio

i2c = busio.I2C(board.SCL, board.SDA)
mpu = Adafruit_MPU6050(i2c)
print(mpu.acceleration, mpu.gyro)
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
- [ ] GPS getting fixes: `cat /dev/ttyUSB0` (watch for NMEA `$GPA` sentences with A = active)
- [ ] IMU responding (if enabled): `i2cdetect -y 1` (should show 0x68)
- [ ] Storage space: `df -h` (ensure >50GB free)
- [ ] Battery/power: Adequate for planned duration
- [ ] Network connectivity: Not required for logging, but helpful for monitoring

## Troubleshooting

### Camera Not Found
```bash
# List devices
ls /dev/video*

# Adjust --camera-id to match (usually 0 or 1)
python src/main.py --camera-id 0
```

### GPS Not Getting Fix
- Ensure antenna is outdoors and away from metal
- Wait 30-60 seconds (cold start)
- Check NMEA output: `cat /dev/ttyUSB0` should show $GPRMC or $GPGGA with status A (active)
- Verify baud rate (usually 9600)

### Low Frame Rate / Dropped Frames
- Reduce resolution: `--fps 15` or adjust in src/core/config.py
- Monitor CPU: `top` or `htop`
- Consider USB hub if multiple devices compete for bandwidth

### I2C Device Not Found
```bash
i2cdetect -y 1
# Should show device address (0x68 for MPU-6050)
# If not found: check wiring, run `sudo i2cdetect -r 1` to detect
```

## Performance Tips

1. **Use buffering**: Enable async writes to prevent data loss
2. **Reduce resolution**: 640x480 @ 15 fps often better than 1280x720 @ 30 fps on RPi
3. **SSD vs microSD**: Fast storage critical; consider USB 3.0 external SSD
4. **Dedicated power**: Use quality USB adapter, avoid underpowering RPi
5. **Thermal management**: Consider heatsinks/fan for long runs in hot weather
