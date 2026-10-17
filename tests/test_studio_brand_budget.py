import unittest

from studio_brand_review import generate_brand_review
from studio_review_parts import ReviewOutputBudgetError


class BrandBudgetTests(unittest.TestCase):
    def run_brand(self, text, complete):
        report = {'video': {'duration_seconds': 5}, 'transcript': {'language': 'hi'},
                  'brand_context': {'id': 'brand', 'name': 'Brand', 'version': 1,
                                    'documents': {'product_brief': {'name': 'Brief', 'text': text}},
                                    'calibration': {'adjustment': 0}, 'note': 'Snapshot'}}
        review = {'sources': [{'id': 'O3', 'start': 0, 'end': 5, 'text': 'Brand overlay'}],
                  'estimate': {'score': 60, 'range': [50, 70]}}
        generate_brand_review(report, review, review['sources'], complete, len, lambda *_: None)
        return review['brand_review']

    def section(self, prompt):
        return prompt.split('each check):\n', 1)[1].split('\nReturn JSON', 1)[0]

    def response(self, section):
        return {'checks': [{'requirement': section, 'status': 'unknown', 'source_ids': [],
                            'reason': 'Visual evidence needs verification.', 'change': 'Verify the source frame.'}]}

    def test_budget_overflow_splits_without_repeating_or_losing_source_text(self):
        text = 'Mention the brand clearly. Keep the product label visible. Use the original language. Preserve approved CTA wording.'
        calls = []; leaves = []
        def complete(prompt, tokens, label):
            section = self.section(prompt); calls.append((label, section))
            self.assertIn('"source_ids":["O3"]', prompt)
            if '/ subsection ' not in label:
                raise ReviewOutputBudgetError('Review part exceeded its output budget; incomplete text was rejected')
            leaves.append(section)
            return self.response(section)
        result = self.run_brand(text, complete)
        self.assertEqual(''.join(leaves), text)
        self.assertEqual(sum('/ subsection ' not in label for label, _ in calls), 1)
        self.assertEqual(len(result['checks']), len(leaves))
        self.assertTrue(all(r['status'] == 'unknown' for r in result['checks']))

    def test_explicit_density_signal_preserves_every_section(self):
        text = 'Require a clear product name. Require a closing action. Preserve brand colors. Keep claims grounded.'
        leaves = []
        def complete(prompt, tokens, label):
            section = self.section(prompt)
            if '/ subsection ' not in label: return {'split_required': True}
            leaves.append(section)
            return self.response(section)
        self.run_brand(text, complete)
        self.assertEqual(''.join(leaves), text)

    def test_minimal_section_overflow_fails_without_scoring_incomplete_checks(self):
        def complete(*_): raise ReviewOutputBudgetError('output budget')
        with self.assertRaisesRegex(ValueError, 'no incomplete checks were scored'):
            self.run_brand('Keep logo visible.', complete)

    def test_regular_schema_errors_still_retry_and_reject_invalid_source_ids(self):
        calls = []
        def complete(prompt, tokens, label):
            calls.append(label)
            row = self.response(self.section(prompt))
            row['checks'][0].update(status='meets', source_ids=['O999'])
            return row
        with self.assertRaisesRegex(ValueError, 'missing video source'):
            self.run_brand('Keep logo visible.', complete)
        self.assertEqual(len(calls), 2)
