"""NVIDIA transport and writer integration tests; no network requests."""
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import studio_script_nvidia as n
import studio_script_hf as hf
import studio_script_writer as writer


class Stream(io.BytesIO):
    status = 200


def stream(chunks, done=True):
    data = b''.join(b'data: '+json.dumps(c).encode()+b'\n\n' for c in chunks)
    return Stream(data + (b'data: [DONE]\n\n' if done else b''))


def answer(text='{"ok":true}', reason='stop'):
    return {'choices': [{'delta': {'content': text}, 'finish_reason': reason}]}


class NvidiaTests(unittest.TestCase):
    def test_voice_edit_preserves_untargeted_paragraphs_and_metadata(self):
        from tests.test_studio_script_writer import script, brief
        import copy
        original=script();snapshot=copy.deepcopy(original)
        request={'brief':dict(brief(),language='Hinglish'),'scene_index':1,'revision_notes':'Make only the middle casual'}
        with patch.object(n,'chat_completion',return_value=({'paragraphs':['Yaar bas ek simple baat hai, mujhe itna sochna hi nahi.']},{})) as send:
            changed,_=n.voice_edit('nvapi-TEST',original,request)
        self.assertEqual(original,snapshot)
        self.assertEqual(changed['scenes'][0],original['scenes'][0])
        self.assertEqual(changed['scenes'][2],original['scenes'][2])
        self.assertNotEqual(changed['scenes'][1]['spoken'],original['scenes'][1]['spoken'])
        self.assertEqual(changed['scenes'][1]['start'],original['scenes'][1]['start'])
        self.assertIn('Make only the middle casual',send.call_args.args[3])
        self.assertNotIn('inventive',send.call_args.args[2])

    def test_voice_edit_failure_preserves_original_with_review_blocker(self):
        from tests.test_studio_script_writer import script, brief
        original=script()
        def fake_writer(path,complete,progress):
            returned=complete('prompt',100,'Draft 1')
            self.assertEqual(returned['scenes'],original['scenes'])
            self.assertTrue(any('voice' in note for note in returned['missing_proof']))
        with tempfile.TemporaryDirectory() as directory:
            request={'brief':dict(brief(),writer_backend='nvidia'),'mode':'script'}
            with patch.object(n,'nvidia_token',return_value='nvapi-TEST'),patch.object(n,'chat_completion',return_value=(original,{})),patch.object(n,'voice_edit',side_effect=hf.HostedWriterError('quota')),patch.object(writer,'run_writer',side_effect=fake_writer):
                n.run_nvidia_writer(Path(directory),request,lambda *a:None)
            usage=json.loads((Path(directory)/'nvidia_writer_usage.json').read_text())
            self.assertEqual(usage['calls_this_run'],2)
            self.assertTrue(usage['warnings'])

    def test_credentials_environment_file_and_public_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'.env').write_text('NVIDIA_API_KEY="nvapi-TESTFILE"\n')
            with patch.object(n, 'ROOT', root), patch.dict(os.environ, {'NVIDIA_API_KEY': ''}):
                self.assertEqual(n.nvidia_token(), 'nvapi-TESTFILE')
            with patch.object(n, 'ROOT', root), patch.dict(os.environ, {'NVIDIA_API_KEY': 'nvapi-TESTENV'}):
                self.assertEqual(n.nvidia_token(), 'nvapi-TESTENV')
                config = hf.configuration()
                self.assertTrue(config['nvidia_token_configured'])
                self.assertEqual(config['default_backend'], 'fast')
                self.assertNotIn('nvapi-TEST', json.dumps(config))

    def test_backend_validation_and_missing_key(self):
        brief = writer.brief_values({'topic':'Notebook','facts':'80 pages','writer_backend':'nvidia'})
        with patch.object(n, 'nvidia_token', return_value=''):
            with self.assertRaisesRegex(ValueError, 'NVIDIA_API_KEY'):
                hf.validate_configuration(brief)
        with patch.object(n, 'nvidia_token', return_value='nvapi-TEST'):
            hf.validate_configuration(brief)
        self.assertEqual(brief['writer_backend'], 'nvidia')

    def test_stream_ignores_reasoning_and_empty_choices_and_parses_json(self):
        chunks = [{'choices':[]}, {'choices':[{'delta':{'reasoning_content':'PRIVATE THOUGHTS'}}]},
                  answer('{"ok":', None), answer('true}'), {'choices':[], 'usage':{'total_tokens':42}}]
        previews = []
        with patch.object(n.urllib.request, 'urlopen') as send:
            send.return_value.__enter__.return_value = stream(chunks)
            result, usage = n.chat_completion('nvapi-TEST', n.MODEL, 'system', 'prompt', 1200, 1, previews.append)
            req = send.call_args.args[0]
        body = json.loads(req.data)
        self.assertEqual(body['model'], n.MODEL)
        self.assertTrue(body['stream'])
        self.assertEqual(body['chat_template_kwargs'], {'enable_thinking':True})
        self.assertEqual(body['reasoning_effort'],'medium')
        self.assertEqual(req.get_header('Authorization'), 'Bearer nvapi-TEST')
        self.assertEqual(result, {'ok':True})
        self.assertEqual(usage, {'total_tokens':42})
        self.assertEqual(previews[-1], '{"ok":true}')
        self.assertNotIn('PRIVATE', str(previews))

    def test_truncated_invalid_and_filtered_results(self):
        for chunks, error in [([answer(reason='length')], ValueError),
                              ([answer('not JSON')], ValueError),
                              ([answer(reason=None)], hf.HostedWriterError),
                              ([answer(reason='content_filter')], hf.HostedWriterError),
                              ([{'error':{'message':'nvapi-TESTSECRET'}}], hf.HostedWriterError)]:
            with self.subTest(chunks=chunks), patch.object(n.urllib.request, 'urlopen') as send:
                send.return_value.__enter__.return_value = stream(chunks)
                with self.assertRaises(error) as caught:
                    n.chat_completion('nvapi-TESTSECRET', n.MODEL, 's', 'p', 100, 0)
                self.assertNotIn('nvapi-TESTSECRET', str(caught.exception))
                self.assertEqual(send.call_count, 1)

    def test_transport_errors_are_sanitized_and_not_retried(self):
        for code in (400,401,402,403,404,429,500):
            exc = urllib.error.HTTPError(n.ENDPOINT, code, 'nvapi-TESTSECRET', None, None)
            with patch.object(n.urllib.request, 'urlopen', side_effect=exc) as send:
                with self.assertRaises(hf.HostedWriterError) as caught:
                    n.chat_completion('nvapi-TESTSECRET', n.MODEL, 's', 'p', 100, 0)
                self.assertNotIn('nvapi-TESTSECRET', str(caught.exception))
                self.assertEqual(send.call_count, 1)

    def test_stream_failure_after_valid_json_does_not_accept_partial_result(self):
        with patch.object(n.urllib.request, 'urlopen') as send:
            send.return_value.__enter__.return_value = stream([answer(reason=None)], done=False)
            with self.assertRaises(hf.HostedWriterError):
                n.chat_completion('nvapi-TEST', n.MODEL, 's', 'p', 100, 0)

    def test_checkpoint_preview_and_shared_revision_pipeline(self):
        brief = writer.brief_values({'topic':'Notebook','facts':'80 pages','writer_backend':'nvidia'})
        request = {'brief':brief, 'mode':'script', 'revision_notes':'Make it funnier'}
        def fake_writer(path, complete, progress):
            self.assertEqual(complete('draft prompt',100,'Draft 1'), {'ok':True})
            complete('draft prompt',100,'Draft 1')
        def fake_chat(token, model, system, prompt, tokens, temperature, preview):
            preview('{"scenes":[{"spoken":"A notebook staged a rebellion."}]}')
            return {'ok':True}, {'total_tokens':12}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            with patch.object(n, 'nvidia_token', return_value='nvapi-TESTSECRET'), patch.object(n, 'chat_completion', side_effect=fake_chat) as send, patch.object(writer, 'run_writer', side_effect=fake_writer):
                n.run_nvidia_writer(path, request, lambda *a: None)
                self.assertEqual(send.call_count, 1)
                n.run_nvidia_writer(path, request, lambda *a: None)
                self.assertEqual(send.call_count, 1)
            self.assertEqual(json.loads((path/'script_live.json').read_text())['paragraphs'], ['A notebook staged a rebellion.'])
            self.assertEqual(json.loads((path/'nvidia_writer_usage.json').read_text())['backend'], 'nvidia')
            self.assertFalse((path/'hf_writer_checkpoint.json').exists())
            for file in path.glob('*.json'):
                self.assertNotIn('nvapi-TESTSECRET', file.read_text())


if __name__ == '__main__':
    unittest.main()
