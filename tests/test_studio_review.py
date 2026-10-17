import copy
import unittest
from studio_review import validate_review, review_prompt, RUBRIC, LANGUAGES
from studio_review_output import detailed_html


class SemanticReviewTests(unittest.TestCase):
    def test_unreliable_recognition_estimates_score_until_corrected(self):
        self.report["transcript"]["segments"][0]["words"] = [{"word": "x", "probability": .2}] * 10
        result = validate_review(self.raw, self.report)
        self.assertEqual(result["overall_score"], 50)
        self.assertEqual(result["estimate"]["range"], [0, 100])
        self.assertTrue(result["transcript_quality"]["withhold_score"])
        self.report["transcript"]["manually_corrected"] = True
        self.assertEqual(validate_review(self.raw, self.report)["overall_score"], 50)

    def setUp(self):
        self.report = {"video": {"duration_seconds": 20, "name": "Regional <video>"},
                       "transcript": {"language": "hi", "segments": [{"start": 0, "end": 5, "text": "आप अपने बालों का ध्यान कैसे रखते हैं?"}]},
                       "processing": {}, "brief": {"clips": []}}
        self.raw = {"summary": "Specific assessment", "verdict": "Revise the hook", "content_language": "Hindi",
                    "dimensions": [{"key": r[0], "grade": 2, "rationale": "Explanation", "source_ids": ["S1"]} for r in RUBRIC],
                    "strengths": [{"title": "Relevant question", "detail": "Addresses viewer", "source_ids": ["S1"]}],
                    "edits": [{"title": "Edit", "operation": "replace", "source_ids": ["S1"], "targets": [r[0] for r in RUBRIC],
                               "instruction": "Replace opening", "replacement": "अपने बालों के लिए यह तरीका देखें।", "english_gloss": "Try this approach for your hair",
                               "why": "Specific payoff", "verify": "Payoff stated within first five seconds"} for _ in range(4)],
                    "uncertainties": ["Transcript needs fluent review"]}

    def test_weighted_score_is_computed_not_model_supplied_or_forced_over_70(self):
        self.raw["overall_score"] = 99
        result = validate_review(self.raw, self.report)
        self.assertEqual(result["overall_score"], 50)
        self.assertEqual(result["target"]["score"], 75)
        self.assertNotIn("predicted_score", result)
        self.assertEqual(result["target"]["gap"], 25)
        self.assertTrue(result["target"]["needs_improvement"])
        self.assertEqual(len(result["target"]["priorities"]), len(RUBRIC))
        self.assertEqual(result["target"]["priorities"][0]["key"], "visual")

    def test_below_70_priorities_only_include_generated_top_edits(self):
        for edit in self.raw["edits"]:
            edit["targets"] = ["hook"]
        result = validate_review(self.raw, self.report)
        self.assertEqual([row["key"] for row in result["target"]["priorities"]], ["hook"])

    def test_add_is_an_insert_edit_not_a_cuda_failure(self):
        self.raw["edits"][0]["operation"] = " Add "
        result = validate_review(self.raw, self.report)
        self.assertEqual(result["edits"][0]["operation"], "insert")

    def test_strong_video_does_not_get_below_70_plan(self):
        self.report["transcript"]["manually_corrected"] = True
        for row in self.raw["dimensions"]:
            row["grade"] = 3
        result = validate_review(self.raw, self.report)
        self.assertEqual(result["overall_score"], 75)
        self.assertFalse(result["target"]["needs_improvement"])
        self.assertEqual(result["target"]["priorities"], [])

    def test_regional_language_receives_same_rubric_and_original_script_is_preserved(self):
        for language in ["hi", "ta", "te", "kn", "ml", "bn", "mr", "gu"]:
            self.assertIn(language, LANGUAGES)
            self.report["transcript"]["language"] = language
            result = validate_review(self.raw, self.report)
            self.assertEqual(result["overall_score"], 50)
        self.assertIn("आप अपने", review_prompt(self.report, [] if False else [{"text": "आप अपने"}]))
        self.assertIn("अपने बालों", result["edits"][0]["replacement"])

    def test_invalid_grades_and_invented_source_references_are_rejected(self):
        for grade in [5, -1, 2.5, True, "3"]:
            raw = copy.deepcopy(self.raw)
            raw["dimensions"][0]["grade"] = grade
            with self.assertRaises(ValueError):
                validate_review(raw, self.report)
        raw = copy.deepcopy(self.raw)
        raw["edits"][0]["source_ids"] = ["S99"]
        with self.assertRaises(ValueError):
            validate_review(raw, self.report)

    def test_exact_times_come_from_source_not_generated_timestamps(self):
        self.raw["edits"][0].update(start=999, end=2000)
        result = validate_review(self.raw, self.report)
        self.assertEqual((result["edits"][0]["start"], result["edits"][0]["end"]), (0, 5))

    def test_all_cited_sources_are_kept_for_confidence_and_audit(self):
        self.report["transcript"]["segments"] *= 6
        self.raw["dimensions"][0]["source_ids"] = [f"S{i}" for i in range(1, 7)]
        result = validate_review(self.raw, self.report)
        self.assertEqual(result["dimensions"][0]["source_ids"], [f"S{i}" for i in range(1, 7)])

    def test_grade_zero_absence_uses_explicit_search_scope(self):
        self.report["transcript"]["segments"] *= 2
        self.raw["dimensions"][-1].update(grade=0, source_ids=[])
        result = validate_review(self.raw, self.report)
        row = result["dimensions"][-1]
        self.assertEqual(row["source_ids"], ["S1", "S2"])
        self.assertEqual(row["evidence_scope"], "whole_transcript_absence_check")
        self.raw["dimensions"][-1].update(grade=2, source_ids=[])
        with self.assertRaises(ValueError):
            validate_review(self.raw, self.report)

    def test_pdf_document_escapes_model_text_and_preserves_indian_scripts(self):
        self.raw["edits"][0]["replacement"] = '<script>alert(1)</script> உங்கள் முடி మీ జుట్టు अपने बाल'
        self.report["review"] = validate_review(self.raw, self.report)
        document = detailed_html(self.report, "a" * 32)
        self.assertNotIn('<script>', document)
        self.assertIn('&lt;script&gt;', document)
        for word in ["உங்கள்", "మీ", "अपने"]:
            self.assertIn(word, document)
