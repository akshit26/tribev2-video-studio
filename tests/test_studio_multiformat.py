import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import studio_script_writer as writer
from studio_evaluation import validate_draft_score,score_draft_script

GOOD=dict(has_cta=True,has_visual_demo=True,invented_experience=False,overall_score=87,critique='Specific hook, grounded demo and clear purchase action.')
VISUALS=('[B-ROLL: Wet hair clump on drain] ', '[B-ROLL: Place silicone catcher over drain] ', '[B-ROLL: Lift catcher and remove collected hair] ')

def with_visuals(text,separator='. '):
    parts=text.split(separator,2)
    return separator.join(cue+part for cue,part in zip(VISUALS,parts))

SHORT=with_visuals('Drain hair looks like a tiny swamp creature. A silicone catcher sits over the drain and catches loose hair. When you are done, lift it, remove the hair, give it a rinse, and reuse it. Grab one before your next shower.')

class MultiFormatValidationTests(unittest.TestCase):
    def test_duration_normalization_and_invalid_values(self):
        for kind,seconds in [('short',30),('mid',60),('long',600)]:
            b=writer.brief_values(dict(topic='Test',facts='Verified',content_duration=kind))
            self.assertEqual(b['duration'],seconds);self.assertEqual(b['content_duration'],kind)
            self.assertIn(writer.FORMATS[kind][3],writer.system_prompt(b))
        for invalid in ['huge',[],{},12]:
            with self.assertRaises(ValueError):writer.brief_values(dict(topic='Test',facts='Verified',content_duration=invalid))


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


    def test_hindi_sentence_punctuation_does_not_make_entire_script_the_hook(self):
        brief=writer.brief_values(dict(topic='Hair catcher',facts='Silicone insert catches loose hair. Lift, remove hair and rinse.',language='Hindi',content_duration='short'))
        text=('बालों का गुच्छा छोटे राक्षस जैसा लगता है। सिलिकॉन का यह कैचर नाली पर ढीले बाल पकड़ता है। '
              'इसे उठाओ, बाल निकालो, पानी से धोओ और फिर इस्तेमाल करो। अपने शावर के लिए यह हेयर कैचर खरीदो।')
        self.assertEqual(writer.final_script_issues({'final_script':with_visuals(text,'\u0964 ')},brief),[])


    def test_scorer_receives_brand_evidence_and_distinguishes_jokes_from_claims(self):
        brand={'name':'Test brand','documents':{'product_facts':'Reusable silicone.'}}
        with patch('studio_script_fast.nvidia_token',return_value='test-key'),patch('studio_script_team.chat_json',return_value=(GOOD,{})) as call:
            score_draft_script(SHORT,{'facts':'Catches loose hair.','brand_context':brand},'short')
        self.assertEqual(json.loads(call.call_args.args[3])['brief']['brand_context'],brand)
        self.assertIn('comic comparisons are not literal product claims',call.call_args.args[2])


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
