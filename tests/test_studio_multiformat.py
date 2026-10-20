import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import studio_script_writer as writer
from studio_evaluation import validate_draft_score,score_draft_script

GOOD=dict(has_cta=True,has_visual_demo=True,invented_experience=False,overall_score=87,critique='Specific hook, grounded demo and clear purchase action.')
VISUALS=('[B-ROLL: Wet hair clump on drain] ', '[B-ROLL: Place silicone catcher over drain] ', '[B-ROLL: Lift catcher and remove collected hair] ')

def with_visuals(text):
    parts=text.split('. ',2)
    return '. '.join(cue+part for cue,part in zip(VISUALS,parts))

SHORT=with_visuals('Drain hair looks like a tiny swamp creature. A silicone catcher sits over the drain and catches loose hair. When you are done, lift it, remove the hair, give it a rinse, and reuse it. Grab one before your next shower.')

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
            result,complete,score=self.run_draft(kind=kind,texts=[with_visuals(text)])
            self.assertTrue(result['approved'],result['best']['assessment']['blockers'])
            self.assertEqual(score.call_args.args[2],kind)
            if kind=='long':self.assertGreater(complete.call_args.args[1],4096)

    def test_deterministic_word_and_experience_checks_override_high_score(self):
        for text in ['Buy it now.',SHORT.replace('A silicone catcher sits','I use a silicone catcher that sits'),SHORT+' Ready?']:
            result,complete,score=self.run_draft(texts=[text,text],scores=[GOOD,GOOD])
            self.assertFalse(result['approved']);self.assertEqual(complete.call_count,2)

    def test_mid_missing_required_cues_cannot_pass_even_with_high_score(self):
        text=' '.join(['Fresh detail adds something useful.' for _ in range(30)])+' [B-ROLL: fast zoom]'
        result,complete,score=self.run_draft(kind='mid',texts=[text,text],scores=[GOOD,GOOD])
        self.assertFalse(result['approved']);self.assertEqual(complete.call_count,2)
        self.assertIn('at least three',' '.join(result['best']['assessment']['blockers']))

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
        self.assertEqual(payload['spoken_word_count'],writer.spoken_word_count(SHORT))

    def test_locally_invalid_first_draft_skips_remote_score_and_rewrites_once(self):
        result,complete,score=self.run_draft(texts=['Buy it now.',SHORT],scores=[GOOD])
        self.assertTrue(result['approved'])
        self.assertEqual(complete.call_count,2)
        self.assertEqual(score.call_count,1)
        self.assertIsNone(result['gate_history'][0]['evaluation'])
        self.assertEqual(result['gate_history'][0]['scoring_skipped'],'local_validation_failed')
        self.assertIn('found 3',complete.call_args.args[0])

    def test_two_locally_invalid_drafts_never_receive_an_invented_score(self):
        result,complete,score=self.run_draft(texts=['Buy it now.']*2)
        self.assertFalse(result['approved'])
        score.assert_not_called()
        self.assertIsNone(result['evaluation'])
        self.assertIsNone(result['best']['assessment']['score'])
        self.assertIn('local validation',result['best']['assessment']['critique'])
        self.assertEqual(complete.call_count,2)

    def test_wrong_language_cannot_pass_a_high_remote_score(self):
        brief=writer.brief_values(dict(topic='Hair catcher',facts='Silicone insert catches loose hair. Lift, remove hair and rinse.',language='Hindi',content_duration='short'))
        complete=Mock(return_value={'final_script':SHORT})
        with patch('studio_pipeline.score_draft_script',return_value=GOOD) as score:
            result=writer.write_final_script({'brief':brief},complete,lambda row:None,lambda *args:None)
        self.assertFalse(result['approved'])
        score.assert_not_called()
        self.assertIn('Devanagari',' '.join(result['best']['assessment']['blockers']))

    def test_hindi_sentence_punctuation_does_not_make_entire_script_the_hook(self):
        brief=writer.brief_values(dict(topic='Hair catcher',facts='Silicone insert catches loose hair. Lift, remove hair and rinse.',language='Hindi',content_duration='short'))
        text=('बालों का गुच्छा छोटे राक्षस जैसा लगता है। सिलिकॉन का यह कैचर नाली पर ढीले बाल पकड़ता है। '
              'इसे उठाओ, बाल निकालो, पानी से धोओ और फिर इस्तेमाल करो। अपने शावर के लिए यह हेयर कैचर खरीदो।')
        self.assertEqual(writer.final_script_issues({'final_script':''.join(VISUALS)+text},brief),[])

    def test_selected_hook_reaches_direct_writer_without_unsafe_claims(self):
        brief=writer.brief_values(dict(topic='Hair catcher',facts='Silicone catcher catches loose hair.',content_duration='short'))
        for hook in [dict(angle='Drain monster',spoken='The drain monster is collecting rent.',payoff='Give the hair somewhere to land.'),
                     dict(angle='Routine confession',spoken='I use this every morning.',payoff='It is my personal routine.')]:
            complete=Mock(return_value={'final_script':SHORT})
            with patch('studio_pipeline.score_draft_script',return_value=GOOD):
                writer.write_final_script({'brief':brief,'selected_hook':hook},complete,lambda row:None,lambda *args:None)
            context=json.loads(complete.call_args.args[0].split(' BRIEF: ',1)[1])
            self.assertEqual(context['selected_hook']['angle'],hook['angle'])
            if hook['angle']=='Routine confession':
                self.assertNotIn('spoken',context['selected_hook'])
                self.assertIn('unsupported',context['selected_hook']['direction'])
            else:self.assertEqual(context['selected_hook']['spoken'],hook['spoken'])

    def test_provider_system_prompt_is_not_duplicated_in_user_message(self):
        brief=writer.brief_values(dict(topic='Hair catcher',facts='Silicone catcher catches loose hair.',content_duration='short'))
        complete=Mock(return_value={'final_script':SHORT})
        complete.system_prompt=writer.system_prompt(brief)
        with patch('studio_pipeline.score_draft_script',return_value=GOOD):
            writer.write_final_script({'brief':brief},complete,lambda row:None,lambda *args:None)
        self.assertNotIn(writer.SYSTEM,complete.call_args.args[0])
        self.assertIn('creator_direction',complete.call_args.args[0])

    def test_explicit_product_identity_conflict_stops_before_generation(self):
        with self.assertRaisesRegex(ValueError,'Product mismatch'):
            writer.brief_values(dict(topic='Neem facewash',facts='Plum goodness coconut shampoo',content_duration='mid'))
        # Comparisons and multiproduct facts are valid creative briefs.
        writer.brief_values(dict(topic='Facewash versus shampoo',facts='Shampoo and facewash use different labels.'))
        writer.brief_values(dict(topic='Facewash',facts='Compare facewash with shampoo.'))
        brief=dict(topic='Neem facewash',facts='Coconut shampoo',content_duration='mid')
        complete=Mock()
        with self.assertRaisesRegex(ValueError,'Product mismatch'):
            writer.write_final_script({'brief':brief},complete,lambda row:None,lambda *args:None)
        complete.assert_not_called()

    def test_scorer_receives_brand_evidence_and_distinguishes_jokes_from_claims(self):
        brand={'name':'Test brand','documents':{'product_facts':'Reusable silicone.'}}
        with patch('studio_script_fast.nvidia_token',return_value='test-key'),patch('studio_script_team.chat_json',return_value=(GOOD,{})) as call:
            score_draft_script(SHORT,{'facts':'Catches loose hair.','brand_context':brand},'short')
        self.assertEqual(json.loads(call.call_args.args[3])['brief']['brand_context'],brand)
        self.assertIn('comic comparisons are not literal product claims',call.call_args.args[2])

    def test_cleanup_demo_preserves_supplied_hair_removal_step(self):
        brief=writer.brief_values(dict(topic='Silicone hair catcher',facts='Catches loose hair. Lift, remove collected hair, rinse and reuse.',content_duration='short'))
        missing=("Someone's hair is doing laps in my drain again. I am not reaching in there with my fingers like a raccoon. "
                 'This silicone insert sits over the drain, catches loose hair, then you lift it, rinse it, reuse it. Tap to buy one now.')
        self.assertIn('removing collected hair',' '.join(writer.claim_issues(missing,brief)))
        corrected=missing.replace('lift it, rinse it, reuse it','lift it, remove the hair, rinse it, reuse it')
        missing,corrected=with_visuals(missing),with_visuals(corrected)
        self.assertEqual(writer.claim_issues(corrected,brief),[])
        complete=Mock(side_effect=[{'final_script':missing},{'final_script':corrected}])
        with patch('studio_pipeline.score_draft_script',return_value=GOOD) as scorer:
            result=writer.write_final_script({'brief':brief},complete,lambda row:None,lambda *args:None)
        self.assertTrue(result['approved'])
        self.assertEqual(scorer.call_count,1)
        self.assertEqual(complete.call_count,2)

    def test_cleanup_requirement_is_limited_to_explicit_instructions_and_demos(self):
        brief=dict(topic='Hair catcher',facts='Catches loose hair. Lift, remove collected hair, rinse and reuse.')
        self.assertEqual(writer.claim_issues('Loose hair has found its tiny landing pad. Buy the catcher.',brief),[])
        unsupplied=dict(brief,facts='Silicone hair catcher catches loose hair.')
        self.assertEqual(writer.claim_issues('Lift it, rinse it, reuse it.',unsupplied),[])
        automatic=dict(brief,facts='Hair catcher. No need to remove hair manually.')
        self.assertFalse(writer.hair_catcher_manual_cleanup(automatic))
        self.assertIn('no-touch',' '.join(writer.claim_issues('Your fingers stay dry. No need to touch the hair.',brief)))

    def test_saved_approval_is_revoked_for_current_product_conflict_without_mutating_archive(self):
        brief=writer.brief_values(dict(topic='Facewash',facts='Facewash',content_duration='short'))
        brief['facts']='Coconut shampoo'
        original={'approved':True,'target_met':True,'quality_status':'ready','stop_reason':'gate_approved',
                  'best':{'script':{'final_script':SHORT},'assessment':{'score':87,'blockers':[]}},'evaluation':dict(GOOD)}
        before=copy.deepcopy(original)
        with patch('studio_pipeline.score_draft_script') as scorer:
            result=writer.recheck_saved_result(original,brief)
        self.assertFalse(result['approved'])
        self.assertFalse(result['target_met'])
        self.assertIn('Product mismatch',' '.join(result['best']['assessment']['blockers']))
        self.assertEqual(result['evaluation'],GOOD)
        self.assertEqual(original,before)
        scorer.assert_not_called()

    def test_saved_cleanup_omission_cannot_retain_approval(self):
        result,_,_=self.run_draft()
        result['best']['script']['final_script']=SHORT.replace('remove the hair, ','')
        checked=writer.recheck_saved_result(result,result['brief'])
        self.assertFalse(checked['approved'])
        self.assertIn('removing collected hair',' '.join(checked['best']['assessment']['blockers']))

    def test_cleanup_accepts_plain_manual_removal_synonyms(self):
        brief=writer.brief_values(dict(topic='Silicone hair catcher',facts='Reusable silicone insert catches loose hair. Lift, remove collected hair, rinse and reuse.',content_duration='short'))
        text=('Those hair boulders in the drain, wow. Just slide this reusable silicone insert over the drain, it catches hair. '
              'Lift it, dump the collected hair, rinse, then reuse immediately. Grab one today through the link in bio.')
        text=with_visuals(text)
        for verb in ('dump','tip','toss','empty','clear','scrape'):
            self.assertEqual(writer.final_script_issues({'final_script':text.replace('dump',verb)},brief),[])
        self.assertIn('removing collected hair',' '.join(writer.claim_issues('Lift it; it automatically dumps the hair. Rinse and reuse.',brief)))

    def test_typographic_dashes_do_not_undercount_real_benchmark_speech(self):
        brief=writer.brief_values(dict(topic='Silicone hair catcher',facts='Reusable silicone insert catches loose hair. Lift, remove collected hair, rinse and reuse.',content_duration='short'))
        text=('Picture this\u2014shower drain turning into a hair buffet. A slick silicone disc slides over the drain, scoops every stray strand. '
              'Just lift it, dump the clogs, rinse it, and slap it back. Buy one.')
        for dash in ('\u2013','\u2014'):
            speech=with_visuals(text.replace('\u2014',dash))
            self.assertEqual(writer.spoken_word_count(speech+' [Hold product]'),35)
            issues=writer.final_script_issues({'final_script':speech},brief)
            self.assertEqual(len(issues),1)
            self.assertIn('Unsupported universal collection',issues[0])
            self.assertEqual(writer.spoken_timing({'final_script':speech},brief)['words'],35)
            with patch('studio_script_fast.nvidia_token',return_value='test-key'),patch('studio_script_team.chat_json',return_value=(GOOD,{})) as call:
                score_draft_script(speech,brief,'short')
            self.assertEqual(json.loads(call.call_args.args[3])['spoken_word_count'],35)
        self.assertEqual(writer.claim_issues('Lift it, empty it, rinse it and reuse it.',brief),[])
        self.assertIn('removing collected hair',' '.join(writer.claim_issues('Lift it; it will automatically dump the clogs. Rinse and reuse.',brief)))

    def test_universal_collection_guarantee_is_blocked_without_overbroad_every_word_filter(self):
        brief=dict(topic='Silicone hair catcher',facts='Silicone insert catches loose hair.')
        self.assertIn('Unsupported universal collection',' '.join(writer.claim_issues('This disc scoops every stray strand.',brief)))
        self.assertIn('Unsupported universal collection',' '.join(writer.claim_issues('This disc catches all the hair.',brief)))
        self.assertEqual(writer.claim_issues('This disc catches loose hair. Every wash day has a horror-movie moment.',brief),[])
        self.assertEqual(writer.claim_issues('Lift it and remove all the collected hair before rinsing.',brief),[])
        supported=dict(brief,facts='Silicone insert catches all loose hair.')
        self.assertEqual(writer.claim_issues('This disc catches every stray strand.',supported),[])
        unrelated=dict(brief,facts='Cleaner removes every stain. Silicone insert catches loose hair.')
        self.assertIn('Unsupported universal collection',' '.join(writer.claim_issues('This disc catches every hair.',unrelated)))
        negated=dict(brief,facts='Silicone insert does not catch all loose hair.')
        self.assertIn('Unsupported universal collection',' '.join(writer.claim_issues('This disc catches every hair.',negated)))
