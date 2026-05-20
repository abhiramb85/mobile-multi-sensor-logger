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
        
        print(f"\nReplaying {len(self.records)} frames at {speed}x speed")
        print("Controls: SPACE=pause, ESC=quit, LEFT/RIGHT=seek")
        
        paused = False
        current_idx = 0
        
        while current_idx < len(self.records):
            record = self.records[current_idx]
            
            # Load image
            image_path = self.images_dir / Path(record['image_path']).name
            if not image_path.exists():
                print(f"Image not found: {image_path}")
                current_idx += 1
                continue
            
            frame = cv2.imread(str(image_path))
            if frame is None:
                current_idx += 1
                continue
            
            # Draw overlays
            self._draw_overlay(frame, record)
            
            # Display
            cv2.imshow(window_name, frame)
            
            # Handle keyboard input
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
        h, w = frame.shape[:2]
        
        # Text overlay
        text_lines = [
            f"Time: {record.get('timestamp', 'N/A')}",
            f"Lat: {record.get('latitude', 'N/A')}",
            f"Lon: {record.get('longitude', 'N/A')}",
        ]
        
        # Add IMU if available
        if record.get('ax') and record.get('ax') != 'None':
            text_lines.append(f"Accel: {record.get('ax', 'N/A'):.2f} m/s²")
        
        # Draw text
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
        Generate plot of IMU telemetry over time.
        
        Args:
            output_path: PNG output filename
        """
        if not HAS_MATPLOTLIB:
            print("matplotlib not installed. Install with: pip install matplotlib")
            return
        
        # Extract IMU data
        timestamps = []
        accelerations = []
        
        for record in self.records:
            try:
                ts = float(record.get('timestamp', 0))
                ax = float(record.get('ax', 0)) if record.get('ax') and record.get('ax') != 'None' else 0
                timestamps.append(ts)
                accelerations.append(ax)
            except ValueError:
                pass
        
        if not timestamps:
            print("No telemetry data found")
            return
        
        # Normalize timestamps to start at 0
        if timestamps:
            min_ts = min(timestamps)
            timestamps = [t - min_ts for t in timestamps]
        
        # Plot
        plt.figure(figsize=(12, 4))
        plt.plot(timestamps, accelerations, label='X-Acceleration')
        plt.xlabel('Time (s)')
        plt.ylabel('Acceleration (m/s²)')
        plt.title('IMU Telemetry')
        plt.legend()
        plt.grid(True)
        plt.savefig(output_path)
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
    
    args = parser.parse_args()
    
    # Load dataset
    try:
        replayer = DatasetReplayer(args.dataset_dir)
    except Exception as e:
        print(f"Error loading dataset: {e}")
        return
    
    # Generate outputs
    if args.map:
        replayer.generate_map()
    if args.telemetry:
        replayer.generate_telemetry_plot()
    
    # Replay video
    replayer.replay_video(speed=args.speed)


if __name__ == "__main__":
    main()
