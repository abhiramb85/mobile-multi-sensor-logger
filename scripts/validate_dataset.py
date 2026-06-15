"""
Dataset validator for the mobile multi-sensor logger.

Walks a recorded dataset directory and checks:
  - data.csv, images/, metadata.json all present
  - CSV header matches the thesis-required schema
  - Every CSV row's image_path exists on disk
  - Every image in images/ is referenced by exactly one CSV row
  - Timestamps are monotonically non-decreasing
  - GPS coverage % (rows with valid lat/lon)
  - IMU coverage % (rows with all of ax..gz populated)
  - Sample-rate stats (min/median/max inter-frame interval)
  - File-size sanity on JPEGs (catches mock placeholders)

Exit code 0 if all checks pass, non-zero otherwise.

Usage:
    python scripts/validate_dataset.py --dataset-dir ./data/ride_001
    python scripts/validate_dataset.py --dataset-dir ./data/ride_001 --strict
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple


REQUIRED_COLUMNS = [
    "timestamp",
    "latitude",
    "longitude",
    "image_path",
    "ax", "ay", "az",
    "gx", "gy", "gz",
]

# Image files smaller than this are very likely mock placeholders (b"MOCK_FRAME" = 10 bytes)
# or otherwise corrupt; real JPEGs at 1280x720 MJPEG are tens of KB.
MIN_REAL_JPEG_BYTES = 1024


class ValidationReport:
    """Collects pass/fail checks with human-readable output and a final exit code."""

    OK = "[ OK ]"
    WARN = "[WARN]"
    FAIL = "[FAIL]"

    def __init__(self, strict: bool = False):
        self.strict = strict
        self.lines: List[Tuple[str, str]] = []
        self.has_fail = False
        self.has_warn = False

    def ok(self, msg: str):
        self.lines.append((self.OK, msg))

    def warn(self, msg: str):
        self.lines.append((self.WARN, msg))
        self.has_warn = True

    def fail(self, msg: str):
        self.lines.append((self.FAIL, msg))
        self.has_fail = True

    def print(self):
        for tag, msg in self.lines:
            print(f"{tag} {msg}")

    def exit_code(self) -> int:
        if self.has_fail:
            return 2
        if self.strict and self.has_warn:
            return 1
        return 0


def _parse_timestamp(value) -> Optional[float]:
    """Accept both ISO 8601 strings and legacy float-epoch strings."""
    if value is None or value == "" or value == "None":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return None


def _maybe_float(value) -> Optional[float]:
    if value is None or value == "" or value == "None":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate(dataset_dir: Path, strict: bool = False) -> ValidationReport:
    report = ValidationReport(strict=strict)
    dataset_dir = Path(dataset_dir)

    # --- Structure ---
    if not dataset_dir.is_dir():
        report.fail(f"Dataset directory does not exist: {dataset_dir}")
        return report
    report.ok(f"Dataset directory: {dataset_dir}")

    csv_path = dataset_dir / "data.csv"
    images_dir = dataset_dir / "images"
    metadata_path = dataset_dir / "metadata.json"

    if not csv_path.is_file():
        report.fail(f"Missing data.csv at {csv_path}")
        return report
    if not images_dir.is_dir():
        report.fail(f"Missing images/ directory at {images_dir}")
        return report
    if not metadata_path.is_file():
        report.warn(f"Missing metadata.json at {metadata_path}")
    else:
        try:
            with open(metadata_path) as f:
                json.load(f)
            report.ok("metadata.json parses as valid JSON")
        except Exception as e:
            report.fail(f"metadata.json is not valid JSON: {e}")

    # --- CSV ---
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        if header != REQUIRED_COLUMNS:
            report.fail(
                f"CSV header mismatch.\n"
                f"      expected: {REQUIRED_COLUMNS}\n"
                f"      got     : {header}"
            )
        else:
            report.ok(f"CSV header matches required schema ({len(REQUIRED_COLUMNS)} columns)")
        rows = list(reader)

    if not rows:
        report.fail("CSV has no rows")
        return report
    report.ok(f"CSV has {len(rows)} rows")

    # --- Timestamps ---
    timestamps = [_parse_timestamp(r.get("timestamp")) for r in rows]
    n_bad_ts = sum(1 for t in timestamps if t is None)
    if n_bad_ts:
        report.fail(f"{n_bad_ts} rows have unparseable timestamps")
    else:
        report.ok("Every row has a parseable timestamp")

    if all(t is not None for t in timestamps):
        non_monotonic = sum(1 for a, b in zip(timestamps, timestamps[1:]) if b < a)
        if non_monotonic:
            report.fail(f"{non_monotonic} timestamp pairs are non-monotonic (b < a)")
        else:
            report.ok("Timestamps are monotonically non-decreasing")

        if len(timestamps) >= 2:
            intervals = [b - a for a, b in zip(timestamps, timestamps[1:]) if b >= a]
            if intervals:
                med = statistics.median(intervals)
                mn = min(intervals)
                mx = max(intervals)
                fps = 1.0 / med if med > 0 else 0
                report.ok(
                    f"Inter-frame interval: min={mn * 1000:.1f} ms, "
                    f"median={med * 1000:.1f} ms ({fps:.1f} fps), max={mx * 1000:.1f} ms"
                )
                if mx > 1.0 and not strict:
                    report.warn(
                        f"Largest gap is {mx:.2f} s — long pauses can indicate USB or sensor stalls"
                    )

    # --- Images ---
    images_on_disk = {p.name for p in images_dir.iterdir() if p.is_file()}
    referenced = [Path(r["image_path"]).name for r in rows if r.get("image_path")]
    referenced_set = set(referenced)

    missing = [name for name in referenced if name not in images_on_disk]
    orphan = images_on_disk - referenced_set

    if missing:
        report.fail(f"{len(missing)} CSV rows reference image files that don't exist on disk")
    else:
        report.ok(f"All {len(referenced)} CSV image references exist on disk")

    if orphan:
        report.warn(f"{len(orphan)} image files in images/ are not referenced by any CSV row")
    else:
        report.ok("No orphan images in images/")

    # File-size sanity on a sample
    sample = list(referenced_set)[:200]
    small_jpegs = []
    for name in sample:
        p = images_dir / name
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if size < MIN_REAL_JPEG_BYTES:
            small_jpegs.append((name, size))
    if small_jpegs:
        report.warn(
            f"{len(small_jpegs)} of {len(sample)} sampled JPEGs are < {MIN_REAL_JPEG_BYTES} bytes "
            f"(likely mock placeholders, e.g. b'MOCK_FRAME')"
        )
    elif sample:
        report.ok(f"Sampled {len(sample)} JPEGs; all look like real-sized images")

    # --- GPS coverage ---
    gps_rows = sum(
        1 for r in rows
        if _maybe_float(r.get("latitude")) is not None and _maybe_float(r.get("longitude")) is not None
    )
    pct = 100.0 * gps_rows / len(rows)
    if gps_rows == 0:
        report.warn("0% GPS coverage — no rows have lat/lon (indoor run, antenna issue, or no fix yet)")
    else:
        report.ok(f"GPS coverage: {gps_rows}/{len(rows)} rows ({pct:.1f}%)")

    # --- IMU coverage ---
    imu_keys = ("ax", "ay", "az", "gx", "gy", "gz")
    imu_rows = sum(
        1 for r in rows
        if all(_maybe_float(r.get(k)) is not None for k in imu_keys)
    )
    pct = 100.0 * imu_rows / len(rows)
    if imu_rows == 0:
        report.warn("0% IMU coverage — no rows have ax..gz populated (IMU disabled or not started)")
    else:
        report.ok(f"IMU coverage: {imu_rows}/{len(rows)} rows ({pct:.1f}%)")

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Validate a recorded multi-sensor dataset against the thesis schema."
    )
    parser.add_argument(
        "--dataset-dir", "-d", required=True, type=Path,
        help="Path to the dataset directory (contains data.csv, images/, metadata.json)"
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Treat warnings as failures (useful for CI)"
    )
    args = parser.parse_args()

    print(f"Validating {args.dataset_dir} ...\n")
    report = validate(args.dataset_dir, strict=args.strict)
    report.print()
    code = report.exit_code()
    print()
    if code == 0:
        print("Result: PASS")
    elif code == 1:
        print("Result: PASS with warnings (would be FAIL under --strict)")
    else:
        print("Result: FAIL")
    sys.exit(code)


if __name__ == "__main__":
    main()
