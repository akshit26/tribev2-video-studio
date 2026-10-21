import asyncio,base64,copy,json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import AsyncMock,Mock,patch

from studio_av_signals import extract_media_parallel
from studio_virality import simulate_cognitive_response,validate_cognitive_response
from studio_pipeline import run_cognitive_audit
from actor_critic_fixtures import SCRIPT,CRITIQUE,EDIT

COG=dict(attention_retention_score=60,emotional_arousal_state='Low-arousal boredom (hypothesis)',
         cognitive_load_warning=False,psychological_critique='The opening at 0.5s lacks a visible audience stake.',
         failure_timestamps=[dict(timestamp=.5,reason='Static opening')],
         visual_observations=[dict(timestamp=.5,observation='Static blue frame')])
PACING=dict(available=True,duration_seconds=4.,text='Original words',words=[dict(start=1.,end=2.,word='Original')],
            wpm=30,dead_air=[],note='ASR speech-free gaps are not acoustic silence.')


class UnifiedMediaTests(unittest.TestCase):
    def test_frame_and_audio_extraction_actually_overlap(self):
        barrier=threading.Barrier(2)
        entered=[]
        def frames(*args):
            entered.append('visual');barrier.wait(timeout=2)
            return [dict(timestamp=0,path='sample.jpg')]
        def speech(*args):
            entered.append('audio');barrier.wait(timeout=2)
            return copy.deepcopy(PACING)
        with patch('studio_av_signals.extract_visual_frames',side_effect=frames),patch('studio_av_signals.transcribe_pacing',side_effect=speech):
            result=asyncio.run(extract_media_parallel('video','output',4))
        self.assertEqual(set(entered),{'visual','audio'})
        self.assertTrue(result['frames'])
        self.assertEqual(result['pacing']['wpm'],30)
        self.assertEqual(result['warnings'],[])

    def test_one_failed_extractor_does_not_erase_other_evidence(self):
        with patch('studio_av_signals.extract_visual_frames',side_effect=ValueError('bad video')),patch('studio_av_signals.transcribe_pacing',return_value=copy.deepcopy(PACING)):
            result=asyncio.run(extract_media_parallel('video','output',4))
        self.assertEqual(result['frames'],[])
        self.assertEqual(result['pacing'],PACING)
        with patch('studio_av_signals.extract_visual_frames',return_value=[dict(timestamp=0,path='frame.jpg')]),patch('studio_av_signals.transcribe_pacing',side_effect=ValueError('no audio')):
            result=asyncio.run(extract_media_parallel('video','output',4))
        self.assertTrue(result['frames'])
        self.assertFalse(result['pacing']['available'])
        self.assertIsNone(result['pacing']['wpm'])

    def test_simulator_receives_real_pixels_transcript_wpm_and_word_times(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            frame=Path(folder)/'frame.jpg';Image.new('RGB',(24,24),'blue').save(frame)
            with patch('studio_script_nvidia.nvidia_token',return_value='test'),patch('studio_script_team.chat_json',return_value=(copy.deepcopy(COG),{})) as api:
                result=simulate_cognitive_response([dict(timestamp=.5,path=str(frame))],PACING['text'],PACING)
            content=api.call_args.args[3]
            payload=json.loads(content[0]['text'])
            self.assertEqual(payload['transcript'],PACING['text'])
            self.assertEqual(payload['audio_pacing']['wpm'],30)
            self.assertEqual(payload['word_timestamps'],PACING['words'])
            self.assertNotIn(str(frame),content[0]['text'])
            encoded=next(item['image_url']['url'] for item in content if item['type']=='image_url')
            self.assertEqual(base64.b64decode(encoded.split(',',1)[1]),frame.read_bytes())
            self.assertEqual(result['model'],'nvidia/nemotron-3.5-super-vl-120b-a12b')

    def test_unsupplied_failure_timestamp_is_not_presented_as_visual_evidence(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            frame=Path(folder)/'frame.jpg';Image.new('RGB',(24,24),'blue').save(frame)
            with patch('studio_script_nvidia.nvidia_token',return_value='test'),patch('studio_script_team.chat_json',return_value=(copy.deepcopy(COG),{})):
                with self.assertRaisesRegex(ValueError,'without a supplied frame'):
                    simulate_cognitive_response([dict(timestamp=0,path=str(frame))],PACING['text'],PACING)

    def test_four_required_simulator_fields_are_accepted(self):
        basic={k:COG[k] for k in ('attention_retention_score','emotional_arousal_state','cognitive_load_warning','psychological_critique')}
        self.assertEqual(validate_cognitive_response(basic,4)['failure_timestamps'],[])

    def pipeline(self,folder,score):
        from PIL import Image
        output=Path(folder);frame=output/'sample.jpg';Image.new('RGB',(32,32),'blue').save(frame)
        media=dict(frames=[dict(timestamp=.5,path=str(frame))],pacing=copy.deepcopy(PACING),warnings=[],extraction_seconds=.2)
        def metadata(*args):yield dict(duration=4)
        def screenshot(video,timestamp,target):
            self.assertEqual(timestamp,.5)
            target.parent.mkdir(exist_ok=True);Image.new('RGB',(32,32),'blue').save(target)
            return target
        with patch('imageio_ffmpeg.read_frames',side_effect=metadata),patch('studio_av_signals.extract_media_parallel',new_callable=AsyncMock,return_value=media),patch('studio_virality.simulate_cognitive_response',return_value=dict(copy.deepcopy(COG),attention_retention_score=score)),patch('studio_script_team.chat_json',side_effect=[({'final_script':SCRIPT},{}),(CRITIQUE,{}),(EDIT,{})]) as actor,patch('studio_script_nvidia.nvidia_token',return_value='test'),patch('studio_pipeline.extract_audit_frame',side_effect=screenshot),patch('studio_pipeline.score_draft_script') as old_grade:
            result=run_cognitive_audit(output/'input.mp4',output,[],lambda *args:None,brief=dict(topic='Shower hair catcher',facts='Reusable silicone insert catches loose hair over a shower drain. Lift, remove hair, rinse and reuse.'))
        old_grade.assert_not_called()
        return result,actor

    def test_threshold_70_does_not_trigger_script_or_pdf(self):
        with tempfile.TemporaryDirectory() as folder:
            result,actor=self.pipeline(folder,70)
            self.assertFalse(result['audit']['triggered'])
            actor.assert_not_called()
            self.assertFalse((Path(folder)/'audit.pdf').exists())

    def test_below_70_runs_three_stage_revision_and_exactly_three_pdf_pages(self):
        from pypdf import PdfReader
        with tempfile.TemporaryDirectory() as folder:
            result,actor=self.pipeline(folder,69)
            self.assertEqual(actor.call_count,3)
            self.assertTrue(result['audit']['rewrite_approved'],result['audit'].get('blockers'))
            self.assertEqual(len(result['audit']['ab_hooks']),3)
            pdf=PdfReader(Path(folder)/'audit.pdf')
            self.assertEqual(len(pdf.pages),3)
            self.assertIn('Original spoken transcript',pdf.pages[2].extract_text())
            self.assertIn('Edited revision',pdf.pages[2].extract_text())
            self.assertIn('XObject',str(pdf.pages[1]['/Resources']))


if __name__=='__main__':unittest.main()
