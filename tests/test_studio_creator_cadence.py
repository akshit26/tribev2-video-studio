import copy
import json
import unittest
from unittest.mock import Mock, patch

import studio_script_writer as writer
from studio_evaluation import (
    MANUAL_CRITIQUE, METAPHOR_CRITIQUE, ROBOTIC_CTA_CRITIQUE, apply_cta_quality_rule,
    blunt_closing_cta, score_draft_script, sterile_cleanup_sequence,
)


GOOD = dict(has_cta=True, has_visual_demo=True, invented_experience=False,
            overall_score=90, critique='Grounded demo and conversational close.')
SCRIPT = ('[B-ROLL: Wet hair clump on drain] If drain hair makes you gag, watch this. '
          '[B-ROLL: Place silicone catcher over drain] This silicone catcher sits over the drain and catches loose hair. '
          '[B-ROLL: Lift catcher and remove collected hair] Just lift it up, peel the hair off, give it a rinse, and use it again. '
          'Grab one before your next shower.')


class CreatorCadenceTests(unittest.TestCase):
    def brief(self, **overrides):
        return writer.brief_values(dict(topic='Reusable shower hair catcher',
            facts='A silicone insert sits over a shower drain and catches loose hair. Lift it, remove collected hair, rinse and reuse.',
            content_duration='short', content_mode='ugc', writer_backend='fast', **overrides))

    def test_short_closing_has_fixed_penalty_and_cannot_approve(self):
        original=copy.deepcopy(GOOD)
        for closing in ('Buy one.', 'Purchase today.', 'Grab one!', 'Buy.', '\u0916\u0930\u0940\u0926 \u0932\u094b\u0964', 'Order karlo.'):
            with self.subTest(closing=closing):
                self.assertTrue(blunt_closing_cta('A useful demo. '+closing))
                scored=apply_cta_quality_rule(GOOD, 'A useful demo. '+closing)
                self.assertEqual(scored['overall_score'],75)
                self.assertFalse(scored['has_cta'])
                self.assertTrue(scored['critique'].startswith(ROBOTIC_CTA_CRITIQUE))
        self.assertEqual(GOOD,original)
        self.assertEqual(apply_cta_quality_rule(dict(GOOD,overall_score=8),'Buy one.')['overall_score'],0)

    def test_natural_close_or_non_cta_fragment_is_not_penalized(self):
        for speech in (SCRIPT, 'Grab one before shower day. Seriously.', 'Do not buy.', 'This is gross.',
                       'Check the supplied link to grab one.', 'Grab one before shower day. [Hold product]'):
            with self.subTest(speech=speech):
                self.assertFalse(blunt_closing_cta(speech))
                self.assertEqual(apply_cta_quality_rule(GOOD,speech),GOOD)

    def test_live_manual_failure_cannot_be_approved_by_an_overgenerous_judge(self):
        manual=SCRIPT.replace('Just lift it up, peel the hair off, give it a rinse, and use it again.',
                              'Lift it, pull the hair out, rinse it, reuse it.')
        self.assertTrue(sterile_cleanup_sequence(manual))
        self.assertTrue(sterile_cleanup_sequence('Lift it, peel off the caught hair, rinse it, and set it back down.'))
        self.assertFalse(sterile_cleanup_sequence(SCRIPT))
        with patch('studio_script_fast.nvidia_token',return_value='test'), patch('studio_script_team.chat_json',return_value=(GOOD,{})):
            result=score_draft_script(manual,self.brief(),'short')
        self.assertEqual(result['overall_score'],79)
        self.assertIn(MANUAL_CRITIQUE,result['critique'])
        self.assertIn('Unsupported universal collection',' '.join(writer.claim_issues('It catches all that loose hair.',self.brief())))

    def test_api_gate_applies_deduction_even_if_model_misses_blunt_close(self):
        with patch('studio_script_fast.nvidia_token',return_value='test'), patch('studio_script_team.chat_json',return_value=(GOOD,{})) as api:
            result=score_draft_script(SCRIPT.rsplit('Grab one',1)[0]+'Buy one.',self.brief(),'short')
        self.assertEqual(result['overall_score'],75)
        self.assertFalse(result['has_cta'])
        self.assertTrue(json.loads(api.call_args.args[3])['blunt_closing_cta'])
        self.assertIn('BEFORE that fixed deduction',api.call_args.args[2])
        self.assertIn('more than 40%',api.call_args.args[2])
        self.assertIn(METAPHOR_CRITIQUE,api.call_args.args[2])


    def test_hook_limit_and_conversational_cleanup_preserve_safety(self):
        brief=self.brief()
        self.assertEqual(writer.final_script_issues({'final_script':SCRIPT},brief),[])
        too_long=SCRIPT.replace('If drain hair makes you gag, watch this.', 'This wet drain hair is really just an absolutely unacceptable hard no.')
        self.assertIn('under 12 words',' '.join(writer.final_script_issues({'final_script':too_long},brief)))
        for bad in (SCRIPT.replace('peel the hair off, ',''),
                    SCRIPT.replace('catches loose hair','catches every strand'),
                    SCRIPT.replace('This silicone catcher sits','I use a silicone catcher that sits')):
            with self.subTest(script=bad):
                self.assertTrue(writer.final_script_issues({'final_script':bad},brief))

    def test_hindi_register_and_unverified_link_constraints_are_in_master(self):
        for language in ('Hindi','Hindi (Roman)','Hinglish'):
            prompt=writer.system_prompt(self.brief(language=language))
            self.assertIn('never textbook translation',prompt)
            self.assertIn('English loan words',prompt)
            self.assertIn('respecting the selected writing system',prompt)
            self.assertNotIn('a simple Buy one CTA is enough',prompt)
            self.assertIn('unless creator notes actually confirm it',prompt)

    def test_visual_cues_are_mandatory_and_not_spoken_words(self):
        import re
        plain=re.sub(r'\[[^\]]*\]','',SCRIPT)
        self.assertEqual(writer.spoken_word_count(SCRIPT),writer.spoken_word_count(plain))
        for cues in ('', '[B-ROLL: Wet hair] ', '[B-ROLL: Wet hair] [B-ROLL: Product] ',
                     '[B-ROLL: Wet hair] [B-ROLL: Product] [B-ROLL: ] ',
                     '[SECTION 1: Problem] [SECTION 2: Product] [SECTION 3: Payoff] '):
            with self.subTest(cues=cues):
                issues=writer.final_script_issues({'final_script':cues+plain},self.brief())
                self.assertIn('at least three',' '.join(issues))
        self.assertEqual(writer.final_script_issues({'final_script':SCRIPT},self.brief()),[])


    def test_bland_problem_declarations_are_rejected_before_scoring(self):
        for hook in ('Drain hair is the worst.', 'Drain clogs are annoying.'):
            bad=SCRIPT.replace('If drain hair makes you gag, watch this.',hook)
            self.assertIn('bland hook',' '.join(writer.final_script_issues({'final_script':bad},self.brief())))

    def test_visual_directions_cannot_invent_product_promises(self):
        bad=SCRIPT.replace('[B-ROLL: Place silicone catcher over drain]',
                           '[B-ROLL: Product catches every strand]')
        self.assertIn('Unsupported universal collection',' '.join(writer.final_script_issues({'final_script':bad},self.brief())))

    def test_all_format_prompts_include_ordered_visual_beats(self):
        for kind in ('short','mid','long'):
            brief=self.brief()
            brief['content_duration']=kind
            for prompt in (writer.system_prompt(brief),writer.final_script_guidance(brief)):
                self.assertIn('at least three',prompt)
                self.assertLess(prompt.index('Frame 1'),prompt.index('Frame 2'))
                self.assertLess(prompt.index('Frame 2'),prompt.index('Frame 3'))
                self.assertNotIn('spoken words only',prompt)
            self.assertNotIn('every 3 sentences',writer.system_prompt(brief))


if __name__=='__main__':
    unittest.main()
