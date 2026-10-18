import unittest

from studio_virality import check_virality
from studio_decision_pdf import decision_html


class ViralityCheckerTests(unittest.TestCase):
    def setUp(self):
        keys = ("hook", "visual", "structure", "voice", "clarity", "credibility", "emotion", "cta")
        self.review = {"available": True,
                       "overall_score": 91,
                       "brand_review": {"compliance_score": 100},
                       "dimensions": [{"key": key, "label": key.title(), "grade": 2,
                                       "source_ids": [f"S{i+1}"]} for i, key in enumerate(keys)],
                       "estimate": {"dimensions": [{"key": key, "estimated_score": 50} for key in keys]},
                       "edits": [{"targets": ["hook"], "start": 0, "end": 3,
                                  "instruction": "Replace the opening with a specific payoff."}]}

    def test_separate_index_uses_adjusted_evidence_and_excludes_brand(self):
        checked = check_virality(self.review)
        self.assertEqual(checked["score"], 50)
        self.assertEqual(sum(row["weight"] for row in checked["levers"]), 100)
        self.assertEqual(len(checked["levers"]), 5)
        self.assertEqual(checked["priorities"][0]["edit"]["start"], 0)
        self.assertNotIn("probability", checked)

    def test_weak_opening_can_diverge_from_overall_rating(self):
        self.review["estimate"]["dimensions"][0]["estimated_score"] = 0
        checked = check_virality(self.review)
        self.assertLess(checked["score"], 50)
        self.assertEqual(self.review["overall_score"], 91)
        self.assertLess(checked["levers"][0]["score"], 50)

    def test_pdf_labels_virality_separately_from_overall(self):
        self.review.pop("brand_review")
        self.review["virality"] = check_virality(self.review)
        document = decision_html({"video": {"name": "ad.mp4", "duration_seconds": 20},
                                  "review": self.review, "brief": {}})
        self.assertIn("Overall rating", document)
        self.assertIn("Virality checker", document)
        self.assertIn("not a chance of going viral", document)
