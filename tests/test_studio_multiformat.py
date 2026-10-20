import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import studio_script_writer as writer
from studio_evaluation import validate_draft_score,score_draft_script

GOOD=dict(has_cta=True,has_visual_demo=True,invented_experience=False,overall_score=87,critique='Specific hook, grounded demo and clear purchase action.')
SHORT='Drain hair looks like a tiny swamp creature. A silicone catcher sits over the drain and catches loose hair. Lift it, remove the hair, rinse it, and reuse it. Buy a hair catcher for your shower.'

class MultiFormatTests(unittest.TestCase):
    def run_draft(self,kind='short',texts=None,scores=None):
        brief=writer.brief_values(dict(topic='Silicone hair catcher',facts='Reusable silicone catcher. Catches loose hair over the drain. Lift, remove hair and rinse.',writer_backend='fast',content_duration=kind))
        complete=Mock(side_effect=[{'final_script':t} for t in (texts or [SHORT])]);saved=[]
        with patch('studio_pipeline.score_draft_script',side_effect=scores or [GOOD]) as scorer:
            result=writer.write_final_script({'brief':brief},complete,saved.append,lambda *args:None)
        return result,complete,scorer

    def test_duration_normalization_and_invalid_values(self):
        for kind,seconds in [('short',30),('mid',60),('long',600)]:
            b=writer.brief_values(dict(topic='Test',facts='Verified',content_duration=kind))
            self.assertEqual(b['duration'],seconds);self.assertEqual(b['content_duration'],kind)
            self.assertIn(writer.FORMATS[kind][3],writer.system_prompt(b))
        for invalid in ['huge',[],{},12]:
            with self.assertRaises(ValueError):writer.brief_values(dict(topic='Test',facts='Verified',content_duration=invalid))

    def test_short_passes_once_with_score(self):
        result,complete,score=self.run_draft()
        self.assertTrue(result['approved']);self.assertEqual(result['evaluation']['overall_score'],87)
        self.assertEqual(complete.call_count,1);self.assertEqual(score.call_count,1)
        self.assertEqual(set(result['best']['script']),{'final_script'})

    def test_each_gate_failure_gets_only_one_rewrite_with_critique(self):
        for bad in [dict(GOOD,has_cta=False),dict(GOOD,invented_experience=True),dict(GOOD,overall_score=79)]:
            result,complete,score=self.run_draft(texts=[SHORT,SHORT],scores=[bad,GOOD])
            self.assertTrue(result['approved']);self.assertEqual(complete.call_count,2)
            self.assertIn(bad['critique'],complete.call_args.args[0]);self.assertEqual(score.call_count,2)

    def test_twice_rejected_is_never_approved(self):
        result,complete,score=self.run_draft(texts=[SHORT,SHORT],scores=[dict(GOOD,has_cta=False)]*2)
        self.assertFalse(result['approved']);self.assertFalse(result['target_met'])
        self.assertEqual(result['quality_status'],'needs_review');self.assertEqual(complete.call_count,2)
        self.assertFalse(writer.recheck_saved_result(result,result['brief'])['approved'])

    def test_scoring_outage_keeps_draft_unapproved_without_useless_rewrite(self):
        result,complete,score=self.run_draft(scores=[RuntimeError('Provider unavailable')])
        self.assertFalse(result['approved']);self.assertIsNone(result['evaluation'])
        self.assertEqual(complete.call_count,1);self.assertIsNone(result['best']['assessment']['score'])

    def test_rewrite_connection_failure_retains_critique_without_approval(self):
        brief=writer.brief_values(dict(topic='Hair catcher',facts='Reusable silicone catcher.',content_duration='short'))
        complete=Mock(side_effect=[{'final_script':SHORT},RuntimeError('Provider unavailable')])
        with patch('studio_pipeline.score_draft_script',return_value=dict(GOOD,overall_score=70,critique='Improve the CTA.')):
            result=writer.write_final_script({'brief':brief},complete,lambda row:None,lambda *args:None)
        self.assertFalse(result['approved']);self.assertEqual(result['evaluation']['overall_score'],70)
        self.assertEqual(result['best']['assessment']['critique'],'Improve the CTA.')
        self.assertIn('Rewrite unavailable',' '.join(result['best']['assessment']['blockers']))
        self.assertEqual(complete.call_count,2)

    def test_mid_and_long_word_limits_and_single_field(self):
        mid=' '.join('Fresh detail adds something useful. Another point makes it clearer. Buy this practical product today. [B-ROLL: fast zoom]' for _ in range(10))
        long=' '.join('[SECTION '+str(i)+': Detail] '+' '.join(['Useful detail explains a choice.' for _ in range(80)]) for i in range(1,5))
        for kind,text in [('mid',mid),('long',long)]:
            result,complete,score=self.run_draft(kind=kind,texts=[text])
            self.assertTrue(result['approved'],result['best']['assessment']['blockers'])
            self.assertEqual(score.call_args.args[2],kind)
            if kind=='long':self.assertGreater(complete.call_args.args[1],4096)

    def test_deterministic_word_and_experience_checks_override_high_score(self):
        for text in ['Buy it now.',SHORT.replace('A silicone catcher sits','I use a silicone catcher that sits'),SHORT+' Ready?']:
            result,complete,score=self.run_draft(texts=[text,text],scores=[GOOD,GOOD])
            self.assertFalse(result['approved']);self.assertEqual(complete.call_count,2)

    def test_mid_misplaced_cues_cannot_pass_even_with_high_score(self):
        text=' '.join(['Fresh detail adds something useful.' for _ in range(30)])+' [B-ROLL: fast zoom]'
        result,complete,score=self.run_draft(kind='mid',texts=[text,text],scores=[GOOD,GOOD])
        self.assertFalse(result['approved']);self.assertEqual(complete.call_count,2)
        self.assertIn('three sentences',' '.join(result['best']['assessment']['blockers']))

    def test_smart_apostrophe_filler_cannot_pass_high_score(self):
        text='Let'+chr(0x2019)+'s dive in. '+SHORT
        result,complete,score=self.run_draft(texts=[text,text],scores=[GOOD,GOOD])
        self.assertFalse(result['approved'])
        self.assertIn('Remove filler',' '.join(result['best']['assessment']['blockers']))

    def test_strict_score_schema(self):
        self.assertEqual(validate_draft_score(GOOD),GOOD)
        for bad in [dict(GOOD,overall_score=True),dict(GOOD,overall_score=101),dict(GOOD,has_cta='true'),dict(GOOD,critique=''),dict(GOOD,extra=1)]:
            with self.assertRaises(ValueError):validate_draft_score(bad)

    def test_score_api_receives_script_and_duration_not_video_or_local_model(self):
        with patch('studio_script_fast.nvidia_token',return_value='test-key'),patch('studio_script_team.chat_json',return_value=(GOOD,{})) as call:
            self.assertEqual(score_draft_script(SHORT,{'facts':'Silicone'},'short'),GOOD)
        payload=json.loads(call.call_args.args[3]);self.assertEqual(payload['script_text'],SHORT)
        self.assertIn('35-60',payload['duration_rules'])
        self.assertEqual(payload['spoken_word_count'],len(SHORT.split()))
