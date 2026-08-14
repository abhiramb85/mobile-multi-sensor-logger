"""Export a recorded dataset to a rosbag2 bag readable by `ros2 bag`.

The acquisition pipeline stays ROS-free (the Pi shouldn't have to carry a ROS 2
install just to log). Instead this tool converts a finished dataset directory
into a rosbag2 bag on the MCAP storage backend, writing CDR-serialized
sensor_msgs so a ROS workstation can `ros2 bag info/play/read` it directly.

Topics produced:
    /gps/fix                        sensor_msgs/msg/NavSatFix
    /imu/data_raw                   sensor_msgs/msg/Imu
    /camera/image_raw/compressed    sensor_msgs/msg/CompressedImage
    /camera/camera_info             sensor_msgs/msg/CameraInfo
    /camera/image_raw               sensor_msgs/msg/Image      (--raw-images)

Usage:
    python src/tools/to_rosbag.py --dataset-dir ./data/run_001
    ros2 bag info ./data/run_001_rosbag
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.tools import ros2_msgs
from src.tools.ros2_common import (
    DEG_TO_RAD,
    TOPIC_GPS,
    TOPIC_IMU,
    TOPIC_IMAGE_COMPRESSED,
    TOPIC_IMAGE_RAW,
    TOPIC_CAMERA_INFO,
    COVARIANCE_TYPE_UNKNOWN,
    STATUS_FIX,
    SERVICE_GPS,
    ORIENTATION_UNAVAILABLE,
    parse_timestamp,
    to_ros_time,
    to_nanoseconds,
)

# rosbag2 metadata format version 5 — understood by Humble through Kilted.
BAG_METADATA_VERSION = 5

_ZERO_COV_9 = [0.0] * 9


def resolve_image(dataset_dir: Path, image_path: str) -> Optional[Path]:
    """Locate a frame on disk.

    `image_path` in data.csv may be absolute, relative to the repo root, or
    carry Windows separators from a recording made on another machine, so fall
    back to matching the basename inside the dataset's own images/ directory.
    """
    if not image_path:
        return None
    raw = image_path.replace("\\", "/")
    candidates = [
        Path(raw),
        dataset_dir / raw,
        dataset_dir / "images" / Path(raw).name,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def read_records(csv_path: Path) -> List[Dict]:
    with open(csv_path, newline="") as f:
        return list(csv.DictReader(f))


def _float(record: Dict, key: str) -> Optional[float]:
    value = record.get(key)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_navsatfix(record: Dict, stamp: Dict, frame_id: str) -> Optional[Dict]:
    lat = _float(record, "latitude")
    lon = _float(record, "longitude")
    if lat is None or lon is None:
        return None
    return {
        "header": {"stamp": stamp, "frame_id": frame_id},
        # The NMEA driver reports position only, with no accuracy estimate, so
        # the fix is advertised as a plain GPS fix with unknown covariance.
        "status": {"status": ros2_msgs.STATUS_FIX, "service": ros2_msgs.SERVICE_GPS},
        "latitude": lat,
        "longitude": lon,
        "altitude": float("nan"),
        "position_covariance": list(_ZERO_COV_9),
        "position_covariance_type": ros2_msgs.COVARIANCE_TYPE_UNKNOWN,
    }


def build_imu(record: Dict, stamp: Dict, frame_id: str) -> Optional[Dict]:
    accel = [_float(record, k) for k in ("ax", "ay", "az")]
    gyro = [_float(record, k) for k in ("gx", "gy", "gz")]
    if any(v is None for v in accel + gyro):
        return None
    return {
        "header": {"stamp": stamp, "frame_id": frame_id},
        # The BNO085 driver logs raw accel/gyro only; a -1 leading covariance
        # element is how sensor_msgs/Imu marks a field as not supplied.
        "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
        "orientation_covariance": [-1.0] + [0.0] * 8,
        # data.csv stores gyro in deg/s for readability; REP-103 requires rad/s.
        "angular_velocity": dict(zip("xyz", (g * DEG_TO_RAD for g in gyro))),
        "angular_velocity_covariance": list(_ZERO_COV_9),
        "linear_acceleration": dict(zip("xyz", accel)),
        "linear_acceleration_covariance": list(_ZERO_COV_9),
    }


def build_camera_info(stamp: Dict, frame_id: str, width: int, height: int) -> Dict:
    # No intrinsic calibration is captured by the logger, so k/p stay zeroed.
    # Consumers that need rectification should run camera_calibration and
    # republish; zeroed intrinsics are the documented "uncalibrated" state.
    return {
        "header": {"stamp": stamp, "frame_id": frame_id},
        "height": height,
        "width": width,
        "distortion_model": "plumb_bob",
        "d": [0.0] * 5,
        "k": list(_ZERO_COV_9),
        "r": list(_ZERO_COV_9),
        "p": [0.0] * 12,
        "binning_x": 0,
        "binning_y": 0,
        "roi": {
            "x_offset": 0,
            "y_offset": 0,
            "height": 0,
            "width": 0,
            "do_rectify": False,
        },
    }


def load_resolution(dataset_dir: Path) -> Tuple[int, int]:
    """Read camera resolution from metadata.json, falling back to 1280x720."""
    metadata_path = dataset_dir / "metadata.json"
    if metadata_path.is_file():
        try:
            with open(metadata_path) as f:
                metadata = json.load(f)
            camera = metadata.get("sensor_configuration", {}).get("camera", {})
            width = int(camera.get("resolution_width", 0))
            height = int(camera.get("resolution_height", 0))
            if width > 0 and height > 0:
                return width, height
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass
    return 1280, 720


def decode_raw(image_file: Path):
    """Decode a JPEG to a BGR array for sensor_msgs/Image, or None on failure."""
    try:
        import cv2
    except ImportError:
        print("--raw-images needs opencv-python; skipping raw image topic.")
        return None
    return cv2.imread(str(image_file))


def write_metadata_yaml(
    bag_dir: Path,
    bag_file: str,
    topic_counts: Dict[str, str],
    counts: Dict[str, int],
    start_ns: int,
    end_ns: int,
) -> None:
    """Emit rosbag2's metadata.yaml.

    rosbag2 can reconstruct most of this from the MCAP itself, but older
    readers expect the file to exist, and `ros2 bag info` uses it directly.
    """
    total = sum(counts.values())
    lines = [
        "rosbag2_bagfile_information:",
        f"  version: {BAG_METADATA_VERSION}",
        "  storage_identifier: mcap",
        "  relative_file_paths:",
        f"    - {bag_file}",
        "  duration:",
        f"    nanoseconds: {max(0, end_ns - start_ns)}",
        "  starting_time:",
        f"    nanoseconds_since_epoch: {start_ns}",
        f"  message_count: {total}",
        "  topics_with_message_count:",
    ]
    for topic, msg_type in topic_counts.items():
        lines += [
            "    - topic_metadata:",
            f"        name: {topic}",
            f"        type: {msg_type}",
            "        serialization_format: cdr",
            '        offered_qos_profiles: ""',
            f"      message_count: {counts.get(topic, 0)}",
        ]
    lines += [
        '  compression_format: ""',
        '  compression_mode: ""',
        "",
    ]
    (bag_dir / "metadata.yaml").write_text("\n".join(lines), encoding="utf-8")


def convert(
    dataset_dir: Path,
    output_dir: Path,
    frames: Dict[str, str],
    raw_images: bool = False,
) -> Dict[str, int]:
    """Convert a dataset directory into a rosbag2 bag. Returns per-topic counts."""
    from mcap_ros2.writer import Writer

    csv_path = dataset_dir / "data.csv"
    if not csv_path.is_file():
        raise FileNotFoundError(f"No data.csv in {dataset_dir}")

    records = read_records(csv_path)
    width, height = load_resolution(dataset_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    bag_file = f"{output_dir.name}_0.mcap"

    counts: Dict[str, int] = {}
    topic_types = {
        TOPIC_GPS: "sensor_msgs/msg/NavSatFix",
        TOPIC_IMU: "sensor_msgs/msg/Imu",
        TOPIC_IMAGE_COMPRESSED: "sensor_msgs/msg/CompressedImage",
        TOPIC_CAMERA_INFO: "sensor_msgs/msg/CameraInfo",
    }
    if raw_images:
        topic_types[TOPIC_IMAGE_RAW] = "sensor_msgs/msg/Image"

    start_ns: Optional[int] = None
    end_ns = 0
    missing_images = 0
    skipped_rows = 0
    seen_images = set()

    with open(output_dir / bag_file, "wb") as stream:
        writer = Writer(stream)
        schemas = {
            TOPIC_GPS: writer.register_msgdef(
                "sensor_msgs/msg/NavSatFix", ros2_msgs.NAVSATFIX),
            TOPIC_IMU: writer.register_msgdef(
                "sensor_msgs/msg/Imu", ros2_msgs.IMU),
            TOPIC_IMAGE_COMPRESSED: writer.register_msgdef(
                "sensor_msgs/msg/CompressedImage", ros2_msgs.COMPRESSED_IMAGE),
            TOPIC_CAMERA_INFO: writer.register_msgdef(
                "sensor_msgs/msg/CameraInfo", ros2_msgs.CAMERA_INFO),
        }
        if raw_images:
            schemas[TOPIC_IMAGE_RAW] = writer.register_msgdef(
                "sensor_msgs/msg/Image", ros2_msgs.IMAGE)

        def emit(topic: str, message: Dict, log_ns: int) -> None:
            writer.write_message(
                topic=topic,
                schema=schemas[topic],
                message=message,
                log_time=log_ns,
                publish_time=log_ns,
                sequence=counts.get(topic, 0),
            )
            counts[topic] = counts.get(topic, 0) + 1

        for record in records:
            epoch = parse_timestamp(record.get("timestamp"))
            if epoch is None:
                skipped_rows += 1
                continue

            log_ns = to_nanoseconds(epoch)
            stamp = to_ros_time(epoch)
            start_ns = log_ns if start_ns is None else min(start_ns, log_ns)
            end_ns = max(end_ns, log_ns)

            fix = build_navsatfix(record, stamp, frames["gps"])
            if fix:
                emit(TOPIC_GPS, fix, log_ns)

            imu = build_imu(record, stamp, frames["imu"])
            if imu:
                emit(TOPIC_IMU, imu, log_ns)

            image_path = record.get("image_path") or ""
            if not image_path:
                continue
            # The synchronizer can align several rows to one frame; publishing
            # it once per row would fabricate a higher frame rate than recorded.
            if image_path in seen_images:
                continue
            seen_images.add(image_path)

            image_file = resolve_image(dataset_dir, image_path)
            if image_file is None:
                missing_images += 1
                continue

            emit(TOPIC_IMAGE_COMPRESSED, {
                "header": {"stamp": stamp, "frame_id": frames["camera"]},
                "format": "jpeg",
                "data": image_file.read_bytes(),
            }, log_ns)

            emit(TOPIC_CAMERA_INFO,
                 build_camera_info(stamp, frames["camera"], width, height),
                 log_ns)

            if raw_images:
                array = decode_raw(image_file)
                if array is not None:
                    img_h, img_w = array.shape[:2]
                    emit(TOPIC_IMAGE_RAW, {
                        "header": {"stamp": stamp, "frame_id": frames["camera"]},
                        "height": img_h,
                        "width": img_w,
                        "encoding": "bgr8",
                        "is_bigendian": 0,
                        "step": img_w * 3,
                        "data": array.tobytes(),
                    }, log_ns)

        writer.finish()

    write_metadata_yaml(
        output_dir, bag_file, topic_types, counts, start_ns or 0, end_ns)

    if skipped_rows:
        print(f"Warning: skipped {skipped_rows} row(s) with an unparseable timestamp.")
    if missing_images:
        print(f"Warning: {missing_images} frame(s) referenced in data.csv were not found on disk.")

    return counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert a logged dataset into a rosbag2 (MCAP) bag.")
    parser.add_argument("--dataset-dir", required=True, type=Path,
                        help="Dataset directory containing data.csv and images/")
    parser.add_argument("--output-dir", type=Path,
                        help="Bag directory to create (default: <dataset>_rosbag)")
    parser.add_argument("--raw-images", action="store_true",
                        help="Also publish uncompressed sensor_msgs/Image (much larger bags)")
    parser.add_argument("--camera-frame", default="camera_link")
    parser.add_argument("--gps-frame", default="gps_link")
    parser.add_argument("--imu-frame", default="imu_link")
    args = parser.parse_args()

    dataset_dir = args.dataset_dir.resolve()
    if not dataset_dir.is_dir():
        print(f"Error: {dataset_dir} is not a directory")
        return 1

    output_dir = args.output_dir or dataset_dir.parent / f"{dataset_dir.name}_rosbag"

    try:
        counts = convert(
            dataset_dir,
            Path(output_dir).resolve(),
            {"camera": args.camera_frame, "gps": args.gps_frame, "imu": args.imu_frame},
            raw_images=args.raw_images,
        )
    except ImportError:
        print("Error: rosbag2 export needs the MCAP writers.\n"
              "  pip install mcap mcap-ros2-support")
        return 1
    except (FileNotFoundError, OSError) as e:
        print(f"Error: {e}")
        return 1

    if not counts:
        print("No messages written — the dataset had no usable records.")
        return 1

    print(f"Wrote bag to {output_dir}")
    for topic, count in sorted(counts.items()):
        print(f"  {topic}: {count} messages")
    print(f"\nVerify with:\n  ros2 bag info {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
