"""Smoke tests for the web viewer API."""

import csv
import json
import tempfile
import unittest
from pathlib import Path


def _make_fake_run(root: Path, name: str, rows: int = 5):
    """Create a minimal valid dataset on disk for the API to serve."""
    run_dir = root / name
    images_dir = run_dir / "images"
    images_dir.mkdir(parents=True)

    with open(run_dir / "data.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "latitude", "longitude", "image_path",
                         "ax", "ay", "az", "gx", "gy", "gz"])
        for i in range(rows):
            fname = f"frame_{1000 + i}.jpg"
            (images_dir / fname).write_bytes(b"FAKE_JPEG_BYTES_" + str(i).encode())
            writer.writerow([
                f"2026-06-15T12:00:0{i}.000000+00:00",
                52.5 + i * 0.0001,
                13.4 + i * 0.0001,
                f"images/{fname}",
                0.1, 0.2, 9.81,
                0.0, 0.0, 0.0,
            ])

    with open(run_dir / "metadata.json", "w") as f:
        json.dump({
            "recording_start": "2026-06-15T12:00:00",
            "total_records": rows,
            "sensor_configuration": {"camera": {"fps": 30}},
        }, f)


class WebApiTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from src.web.server import create_app
        cls._tmp = tempfile.TemporaryDirectory()
        cls.data_dir = Path(cls._tmp.name)
        _make_fake_run(cls.data_dir, "ride_001", rows=5)
        _make_fake_run(cls.data_dir, "ride_002", rows=3)
        cls.app = create_app(cls.data_dir)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_index_html_served(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Multi-Sensor Dataset Viewer", resp.data)

    def test_list_runs(self):
        resp = self.client.get("/api/runs")
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        names = sorted(r["name"] for r in payload["runs"])
        self.assertEqual(names, ["ride_001", "ride_002"])
        for r in payload["runs"]:
            self.assertTrue(r["has_metadata"])
            self.assertGreater(r["size_bytes"], 0)

    def test_metadata(self):
        resp = self.client.get("/api/runs/ride_001/metadata")
        self.assertEqual(resp.status_code, 200)
        md = resp.get_json()
        self.assertEqual(md["total_records"], 5)
        self.assertEqual(md["sensor_configuration"]["camera"]["fps"], 30)

    def test_data_rows(self):
        resp = self.client.get("/api/runs/ride_001/data")
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["count"], 5)
        self.assertEqual(payload["stride"], 1)
        row = payload["rows"][0]
        self.assertTrue(row["timestamp"].startswith("2026-06-15T"))
        self.assertEqual(row["image_path"], "images/frame_1000.jpg")

    def test_data_rows_stride(self):
        resp = self.client.get("/api/runs/ride_001/data?stride=2")
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["count"], 3)  # rows 0, 2, 4
        self.assertEqual(payload["stride"], 2)

    def test_serve_image(self):
        resp = self.client.get("/api/runs/ride_001/images/frame_1000.jpg")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data.startswith(b"FAKE_JPEG_BYTES_"))

    def test_unknown_run_404(self):
        resp = self.client.get("/api/runs/nope/metadata")
        self.assertEqual(resp.status_code, 404)

    def test_path_traversal_rejected(self):
        # Both raw and url-encoded variants must be refused.
        resp = self.client.get("/api/runs/..%2F..%2Fetc/metadata")
        self.assertIn(resp.status_code, (400, 404))

    def test_recording_status_idle_when_nothing_running(self):
        resp = self.client.get("/api/recording/status")
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertFalse(payload["running"])
        self.assertIsNone(payload["state"])

    def test_recording_start_rejects_bad_fps(self):
        resp = self.client.post("/api/recording/start", json={"fps": 9999})
        self.assertEqual(resp.status_code, 400)

    def test_recording_start_rejects_bad_output_name(self):
        resp = self.client.post("/api/recording/start", json={"output_name": "../etc/passwd"})
        self.assertEqual(resp.status_code, 400)

    def test_recording_stop_when_idle_returns_409(self):
        resp = self.client.post("/api/recording/stop")
        self.assertEqual(resp.status_code, 409)


class RecordingManagerValidationTests(unittest.TestCase):
    """Cover the input-validation helper without spawning real subprocesses."""

    def test_validate_opts_defaults(self):
        from src.web.server import _validate_opts
        out = _validate_opts({})
        self.assertEqual(out["fps"], 30)
        self.assertEqual(out["duration"], 60)
        self.assertFalse(out["real_camera"])
        self.assertFalse(out["enable_imu"])

    def test_validate_opts_real_imu_implies_enable_imu(self):
        from src.web.server import _validate_opts
        out = _validate_opts({"real_imu": True})
        self.assertTrue(out["enable_imu"])
        self.assertTrue(out["real_imu"])

    def test_validate_opts_rejects_out_of_range_fps(self):
        from src.web.server import _validate_opts
        with self.assertRaises(ValueError):
            _validate_opts({"fps": 0})
        with self.assertRaises(ValueError):
            _validate_opts({"fps": 200})

    def test_sanitize_name_autogenerates(self):
        from src.web.server import _sanitize_name
        name = _sanitize_name("")
        self.assertTrue(name.startswith("ride_"))

    def test_sanitize_name_rejects_path_chars(self):
        from src.web.server import _sanitize_name
        for bad in ["../etc", "foo bar", "foo/bar", "foo\\bar"]:
            with self.assertRaises(ValueError):
                _sanitize_name(bad)


if __name__ == "__main__":
    unittest.main()
