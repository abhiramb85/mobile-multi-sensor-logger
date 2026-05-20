# Development Roadmap

## Phase 1: Project Setup & Architecture ✓
- [x] Initialize repository structure
- [x] Create Python environment and dependencies
- [x] Define core data structures
- [x] Create configuration schemas

## Phase 2: Sensor Data Acquisition Modules (In Progress)
- [x] Camera driver skeleton (`src/sensors/camera.py`)
- [x] GPS driver skeleton (`src/sensors/gps.py`)
- [x] IMU driver skeleton (`src/sensors/imu.py`)
- [ ] Test each sensor individually (100+ samples each)
- [ ] Handle sensor error conditions (disconnects, timeouts)

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

1. **IMU integration**: Currently placeholder implementation. Awaits hardware selection.
2. **USB camera timestamps**: Drifts over time. RPi CSI camera recommended for better sync.
3. **GPS cold start**: 30+ seconds typical in open sky. Document in user guide.
4. **Performance**: Raspberry Pi 4 may bottleneck at >20 fps full resolution. Test early.

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
