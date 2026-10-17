import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from studio_scores import creative_scores
from studio_pipeline import _write_json


class CreativeScoresTests(unittest.TestCase):
    def report(self, language="en", text="How can you save time?", end_text="Comment link and get the guide"):
        def segment(text, start):
            words = text.split()
            return {"text": text, "start": start, "end": start + len(words) * .3,
                    "words": [{"word": word, "start": start + i * .3, "end": start + (i + 1) * .3, "probability": .9} for i, word in enumerate(words)]}
        return {"video": {"duration_seconds": 20}, "transcript": {"language": language, "segments": [segment(text, 0), segment(end_text, 16)]},
                "metrics": {"words_per_minute": 150, "visual_change_seconds": [3, 7, 11], "word_count": 13}}

    def test_complete_score_and_cta_have_reproducible_inputs(self):
        result = creative_scores(self.report())
        values = {c["key"]: c["value"] for c in result["cards"]}
        self.assertEqual(values["cta"], 100)
        self.assertEqual(values["virality"], round(.35 * values["hook"] + .25 * 100 + .2 * values["pacing"] + .2 * values["visual"]))
        self.assertEqual(result["cta_matches"][0]["time_seconds"], 16)
        self.assertIn("unvalidated", result["method_note"])

    def test_missing_or_non_english_speech_does_not_invent_viral_score(self):
        for report in [self.report(language="hi"), {"video": {"duration_seconds": 20}, "transcript": None, "metrics": {}}]:
            values = {c["key"]: c["value"] for c in creative_scores(report)["cards"]}
            self.assertIsNone(values["virality"])
            self.assertIsNone(values["hook"])
            self.assertIsNone(values["cta"])

    def test_ordinary_like_is_not_a_call_to_action(self):
        result = creative_scores(self.report(end_text="I like this product very much"))
        self.assertEqual(result["cta_matches"], [])
        self.assertEqual(next(c["value"] for c in result["cards"] if c["key"] == "cta"), 0)

    def test_atomic_progress_retries_a_windows_reader_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            original = Path.replace
            calls = []
            def replace(source, destination):
                calls.append(1)
                if len(calls) == 1:
                    raise PermissionError("transient file lock")
                return original(source, destination)
            with patch.object(Path, "replace", replace), patch("studio_pipeline.time.sleep"):
                _write_json(path, {"progress": 50})
            self.assertEqual(len(calls), 2)
            self.assertIn('50', path.read_text())


if __name__ == "__main__":
    unittest.main()
