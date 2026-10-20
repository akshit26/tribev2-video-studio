import json
import unittest
from unittest.mock import patch
import httpx
import openai
import studio_script_team as team

class TeamTransportTests(unittest.TestCase):
    def invoke(self, handler, model=team.MODEL, preview=None):
        real=openai.AsyncOpenAI
        def client(**kwargs):
            self.assertEqual(kwargs['timeout'].read,600)
            self.assertEqual(kwargs['timeout'].connect,600)
            return real(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),**kwargs)
        with patch('openai.AsyncOpenAI',side_effect=client):
            return team.chat_json('test-key',model,'Return JSON','Test',1200,.7,preview)

    def test_sdk_final_content_only_and_high_reasoning(self):
        seen=[];previews=[]
        def handler(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200,json={'id':'test','object':'chat.completion','created':0,'model':team.MODEL,'choices':[{'index':0,'message':{'role':'assistant','content':'{"ok":true}','reasoning_content':'PRIVATE'},'finish_reason':'stop'}],'usage':{'prompt_tokens':5,'completion_tokens':5,'total_tokens':10}})
        result,usage=self.invoke(handler,preview=previews.append)
        self.assertEqual(result,{'ok':True});self.assertEqual(usage['total_tokens'],10)
        self.assertNotIn('PRIVATE',str(previews));self.assertFalse(seen[0]['stream'])
        self.assertEqual(seen[0]['reasoning_effort'],'high');self.assertEqual(seen[0]['temperature'],.7)
        self.assertEqual(seen[0]['max_tokens'],32768)

    def test_nemotron_role_budgets_preserve_draft_and_scoring_capacity(self):
        seen=[];real=openai.AsyncOpenAI
        def handler(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200,json={'choices':[{'index':0,'message':{'role':'assistant','content':'{"ok":true}'},'finish_reason':'stop'}]})
        def client(**kwargs):return real(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),**kwargs)
        with patch('openai.AsyncOpenAI',side_effect=client):
            for budget in (1400,2500,12000):
                team.chat_json('test-key','nvidia/nemotron-3.5-super-vl-120b-a12b','Return final_script JSON','Format draft',budget,.7)
        self.assertTrue(all(body['response_format']=={'type':'json_object'} for body in seen))
        self.assertEqual([body['max_tokens'] for body in seen],[32768,32768,32768])
        self.assertEqual(seen[1]['reasoning_effort'],'high')
        for body in seen:
            self.assertEqual(body['chat_template_kwargs'],{'enable_thinking':True})
            self.assertEqual(body['reasoning_effort'],'high')

    def test_timeout_is_specific_and_not_retried(self):
        calls=[]
        def handler(request):calls.append(request);raise httpx.ReadTimeout('private endpoint detail')
        with self.assertRaisesRegex(team.HostedWriterError,'within 600 seconds'):self.invoke(handler)
        self.assertEqual(len(calls),1)

    def test_ultra_keeps_reasoning_enabled(self):
        seen=[]
        def handler(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200,json={'choices':[{'index':0,'message':{'role':'assistant','content':'{"ok":true}'},'finish_reason':'stop'}]})
        self.assertEqual(self.invoke(handler,model='nvidia/nemotron-3-ultra-550b-a55b')[0],{'ok':True})
        self.assertEqual(seen[0]['reasoning_effort'],'high')
        self.assertEqual(seen[0]['chat_template_kwargs'],{'enable_thinking':True})

    def test_connection_drop_retries_once_with_fresh_client(self):
        calls=[]
        def handler(request):
            calls.append(request)
            if len(calls)==1:
                raise httpx.ConnectError('Temporary connection interruption')
            return httpx.Response(200,json={'choices':[{'index':0,'message':{'role':'assistant','content':'{"ok":true}'},'finish_reason':'stop'}]})
        self.assertEqual(self.invoke(handler)[0],{'ok':True})
        self.assertEqual(len(calls),2)

    def test_repeated_connection_failure_is_bounded(self):
        calls=[]
        def handler(request):
            calls.append(request)
            raise httpx.ConnectError('private diagnostic')
        with self.assertRaisesRegex(team.HostedWriterError,'could not connect'):
            self.invoke(handler)
        self.assertEqual(len(calls),2)

    def test_truncated_completion_cannot_be_saved_as_valid(self):
        def handler(request):return httpx.Response(200,json={'choices':[{'index':0,'message':{'role':'assistant','content':'{}'},'finish_reason':'length'}]})
        with self.assertRaisesRegex(ValueError,'reached its limit'):self.invoke(handler)

    def test_gemma_enables_thinking_and_status_failure_has_no_retry(self):
        seen=[]
        def handler(request):seen.append(json.loads(request.content));return httpx.Response(429,json={'error':{'message':'private provider message'}})
        with self.assertRaisesRegex(team.HostedWriterError,'HTTP 429'):self.invoke(handler,team.GEMMA)
        self.assertEqual(len(seen),1);self.assertEqual(seen[0]['chat_template_kwargs'],{'enable_thinking':True})
        self.assertEqual([m['role'] for m in seen[0]['messages']],['user'])
        self.assertEqual(seen[0]['max_tokens'],16384)
        self.assertEqual(seen[0]['temperature'],.5)
        self.assertEqual(seen[0]['seed'],0)

    def test_reasoning_tags_are_discarded_before_final_json(self):
        previews=[]
        def handler(request):return httpx.Response(200,json={'choices':[{'index':0,'message':{'role':'assistant','content':'<|channel>thoughtPRIVATE {"wrong":true}<channel|>{"ok":true}'},'finish_reason':'stop'}]})
        result,_=self.invoke(handler,team.GEMMA,previews.append)
        self.assertEqual(result,{'ok':True});self.assertNotIn('PRIVATE',str(previews))

    def test_pending_request_is_polled_without_resubmitting(self):
        from unittest.mock import AsyncMock
        identifier='42c8dc9c-eace-4d89-949f-c330a7d2d08b';calls=[]
        def handler(request):
            calls.append(request)
            self.assertEqual(request.headers['NVCF-POLL-SECONDS'],'300')
            return httpx.Response(202,json={'requestId':identifier})
        result={'id':'queued-result','object':'chat.completion','created':0,'model':team.MODEL,'choices':[{'index':0,'message':{'role':'assistant','content':'{"ok":true}'},'finish_reason':'stop'}]}
        with patch('studio_gemma_video.poll_result',new_callable=AsyncMock,return_value=result) as poll:
            self.assertEqual(self.invoke(handler)[0],{'ok':True})
        poll.assert_awaited_once_with('test-key',identifier);self.assertEqual(len(calls),1)

    def test_queued_request_is_not_parsed_as_corrupt_json(self):
        def handler(request):return httpx.Response(202,json={'requestId':'test'})
        with self.assertRaisesRegex(team.HostedWriterError,'queued or incomplete'):self.invoke(handler)

class CompactHookTests(unittest.TestCase):
    def test_prompt_keeps_facts_language_and_does_not_replace_repairs(self):
        from studio_script_writer import brief_values
        request={'brief':brief_values({'topic':'Notebook','facts':'80 blank pages.','language':'Hindi','writer_backend':'team'})}
        compact=team.prepare_prompt('Repeated instructions'*500,'Hook options 1',request)
        self.assertIn('80 blank pages.',compact);self.assertIn('Hindi',compact)
        self.assertLess(len(compact),5000)
        self.assertEqual(team.prepare_prompt('Repair exactly one word','Hook options 1 repair',request),'Repair exactly one word')
