import json
import unittest
from unittest.mock import patch
import httpx
import openai
import studio_script_team as team

class TeamTransportTests(unittest.TestCase):
    def invoke(self, handler, model=team.MODEL, preview=None, effort='high'):
        real=openai.AsyncOpenAI
        def client(**kwargs):
            self.assertEqual(kwargs['timeout'].read,600)
            self.assertEqual(kwargs['timeout'].connect,600)
            return real(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),**kwargs)
        with patch('openai.AsyncOpenAI',side_effect=client):
            return team.chat_json('test-key',model,'Return JSON','Test',1200,.7,preview,reasoning_effort=effort)

    def test_short_drafts_keep_balanced_reasoning_and_reviewers_keep_full_effort(self):
        with patch.object(team,'credential',return_value=''):
            self.assertEqual(team.draft_reasoning_effort(2500,'Draft 1'),'medium')
            self.assertEqual(team.draft_reasoning_effort(12000,'Draft 1'),'high')
            self.assertEqual(team.draft_reasoning_effort(1400,'Critique 1'),'high')
        with patch.object(team,'credential',return_value='high'):
            self.assertEqual(team.draft_reasoning_effort(2500,'Draft 1'),'high')
        seen=[]
        def handler(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200,json={'choices':[{'index':0,'message':{'role':'assistant','content':'{"ok":true}'},'finish_reason':'stop'}]})
        self.invoke(handler,model='nvidia/nemotron-3.5-super-vl-120b-a12b',effort='medium')
        self.assertEqual(seen[0]['reasoning_effort'],'medium')
        self.assertTrue(seen[0]['chat_template_kwargs']['enable_thinking'])

    def test_sdk_final_content_only_and_high_reasoning(self):
        seen=[];previews=[]
        def handler(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200,json={'id':'test','object':'chat.completion','created':0,'model':team.MODEL,'choices':[{'index':0,'message':{'role':'assistant','content':'{"ok":true}','reasoning_content':'PRIVATE'},'finish_reason':'stop'}],'usage':{'prompt_tokens':5,'completion_tokens':5,'total_tokens':10}})
        result,usage=self.invoke(handler,preview=previews.append)
        self.assertEqual(result,{'ok':True});self.assertEqual(usage['total_tokens'],10)
        self.assertNotIn('PRIVATE',str(previews));self.assertTrue(seen[0]['stream'])
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

    def test_transient_service_error_recovers_with_one_fresh_client(self):
        seen=[];notices=[]
        def handler(request):
            seen.append(request)
            if len(seen)==1:return httpx.Response(500,json={'error':{'message':'private provider details'}})
            return httpx.Response(200,json={'choices':[{'index':0,'message':{'role':'assistant','content':'{"ok":true}'},'finish_reason':'stop'}]})
        def preview(content):pass
        preview.status=notices.append
        self.assertEqual(self.invoke(handler,preview=preview)[0],{'ok':True})
        self.assertEqual(len(seen),2)
        self.assertTrue(any('HTTP 500' in notice for notice in notices))
        self.assertNotIn('private provider details',str(notices))

    def test_service_retry_and_connection_retry_share_one_allowance(self):
        seen=[]
        def handler(request):
            seen.append(request)
            if len(seen)==1:return httpx.Response(503,json={})
            raise httpx.ConnectError('Still unavailable')
        with self.assertRaisesRegex(team.HostedWriterError,'could not connect'):
            self.invoke(handler)
        self.assertEqual(len(seen),2)

    def test_buffered_request_emits_waiting_progress_without_private_reasoning(self):
        import asyncio
        notices=[]
        async def handler(request):
            await asyncio.sleep(.04)
            return httpx.Response(200,json={'choices':[{'index':0,'message':{'role':'assistant','content':'{"ok":true}','reasoning_content':'PRIVATE'},'finish_reason':'stop'}]})
        def preview(content):pass
        preview.status=notices.append
        with patch.object(team,'HEARTBEAT_SECONDS',.01):
            self.assertEqual(self.invoke(handler,preview=preview)[0],{'ok':True})
        self.assertTrue(any('Waiting for NVIDIA output' in notice for notice in notices))
        self.assertNotIn('PRIVATE',str(notices))

    def test_streaming_collects_only_final_answer_and_usage(self):
        previews=[]
        chunks=[{'choices':[{'index':0,'delta':{'reasoning_content':'PRIVATE'}}]},
                {'choices':[{'index':0,'delta':{'content':'{"ok":'}}]},
                {'choices':[{'index':0,'delta':{'content':'true}'},'finish_reason':'stop'}]},
                {'choices':[],'usage':{'prompt_tokens':3,'completion_tokens':5,'total_tokens':8}}]
        def handler(request):
            self.assertTrue(json.loads(request.content)['stream'])
            body=''.join('data: '+json.dumps(chunk)+'\n\n' for chunk in chunks)+'data: [DONE]\n\n'
            return httpx.Response(200,headers={'content-type':'text/event-stream'},content=body)
        result,usage=self.invoke(handler,preview=previews.append)
        self.assertEqual(result,{'ok':True})
        self.assertEqual(usage['total_tokens'],8)
        self.assertNotIn('PRIVATE',str(previews))

    def test_incomplete_stream_retries_once_without_approving_partial_json(self):
        calls=[]
        def handler(request):
            calls.append(request)
            chunk={'choices':[{'index':0,'delta':{'content':'{"ok":true}'}}]}
            if len(calls)==2:chunk['choices'][0]['finish_reason']='stop'
            return httpx.Response(200,headers={'content-type':'text/event-stream'},content='data: '+json.dumps(chunk)+'\n\n')
        self.assertEqual(self.invoke(handler)[0],{'ok':True})
        self.assertEqual(len(calls),2)

    def test_tagged_reasoning_inside_content_never_reaches_stream_preview(self):
        previews=[]
        chunks=[{'choices':[{'index':0,'delta':{'content':'<|channel>analysisPRIVATE {"final_script":"secret"}'}}]},
                {'choices':[{'index':0,'delta':{'content':'<channel|>{"ok":true}'},'finish_reason':'stop'}]}]
        def handler(request):
            return httpx.Response(200,headers={'content-type':'text/event-stream'},content=''.join('data: '+json.dumps(c)+'\n\n' for c in chunks))
        self.assertEqual(self.invoke(handler,preview=previews.append)[0],{'ok':True})
        self.assertTrue(previews)
        self.assertNotIn('PRIVATE',str(previews))
        self.assertNotIn('secret',str(previews))

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
