import json
import tempfile
import unittest
from pathlib import Path

from studio_review import review_signature


class ReviewCacheSignatureTests(unittest.TestCase):
    def test_runtime_policy_does_not_invalidate_evidence_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "review_input.json"
            report = {"transcript": {"segments": [{"text": "Shop now"}]},
                      "processing": {"memory_policy": "pause at 76 C"},
                      "created_at": "first"}
            path.write_text(json.dumps(report), encoding="utf-8")
            first = review_signature(Path(folder))
            report["processing"]["memory_policy"] = "pause at 75 C"
            report["created_at"] = "later"
            path.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(first, review_signature(Path(folder)))
            report["transcript"]["segments"][0]["text"] = "Do not shop"
            path.write_text(json.dumps(report), encoding="utf-8")
            self.assertNotEqual(first, review_signature(Path(folder)))
