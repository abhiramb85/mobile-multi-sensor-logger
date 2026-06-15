"""
Local web viewer for recorded multi-sensor datasets.

Single Flask app serves both the API and the static HTML/JS/CSS viewer.
Designed for local use on the Pi or any machine that has the data
directory mounted; not hardened for the public internet.

Run:
    python -m src.web.server
    python -m src.web.server --data-dir ./data --host 0.0.0.0 --port 5000

Then open http://<host-ip>:5000 in any browser.

API:
    GET /                                   -> the viewer HTML
    GET /api/runs                           -> list of dataset directories
    GET /api/runs/<run>/metadata            -> metadata.json
    GET /api/runs/<run>/data                -> CSV rows as JSON (?stride=N to thin)
    GET /api/runs/<run>/images/<filename>   -> JPEG bytes
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import List

from flask import (
    Flask,
    abort,
    jsonify,
    request,
    send_from_directory,
)


def create_app(data_dir: Path) -> Flask:
    data_dir = Path(data_dir).resolve()
    if not data_dir.is_dir():
        raise FileNotFoundError(f"data directory does not exist: {data_dir}")

    static_dir = Path(__file__).parent / "static"
    app = Flask(__name__, static_folder=str(static_dir), static_url_path="/static")
    app.config["DATA_DIR"] = data_dir

    def _resolve_run(run: str) -> Path:
        """Look up a run directory, refusing path-traversal attempts."""
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
        # send_from_directory handles path-traversal rejection for us.
        return send_from_directory(str(run_dir / "images"), filename)

    @app.errorhandler(404)
    def not_found(err):
        return jsonify({"error": "not found", "detail": str(err.description)}), 404

    @app.errorhandler(400)
    def bad_request(err):
        return jsonify({"error": "bad request", "detail": str(err.description)}), 400

    return app


def main():
    parser = argparse.ArgumentParser(description="Local web viewer for recorded datasets.")
    parser.add_argument(
        "--data-dir", "-d", default="./data", type=Path,
        help="Root directory containing recorded run subdirectories",
    )
    parser.add_argument(
        "--host", default="0.0.0.0",
        help="Address to bind (default 0.0.0.0 = all interfaces)",
    )
    parser.add_argument(
        "--port", "-p", default=5000, type=int,
        help="Port to listen on (default 5000)",
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Enable Flask debug mode (auto-reload on code changes)",
    )
    args = parser.parse_args()

    app = create_app(args.data_dir)
    print(f"Serving {Path(args.data_dir).resolve()} on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
