import unittest

from studio_decision_pdf import decision_html, decisive_reason


class DetailedDecisionPdfTests(unittest.TestCase):
    def test_low_grade_explanation_uses_weakness_not_ocr_noise(self):
        row = {"key": "clarity", "grade": 2,
               "rationale": "The problem is clear. However, the script repeats claims without a payoff. OCR errors may misspell the product."}
        self.assertEqual(decisive_reason(row), "However, the script repeats claims without a payoff.")

    def test_fourth_page_explains_grades_without_a_brand(self):
        report = {"video": {"name": "ad.mp4", "duration_seconds": 20},
                  "review": {"available": True, "overall_score": 50, "content_language": "hi",
                             "summary": "A shampoo ad addresses dandruff.", "verdict": "Needs revision",
                             "sources": [{"id": "S1", "start": 0, "end": 3,
                                          "kind": "speech", "text": "Dandruff problem"}],
                             "dimensions": [{"key": "clarity", "label": "Script and payoff", "grade": 2,
                                             "rationale": "The script repeats claims without a payoff.",
                                             "source_ids": ["S1"]}],
                             "strengths": [], "edits": [], "uncertainties": []}}
        document = decision_html(report)
        self.assertEqual(document.count('class="sheet"'), 4)
        self.assertIn("Why each grade was given", document)
        self.assertIn("Evidence near 0.0s", document)
        self.assertIn("Script and payoff", document)


class LegacyDecisionPdfTests(unittest.TestCase):
    def test_legacy_speech_sources_without_kind_can_render(self):
        report={'video':{'name':'archive.mp4','duration_seconds':20},'review':{
            'available':True,'overall_score':50,'content_language':'en','summary':'A saved review.',
            'sources':[{'id':'S1','start':0,'end':3,'text':'A shampoo claim.'}],
            'dimensions':[{'key':'clarity','label':'Clarity','grade':2,'rationale':'A clear statement, with limited proof.','source_ids':['S1']}],
            'strengths':[],'edits':[],'uncertainties':[]}}
        document=decision_html(report)
        self.assertEqual(document.count('class="sheet"'),4)
        self.assertIn('A shampoo claim.',document)
