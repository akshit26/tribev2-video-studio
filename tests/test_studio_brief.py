import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader
from studio_brief import build_brief, create_clips
from studio_report import render_pdf


class BriefTests(unittest.TestCase):
    def report(self, duration=41):
        return {"video": {"duration_seconds": duration, "name": "Example video"}, "processing": {},
                "creative": {"cards": [{"key": "virality", "value": 74}, {"key": "hook", "value": 45}],
                             "opening_text": "Whenever you go outside", "cta_matches": []},
                "metrics": {"words_per_minute": 204, "visual_change_seconds": [3, 6]}}

    def test_short_and_long_excerpt_windows_are_bounded_and_do_not_overlap(self):
        for duration in (.3, 6, 11.9, 12, 18, 19.9, 20, 41, 600):
            with self.subTest(duration=duration):
                clips = build_brief(self.report(duration))["clips"]
                self.assertGreaterEqual(len(clips), 1)
                previous = 0
                for clip in clips:
                    self.assertGreaterEqual(clip["start"], previous)
                    self.assertGreater(clip["end"], clip["start"])
                    self.assertLessEqual(clip["end"], duration)
                    self.assertLessEqual(clip["end"] - clip["start"], 7.01)
                    previous = clip["end"]

    def test_missing_scores_are_not_invented(self):
        report = self.report()
        report["creative"] = {}
        brief = build_brief(report)
        self.assertIsNone(brief["overall_score"])
        self.assertIn("Not enough evidence", brief["verdict"])

    def test_failed_encoding_preserves_review_without_broken_asset(self):
        with tempfile.TemporaryDirectory() as temp:
            brief = build_brief(self.report(4))
            with patch("imageio_ffmpeg.get_ffmpeg_exe", return_value="ffmpeg"), \
                    patch("studio_video.run_gpu_render", side_effect=subprocess.TimeoutExpired("ffmpeg", 90)):
                create_clips(Path("source.mp4"), Path(temp), brief)
            self.assertNotIn("file", brief["clips"][0])
            self.assertIn("error", brief["clips"][0])
            self.assertEqual(brief["overall_score"], 74)

    def test_concise_pdf_embeds_screenshots_without_clip_links(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp) / ("a" * 32)
            report = self.report()
            report["brief"] = build_brief(report)
            (directory / "screenshots").mkdir(parents=True)
            Image.new("RGB", (60, 100), "green").save(directory / "screenshots/frame_000.jpg")
            for i, clip in enumerate(report["brief"]["clips"]):
                clip["file"] = f"clips/clip_{i:02d}.mp4"
                clip["screenshots"] = [{"file": "screenshots/frame_000.jpg", "time_seconds": clip["start"]}]
            pdf = PdfReader(render_pdf(report, directory))
            self.assertLessEqual(len(pdf.pages), 3)
            text = " ".join(page.extract_text() for page in pdf.pages)
            for label in ["74 / 100", "What works well", "Changes to make first", "Video screenshots"]:
                self.assertIn(label, text)
            self.assertNotIn("Emotional", text)
            self.assertEqual(sum(len(page.get("/Annots", [])) for page in pdf.pages), 0)
            self.assertGreater(sum(len(page.images) for page in pdf.pages), 0)
