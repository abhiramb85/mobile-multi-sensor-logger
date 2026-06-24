"""
Local web viewer + control panel for the multi-sensor logger.

Single Flask app serves the static SPA, the read-only dataset API, and a
small recording-control API that spawns / monitors / stops the acquisition
process. Designed for local LAN use; not hardened for the public internet.

Run:
    python -m src.web.server
    python -m src.web.server --data-dir ./data --host 0.0.0.0 --port 5000

Then open http://<host-ip>:5000 in any browser.

API:
    GET  /                                   -> the viewer HTML
    GET  /api/runs                           -> list of dataset directories
    GET  /api/runs/<run>/metadata            -> metadata.json
    GET  /api/runs/<run>/data                -> CSV rows as JSON (?stride=N)
    GET  /api/runs/<run>/images/<filename>   -> JPEG bytes
    GET  /api/recording/status               -> live recording status
    POST /api/recording/start                -> spawn an acquisition subprocess
    POST /api/recording/stop                 -> SIGINT the active recording
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional

from flask import (
    Flask,
    abort,
    jsonify,
    request,
    send_file,
    send_from_directory,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_PROGRESS_RE = re.compile(r"\[(\d+\.?\d*)s\]\s+Frames:\s+(\d+),\s+Records:\s+(\d+)")
_LOG_TAIL_LINES = 30
_VALID_BOOL_KEYS = ("real_camera", "real_gps", "enable_imu", "real_imu")


def _utcnow_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _sanitize_name(name: Optional[str]) -> str:
    """Return a filesystem-safe run name; auto-generate one if empty."""
    if not name:
        return "ride_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    name = name.strip()
    if not _NAME_RE.match(name):
        raise ValueError(
            "output_name must contain only letters, digits, '.', '_', '-' "
            "(no spaces or path separators)"
        )
    if len(name) > 80:
        raise ValueError("output_name too long")
    return name


def _pid_alive(pid: Optional[int]) -> bool:
    if not pid:
        return False
    try:
        if os.name == "posix":
            os.kill(pid, 0)
            return True
        # Windows fallback
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True, text=True, timeout=5,
        )
        return str(pid) in result.stdout
    except (ProcessLookupError, PermissionError, OSError, subprocess.SubprocessError):
        return False


def _validate_opts(raw: Dict) -> Dict:
    if not isinstance(raw, dict):
        raise ValueError("body must be a JSON object")
    try:
        fps = int(raw.get("fps", 30))
    except (TypeError, ValueError):
        raise ValueError("fps must be an integer")
    if not (1 <= fps <= 120):
        raise ValueError("fps must be between 1 and 120")
    try:
        duration = int(raw.get("duration", 60))
    except (TypeError, ValueError):
        raise ValueError("duration must be an integer (seconds)")
    if not (0 <= duration <= 24 * 60 * 60):
        raise ValueError("duration must be between 0 (unlimited) and 86400 seconds")
    try:
        camera_id = int(raw.get("camera_id", 0))
    except (TypeError, ValueError):
        raise ValueError("camera_id must be an integer")
    if not (0 <= camera_id <= 10):
        raise ValueError("camera_id out of range")

    out = {
        "fps": fps,
        "duration": duration,
        "camera_id": camera_id,
        "output_name": raw.get("output_name") or "",
    }
    for key in _VALID_BOOL_KEYS:
        out[key] = bool(raw.get(key, False))
    # Convenience: --real-imu without --enable-imu would silently no-op; auto-enable.
    if out["real_imu"] and not out["enable_imu"]:
        out["enable_imu"] = True
    return out


class RecordingManager:
    """Tracks the single active acquisition subprocess (if any).

    Assumes the Flask dev server runs as a single process; simple in-memory
    state plus a small `.recording.json` file on disk for restart-safety.
    """

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir).resolve()
        self.state_path = self.data_dir / ".recording.json"
        self.lock = Lock()
        self.proc: Optional[subprocess.Popen] = None
        self.state: Optional[Dict] = self._load_state()
        if self.state and not _pid_alive(self.state.get("pid")):
            self.state = None
            self._save_state()

    def _load_state(self) -> Optional[Dict]:
        if not self.state_path.is_file():
            return None
        try:
            with open(self.state_path) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    def _save_state(self):
        try:
            if self.state is None:
                if self.state_path.exists():
                    self.state_path.unlink()
                return
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with open(self.state_path, "w") as f:
                json.dump(self.state, f, indent=2)
        except OSError:
            pass

    def is_running(self) -> bool:
        if self.proc is not None:
            return self.proc.poll() is None
        if self.state and self.state.get("pid"):
            return _pid_alive(self.state["pid"])
        return False

    def start(self, opts: Dict) -> Dict:
        with self.lock:
            if self.is_running():
                raise RuntimeError("a recording is already in progress")

            params = _validate_opts(opts)
            out_name = _sanitize_name(params["output_name"])
            out_dir = (self.data_dir / out_name).resolve()
            if self.data_dir not in out_dir.parents:
                raise ValueError("output_name escapes data dir")
            out_dir.mkdir(parents=True, exist_ok=True)

            cmd = [
                sys.executable, "-m", "src.main",
                "--output-dir", str(out_dir),
                "--duration", str(params["duration"]),
                "--fps", str(params["fps"]),
                "--camera-id", str(params["camera_id"]),
            ]
            if params["real_camera"]:
                cmd.append("--real-camera")
            if params["real_gps"]:
                cmd.append("--real-gps")
            if params["enable_imu"]:
                cmd.append("--enable-imu")
            if params["real_imu"]:
                cmd.append("--real-imu")

            log_path = out_dir / "acquisition.log"
            log_file = open(log_path, "w", buffering=1)
            # PYTHONUNBUFFERED is critical: without it, the subprocess's stdout
            # block-buffers when redirected to a file, so the [X.Xs] Frames: N
            # progress lines don't reach the log (and our status endpoint)
            # until many seconds in. With it, every print() flushes immediately.
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            kwargs = {
                "cwd": str(PROJECT_ROOT),
                "stdout": log_file,
                "stderr": subprocess.STDOUT,
                "env": env,
            }
            # Detach the recording so it survives a web-server crash.
            if os.name == "posix":
                kwargs["start_new_session"] = True
            else:
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

            self.proc = subprocess.Popen(cmd, **kwargs)

            self.state = {
                "pid": self.proc.pid,
                "output_dir": str(out_dir),
                "output_name": out_name,
                "log_path": str(log_path),
                "params": params,
                "started_at": _utcnow_iso(),
            }
            self._save_state()
            return dict(self.state)

    def stop(self) -> bool:
        """SIGINT the recording so its logger.finalize() runs."""
        with self.lock:
            if not self.is_running():
                return False
            pid = self.state["pid"] if self.state else self.proc.pid
            try:
                if os.name == "posix":
                    os.kill(pid, signal.SIGINT)
                else:
                    os.kill(pid, signal.CTRL_BREAK_EVENT)
            except (ProcessLookupError, OSError):
                return False
            if self.proc is not None:
                try:
                    self.proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.proc.terminate()
            return True

    def status(self) -> Dict:
        with self.lock:
            running = self.is_running()
            out: Dict = {
                "running": running,
                "state": self.state,
                "log_tail": [],
                "progress": None,
            }
            if self.state:
                tail, progress = self._read_log_tail(Path(self.state["log_path"]))
                out["log_tail"] = tail
                out["progress"] = progress
            if not running and self.proc is not None and self.state is not None:
                out["exit_code"] = self.proc.returncode
                # Clear state once the process has fully exited so a new
                # recording can start cleanly.
                self.state = None
                self.proc = None
                self._save_state()
            return out

    @staticmethod
    def _read_log_tail(log_path: Path):
        if not log_path.is_file():
            return [], None
        try:
            with open(log_path, "r", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            return [], None
        tail = [line.rstrip("\n") for line in lines[-_LOG_TAIL_LINES:]]
        progress = None
        for line in reversed(lines):
            m = _PROGRESS_RE.search(line)
            if m:
                progress = {
                    "elapsed_s": float(m.group(1)),
                    "frames": int(m.group(2)),
                    "records": int(m.group(3)),
                }
                break
        return tail, progress


def create_app(data_dir: Path) -> Flask:
    data_dir = Path(data_dir).resolve()
    if not data_dir.is_dir():
        raise FileNotFoundError(f"data directory does not exist: {data_dir}")

    static_dir = Path(__file__).parent / "static"
    app = Flask(__name__, static_folder=str(static_dir), static_url_path="/static")
    app.config["DATA_DIR"] = data_dir
    # Disable browser caching of the SPA + static assets. This is a local dev
    # tool, not a public site; the cost of always re-fetching ~150 KB of JS/CSS
    # is negligible, but the cost of users debugging stale-cache bugs after a
    # `git pull` (play button silently bound to the previous app.js, etc.) is
    # very high. Tradeoff is firmly on the side of "no cache".
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

    @app.after_request
    def _no_cache_for_static(resp):
        if request.path.startswith("/static/") or request.path == "/":
            resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
        return resp

    recorder = RecordingManager(data_dir)
    app.config["RECORDER"] = recorder

    def _resolve_run(run: str) -> Path:
        if "/" in run or "\\" in run or run.startswith("."):
            abort(400, "invalid run name")
        run_dir = (data_dir / run).resolve()
        if data_dir not in run_dir.parents and run_dir != data_dir:
            abort(400, "run directory escapes data dir")
        if not run_dir.is_dir():
            abort(404, f"unknown run: {run}")
        return run_dir

    @app.route("/")
    def index():
        return send_from_directory(str(static_dir), "index.html")

    @app.route("/api/runs")
    def list_runs():
        runs: List[dict] = []
        for entry in sorted(data_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            csv_path = entry / "data.csv"
            if not csv_path.is_file():
                continue
            try:
                size = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
            except OSError:
                size = 0
            runs.append({
                "name": entry.name,
                "size_bytes": size,
                "has_metadata": (entry / "metadata.json").is_file(),
            })
        return jsonify({"runs": runs})

    @app.route("/api/runs/<run>/metadata")
    def metadata(run: str):
        run_dir = _resolve_run(run)
        metadata_path = run_dir / "metadata.json"
        if not metadata_path.is_file():
            abort(404, "no metadata.json in this run")
        with open(metadata_path) as f:
            return jsonify(json.load(f))

    @app.route("/api/runs/<run>/data")
    def data_rows(run: str):
        run_dir = _resolve_run(run)
        csv_path = run_dir / "data.csv"
        try:
            stride = max(1, int(request.args.get("stride", 1)))
        except ValueError:
            stride = 1
        rows = []
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i % stride != 0:
                    continue
                rows.append(row)
        return jsonify({"run": run, "stride": stride, "count": len(rows), "rows": rows})

    @app.route("/api/runs/<run>/images/<path:filename>")
    def serve_image(run: str, filename: str):
        run_dir = _resolve_run(run)
        return send_from_directory(str(run_dir / "images"), filename)

    @app.route("/api/recording/status")
    def recording_status():
        return jsonify(recorder.status())

    @app.route("/api/recording/start", methods=["POST"])
    def recording_start():
        body = request.get_json(silent=True) or {}
        try:
            state = recorder.start(body)
        except ValueError as e:
            abort(400, str(e))
        except RuntimeError as e:
            abort(409, str(e))
        return jsonify({"ok": True, "state": state})

    @app.route("/api/recording/stop", methods=["POST"])
    def recording_stop():
        ok = recorder.stop()
        if not ok:
            abort(409, "no recording is running")
        return jsonify({"ok": True})

    @app.route("/api/recording/latest_frame")
    def recording_latest_frame():
        """Serve the most recently captured JPEG from the live recording's images/ dir."""
        st = recorder.status()
        if not st["running"] or not st["state"]:
            abort(404, "no recording is running")
        images_dir = Path(st["state"]["output_dir"]) / "images"
        if not images_dir.is_dir():
            abort(404, "images directory not ready yet")
        # Filenames are frame_<unix_ms>.jpg so max() by name == newest.
        try:
            latest = max(images_dir.iterdir(), key=lambda p: p.name, default=None)
        except OSError:
            abort(503, "image dir read failed")
        if latest is None or latest.suffix.lower() != ".jpg":
            abort(404, "no frames captured yet")
        # Tell the browser never to cache this URL — every poll is a fresh frame.
        resp = send_file(str(latest), mimetype="image/jpeg")
        resp.headers["Cache-Control"] = "no-store, max-age=0"
        return resp

    @app.route("/api/recording/latest_row")
    def recording_latest_row():
        """Return the last complete CSV row from the live recording."""
        st = recorder.status()
        if not st["running"] or not st["state"]:
            abort(404, "no recording is running")
        csv_path = Path(st["state"]["output_dir"]) / "data.csv"
        if not csv_path.is_file():
            return jsonify({"row": None})
        try:
            with open(csv_path, "r") as f:
                lines = f.readlines()
        except OSError:
            return jsonify({"row": None})
        if len(lines) < 2:
            return jsonify({"row": None})
        header = lines[0].strip().split(",")
        # The very last line could be a partial write mid-flush; if it has fewer
        # columns than the header, fall back to the previous line.
        for candidate in reversed(lines[1:]):
            fields = candidate.strip().split(",")
            if len(fields) == len(header):
                return jsonify({"row": dict(zip(header, fields))})
        return jsonify({"row": None})

    @app.errorhandler(404)
    def _not_found(err):
        return jsonify({"error": "not found", "detail": str(err.description)}), 404

    @app.errorhandler(400)
    def _bad_request(err):
        return jsonify({"error": "bad request", "detail": str(err.description)}), 400

    @app.errorhandler(409)
    def _conflict(err):
        return jsonify({"error": "conflict", "detail": str(err.description)}), 409

    return app


def main():
    parser = argparse.ArgumentParser(description="Local web viewer + control panel.")
    parser.add_argument("--data-dir", "-d", default="./data", type=Path)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", "-p", default=5000, type=int)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    app = create_app(args.data_dir)
    print(f"Serving {Path(args.data_dir).resolve()} on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
