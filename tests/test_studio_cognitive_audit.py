import copy
import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

from studio_av_signals import pacing_from_words
from studio_virality import validate_cognitive_response, simulate_cognitive_response
from studio_pipeline import run_cognitive_audit
from studio_decision_pdf import generate_audit_pdf

COGNITIVE = dict(attention_retention_score=60, emotional_arousal_state='Low-arousal boredom (hypothesis)',
    cognitive_load_warning=False, psychological_critique='The opening at 0.5s lacks a clear audience stake.',
    failure_timestamps=[{'timestamp': .5, 'reason': 'Static opening'}])
SCRIPT = ('Drain hair looks like a tiny swamp creature. A silicone catcher sits over the drain and catches loose hair. '
          'Lift it, remove the hair, rinse it, and reuse it. Buy a hair catcher for your shower.')
GOOD = dict(has_cta=True, has_visual_demo=True, invented_experience=False, overall_score=85, critique='Grounded action.')


class CognitiveTests(unittest.TestCase):
    def test_human_correction_is_used_for_simulation_without_retranscription(self):
        def metadata(*args):
            yield {'duration':12}
        transcript=dict(manually_corrected=True,language='hi',segments=[
            dict(start=1,end=5,text='These are the corrected words.'),
            dict(start=7,end=11,text='This ending is corrected too.')])
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)
            (output/'review_input.json').write_text(json.dumps({'transcript':transcript}))
            with patch('imageio_ffmpeg.read_frames',side_effect=metadata),patch('studio_av_signals.transcribe_pacing') as asr,patch('studio_virality.simulate_cognitive_response',return_value=dict(COGNITIVE,attention_retention_score=85)) as simulate:
                result=run_cognitive_audit(output/'input.mp4',output,[{'timestamp':1.}],lambda *args:None)
            asr.assert_not_called()
            self.assertEqual(simulate.call_args.args[1],'These are the corrected words. This ending is corrected too.')
            self.assertEqual(result['pacing']['wpm'],50)
            self.assertEqual(result['pacing']['words'],[])
            self.assertEqual(result['pacing']['dead_air'],[dict(start=5,end=7)])
    def test_nemotron_selection_accepts_both_models_and_normalizes_short_ids(self):
        from studio_virality import cognitive_model, DEFAULT_COGNITIVE_MODEL
        for configured, expected in [('', DEFAULT_COGNITIVE_MODEL),
                ('nemotron-3-ultra-550b-a55b', 'nvidia/nemotron-3-ultra-550b-a55b'),
                ('nvidia/nemotron-3.5-super-vl-120b-a12b', DEFAULT_COGNITIVE_MODEL)]:
            with patch('studio_script_nvidia.nvidia_token', return_value=configured):
                self.assertEqual(cognitive_model(), expected)
        with patch('studio_script_nvidia.nvidia_token', return_value='retired-model'):
            with self.assertRaises(ValueError):
                cognitive_model()

    def test_word_pacing_counts_full_duration_and_only_gaps_over_one_second(self):
        result = pacing_from_words([dict(start=1, end=2, word='One'), dict(start=3.01, end=4, word='two')], 6)
        self.assertEqual(result['wpm'], 20)
        self.assertEqual(result['dead_air'], [{'start': 2, 'end': 3.01}, {'start': 4, 'end': 6}])
        self.assertEqual(pacing_from_words([], 5)['wpm'], 0)
        with self.assertRaises(ValueError):
            pacing_from_words([dict(start=0, end=float('nan'), word='Bad')], 5)

    def test_schema_rejects_false_scores_and_out_of_bounds_frame_times(self):
        self.assertEqual(validate_cognitive_response(copy.deepcopy(COGNITIVE), 4), COGNITIVE)
        for update in [dict(attention_retention_score=True), dict(cognitive_load_warning=1),
                       dict(failure_timestamps=[dict(timestamp=4, reason='Outside clip')])]:
            with self.assertRaises(ValueError):
                validate_cognitive_response(dict(COGNITIVE, **update), 4)

    def test_cloud_receives_actual_transcript_and_frame_observations(self):
        with patch('studio_script_nvidia.nvidia_token', side_effect=lambda name='NVIDIA_API_KEY': '' if name=='COGNITIVE_MODEL' else 'test'), patch('studio_script_team.chat_json', return_value=(copy.deepcopy(COGNITIVE), {})) as api:
            result = simulate_cognitive_response([dict(timestamp=.5, observation='Static label')], 'Actual words', {'duration_seconds': 4, 'wpm': 30, 'words': []})
        payload = json.loads(api.call_args.args[3])
        self.assertEqual(payload['transcript'], 'Actual words')
        self.assertEqual(payload['visual_frame_data'][0]['timestamp'], .5)
        self.assertNotIn('words', payload['audio_pacing'])
        self.assertEqual(result['attention_retention_score'], 60)

    def pipeline(self, folder, score=60, rewrite_error=None):
        def metadata(*args):
            yield {'duration': 4}
        pacing = dict(available=True, duration_seconds=4, wpm=30, words=[], text='Original text', dead_air=[], note='ASR')
        cognitive = dict(copy.deepcopy(COGNITIVE), attention_retention_score=score)
        complete = Mock(side_effect=rewrite_error, return_value=({'final_script': SCRIPT}, {}))
        def image(video, timestamp, path):
            from PIL import Image
            path.parent.mkdir(exist_ok=True)
            Image.new('RGB', (64, 64), 'red').save(path)
            return path
        with patch('imageio_ffmpeg.read_frames', side_effect=metadata), patch('studio_av_signals.transcribe_pacing', return_value=pacing), patch('studio_virality.simulate_cognitive_response', return_value=cognitive), patch('studio_script_team.chat_json', complete), patch('studio_script_team.nvidia_token', return_value='test'), patch('studio_pipeline.score_draft_script', return_value=GOOD), patch('studio_pipeline.extract_audit_frame', side_effect=image):
            result = run_cognitive_audit(Path(folder)/'input.mp4', Path(folder), [{'timestamp': .5}], lambda *x: None,
                                         dict(facts='Reusable silicone catcher catches loose hair over the drain. Lift, remove hair and rinse.'))
        return result, complete

    def test_threshold_is_strict_and_rewrite_happens_exactly_once(self):
        with tempfile.TemporaryDirectory() as folder:
            result, complete = self.pipeline(folder, score=70)
            complete.assert_not_called()
            self.assertFalse(result['audit']['triggered'])
            result, complete = self.pipeline(folder)
            self.assertEqual(complete.call_count, 1)
            self.assertTrue(result['audit']['rewrite_approved'])
            self.assertEqual(result['audit']['pdf_file'], 'audit.pdf')

    def test_failed_rewrite_keeps_critique_and_pdf_without_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            result, complete = self.pipeline(folder, rewrite_error=RuntimeError('Unavailable'))
            self.assertEqual(complete.call_count, 1)
            self.assertFalse(result['audit']['rewrite_approved'])
            self.assertTrue((Path(folder)/'audit.pdf').is_file())

    def test_large_pdf_never_exceeds_three_pages_and_embeds_evidence(self):
        from PIL import Image
        from pypdf import PdfReader
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder)/'frame.jpg'
            Image.new('RGB', (100, 200), 'blue').save(image)
            data = generate_audit_pdf('Original words. '*5000, 'Revised words. '*5000, '<unsafe> & critique '*1000, [image]*3)
            pdf = PdfReader(BytesIO(data))
            self.assertEqual(len(pdf.pages), 3)
            self.assertTrue(list(pdf.pages[1].images))
            self.assertIn('Script Revisions', pdf.pages[2].extract_text())
            self.assertIn('Excerpt', pdf.pages[2].extract_text())
