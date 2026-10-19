"""HF integration tests: no paid/network inference is performed."""
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import studio_script_hf as hf
import studio_script_writer as writer


def approved():
    return writer.brief_values({"topic": "Notebook", "facts": "80 pages.",
        "writer_backend": "huggingface", "hf_credits_allowed": True})


class HostedWriterTests(unittest.TestCase):
    def test_local_is_default_and_does_not_need_a_token(self):
        b=writer.brief_values({"topic":"Notebook","facts":"80 pages."})
        self.assertEqual(b['writer_backend'],'local')
        self.assertFalse(b['hf_credits_allowed'])
        with patch.object(hf,'hf_token',side_effect=AssertionError('Local must not read credentials')):
            hf.validate_configuration(b)

    def test_hosted_requires_real_boolean_opt_in_and_known_model(self):
        b=approved();b['hf_credits_allowed']=False
        with self.assertRaisesRegex(ValueError,'disabled'):hf.validate_configuration(b)
        for changes in ({'hf_credits_allowed':'true'},{'hf_model':'evil/model'},{'writer_backend':'unknown'}):
            with self.assertRaises(ValueError):writer.brief_values(dict(approved(),**changes))
        with patch.object(hf,'hf_token',return_value=None):
            with self.assertRaisesRegex(ValueError,'HF_TOKEN'):hf.validate_configuration(approved())

    def test_existing_env_file_and_environment_token_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'.env').write_text('HF_TOKEN="hf_TESTFILEONLY"\n',encoding='utf-8')
            with patch.object(hf,'ROOT',root),patch.dict(os.environ,{'HF_TOKEN':''}):
                self.assertEqual(hf.hf_token(),'hf_TESTFILEONLY')
                with patch.dict(os.environ,{'HF_TOKEN':'hf_TESTENVONLY'}):
                    self.assertEqual(hf.hf_token(),'hf_TESTENVONLY')

    def test_configuration_exposes_only_token_presence(self):
        with patch.object(hf,'hf_token',return_value='hf_TESTONLY'), patch('studio_script_nvidia.nvidia_token',return_value=''):
            config=hf.configuration()
        self.assertTrue(config['token_configured'])
        self.assertNotIn('hf_TESTONLY',json.dumps(config))
        self.assertEqual(config['default_backend'],'local')
        self.assertEqual(len(config['models']),3)

    def test_router_uses_only_hf_token_cheapest_policy_and_json(self):
        response={'choices':[{'message':{'content':'```json\n{"hooks":[]}\n```'},'finish_reason':'stop'}],
                  'usage':{'prompt_tokens':20,'completion_tokens':10}}
        with patch.object(hf.urllib.request,'urlopen') as send:
            send.return_value.__enter__.return_value=io.BytesIO(json.dumps(response).encode())
            result,usage=hf.chat_completion('hf_TESTONLY',hf.DEFAULT_MODEL,'system','prompt',9999,.7)
        request=send.call_args.args[0]
        self.assertEqual(request.full_url,hf.ENDPOINT)
        self.assertEqual(request.get_header('Authorization'),'Bearer hf_TESTONLY')
        body=json.loads(request.data)
        self.assertEqual(body['model'],hf.DEFAULT_MODEL+':cheapest')
        self.assertEqual(body['response_format'],{'type':'json_object'})
        self.assertLessEqual(body['max_tokens'],2400)
        self.assertEqual(result,{'hooks':[]})
        self.assertEqual(usage['completion_tokens'],10)

    def test_http_errors_are_safe_and_never_automatically_retried(self):
        for code,phrase in ((401,'token'),(402,'credits'),(403,'permission'),(404,'model'),(429,'limit'),(503,'unavailable')):
            error=urllib.error.HTTPError(hf.ENDPOINT,code,'hf_TESTSECRET',None,io.BytesIO(b'hf_TESTSECRET'))
            with patch.object(hf.urllib.request,'urlopen',side_effect=error) as send:
                with self.assertRaises(hf.HostedWriterError) as caught:
                    hf.chat_completion('hf_TESTSECRET',hf.DEFAULT_MODEL,'s','p',100,0)
            self.assertIn(phrase,str(caught.exception))
            self.assertNotIn('hf_TESTSECRET',str(caught.exception))
            self.assertEqual(send.call_count,1)

    def test_network_error_is_not_retried_and_does_not_expose_headers(self):
        with patch.object(hf.urllib.request,'urlopen',side_effect=urllib.error.URLError('hf_TESTSECRET')):
            with self.assertRaises(hf.HostedWriterError) as caught:
                hf.chat_completion('hf_TESTSECRET',hf.DEFAULT_MODEL,'s','p',100,0)
        self.assertNotIn('hf_TESTSECRET',str(caught.exception))

    def test_malformed_and_truncated_response_requests_structured_repair(self):
        for choice in ({'message':{'content':'Not JSON'}},
                       {'message':{'content':'{}'},'finish_reason':'length'}):
            with patch.object(hf.urllib.request,'urlopen') as send:
                send.return_value.__enter__.return_value=io.BytesIO(json.dumps({'choices':[choice]}).encode())
                with self.assertRaises(ValueError):hf.chat_completion('hf_TESTONLY',hf.DEFAULT_MODEL,'s','p',100,0)

    def test_checkpoint_cache_reuses_completions_and_keeps_credentials_out(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory);request={'brief':approved()}
            def fake_writer(path,complete,progress):
                progress(.2,'Writing')
                self.assertEqual(complete('test prompt',100,'Draft 1'),{'ok':True})
                self.assertEqual(complete('test prompt',100,'Draft 1'),{'ok':True})
            with patch.object(hf,'hf_token',return_value='hf_TESTSECRET'),patch.object(writer,'run_writer',side_effect=fake_writer),patch.object(hf,'chat_completion',return_value=({'ok':True},{'total_tokens':30})) as send:
                hf.run_hf_writer(output,request,lambda *a:None)
                hf.run_hf_writer(output,request,lambda *a:None)
                self.assertEqual(send.call_count,1)
                stats=json.loads((output/'hf_writer_usage.json').read_text())
                self.assertEqual(stats['calls_this_run'],0)
                self.assertEqual(stats['cache_hits'],2)
                request['brief']['hf_model']='deepseek-ai/DeepSeek-V3.2'
                hf.run_hf_writer(output,request,lambda *a:None)
                self.assertEqual(send.call_count,2)
            for file in output.glob('*.json'):
                self.assertNotIn('hf_TESTSECRET',file.read_text())

    def test_explicit_request_limit_prevents_unbounded_credit_use(self):
        with tempfile.TemporaryDirectory() as directory:
            def fake_writer(path,complete,progress):
                complete('one',100,'Draft 1');complete('two',100,'Draft 2')
            with patch.object(hf,'MAX_CALLS',1),patch.object(hf,'hf_token',return_value='hf_TESTONLY'),patch.object(writer,'run_writer',side_effect=fake_writer),patch.object(hf,'chat_completion',return_value=({},{})) as send:
                with self.assertRaisesRegex(hf.HostedWriterError,'limit'):
                    hf.run_hf_writer(Path(directory),{'brief':approved()},lambda *a:None)
                self.assertEqual(send.call_count,1)


if __name__=='__main__':unittest.main()
