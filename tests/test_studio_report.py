"""Evidence, privacy, and real PDF layout checks without model downloads."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from studio_report import build_report, render_pdf


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.video = {"video": r"C:\private\video.mp4", "duration_seconds": 10,
                      "width": 720, "height": 1280, "fps": 30,
                      "file_bytes": 1048576, "has_audio": True}
        self.processing = {"device": "cuda", "gpu_name": "Example GPU", "budget_mb": 4096,
                           "peak_gpu_mb": 1234, "models": ["speech model"]}

    def test_measurements_and_heuristics_use_the_supplied_evidence(self):
        transcript = {"language": "en", "segments": [
            {"start": 0, "end": 2, "text": "one two three four five six seven eight nine ten",
             "words": [{"word": "one", "start": 0, "end": .5, "probability": .59},
                       {"word": "two", "start": .5, "end": 1, "probability": .6}]}
        ]}
        rows = [{"time_seconds": 0, "audio_rms_dbfs": -10, "audio_peak_dbfs": -1, "frame_difference_0_255": 0},
                {"time_seconds": 1, "audio_rms_dbfs": -50, "audio_peak_dbfs": -20, "frame_difference_0_255": 25},
                {"time_seconds": 2, "audio_rms_dbfs": -30, "audio_peak_dbfs": -3, "frame_difference_0_255": 24.9}]
        report = build_report(self.video, rows, transcript, [], self.processing)
        self.assertEqual(report["metrics"]["word_count"], 10)
        self.assertEqual(report["metrics"]["words_per_minute"], 60)
        self.assertEqual(report["metrics"]["median_audio_rms_dbfs"], -30)
        self.assertEqual(report["metrics"]["peak_audio_dbfs"], -1)
        self.assertEqual(report["metrics"]["near_peak_seconds"], [0])
        self.assertEqual(report["metrics"]["visual_change_seconds"], [1])
        self.assertEqual(report["metrics"]["quiet_window_seconds"], [1])
        self.assertEqual(report["metrics"]["low_confidence_word_count"], 1)
        self.assertEqual(report["metrics"]["fast_caption_segment_count"], 1)
        uncertainty = next(item for item in report["findings"] if item["title"] == "Verify uncertain transcript words")
        self.assertIn("00:00.0", uncertainty["evidence"])
        self.assertIn("heuristic", uncertainty["detail"])
        self.assertFalse(report["processing"]["brain_inference"])

    def test_no_transcript_is_not_a_zero_word_transcript(self):
        missing = build_report(self.video, [], None, [], self.processing)
        silent = build_report(self.video, [], {"segments": []}, [], self.processing)
        self.assertIsNone(missing["metrics"]["word_count"])
        self.assertIsNone(missing["metrics"]["words_per_minute"])
        self.assertEqual(silent["metrics"]["word_count"], 0)
        self.assertTrue(any(item["title"] == "Speech analysis unavailable" for item in missing["findings"]))
        self.assertTrue(any(item["title"] == "No words recognized" for item in silent["findings"]))

    def test_sensitive_metadata_and_unsafe_images_are_not_exported(self):
        processing = {**self.processing, "warnings": ["Download failed hf_TestSecretDoNotLeak in C:\\secret\\model.bin"],
                      "token": "not-for-export", "models": [{"name": "speech", "device": "cuda"}]}
        transcript = {"source": {"path": r"C:\private\video.mp4"}, "segments": []}
        scenes = [{"time_seconds": 1, "caption": "A person", "frame_file": "../outside.jpg"},
                  {"time_seconds": 2, "caption": "A room", "frame_file": r"C:\private\outside.jpg"},
                  {"time_seconds": 3, "caption": "A screen", "frame_file": r"frames\frame.jpg"}]
        report = build_report(self.video, [], transcript, scenes, processing)
        exported = json.dumps(report)
        self.assertEqual(report["video"]["name"], "video.mp4")
        self.assertNotIn("private", exported)
        self.assertNotIn("hf_TestSecretDoNotLeak", exported)
        self.assertNotIn("not-for-export", exported)
        self.assertEqual([scene["frame_file"] for scene in report["scenes"]], ["", "", "frames/frame.jpg"])

    def test_nonfinite_measurements_produce_valid_json(self):
        info = {**self.video, "duration_seconds": float("nan")}
        rows = [{"time_seconds": 0, "audio_rms_dbfs": float("-inf"), "audio_peak_dbfs": float("nan")},
                {"time_seconds": float("nan"), "frame_difference_0_255": 255}]
        report = build_report(info, rows, {"segments": []}, [], self.processing)
        json.dumps(report, allow_nan=False)
        self.assertIsNone(report["metrics"]["words_per_minute"])
        self.assertIsNone(report["metrics"]["peak_audio_dbfs"])

    @unittest.skipUnless(importlib.util.find_spec("reportlab"), "reportlab is required for PDF integration")
    def test_real_pdf_paginates_long_text_and_does_not_read_external_image(self):
        from reportlab.pdfgen.canvas import Canvas
        from reportlab.lib.utils import ImageReader
        transcript = {"language": "en", "segments": [
            {"start": i * 10, "end": (i + 1) * 10,
             "text": ("This is a long but readable transcript with <markup> & accents café, हिंदी, and 😀. " * 8)}
            for i in range(20)]}
        scenes = [{"time_seconds": 1, "caption": "Automatic observation, not verified.", "frame_file": "../outside.png"}]
        report = build_report(self.video, [], transcript, scenes, self.processing)
        pages = []
        original = Canvas.drawRightString
        def capture(canvas, x, y, text, *args, **kwargs):
            pages.append(text)
            return original(canvas, x, y, text, *args, **kwargs)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "report_dir"
            from PIL import Image
            Image.new("RGB", (8, 8), "red").save(root / "outside.png")
            with patch.object(Canvas, "drawRightString", capture), patch("reportlab.lib.utils.ImageReader", wraps=ImageReader) as reader:
                path = render_pdf(report, output)
            self.assertEqual(path, output / "report.pdf")
            self.assertTrue(path.read_bytes().startswith(b"%PDF-"))
            self.assertGreater(path.stat().st_size, 5000)
            self.assertGreater(len(pages), 3)
            self.assertEqual(pages, [f"Page {i}" for i in range(1, len(pages) + 1)])
            reader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
