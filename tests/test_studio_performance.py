import unittest
from unittest.mock import Mock, patch
from studio_review_parts import burst_limits, recognition_penalty, contradicts_known_cta, reconcile_summary_cta, check_edit_conflict
from studio_gpu_monitor import read_gpu
from studio_brand_review import validate_checks


class PerformanceAndValidationTests(unittest.TestCase):
    def test_replacement_scripts_cannot_conflict_on_the_same_source_span(self):
        prior=[{'operation':'replace','source_ids':['S1','S2']}]
        with self.assertRaisesRegex(ValueError,'conflicting replacement'):
            check_edit_conflict({'operation':'replace','source_ids':['S2','S3']},prior)
        check_edit_conflict({'operation':'replace','source_ids':['S4']},prior)
        check_edit_conflict({'operation':'overlay','source_ids':['S1']},prior)

    def test_recognition_concession_does_not_penalize_a_valid_rating(self):
        text = "The CTA is clearly visible and functional despite minor recognition noise."
        self.assertFalse(recognition_penalty(text))
        self.assertFalse(recognition_penalty('OCR errors are not counted against the creative.'))
        self.assertFalse(recognition_penalty('The product name has recognition noiseâ€”this does not undermine emotional relevance.'))
        self.assertTrue(recognition_penalty('OCR errors make the message weak and confusing.'))
        self.assertTrue(recognition_penalty('OCR recognition errors undermine clarity.'))
        self.assertTrue(recognition_penalty('Despite OCR noise, recognition errors make this weak.'))
        self.assertTrue(recognition_penalty('Despite OCR errors reducing clarity, the product is visible.'))

    def test_negated_cta_criticism_is_not_a_contradiction(self):
        self.assertFalse(contradicts_known_cta('The CTA is not unclear: comment DUO for the link.'))
        self.assertTrue(contradicts_known_cta('The CTA is unclear.'))

    def test_summary_cta_correction_uses_observed_keyword_without_changing_grade(self):
        row={'summary':'A hair testimonial. The CTA is unclear.', 'verdict':'Weak CTA clarity','grade':2}
        reconcile_summary_cta(row,[{'keyword':'DUO','source_id':'O16'}])
        self.assertIn('comment DUO for a link (O16)',row['summary'])
        self.assertEqual(row['grade'],2)
        self.assertEqual(row['cta_grounding_corrections']['verdict'],'Weak CTA clarity')

    def test_warm_gpu_uses_shorter_bursts_without_changing_token_budget(self):
        self.assertEqual(burst_limits({'temperature_c':63}),(96,32))
        self.assertEqual(burst_limits({'temperature_c':69}),(48,16))
        self.assertEqual(burst_limits({'temperature_c':71}),(48,16))
        self.assertEqual(burst_limits({'temperature_c':75}),(24,8))
        self.assertEqual(burst_limits({'temperature_c':78}),(24,8))
        self.assertEqual(burst_limits({'temperature_c':80}),(24,8))
        self.assertEqual(burst_limits(None),(64,16))

    def test_driver_failure_does_not_return_stale_or_successful_telemetry(self):
        dll=Mock();dll.nvmlDeviceGetMemoryInfo.return_value=1
        with patch('studio_gpu_monitor.driver',return_value=(dll,None)):
            self.assertIsNone(read_gpu())

    def test_driver_reads_are_fresh_for_the_thermal_guard(self):
        temperatures=iter([63,82])
        def memory(handle,out):
            out._obj.total=6144*1024**2;out._obj.used=3300*1024**2;return 0
        def temperature(handle,sensor,out):out._obj.value=next(temperatures);return 0
        def name(handle,out,size):out.value=b'Test GPU';return 0
        dll=Mock(nvmlDeviceGetMemoryInfo=memory,nvmlDeviceGetTemperature=temperature,nvmlDeviceGetName=name)
        with patch('studio_gpu_monitor.driver',return_value=(dll,None)):
            self.assertEqual(read_gpu()['temperature_c'],63)
            self.assertEqual(read_gpu()['temperature_c'],82)

    def test_missing_brand_change_gets_explicit_editor_direction(self):
        row={'requirement':'Name product','status':'meets','reason':'Named in speech','source_ids':['S1']}
        clean=validate_checks({'checks':[row]},'Name product',{'S1'})[0]
        self.assertEqual(clean['status'],'meets')
        self.assertEqual(clean['change'],'No change needed for this requirement.')
        self.assertEqual(clean['change_origin'],'rule-based editor check')

    def test_unsupported_absence_is_unknown_not_zero_brand_fit(self):
        row={'requirement':'Show logo','status':'missing','reason':'Not established','source_ids':[]}
        clean=validate_checks({'checks':[row]},'Show logo',{'S1'})[0]
        self.assertEqual(clean['status'],'unknown')
        self.assertIn('withheld',clean['evidence_note'])

    def test_any_unsupported_scored_brand_status_becomes_unknown(self):
        for status in ('meets','partial','missing','conflicts'):
            row={'requirement':'Show logo','status':status,'reason':'No cited evidence','source_ids':[]}
            clean=validate_checks({'checks':[row]},'Show logo',{'S1'})[0]
            self.assertEqual(clean['status'],'unknown')
            self.assertIn('withheld',clean['evidence_note'])
