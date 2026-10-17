import copy
import unittest
from studio_estimate import estimate_score


class EstimateTests(unittest.TestCase):
    def setUp(self):
        self.dimensions = [{"key": "hook", "grade": 1, "weight": 50, "source_ids": ["S1"]},
                           {"key": "cta", "grade": 3, "weight": 50, "source_ids": ["S2"]}]
        self.transcript = {"segments": [{"words": [{"probability": .2}] * 10},
                                        {"words": [{"probability": .95}] * 10}]}

    def test_unreliable_penalty_is_discounted_without_erasing_reliable_strength(self):
        result = estimate_score(self.dimensions, self.transcript)
        self.assertEqual(result["raw_score"], 50)
        self.assertEqual(result["score"], 62)
        self.assertEqual(result["dimensions"][0]["estimated_score"], 50)
        self.assertEqual(result["dimensions"][1]["estimated_score"], 75)
        self.assertGreater(result["range"][1] - result["range"][0], 50)

    def test_same_evidence_gets_same_result_in_every_language(self):
        baseline = estimate_score(self.dimensions, self.transcript)
        for language in ("en", "hi", "ta", "te", "kn", "mixed"):
            self.transcript["language"] = language
            self.assertEqual(baseline, estimate_score(self.dimensions, self.transcript))

    def test_uncertain_praise_is_also_discounted_never_forced_above_70(self):
        for d in self.dimensions:
            d["grade"] = 4
        self.transcript["segments"][1] = copy.deepcopy(self.transcript["segments"][0])
        result = estimate_score(self.dimensions, self.transcript)
        self.assertEqual(result["score"], 50)
        self.assertEqual(result["range"], [0, 100])

    def test_correction_or_high_confidence_preserves_raw_score(self):
        self.transcript["manually_corrected"] = True
        result = estimate_score(self.dimensions, self.transcript)
        self.assertEqual(result["score"], result["raw_score"])
        self.assertEqual(result["range"], [42, 58])
        self.transcript.pop("manually_corrected")
        self.transcript["segments"][0] = copy.deepcopy(self.transcript["segments"][1])
        self.assertEqual(estimate_score(self.dimensions, self.transcript), result)

    def test_missing_or_invalid_confidence_is_unknown(self):
        self.transcript["segments"] = [{"words": [{"probability": float("nan")}, {"probability": True}]}]
        result = estimate_score(self.dimensions, self.transcript)
        self.assertEqual(result["evidence_weight_percent"], 50)
        self.assertEqual(result["range"], [17, 83])

    def test_explicit_recognition_concerns_override_confident_asr(self):
        self.transcript["segments"][0] = copy.deepcopy(self.transcript["segments"][1])
        self.dimensions[0]["rationale"] = "The hook appears unclear due to recognition uncertainty."
        result = estimate_score(self.dimensions, self.transcript)
        self.assertTrue(result["dimensions"][0]["recognition_concern"])
        self.assertEqual(result["dimensions"][0]["reliability"], .5)
        self.dimensions[0]["rationale"] = "No transcription errors are evident."
        self.assertEqual(estimate_score(self.dimensions, self.transcript)["dimensions"][0]["reliability"], 1)
