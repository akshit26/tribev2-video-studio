import io
import json
import tempfile
import threading
import time
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
import studio_server as server
import studio_script_research as r
from studio_resources import maximum_gpu_budget
from studio_review import review_command


SOURCES=[{'id':'R1','title':'Routine questions','url':'https://example.com/story','excerpt':'People compare simple routines.','published_at':'','evidence':'Search snippet only'}]
ANSWER={'summary':'A routine-choice discussion, not proof of results.','findings':[{'observation':'The source discusses routines.','source_ids':['R1']}],
    'angles':[{'idea':'A solo rant about overcomplicated labels.','source_ids':['R1']}],'questions':['Which part feels confusing?'],'avoid':['No invented product efficacy.']}


class Response(io.BytesIO):status=200


class ResearchTests(unittest.TestCase):
    def test_maximum_budget_reserves_desktop_and_expands_local_context(self):
        self.assertEqual(maximum_gpu_budget(6144),5632)
        self.assertEqual(maximum_gpu_budget(24576),24064)
        self.assertEqual(maximum_gpu_budget(256),0)
        small=review_command(Path('llama-server.exe'),1234,budget_mb=4096)
        large=review_command(Path('llama-server.exe'),1234,budget_mb=5632)
        self.assertEqual(small[small.index('-c')+1],'6144')
        self.assertEqual(large[large.index('-c')+1],'8192')
        self.assertEqual(large[large.index('-b')+1],'128')
        self.assertEqual(large[large.index('-ngl')+1],'all')

    def test_search_has_bounded_snippets_and_no_result_page_fetches(self):
        rss=b'<rss><channel><item><title>Routine discussion</title><link>https://example.com/topic</link><description>'+b'word '*60+b'</description><pubDate>2026-10-01</pubDate></item><item><title>bad</title><link>http://127.0.0.1/private</link><description>hidden</description></item></channel></rss>'
        with patch.object(r.urllib.request,'urlopen') as send:
            send.return_value.__enter__.return_value=Response(rss)
            sources,mode,warnings=r.search_sources(r.values({'topic':'skincare','niche':'skincare'}))
        self.assertEqual(mode,'news_search')
        self.assertEqual(len(sources),1)
        self.assertEqual(len(sources[0]['excerpt'].split()),25)
        self.assertEqual(send.call_count,1)
        self.assertTrue(warnings)

    def test_search_fallback_is_explicitly_historical(self):
        with patch.object(r.urllib.request,'urlopen',side_effect=urllib.error.URLError('blocked')):
            sources,mode,warnings=r.search_sources(r.values({'topic':'arcade','niche':'arcade'}))
        self.assertEqual(mode,'curated_fallback')
        self.assertEqual(len(sources),2)
        self.assertIn('not fresh',warnings[0])

    def test_model_uses_muse_and_never_persists_reasoning_or_credentials(self):
        response={'choices':[{'message':{'content':json.dumps(ANSWER),'reasoning_content':'PRIVATE THOUGHTS'},'finish_reason':'stop'}],'usage':{'total_tokens':100}}
        with patch.object(r,'nvidia_token',return_value='nvapi-TESTSECRET'),patch.object(r.urllib.request,'urlopen') as send:
            send.return_value.__enter__.return_value=Response(json.dumps(response).encode())
            result,usage=r.synthesize(r.values({'topic':'skincare'}),SOURCES)
        body=json.loads(send.call_args.args[0].data)
        self.assertEqual(body['model'],'meta/muse-glimmer-30b')
        self.assertEqual(body['max_tokens'],8192)
        self.assertFalse(body['stream'])
        self.assertNotIn('PRIVATE THOUGHTS',json.dumps(result))
        self.assertNotIn('nvapi-TESTSECRET',json.dumps(result))
        self.assertEqual(usage['total_tokens'],100)
        invalid=dict(ANSWER,findings=[{'observation':'invented','source_ids':['R99']}])
        with self.assertRaises(ValueError):r.validate(invalid,SOURCES)

    def test_research_context_is_bounded_unverified_and_matches_topic(self):
        brief=r.values({'topic':'Moisturiser','niche':'skincare'})
        result=dict(ANSWER,sources=SOURCES,source_mode='news_search')
        state={'status':'completed','brief':brief,'result':result}
        context=r.writing_context(state,brief)
        self.assertIn('never product proof',context['status'])
        self.assertLess(len(json.dumps(context)),1800)
        with self.assertRaises(ValueError):r.writing_context(state,dict(brief,topic='Soda'))


class ResearchAPITests(unittest.TestCase):
    def test_remote_research_works_while_gpu_busy_and_notes_attach_only_on_request(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(server,'RESULTS_DIR',Path(folder)),patch.object(server,'_active_job','gpu-job'),patch('studio_script_nvidia.nvidia_token',return_value='nvapi-TESTSECRET'):
            entered=threading.Event();release=threading.Event()
            def research(brief,save_sources,progress):
                save_sources({'sources':SOURCES,'source_mode':'news_search','warnings':[]})
                entered.set();release.wait(3)
                return dict(ANSWER,sources=SOURCES,source_mode='news_search',warnings=[],method='Fixture research')
            with TestClient(server.app,base_url='http://127.0.0.1:8765') as client,patch.object(r,'research',side_effect=research):
                first=client.post('/api/scripts/research',json={'topic':'Moisturiser','niche':'skincare','language':'English','research_mode':'topic_notes'})
                self.assertEqual(first.status_code,202,first.text)
                self.assertTrue(entered.wait(2))
                sid=first.json()['id']
                self.assertEqual(server._active_job,'gpu-job')
                self.assertEqual(client.post('/api/scripts/research',json={'topic':'Other'}).status_code,409)
                release.set()
                for _ in range(100):
                    state=client.get('/api/scripts/research/'+sid).json()
                    if state['status']=='completed':break
                    time.sleep(.01)
                self.assertEqual(state['status'],'completed')
                self.assertNotIn('nvapi-TESTSECRET',json.dumps(state))
                with patch.object(server,'_active_job',None),patch.object(server._executor,'submit'):
                    response=client.post('/api/scripts',json={'brief':{'topic':'Moisturiser','facts':'A moisturiser.','niche':'skincare','writer_backend':'nvidia','research_id':sid},'mode':'script'})
                    self.assertEqual(response.status_code,202,response.text)
                    self.assertIn('research_context',response.json()['brief'])
                    self.assertEqual(response.json()['brief']['facts'],'A moisturiser.')
                self.assertEqual(client.get('/api/scripts/research/not-valid').status_code,404)


if __name__=='__main__':unittest.main()
