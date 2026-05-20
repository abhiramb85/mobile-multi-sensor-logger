# Development Roadmap

## Phase 1: Project Setup & Architecture ✓
- [x] Initialize repository structure
- [x] Create Python environment and dependencies
- [x] Define core data structures
- [x] Create configuration schemas

## Phase 2: Sensor Data Acquisition Modules ✓
- [x] Camera driver — OpenCV-based, real + mock (`src/sensors/camera.py`)
- [x] GPS driver — pyserial NMEA-0183 parser (RMC + GGA, any talker ID), real + mock (`src/sensors/gps.py`)
- [x] IMU driver — BNO055 over I2C via Adafruit Blinka, real + mock (`src/sensors/imu.py`)
- [x] Mock fallback for every sensor so the pipeline runs end-to-end with no hardware
- [x] Background sampler threads for GPS and IMU so the acquisition loop never blocks on a slow read
- [x] NMEA checksum verification + status='V' / fix-quality=0 sentences ignored
- [ ] Long-duration sensor reliability test (100+ samples each, error injection)
- [ ] Handle sensor disconnects mid-run (USB hot-unplug, I2C bus hang)

## Phase 3: Synchronization & Logging Core
- [x] Timestamp synchronizer sketch (`src/core/sync.py`)
- [x] Data logger sketch (`src/core/logger.py`)
- [x] Main orchestrator sketch (`src/main.py`)
- [ ] Integrate and test synchronization (5-minute lab run)
- [ ] Validate CSV format and file consistency
- [ ] Profile performance on target hardware (Raspberry Pi)

## Phase 4: Visualization & Replay Tool
- [x] Replay tool skeleton (`src/tools/replay.py`)
- [ ] Test video playback with overlays
- [ ] Implement GPS map generation (folium)
- [ ] Add IMU telemetry plots (matplotlib)
- [ ] Add seek/pause controls

## Phase 5: Integration, Testing & Validation
- [ ] End-to-end lab test (camera + GPS + optional IMU)
- [ ] Short mobility test (5-minute walk)
- [ ] Full bicycle/platform test (30+ minutes)
- [ ] Document any issues and limitations
- [ ] Create example dataset for testing

## Future Enhancements
- [ ] Kalman filtering for better timestamp synchronization
- [ ] Support for additional sensor types (barometer, magnetometer)
- [ ] Web-based replay interface
- [ ] Real-time monitoring dashboard
- [ ] Data quality metrics and validation reports
- [ ] Hardware-specific optimization guides

## Testing Checklist

### Unit Tests
- [ ] Camera driver captures frames at target FPS
- [ ] GPS parser handles valid/invalid NMEA sentences
- [ ] Sync engine correctly interpolates timestamps
- [ ] Logger produces valid CSV format
- [ ] Config schemas validate properly

### Integration Tests
- [ ] All sensors start/stop without errors
- [ ] Synchronized records contain all required fields
- [ ] Images linked correctly in CSV
- [ ] Replay tool reads and displays dataset

### Real-World Validation
- [ ] 30+ minute bicycle run, no data loss
- [ ] GPS accuracy verified against ground truth
- [ ] Timestamp drift < 100ms over 1 hour
- [ ] Frame rate maintained under load

## Known Issues & TODOs

1. **IMU integration**: BNO055 driver implemented. Driver exposes the full fusion outputs internally (quaternion, Euler, linear acceleration) but only `ax/ay/az/gx/gy/gz` are persisted to CSV, per the fixed schema. Extending the schema is a future task.
2. **USB camera timestamps**: Drifts over time. RPi CSI camera recommended for better sync — would require a separate picamera2 code path on Pi 5.
3. **GPS cold start**: 30+ seconds typical in open sky. Document in user guide.
4. **Performance**: Raspberry Pi 4 may bottleneck at >20 fps full resolution. Test early on Pi 5 (USB 3.0 gives more headroom).
5. **Real-hardware testing on Pi 5**: All real drivers exist but haven't been validated end-to-end on the user's actual hardware (12 MP USB camera, Navilock NL-852EUSB GPS, BNO055 IMU).

## Next Steps

1. **Immediate** (Week 1): 
   - Select and acquire hardware components
   - Test individual sensor drivers on target platform
   - Set up version control and CI/CD

2. **Short-term** (Weeks 2-3):
   - Implement full sensor integration
   - Conduct lab tests
   - Profile performance

3. **Long-term** (Weeks 4-5):
   - Real-world field tests
   - Finalize documentation
   - Package for release
