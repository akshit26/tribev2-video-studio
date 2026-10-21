import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,AsyncMock
from studio_remote_review import review_video

COGNITIVE=dict(attention_retention_score=82,emotional_arousal_state='High-arousal curiosity',
    cognitive_load_warning=False,psychological_critique='The opening establishes a visible audience problem.',failure_timestamps=[])
UNIFIED=dict(cognitive=COGNITIVE,pacing=dict(available=True,text='Actual words',wpm=120,duration_seconds=12,note='Whisper timestamps'),
    visual_frames=[dict(timestamp=1.,observation='Visible product label')],audit=dict(triggered=False),evidence_warnings=[])

class RemoteReviewTests(unittest.TestCase):
    def test_unified_review_forwards_context_and_preserves_audio_on_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder);video=output/'input.mp4';video.write_bytes(b'original-video')
            (output/'upload_info.json').write_text(json.dumps(dict(original_name='creator.mp4',language='hi',platform='instagram',audience='Hindi creators')))
            (output/'brand_context.json').write_text(json.dumps(dict(name='Brand',documents={'product_brief':{'text':'Reusable silicone catcher.'}})))
            def failure(*args,**kwargs):
                (output/'transcript.json').write_text(json.dumps(UNIFIED['pacing']))
                raise RuntimeError('Simulator unavailable')
            with patch('studio_pipeline.run_cognitive_audit',side_effect=failure) as audit:
                with self.assertRaisesRegex(RuntimeError,'speech evidence'):
                    review_video(video,output,lambda *args:None)
            report=json.loads((output/'report.json').read_text())
            self.assertEqual(audit.call_args.kwargs['brief']['language'],'hi')
            self.assertEqual(audit.call_args.kwargs['brief']['facts'],'Reusable silicone catcher.')
            self.assertEqual(report['video']['name'],'creator.mp4')
            self.assertEqual(report['pacing'],UNIFIED['pacing'])
            self.assertEqual(report['cognitive_status'],'unavailable')
            self.assertEqual(report['result'],{})
            self.assertNotIn('cognitive',report)

    def test_one_unified_call_no_redundant_visual_only_model(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder);video=output/'input.mp4';video.write_bytes(b'original-video')
            with patch('studio_pipeline.run_cognitive_audit',return_value=copy.deepcopy(UNIFIED)) as unified,patch('studio_gemma_video.analyze_virality',new_callable=AsyncMock) as old:
                report=review_video(video,output,lambda *args:None)
            unified.assert_called_once();old.assert_not_called()
            self.assertEqual(unified.call_args.args[2],[])
            self.assertEqual(report['cognitive']['attention_retention_score'],82)
            self.assertEqual(report['dashboard']['status'],'Review ready')
            self.assertEqual(len(report['video_sha256']),64)
            self.assertNotIn('Visual assessment only',json.dumps(report))
            self.assertEqual(json.loads((output/'report.json').read_text())['cognitive'],COGNITIVE)

    def test_provider_failure_never_assigns_scores(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder);video=output/'input.mp4';video.write_bytes(b'original')
            with patch('studio_pipeline.run_cognitive_audit',side_effect=RuntimeError('API unavailable')):
                with self.assertRaises(RuntimeError):review_video(video,output,lambda *args:None)
            report=json.loads((output/'report.json').read_text())
            self.assertEqual(report['dashboard']['status'],'Review unavailable')
            self.assertNotIn('cognitive',report)
            self.assertEqual(report['result'],{})

    def test_replacing_mp4_during_review_does_not_reuse_old_scores(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder);video=output/'input.mp4';video.write_bytes(b'original')
            def changed(*args,**kwargs):
                video.write_bytes(b'changed')
                return copy.deepcopy(UNIFIED)
            with patch('studio_pipeline.run_cognitive_audit',side_effect=changed):
                with self.assertRaises(RuntimeError):review_video(video,output,lambda *args:None)
            report=json.loads((output/'report.json').read_text())
            self.assertNotIn('cognitive',report)
            self.assertEqual(report['result'],{})
