import unittest
from studio_report_quality import separate_recognition_notes


class SummaryQualityTests(unittest.TestCase):
    def test_recognition_weakness_is_separated_without_changing_score(self):
        original = "A relatable product story. Weakness: inconsistent OCR (e.g., 'Bamier' instead of 'barrier')."
        review = {"summary": original, "overall_score": 58, "uncertainties": []}
        separate_recognition_notes(review)
        self.assertEqual(review["summary"], "A relatable product story.")
        self.assertEqual(review["overall_score"], 58)
        self.assertEqual(review["summary_before_recognition_filter"], original)
        self.assertEqual(len(review["summary_extraction_notes"]), 1)
        separate_recognition_notes(review)
        self.assertEqual(len(review["summary_extraction_notes"]), 1)

    def test_ocr_evidence_is_not_removed_just_for_mentioning_ocr(self):
        original = "OCR shows COMMENT DUO FOR LINK. The CTA is explicit."
        review = {"summary": original}
        separate_recognition_notes(review)
        self.assertEqual(review, {"summary": original})
