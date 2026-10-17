import unittest

from studio_viewer_response import viewer_response_map


class ViewerResponseTests(unittest.TestCase):
    def test_weakest_relevant_criterion_is_visible_without_double_scoring(self):
        rows = [
            {"key": "hook", "label": "Opening hook", "grade": 3, "source_ids": ["S1"]},
            {"key": "structure", "label": "Story and pacing", "grade": 2, "source_ids": ["S2"]},
            {"key": "visual", "label": "Visual presentation", "grade": 1, "source_ids": ["V1"]},
        ]
        mapped = viewer_response_map(rows)
        attention = next(row for row in mapped if row["key"] == "attention")
        self.assertEqual(attention["status"], "Needs work")
        self.assertEqual(attention["bottleneck"], "Visual presentation")
        self.assertEqual(attention["source_ids"], ["S1", "S2", "V1"])
        self.assertNotIn("score", attention)
