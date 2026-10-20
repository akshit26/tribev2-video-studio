import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock
from studio_remote_review import review_video

class RemoteReviewTests(unittest.TestCase):
    def test_cloud_review_forwards_context_and_preserves_audio_when_simulator_fails(self):
        result=dict(hook_score=85,pacing_score=80,overall_probability=82,
                    timestamped_revision_advice='00:01: Shorten the opening.',
                    visual_frames=[dict(timestamp=1.,observation='Visible label')])
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder);video=output/'input.mp4';video.write_bytes(b'original-video')
            (output/'upload_info.json').write_text(json.dumps(dict(original_name='creator.mp4',language='hi',platform='instagram',audience='Hindi creators')))
            (output/'brand_context.json').write_text(json.dumps(dict(name='Brand',documents={'product_brief':{'text':'Reusable silicone catcher.'}})))
            pacing=dict(available=True,text='Actual words',wpm=120,duration_seconds=12)
            def failed_audit(*args,**kwargs):
                (output/'transcript.json').write_text(json.dumps(pacing))
                raise RuntimeError('Simulator unavailable')
            with patch('studio_gemma_video.analyze_virality',new_callable=AsyncMock,return_value=result),patch('studio_pipeline.run_cognitive_audit',side_effect=failed_audit) as audit:
                report=review_video(video,output,lambda *args:None)
            self.assertEqual(audit.call_args.kwargs['brief']['language'],'hi')
            self.assertEqual(audit.call_args.kwargs['brief']['facts'],'Reusable silicone catcher.')
            self.assertEqual(report['video']['name'],'creator.mp4')
            self.assertEqual(report['video']['duration_seconds'],12)
            self.assertEqual(report['pacing'],pacing)
            self.assertEqual(report['visual_frames'],[dict(timestamp=1.,observation='Visible label')])
            self.assertEqual(report['cognitive_status'],'unavailable')
    def test_original_mp4_scores_persist_and_no_local_analysis(self):
        result = dict(hook_score=85,pacing_score=80,overall_probability=82,
                      timestamped_revision_advice='00:01-00:03: Shorten the introduction.')
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder); video=output/'input.mp4';video.write_bytes(b'original-video')
            with patch('studio_gemma_video.analyze_virality',new_callable=AsyncMock,return_value=result) as api, patch('studio_pipeline.run_cognitive_audit',side_effect=ValueError('No audio')):
                report=review_video(video,output,lambda *args:None)
            self.assertEqual(report['backend'],'nvidia')
            self.assertEqual(report['dashboard']['status'],'Approved')
            api.assert_awaited_once()
            self.assertEqual(api.call_args.args[0],video)
            self.assertEqual(json.loads((output/'gemma_review.json').read_text())['result'],result)
            self.assertEqual(json.loads((output/'report.json').read_text())['result'],result)
    def test_provider_failure_never_writes_approved_report(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder);video=output/'input.mp4';video.write_bytes(b'original')
            with patch('studio_gemma_video.analyze_virality',new_callable=AsyncMock,side_effect=RuntimeError('API unavailable')):
                with self.assertRaisesRegex(RuntimeError,'API unavailable'):
                    review_video(video,output,lambda *args:None)
            self.assertFalse((output/'report.json').exists())
