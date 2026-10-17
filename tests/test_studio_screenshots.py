from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from studio_screenshots import create_screenshots, screenshot_html, screenshot_path


class ScreenshotTests(unittest.TestCase):
    def test_portable_inline_asset_and_escaping(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            (directory / "screenshots").mkdir()
            (directory / "screenshots/frame_000.jpg").write_bytes(b"image")
            frame = {"file": "screenshots/frame_000.jpg", "time_seconds": 1, "label": "<script>"}
            document = screenshot_html([frame], directory)
            self.assertIn('src="data:image/jpeg;base64,', document)
            self.assertIn("&lt;script&gt;", document)
            self.assertNotIn("href=", document)
            self.assertIsNone(screenshot_path(dict(frame, file="../private.jpg"), directory))
            self.assertIsNone(screenshot_path(dict(frame, file="screenshots/missing.jpg"), directory))

    def test_repeated_timestamps_reuse_capture_and_failures_stay_visible(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            report = {"video": {"duration_seconds": 10, "fps": 30},
                      "review": {"edits": [{"start": 1, "end": 3}] * 2},
                      "brief": {"clips": [{"start": 0, "end": 2}]}}
            with patch("studio_video.run_gpu_render", side_effect=RuntimeError("No decoder")) as render:
                create_screenshots(directory / "input.mp4", directory, report)
            self.assertEqual(render.call_count, 2)
            self.assertIn("error", report["brief"]["clips"][0]["screenshots"][0])
            self.assertIn("screenshot unavailable", screenshot_html(report["review"]["edits"][0]["screenshots"], directory))
