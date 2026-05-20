# Troubleshooting Guide

## Common Issues

### 1. Camera Not Detected

**Symptom**: `Failed to open camera device 0`

**Solutions**:
- Check USB connection: `lsusb` should show device
- List available cameras: `ls /dev/video*`
- Try different device ID: `--camera-id 1` or `--camera-id 2`
- Verify permissions: `sudo usermod -a -G video $USER`

### 2. GPS Not Getting Fix

**Symptom**: `GPS: No valid fix` or empty latitude/longitude in CSV

**Causes**:
- Antenna not outdoors or blocked
- Wrong serial port
- Incorrect baud rate
- Cold start (first fix takes 30-60 seconds)

**Solutions**:
```bash
# Test GPS directly — try ttyACM0 first (native USB modules like Navilock NL-852EUSB)
cat /dev/ttyACM0
# For USB-to-serial bridges:
cat /dev/ttyUSB0
# For UART-connected GPS (Pi GPIO 14/15):
cat /dev/serial0

# Look for lines like:
# $GNRMC,hhmmss.ss,A,ddmm.mmmm,N,dddmm.mmmm,E,...   (multi-GNSS)
# $GPRMC,hhmmss.ss,A,ddmm.mmmm,N,dddmm.mmmm,E,...   (GPS-only)
# Status 'A' = active fix, 'V' = void (no fix). Outdoors, void for the first ~30 s is normal.

# Check which port the device enumerated as:
dmesg | grep -E "ttyACM|ttyUSB"
```

### 3. Low Frame Rate / Frame Drops

**Symptom**: Recording shows `[X frames/s]` << 30 fps target

**Causes**:
- Raspberry Pi CPU saturated
- Slow storage (microSD bottleneck)
- USB bandwidth contention
- OpenCV codec overhead

**Solutions**:
```bash
# Monitor CPU usage
top
# If >90% on core, try:
# - Reduce resolution: 1280x720 → 640x480
# - Reduce FPS: 30 → 15
# - Disable other processes

# Check storage speed
dd if=/dev/zero of=testfile bs=1M count=100 oflag=dsync
# Should see >20 MB/s; if <10 MB/s, upgrade to faster card

# Use USB hub to isolate camera
# Or upgrade to USB 3.0 external SSD for data
```

### 4. IMU Not Responding

**Symptom**: `Error starting IMU` or `IMU device not found`

**Check I2C bus**:
```bash
i2cdetect -y 1
# Expected addresses:
#   0x28 = BNO055 (default, ADR pin low)
#   0x29 = BNO055 (ADR pin high)
#   0x68 = MPU-6050 (not supported by current driver)
# If shows UU: device in use by kernel driver — fine, userspace library still works
# If shows --: device not responding (check wiring)
```

**Wiring checklist (BNO055)**:
- VIN → 3.3V (Adafruit breakouts have a regulator but stick to 3.3 V)
- GND → GND
- SDA → GPIO 2 (pin 3)
- SCL → GPIO 3 (pin 5)
- (Optional) ADR pin: tie to GND for `0x28` (default) or 3.3V for `0x29`
- Most breakouts have onboard SDA/SCL pullups; bare chips need 4.7 kΩ pullups

### 5. CSV Corruption / Missing Rows

**Symptom**: CSV file incomplete after unexpected stop

**Causes**:
- Program crashed
- Power loss
- Storage full

**Prevention**:
```python
# Use async buffering (added in Phase 3)
# Ensure adequate storage: `df -h` before recording
# Check free space: df -h | grep "/$"
```

**Recovery**:
- CSV is text-based, may be partially recoverable
- Images still useful for manual review
- Always keep backups of raw data

### 6. Timestamp Drift (GPS vs Camera)

**Symptom**: Synchronized replay shows images lagging GPS on map

**Causes**:
- USB camera timestamp unreliable
- Asynchronous sensor clocks
- Scheduler jitter on single-core systems

**Mitigation**:
- Use Raspberry Pi CSI camera (better hardware sync)
- Use external NTP sync if available
- Accept ±100ms drift as acceptable (noted in metadata)

### 7. Storage Space Issues

**Symptom**: `No space left on device` mid-recording

**Estimate space needed**:
```
Data rate = (image_size_KB × fps) + (GPS_IMU_overhead)
         ≈ (150 KB × 30 fps) + 1 KB = ~4.5 MB/s ≈ 270 MB/min

For 1 hour: ~16 GB
For 8 hours: ~130 GB (use external USB SSD)
```

**Solutions**:
- Use external SSD: `--output-dir /mnt/usb/data/`
- Reduce image resolution/quality
- Post-process: compress PNGs to JPEGs
- Stream to cloud (not recommended for reliability)

### 8. Power Issues

**Symptom**: Raspberry Pi crashes/reboots during recording

**Causes**:
- Inadequate power supply
- Voltage droop under USB load

**Solutions**:
- Use 5V 3A adapter (not 2A)
- Add capacitor near RPi: 470µF between 5V and GND
- Monitor voltage: `vcgencmd measure_volts core`

## Performance Profiling

```bash
# Record system metrics during acquisition
python -m src.main --output-dir ./test_run &
PID=$!

# In another terminal
watch -n 1 'top -p '$PID' -b | head -15'
watch -n 1 'df -h /dev/sda1'

# Stop after 5 minutes
sleep 300 && kill $PID
```

## Logging & Debug Output

Enable verbose logging:
```python
# In src/main.py, add:
import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s: %(message)s')
```

## Support Resources

- **OpenCV issues**: https://docs.opencv.org/
- **GPS/NMEA spec**: https://www.sparkfun.com/datasheets/GPS/NMEA%20Reference%20Manual1.pdf
- **Raspberry Pi docs**: https://www.raspberrypi.com/documentation/
- **BNO055 datasheet**: Bosch Sensortec (search "BST-BNO055-DS000")
- **Adafruit BNO055 library**: https://docs.circuitpython.org/projects/bno055/en/latest/

## Report an Issue

When reporting problems:
1. Provide hardware configuration (camera model, GPS type, RPi version)
2. Show full error output with `-v` or debug logging enabled
3. Include relevant files: metadata.json, first 10 rows of data.csv
4. Describe what you were doing when error occurred
