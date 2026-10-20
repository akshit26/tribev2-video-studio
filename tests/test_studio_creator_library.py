import json
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import studio_script_writer as writer
import prepare_riva


class CreatorLibraryTests(unittest.TestCase):
    def test_named_brief_variables_and_persona_reach_generation(self):
        brief = writer.brief_values(dict(product_name='Notebook', target_audience='Forgetful students',
                                        facts='80 blank pages', pain_point='Forgotten ideas',
                                        book_principle='One concrete memorable idea', content_duration='short'))
        self.assertEqual(brief['topic'], 'Notebook')
        self.assertEqual(brief['audience'], 'Forgetful students')
        self.assertEqual(brief['pain_point'], 'Forgotten ideas')
        self.assertEqual(brief['book_principle'], 'One concrete memorable idea')

    def test_creator_principles_reach_prompt_and_saved_reference_metadata(self):
        brief = writer.brief_values(dict(topic='Notebook', facts='80 blank pages',
                                        content_duration='short', content_mode='ugc'))
        text = ('My shopping list has a side hustle. This notebook has 80 blank pages. '
                'One can hold groceries; another can hold the ridiculous business idea that arrives '
                'while you remember the onions. Give those thoughts somewhere to land. Buy the notebook.')
        complete = Mock(return_value={'final_script': text})
        gate = dict(has_cta=True, has_visual_demo=False, invented_experience=False,
                    overall_score=85, critique='Specific observation and grounded integration.')
        with patch('studio_pipeline.score_draft_script', return_value=gate):
            result = writer.write_final_script({'brief': brief}, complete, lambda x: None, lambda *x: None)
        context = json.loads(complete.call_args.args[0].split(' BRIEF: ', 1)[1])
        self.assertEqual(context['content_mode'], 'ugc')
        refs = context['creator_references']
        self.assertTrue(all(card['principle'] and card['apply'] for card in refs))
        self.assertTrue({'creator-emotion', 'creator-share', 'creator-brand-bridge', 'creator-payoff'} <= {c['id'] for c in refs})
        self.assertEqual(result['reference_ids'], [c['id'] for c in refs])
        self.assertEqual(set(result['best']['script']), {'final_script'})

    def test_platform_guidance_and_language_notes_are_recalled(self):
        brief = writer.brief_values(dict(topic='Fashion', facts='Cotton shirt',
                                        platform='YouTube Shorts', language='Hindi'))
        ids = {c['id'] for c in writer.reference_cards(brief)}
        self.assertTrue({'youtube-creator-shorts', 'creator-language', 'creator-niches'} <= ids)


class PreparedWhisperTests(unittest.TestCase):
    def test_explicit_transcription_uses_tls_function_metadata_and_deadline(self):
        import grpc
        from riva.client.proto import riva_asr_pb2_grpc
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / 'audio.wav'
            with wave.open(str(audio), 'wb') as stream:
                stream.setnchannels(1)
                stream.setsampwidth(2)
                stream.setframerate(16000)
                stream.writeframes(b'\0\0' * 160)
            channel = Mock()
            channel.__enter__ = Mock(return_value=channel)
            channel.__exit__ = Mock(return_value=False)
            stub = Mock()
            stub.Recognize.return_value = SimpleNamespace(results=[SimpleNamespace(alternatives=[SimpleNamespace(transcript='Hello')])])
            with patch('studio_script_nvidia.nvidia_token', return_value='test-secret'), patch.object(grpc, 'secure_channel', return_value=channel) as connect, patch.object(riva_asr_pb2_grpc, 'RivaSpeechRecognitionStub', return_value=stub):
                self.assertEqual(prepare_riva.transcribe(audio, 'hi'), 'Hello')
            self.assertEqual(connect.call_args.args[0], prepare_riva.SERVER)
            request = stub.Recognize.call_args.args[0]
            self.assertEqual(request.config.language_code, 'hi')
            self.assertEqual(request.config.sample_rate_hertz, 16000)
            self.assertEqual(stub.Recognize.call_args.kwargs['timeout'], 180)
            self.assertIn(('function-id', prepare_riva.FUNCTION_ID), stub.Recognize.call_args.kwargs['metadata'])
