"""Locate and import the repo's existing sensor drivers from inside the ROS package.

The drivers live in the plain-Python tree (`<repo>/src/sensors/`), deliberately
outside this ament package so the CSV acquisition pipeline stays ROS-free. The
nodes reuse them rather than reimplementing hardware access, so we add the repo
root to sys.path once, here.

Resolution order:
  1. $SENSOR_LOGGER_ROOT, if set (explicit override for unusual layouts).
  2. Walk up from this file looking for a dir containing `src/sensors/base_sensor.py`.
     `colcon build --symlink-install` keeps node files symlinked into the source
     tree, so __file__ still resolves back into the repo after building.
"""

import os
import sys
from pathlib import Path


def _looks_like_repo(path: Path) -> bool:
    return (path / "src" / "sensors" / "base_sensor.py").is_file()


def find_repo_root() -> Path:
    override = os.environ.get("SENSOR_LOGGER_ROOT")
    if override:
        root = Path(override).expanduser().resolve()
        if _looks_like_repo(root):
            return root
        raise RuntimeError(
            f"SENSOR_LOGGER_ROOT={override!r} does not contain src/sensors/. "
            f"Point it at the repository root.")

    here = Path(__file__).resolve()
    for parent in here.parents:
        if _looks_like_repo(parent):
            return parent

    raise RuntimeError(
        "Could not locate the sensor-logger repo root (no src/sensors/ found "
        "walking up from this file). Set SENSOR_LOGGER_ROOT to the repo path, "
        "e.g. export SENSOR_LOGGER_ROOT=~/mobile-multi-sensor-logger")


def ensure_drivers_importable() -> Path:
    """Put the repo root on sys.path so `from src.sensors...` works. Idempotent."""
    root = find_repo_root()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root
