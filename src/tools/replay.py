"""Replay tool for synchronized visualization of recorded data."""

import argparse
import csv
import json
from pathlib import Path
from typing import List, Dict
import time

import cv2
try:
    import folium
    HAS_FOLIUM = True
except ImportError:
    HAS_FOLIUM = False

try:
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


class DatasetReplayer:
    """Replays and visualizes synchronized multi-sensor dataset."""
    
    def __init__(self, dataset_dir: Path):
        """
        Initialize replayer.
        
        Args:
            dataset_dir: Path to recorded dataset (with data.csv, images/, metadata.json)
        """
        self.dataset_dir = Path(dataset_dir)
        self.images_dir = self.dataset_dir / "images"
        self.csv_path = self.dataset_dir / "data.csv"
        self.metadata_path = self.dataset_dir / "metadata.json"
        
        self.records = []
        self.metadata = {}
        
        self._validate_dataset()
        self._load_metadata()
        self._load_csv()
    
    def _validate_dataset(self):
        """Validate dataset structure."""
        if not self.csv_path.exists():
            raise FileNotFoundError(f"Missing data.csv at {self.csv_path}")
        if not self.images_dir.exists():
            raise FileNotFoundError(f"Missing images directory at {self.images_dir}")
        print(f"Dataset validated: {self.dataset_dir}")
    
    def _load_metadata(self):
        """Load metadata.json."""
        try:
            if self.metadata_path.exists():
                with open(self.metadata_path, 'r') as f:
                    self.metadata = json.load(f)
                print(f"Metadata loaded: {len(self.metadata)} keys")
        except Exception as e:
            print(f"Warning: Could not load metadata: {e}")
    
    def _load_csv(self):
        """Load synchronized sensor log from CSV."""
        try:
            with open(self.csv_path, 'r') as f:
                reader = csv.DictReader(f)
                self.records = list(reader)
            print(f"Loaded {len(self.records)} records from CSV")
        except Exception as e:
            print(f"Error loading CSV: {e}")
            raise
    
    def get_record_count(self) -> int:
        """Get total records in dataset."""
        return len(self.records)

    @staticmethod
    def _maybe_float(value):
        """Convert a CSV cell to float, returning None for blank/'None'/garbage."""
        if value is None or value == "" or value == "None":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    
    def replay_video(self, speed: float = 1.0, window_name: str = "Replay"):
        """
        Play synchronized video with GPS/IMU overlay.

        Args:
            speed: Playback speed multiplier (1.0 = real-time)
            window_name: OpenCV window title
        """
        if not self.records:
            print("No records to replay")
            return

        # Probe whether OpenCV can actually open a window in this environment.
        # On a headless Pi / SSH session this raises cv2.error; bail cleanly.
        try:
            cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
        except cv2.error as e:
            print(f"No display available, skipping video playback ({e})")
            print("Use --no-video to suppress this attempt, or run on a machine with a GUI.")
            return

        print(f"\nReplaying {len(self.records)} frames at {speed}x speed")
        print("Controls: SPACE=pause, ESC=quit, LEFT/RIGHT=seek")

        paused = False
        current_idx = 0

        while current_idx < len(self.records):
            record = self.records[current_idx]

            image_path = self.images_dir / Path(record['image_path']).name
            if not image_path.exists():
                print(f"Image not found: {image_path}")
                current_idx += 1
                continue

            frame = cv2.imread(str(image_path))
            if frame is None:
                current_idx += 1
                continue

            self._draw_overlay(frame, record)
            cv2.imshow(window_name, frame)

            key = cv2.waitKey(int(33 / speed)) & 0xFF  # 30 fps base

            if key == ord(' '):  # SPACE: pause
                paused = not paused
            elif key == 27:  # ESC: quit
                break
            elif key == 81 or key == ord('d'):  # LEFT: seek back
                current_idx = max(0, current_idx - 10)
            elif key == 83 or key == ord('a'):  # RIGHT: seek forward
                current_idx = min(len(self.records) - 1, current_idx + 10)

            if not paused:
                current_idx += 1

        cv2.destroyAllWindows()
        print("Replay finished")
    
    def _draw_overlay(self, frame, record: Dict):
        """Draw GPS and IMU data on video frame."""
        ts = self._maybe_float(record.get("timestamp"))
        lat = self._maybe_float(record.get("latitude"))
        lon = self._maybe_float(record.get("longitude"))
        ax = self._maybe_float(record.get("ax"))
        ay = self._maybe_float(record.get("ay"))
        az = self._maybe_float(record.get("az"))
        gx = self._maybe_float(record.get("gx"))
        gy = self._maybe_float(record.get("gy"))
        gz = self._maybe_float(record.get("gz"))

        text_lines = [
            f"t = {ts:.3f}" if ts is not None else "t = N/A",
            f"GPS: {lat:.6f}, {lon:.6f}" if (lat is not None and lon is not None) else "GPS: (no fix)",
        ]
        if None not in (ax, ay, az):
            text_lines.append(f"a (m/s^2): {ax:+6.2f} {ay:+6.2f} {az:+6.2f}")
        if None not in (gx, gy, gz):
            text_lines.append(f"w (deg/s): {gx:+7.2f} {gy:+7.2f} {gz:+7.2f}")

        y_offset = 30
        for line in text_lines:
            cv2.putText(frame, line, (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, (0, 255, 0), 2)
            y_offset += 25
    
    def generate_map(self, output_path: str = "replay_map.html"):
        """
        Generate interactive map with GPS trajectory.
        
        Args:
            output_path: HTML output filename
        """
        if not HAS_FOLIUM:
            print("folium not installed. Install with: pip install folium")
            return
        
        # Extract GPS points
        points = []
        for record in self.records:
            lat = record.get('latitude')
            lon = record.get('longitude')
            if lat and lon and lat != 'None' and lon != 'None':
                try:
                    points.append([float(lat), float(lon)])
                except ValueError:
                    pass
        
        if not points:
            print("No GPS points found in dataset")
            return
        
        # Create map centered on first point
        start_point = points[0]
        m = folium.Map(location=start_point, zoom_start=15)
        
        # Add trajectory
        folium.PolyLine(points, color='blue', weight=2, opacity=0.7).add_to(m)
        
        # Add markers for start and end
        folium.Marker(points[0], popup='Start', icon=folium.Icon(color='green')).add_to(m)
        folium.Marker(points[-1], popup='End', icon=folium.Icon(color='red')).add_to(m)
        
        # Save
        m.save(output_path)
        print(f"Map saved to {output_path}")
    
    def generate_telemetry_plot(self, output_path: str = "replay_telemetry.png"):
        """
        Generate a plot of all six IMU channels (accel + gyro) over time.

        Args:
            output_path: PNG output filename
        """
        if not HAS_MATPLOTLIB:
            print("matplotlib not installed. Install with: pip install matplotlib")
            return

        timestamps = []
        ax_s, ay_s, az_s = [], [], []
        gx_s, gy_s, gz_s = [], [], []

        for record in self.records:
            ts = self._maybe_float(record.get("timestamp"))
            ax = self._maybe_float(record.get("ax"))
            ay = self._maybe_float(record.get("ay"))
            az = self._maybe_float(record.get("az"))
            gx = self._maybe_float(record.get("gx"))
            gy = self._maybe_float(record.get("gy"))
            gz = self._maybe_float(record.get("gz"))
            if None in (ts, ax, ay, az, gx, gy, gz):
                continue
            timestamps.append(ts)
            ax_s.append(ax); ay_s.append(ay); az_s.append(az)
            gx_s.append(gx); gy_s.append(gy); gz_s.append(gz)

        if not timestamps:
            print("No telemetry data found")
            return

        t0 = min(timestamps)
        t = [ts - t0 for ts in timestamps]

        fig, (top, bot) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

        top.plot(t, ax_s, label="ax", alpha=0.8)
        top.plot(t, ay_s, label="ay", alpha=0.8)
        top.plot(t, az_s, label="az", alpha=0.8)
        top.set_ylabel("Acceleration (m/s²)")
        top.set_title(f"IMU Telemetry ({len(t)} samples)")
        top.legend(loc="upper right")
        top.grid(True, alpha=0.3)

        bot.plot(t, gx_s, label="gx", alpha=0.8)
        bot.plot(t, gy_s, label="gy", alpha=0.8)
        bot.plot(t, gz_s, label="gz", alpha=0.8)
        bot.set_xlabel("Time (s)")
        bot.set_ylabel("Angular velocity (deg/s)")
        bot.legend(loc="upper right")
        bot.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(output_path, dpi=120)
        plt.close(fig)
        print(f"Telemetry plot saved to {output_path}")


def main():
    """Main entry point for replay tool."""
    parser = argparse.ArgumentParser(description="Replay synchronized dataset")
    parser.add_argument(
        "--dataset-dir", "-d",
        type=str,
        required=True,
        help="Dataset directory (with data.csv, images/)"
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Playback speed (1.0 = real-time)"
    )
    parser.add_argument(
        "--map",
        action="store_true",
        help="Generate GPS trajectory map"
    )
    parser.add_argument(
        "--telemetry",
        action="store_true",
        help="Generate IMU telemetry plot"
    )
    parser.add_argument(
        "--no-video",
        action="store_true",
        help="Skip the video playback step (useful when running headless / over SSH)"
    )

    args = parser.parse_args()

    try:
        replayer = DatasetReplayer(args.dataset_dir)
    except Exception as e:
        print(f"Error loading dataset: {e}")
        return

    if args.map:
        replayer.generate_map()
    if args.telemetry:
        replayer.generate_telemetry_plot()

    if not args.no_video:
        replayer.replay_video(speed=args.speed)


if __name__ == "__main__":
    main()
