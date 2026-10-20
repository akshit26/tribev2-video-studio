import json
import unittest
from unittest.mock import patch
import httpx
import studio_script_team as team

class TeamTransportTests(unittest.TestCase):
    def invoke(self, handler, model=team.MODEL, preview=None):
        real=httpx.AsyncClient
        def client(**kwargs):return real(transport=httpx.MockTransport(handler),**kwargs)
        with patch('httpx.AsyncClient',side_effect=client):
            return team.chat_json('test-key',model,'Return JSON','Test',1200,.7,preview)

    def test_streams_content_only_and_limits_reasoning(self):
        seen=[];previews=[]
        def handler(request):
            seen.append(json.loads(request.content))
            chunks=[{'choices':[{'delta':{'reasoning_content':'PRIVATE REASONING'},'finish_reason':None}]},
                    {'choices':[{'delta':{'content':'{"ok":true}'},'finish_reason':None}]},
                    {'choices':[{'delta':{},'finish_reason':'stop'}],'usage':{'total_tokens':10}}]
            return httpx.Response(200,text=''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n')
        result,usage=self.invoke(handler,preview=previews.append)
        self.assertEqual(result,{'ok':True});self.assertEqual(usage['total_tokens'],10)
        self.assertNotIn('PRIVATE',str(previews));self.assertTrue(seen[0]['stream'])
        self.assertEqual(seen[0]['reasoning_effort'],'low')
        self.assertEqual(seen[0]['temperature'],.7)

    def test_timeout_is_specific_and_not_retried(self):
        calls=[]
        def handler(request):
            calls.append(request);raise httpx.ReadTimeout('private endpoint detail')
        with self.assertRaisesRegex(team.HostedWriterError,'timed out'):
            self.invoke(handler)
        self.assertEqual(len(calls),1)

    def test_partial_stream_is_not_validated_as_complete(self):
        def handler(request):return httpx.Response(200,text='data: {"choices":[{"delta":{"content":"{}"}}]}\n\ndata: [DONE]\n\n')
        with self.assertRaisesRegex(team.HostedWriterError,'before completion'):self.invoke(handler)

    def test_gemma_disables_thinking_and_status_failure_has_no_retry(self):
        seen=[]
        def handler(request):seen.append(json.loads(request.content));return httpx.Response(429)
        with self.assertRaisesRegex(team.HostedWriterError,'HTTP 429'):self.invoke(handler,team.GEMMA)
        self.assertEqual(len(seen),1)
        self.assertEqual(seen[0]['chat_template_kwargs'],{'enable_thinking':False})
