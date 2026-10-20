import asyncio,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import httpx,openai
import studio_gemma_video as gemma
import studio_server as server
from fastapi.testclient import TestClient
RESULT={'hook_score':85,'pacing_score':80,'overall_probability':82,'timestamped_revision_advice':'00:02-00:04: Shorten the repeated opening.'}
MP4=b'\x00\x00\x00\x18ftypisom'+bytes(24)
class GemmaVideoTests(unittest.TestCase):
    def test_strict_results_and_unavailable_never_rejected(self):
        self.assertEqual(gemma.dashboard_state(RESULT)['status'],'Approved')
        self.assertEqual(gemma.dashboard_state(dict(RESULT,pacing_score=50))['status'],'Rejected')
        self.assertEqual(gemma.dashboard_state(None)['status'],'Unavailable')
        for bad in [dict(RESULT,hook_score=True),dict(RESULT,pacing_score=float('nan')),dict(RESULT,hook_score=101),dict(RESULT,extra=1),dict(RESULT,timestamped_revision_advice='No timestamp')]:
            with self.assertRaises(gemma.ViralityAPIError):gemma.validate_result(json.dumps(bad))
    def test_sdk_receives_original_mp4_and_180_second_limit(self):
        seen=[];real=openai.AsyncOpenAI
        def handler(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200,json={'choices':[{'index':0,'message':{'role':'assistant','content':json.dumps(RESULT)},'finish_reason':'stop'}]})
        def client(**kwargs):
            self.assertEqual(kwargs['timeout'].read,180)
            return real(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),**kwargs)
        with tempfile.TemporaryDirectory() as folder,patch('openai.AsyncOpenAI',side_effect=client),patch('studio_script_nvidia.nvidia_token',return_value='test-key'):
            path=Path(folder)/'input.mp4';path.write_bytes(MP4)
            self.assertEqual(asyncio.run(gemma.analyze_virality(path)),RESULT)
        body=seen[0];self.assertEqual(body['model'],gemma.MODEL)
        media=body['messages'][0]['content'][1]
        self.assertEqual(media['type'],'video_url');self.assertTrue(media['video_url']['url'].startswith('data:video/mp4;base64,'))
    def test_background_result_failure_and_persistence_do_not_change_original_report(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(server,'RESULTS_DIR',Path(folder)),patch.object(server,'_jobs',{}),patch('studio_script_nvidia.nvidia_token',return_value='test-key'):
            sid='e'*32;directory=Path(folder)/sid;directory.mkdir()
            (directory/'job.json').write_text(json.dumps({'id':sid,'status':'completed'}))
            (directory/'input.mp4').write_bytes(MP4)
            (directory/'report.json').write_text('{"original":true}')
            async def success(video):return RESULT
            async def failure(video):raise gemma.ViralityAPIError('Provider unavailable')
            with TestClient(server.app,base_url='http://127.0.0.1:8765') as c:
                self.assertEqual(c.get('/api/jobs/'+sid+'/gemma-review').json()['status'],'not_started')
                for outcome,expected in [(success,'completed'),(failure,'failed')]:
                    with patch.object(gemma,'analyze_virality',side_effect=outcome):
                        r=c.post('/api/jobs/'+sid+'/gemma-review');self.assertEqual(r.status_code,202,r.text)
                        for _ in range(100):
                            state=c.get('/api/jobs/'+sid+'/gemma-review').json()
                            if state['status'] in {'completed','failed'}:break
                            time.sleep(.01)
                        self.assertEqual(state['status'],expected)
                        if expected=='failed':self.assertNotIn('dashboard',state);self.assertNotIn('result',state)
                self.assertEqual(json.loads((directory/'report.json').read_text()),{'original':True})
                self.assertEqual(c.post('/api/jobs/invalid/gemma-review').status_code,404)
                (directory/'input.mp4').unlink()
                self.assertEqual(c.post('/api/jobs/'+sid+'/gemma-review').status_code,422)
