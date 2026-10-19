"""Script scoring and lifecycle tests without network or GPU inference."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import studio_script_writer as writer
import studio_server as server


def brief():
    return writer.brief_values({"topic": "Notebook", "facts": "A notebook with 80 blank pages.", "duration": 15})


def script(title="Notebook"):
    return {"title": title, "scenes": [{"start": start, "end": start+5, "spoken": "Write your next idea here before another thought takes its place.",
            "visual": "Open the notebook on a desk.", "overlay": "Your next idea"} for start in (0,5,10)],
            "reference_ids": ["stick"], "missing_proof": []}


def assessment(grade=3, claims=None):
    return {"criteria": [{"key": key, "grade": grade, "scene": 1, "reason": "Concrete scene.",
                          "improvement": "Make the next action more specific."} for key in writer.RUBRIC],
            "unsupported_claims": claims or []}


class WriterTests(unittest.TestCase):
    def test_reported_draft_cannot_pass_even_when_reviewer_praises_it(self):
        b=writer.brief_values(dict(brief(),topic='Anti dandruff shampoo',duration=30,
            facts='A shampoo with salicylic acid that tackles dandruff-causing microbes.'))
        bad=script();bad['title']='...'
        lines=["I thought this would be like any other anti-dandruff shampoo. Just gave me dryness.",
               "Dandruff's got a secret crew hiding behind flakes, feasting on dead skin and germs.",
               "So what if the real fix isn't rinsing it away? What if you stop the party before it starts?"]
        for row,start,end,line in zip(bad['scenes'],(0,5,10),(5,10,30),lines):
            row.update(start=start,end=end,spoken=line)
        result=writer.validate_assessment(assessment(4),bad,b)
        self.assertLess(result['score'],80)
        reasons=' '.join(result['blockers'])
        for expected in ('words for 30 seconds','Paragraph 3','personal product result','biological mechanism','rinse implication'):
            self.assertIn(expected,reasons)
        saved={'best':{'script':bad,'assessment':assessment(4)},'history':[],'target_met':True,'stop_reason':'target_reached'}
        saved['best']['assessment']=dict(saved['best']['assessment'],score=90)
        updated=writer.recheck_saved_result(saved,b)
        self.assertFalse(updated['target_met'])
        self.assertEqual(updated['stop_reason'],'quality_checks_failed')
        self.assertEqual(saved['best']['assessment']['score'],90)

    def test_creator_result_needs_matching_experience_not_just_any_notes(self):
        line='It just gave me dryness.'
        for notes in ('','I opened the bottle today.'):
            self.assertTrue(writer.claim_issues(line,dict(brief(),creator_experience=notes)))
        self.assertFalse(writer.claim_issues(line,dict(brief(),creator_experience='My hair felt dry after using it.')))
        hook=dict(angle='Expectation',spoken=line,visual='',overlay='',payoff='A real fix.')
        self.assertTrue(writer.hook_usage_issues([hook],brief()))

    def test_length_gate_and_realistic_timing(self):
        b=dict(brief(),duration=30)
        s=script()
        for i,row in enumerate(s['scenes']):
            row.update(start=i*10,end=(i+1)*10,spoken=' '.join(['word']*24))
        self.assertFalse(writer.duration_issues(s,b))
        t=writer.spoken_timing(s,b)
        self.assertEqual(t['words'],72)
        self.assertEqual((t['estimated_seconds_min'],t['estimated_seconds_max']),(27,36))
        self.assertEqual(writer.validate_assessment(assessment(4),s,b)['score'],100)
        for row in s['scenes']:row['spoken']='Short line.'
        self.assertLess(writer.validate_assessment(assessment(4),s,b)['score'],80)
        self.assertFalse(writer.duration_issues(s,dict(b,language='Hindi')))

    def test_valid_candidate_beats_higher_scored_blocked_candidate(self):
        bad=script('Blocked');bad['missing_proof']=['Unverified result.']
        good=script('Valid');good['scenes'][0]['spoken']+=' Today.'
        replies=iter([bad,assessment(4),good,assessment(3)])
        result=writer.optimize(brief(),lambda *a:next(replies),lambda r:None,lambda *a:None,max_rounds=2)
        self.assertEqual(result['best']['script']['title'],'Valid')
        self.assertEqual(result['best']['assessment']['score'],75)
        self.assertEqual(result['timing']['words'],sum(len(s['spoken'].split()) for s in good['scenes']))

    def test_invented_creator_history_and_permanent_results_are_blocked(self):
        b=dict(brief(),topic='Shampoo',facts='Anti-dandruff shampoo with 72-hour control.')
        for line in ("I've rinsed dandruff like surface grime for years.","I quit scrubbing and started digging.","My hair's smooth now, no flaking.","It is quieted for good."):
            self.assertTrue(writer.claim_issues(line,b),line)
        self.assertFalse(writer.claim_issues('Why does choosing shampoo feel like homework?',b))
        self.assertFalse(writer.claim_issues('My scalp has questions about this ingredient list.',b))

    def test_strong_grades_allow_empty_optional_improvement_notes(self):
        raw=assessment(3)
        for row in raw['criteria']:row['improvement']=''
        calls=[]
        def complete(prompt,tokens,label):
            calls.append(label);return raw
        result=writer.assess_script(complete,'review',brief(),script(),1)
        self.assertEqual(calls,['Critique 1'])
        self.assertEqual(result['score'],75)
        self.assertTrue(all(c['improvement']=='No specific change proposed.' for c in result['criteria']))
        weak=assessment(2);weak['criteria'][0]['improvement']=''
        with self.assertRaises(ValueError):writer.validate_criterion(weak['criteria'][0],script())

    def test_missing_reference_metadata_does_not_discard_spoken_script(self):
        raw=script();raw.pop('reference_ids');raw.pop('missing_proof')
        result=writer.validate_script(raw,brief())
        self.assertEqual(result['reference_ids'],[])
        self.assertEqual(result['scenes'][0]['spoken'],raw['scenes'][0]['spoken'])
        self.assertEqual(result['missing_proof'],[])
        raw['reference_ids']=[{}]
        with self.assertRaises(ValueError):writer.validate_script(raw,brief())

    def test_live_preview_reads_only_partial_spoken_fields(self):
        partial='{"title":"Secret metadata","scenes":[{"spoken":"First paragraph."},{"spoken":"Next thought'
        self.assertEqual(writer.spoken_preview(partial),['First paragraph.','Next thought'])
        self.assertEqual(writer.spoken_preview('reasoning first {"spoken":"do not show"}'),[])
        value=json.dumps({'spoken':'A split \"quote'});self.assertEqual(writer.spoken_preview(value[:-2]),['A split \"quote'])
        self.assertEqual(writer.spoken_preview('{"title":"No speech yet"}'),[])
        self.assertEqual(writer.spoken_preview('{"spoken":"\\ud83d'),[])
        self.assertEqual(writer.spoken_preview('{"spoken":"\\ud83d\\ude00"}'),['\U0001f600'])

    def test_requested_changes_cannot_pass_without_reviewed_adherence(self):
        b=brief();raw=assessment(4)
        self.assertLess(writer.validate_assessment(raw,script(),b,'Make it funnier')['score'],80)
        raw['requested_changes']={'applied':False,'reason':'The ending was not changed.'}
        self.assertIn('ending',writer.validate_assessment(raw,script(),b,'Make it funnier')['blockers'][0])
        raw['requested_changes']={'applied':True,'reason':'The new ending lands a joke.'}
        self.assertEqual(writer.validate_assessment(raw,script(),b,'Make it funnier')['score'],100)

    def test_requested_changes_reach_targeted_writer_and_reviewer(self):
        notes='Make only the final paragraph funnier. Keep my opening.'
        original=script();prompts=[]
        def complete(prompt,tokens,label):
            prompts.append(prompt)
            if label.startswith('Draft'):return {'spoken':'The blank page has officially rejected my grocery list again.'}
            return dict(assessment(4),requested_changes={'applied':True,'reason':'The ending now has a punchline.'})
        result=writer.optimize(brief(),complete,lambda r:None,lambda *a:None,previous_script=original,scene_index=2,revision_notes=notes,parent_script_id='a'*32,max_rounds=1)
        self.assertEqual(result['best']['script']['scenes'][:2],original['scenes'][:2])
        self.assertTrue(all(notes in prompt for prompt in prompts))
        self.assertTrue(result['target_met'])
        self.assertEqual(result['revision_notes'],notes)
        self.assertEqual(result['parent_script_id'],'a'*32)
        self.assertTrue(writer.recheck_saved_result(result,brief())['target_met'])

    def test_empty_model_title_and_known_punctuation_damage(self):
        raw=script();raw['title']=''
        self.assertEqual(writer.validate_script(raw,brief())['title'],brief()['topic'])
        damaged="Don\u00e2\u20ac\u2122t"
        self.assertEqual(writer.text(damaged),"Don't")
        self.assertEqual(writer.text('\u0928\u092e\u0938\u094d\u0924\u0947'),'\u0928\u092e\u0938\u094d\u0924\u0947')

    def test_personas_replace_tone_in_generation_context(self):
        self.assertEqual(len(writer.personas()),24)
        for persona in writer.personas():
            b=writer.brief_values(dict(brief(),persona=persona['id']))
            self.assertIn(persona['direction'],writer.persona_guidance(b))
            self.assertNotIn('tone',writer.compact_brief(b))
        with self.assertRaises(ValueError):writer.brief_values(dict(brief(),persona='unknown'))
        self.assertEqual(writer.creative_territory(dict(brief(),topic='Arcade games'))['category'],'Arcade/gaming')

    def test_spoken_only_payloads_and_exports(self):
        raw=script()
        for paragraph in raw['scenes']:
            paragraph.pop('visual');paragraph.pop('overlay')
        validated=writer.validate_script(raw,brief())
        result={'best':{'script':validated}}
        self.assertEqual(writer.export_text(result),'Notebook\n\n'+'\n\n'.join(s['spoken'] for s in raw['scenes']))
        hook={'angle':'The blank page','spoken':'Why is page one the hardest?','payoff':'The next thought matters.'}
        def complete(prompt,tokens,label):
            return {'issues':[]} if label.startswith('Hook critique') else {'hooks':[hook]*5}
        self.assertEqual(writer.write_hooks(brief(),complete)[0]['spoken'],hook['spoken'])

    def test_hook_word_limit_does_not_apply_to_script_paragraphs(self):
        raw=script();b=dict(brief(),duration=30)
        for i,row in enumerate(raw['scenes']):
            row.update(start=i*10,end=(i+1)*10,spoken=' '.join(['word']*20))
        self.assertEqual(len(writer.validate_script(raw,b)['scenes']),3)

    def test_shampoo_usage_is_repaired_locally_without_losing_script(self):
        raw=script();raw['scenes'][2]['spoken']='Do not rinse your shampoo.'
        b=dict(brief(),topic='Shampoo',facts="Shampoo. Brand slogan: Don't rinse it. Resolve it.")
        calls=[]
        def complete(prompt,tokens,label):
            calls.append(label)
            self.assertIn('Remove unsupported use instructions',prompt)
            self.assertNotIn("Don't rinse it. Resolve it.",prompt)
            return {'spoken':'A slogan is not your routine.'}
        repaired=writer.validate_draft(raw,b,complete,'Draft 1')
        self.assertEqual(repaired['scenes'][:2],[dict(s,visual='',overlay='') for s in raw['scenes'][:2]])
        self.assertEqual(repaired['scenes'][2]['spoken'],'A slogan is not your routine.')
        self.assertEqual(calls,['Draft 1 paragraph 3 repair'])
        self.assertEqual(raw['scenes'][2]['spoken'],'Do not rinse your shampoo.')

    def test_overlong_draft_repairs_paragraphs_with_explicit_budgets(self):
        raw=script()
        for row in raw['scenes']:row['spoken']=' '.join(['word']*25)
        calls=[]
        def complete(prompt,tokens,label):
            calls.append(label)
            self.assertIn('Maximum 15 spoken words',prompt)
            return {'spoken':'One small thought is enough to start a whole story.'}
        result=writer.validate_draft(raw,brief(),complete,'Draft 1')
        self.assertEqual(len(calls),3)
        self.assertEqual(result['title'],raw['title'])
        self.assertLessEqual(sum(len(r['spoken'].split()) for r in result['scenes']),45)
        self.assertEqual(raw['scenes'][0]['spoken'],' '.join(['word']*25))

    def test_safe_shampoo_warnings_and_persistent_unsafe_repairs(self):
        b=dict(brief(),topic='Shampoo')
        for spoken in ("This is not a leave-in. Follow the label.","Don't leave it in. Follow the label."):
            hook=dict(spoken=spoken,visual='',overlay='',payoff='')
            self.assertEqual(writer.hook_usage_issues([hook],b),[])
        raw=script();raw['scenes'][0]['spoken']='Do not rinse your shampoo.'
        with self.assertRaisesRegex(ValueError,'label'):
            writer.validate_draft(raw,b,lambda *a:{'spoken':'Do not rinse your shampoo.'},'Draft 1')

    def test_solo_defaults_and_new_formats(self):
        self.assertEqual(brief()['production_style'],'solo_simple')
        for fmt in ('rant','hot_take','mini_list','routine_check'):
            self.assertEqual(writer.brief_values(dict(brief(),content_format=fmt))['content_format'],fmt)
        with self.assertRaises(ValueError):
            writer.brief_values(dict(brief(),production_style='unknown'))
        self.assertIn('plain phone-camera',writer.rubric_for(brief())['hook'][1])

    def test_solo_cast_constraint_and_flexible_opt_in(self):
        hook={'spoken':'Who moved my notebook?', 'visual':'Two actors debate at a desk.', 'overlay':'Desk debate', 'payoff':'Find it.'}
        self.assertEqual(len(writer.hook_usage_issues([hook],brief())),1)
        b=dict(brief(),production_style='flexible')
        self.assertEqual(writer.hook_usage_issues([hook],b),[])
        self.assertTrue({'comedy','curiosity'}.issubset({r['id'] for r in writer.creative_routes(b)}))

    def test_beauty_and_instagram_reference_selection(self):
        for topic in ('Skincare cleanser','Haircare shampoo'):
            b=writer.brief_values(dict(brief(),topic=topic,platform='Instagram Reels',content_format='routine_check'))
            refs={c['id'] for c in writer.reference_cards(b)}
            self.assertTrue({'solo-simple','instagram-best-practices','routine-commentary','beauty-storytime'}.issubset(refs))
            self.assertLessEqual(len(refs),6)
        b=writer.brief_values(dict(brief(),content_format='mini_list'))
        self.assertIn('micro-list',{c['id'] for c in writer.reference_cards(b)})

    def test_default_organic_mode_does_not_require_sales_cta(self):
        b=brief()
        self.assertEqual(b['content_mode'],'organic')
        self.assertEqual(b['cta'],'')
        self.assertIn('without any request can earn 4',writer.rubric_for(b)['cta'][1])
        self.assertNotIn('abcd',{c['id'] for c in writer.reference_cards(b)})
        self.assertIn('not a checklist',writer.content_guidance(b))

    def test_content_mode_and_format_validate(self):
        for key,value in [('content_mode','unknown'),('content_format','unknown')]:
            with self.assertRaises(ValueError):writer.brief_values(dict(brief(),**{key:value}))
        b=writer.brief_values(dict(brief(),content_mode='paid_ad'))
        self.assertIn('PAID AD',writer.content_guidance(b))
        self.assertIn('abcd',{c['id'] for c in writer.reference_cards(b)})
        self.assertEqual(writer.rubric_for(b)['cta'],writer.RUBRIC['cta'])

    def test_ugc_honors_supplied_experience_and_mode_in_generation(self):
        b=writer.brief_values(dict(brief(),content_mode='ugc',content_format='storytime',creator_experience='I bought this notebook yesterday. Only the cover has been opened.'))
        hook={'angle':'Notebook confession','spoken':'I bought a notebook. The first page still intimidates me.','visual':'Creator speaks to phone camera at their own desk.','overlay':'Blank page problem','payoff':'End on the first sentence, not a product pitch.'}
        prompts=[]
        def complete(prompt,tokens,label):
            prompts.append(prompt)
            return {'issues':[]} if label.startswith('Hook critique') else {'hooks':[hook]*5}
        self.assertEqual(writer.write_hooks(b,complete)[0]['spoken'],hook['spoken'])
        self.assertIn('UGC:',prompts[0])
        self.assertIn('storytime',prompts[0])
        self.assertIn('Only the cover has been opened.',prompts[0])

    def test_script_and_criterion_repair_use_organic_rubric(self):
        b=brief();prompts=[]
        s=script();s['scenes'][-1]['spoken']='And the grocery list became a poem.'
        def complete(prompt,tokens,label):
            prompts.append(prompt)
            return s if label.startswith('Draft') else assessment(4)
        result=writer.optimize(b,complete,lambda r:None,lambda *args:None)
        self.assertEqual(result['best']['script']['scenes'][-1]['spoken'],s['scenes'][-1]['spoken'])
        self.assertIn('ORGANIC SOCIAL',prompts[0])
        self.assertIn('without any request can earn 4',prompts[1])

    def test_unrequested_sales_ending_cannot_meet_organic_target(self):
        b=brief();s=script();s['scenes'][-1]['spoken']='This is where the story ends. Shop now. Link in bio.'
        result=writer.validate_assessment(assessment(4),s,b)
        self.assertEqual(result['score'],79)
        self.assertIn('unrequested sales CTA',result['blockers'][0])
        b['content_mode']='paid_ad'
        self.assertEqual(writer.validate_assessment(assessment(4),s,b)['score'],100)
        b['content_mode']='organic';b['cta']='Shop now. Link in bio.'
        self.assertEqual(writer.validate_assessment(assessment(4),s,b)['score'],100)

    def test_score_computed_and_proof_blocks_target(self):
        s=script()
        self.assertEqual(writer.validate_assessment(assessment(4),s)["score"],100)
        self.assertEqual(writer.validate_assessment(assessment(4,["Invented results"]),s)["score"],79)
        s["missing_proof"]=["Missing test"]
        self.assertEqual(writer.validate_assessment(assessment(4),s)["score"],79)

    def test_invalid_grades_references_and_timelines(self):
        for field,value in [("grade",True),("grade",5),("scene",99)]:
            raw=assessment();raw["criteria"][0][field]=value
            with self.assertRaises(ValueError):writer.validate_assessment(raw,script())
        raw=assessment();raw["criteria"][1]["key"]="hook"
        with self.assertRaises(ValueError):writer.validate_assessment(raw,script())
        for bad in [float('nan'),-1,4]:
            raw=script();raw["scenes"][0]["start"]=bad
            with self.assertRaises(ValueError):writer.validate_script(raw,brief())
        raw=script();raw["reference_ids"]=["nonexistent"]
        with self.assertRaises(ValueError):writer.validate_script(raw,brief())

    def test_target_stops_and_history_saved(self):
        replies=iter([script(),assessment(4)])
        saved=[]
        result=writer.optimize(brief(),lambda *a:next(replies),lambda r:saved.append(copy.deepcopy(r)),lambda *a:None)
        self.assertTrue(result["target_met"])
        self.assertEqual(len(result["history"]),1)
        self.assertEqual(saved[-1]["best"]["assessment"]["score"],100)

    def test_plateau_retains_best_instead_of_inflating_score(self):
        drafts=[]
        for n,g in enumerate([3,2,2]):
            s=script(str(n));s["scenes"][0]["spoken"]+=str(n)
            drafts.extend([s,assessment(g)])
        replies=iter(drafts)
        result=writer.optimize(brief(),lambda *a:next(replies),lambda r:None,lambda *a:None)
        self.assertEqual(result["stop_reason"],"no_improvement")
        self.assertEqual(result["best"]["assessment"]["score"],75)
        self.assertFalse(result["target_met"])

    def test_duplicate_stops_and_invalid_output_repairs(self):
        replies=iter([script(),assessment(),script()])
        result=writer.optimize(brief(),lambda *a:next(replies),lambda r:None,lambda *a:None)
        self.assertEqual(result["stop_reason"],"duplicate_draft")
        replies=iter([{},script()])
        self.assertEqual(writer.validated_completion(lambda *a:next(replies),'',100,'draft',lambda r:writer.validate_script(r,brief()))["title"],"Notebook")

    def test_attempt_limit_and_scene_regeneration(self):
        original=script()
        changed=script();changed['scenes'][0]['spoken']='A fresh opening.';changed['scenes'][1]['spoken']='Unwanted change.'
        replies=iter([changed,assessment(2)])
        result=writer.optimize(brief(),lambda *a:next(replies),lambda r:None,lambda *a:None,
                               max_rounds=1,previous_script=original,scene_index=0)
        self.assertEqual(result['stop_reason'],'attempt_limit')
        self.assertEqual(result['best']['script']['scenes'][0]['spoken'],'A fresh opening.')
        self.assertEqual(result['best']['script']['scenes'][1],original['scenes'][1])

    def test_overfilled_english_timeline_is_rejected(self):
        raw=script();raw['scenes'][0]['spoken']='word '*25
        with self.assertRaises(ValueError):writer.validate_script(raw,brief())

    def test_long_hook_rewrites_only_flagged_option_and_saves_first(self):
        hook={'angle':'demo','spoken':'Open a blank page.','visual':'Open notebook.','overlay':'One idea','payoff':'Write an idea.'}
        long=dict(hook,spoken=' '.join(['word']*19))
        saved=[];calls=[]
        def complete(prompt,tokens,label):
            calls.append((prompt,label))
            if label.startswith('Hook critique'):return {'issues':[]}
            if label=='Hook options 1':return {'hooks':[hook,long,hook,hook,hook]}
            self.assertEqual(saved[-1]['review_status'],'needs_review')
            self.assertEqual(saved[-1]['issues'][0]['index'],2)
            return {'replacements':[dict(hook,index=2,spoken='Why is the first page so intimidating?')]}
        result=writer.write_hooks(brief(),complete,lambda r:saved.append(copy.deepcopy(r)))
        self.assertEqual(result[0]['spoken'],hook['spoken'])
        self.assertEqual(result[1]['spoken'],'Why is the first page so intimidating?')
        self.assertEqual(saved[-1]['review_status'],'reviewed')
        self.assertEqual(len(calls),4)

    def test_persistent_long_hooks_are_saved_flagged_without_truncation(self):
        hook={'angle':'demo','spoken':' '.join(['word']*19),'visual':'Open notebook.','overlay':'One idea','payoff':'Write an idea.'}
        saved=[]
        def complete(prompt,tokens,label):
            return {'issues':[]} if label.startswith('Hook critique') else {'hooks':[hook]*5}
        result=writer.write_hooks(brief(),complete,lambda r:saved.append(copy.deepcopy(r)))
        self.assertEqual(result[0]['spoken'],hook['spoken'])
        self.assertEqual(saved[-1]['review_status'],'needs_review')
        self.assertEqual(len(saved[-1]['issues']),5)
        self.assertIn('19 English words',saved[-1]['issues'][0]['reason'])

    def test_failed_hook_rewrite_preserves_previous_set_and_issues(self):
        hook={'angle':'demo','spoken':' '.join(['word']*19),'visual':'Open notebook.','overlay':'One idea','payoff':'Write an idea.'}
        saved=[]
        def complete(prompt,tokens,label):
            if label.startswith('Hook critique'):return {'issues':[]}
            return {'hooks':[hook]*5} if label=='Hook options 1' else {'replacements':[]}
        result=writer.write_hooks(brief(),complete,lambda r:saved.append(copy.deepcopy(r)))
        self.assertEqual(len(result),5)
        self.assertEqual(saved[-1]['review_status'],'needs_review')
        self.assertEqual(len(saved[-1]['issues']),5)
        self.assertIn('rewrite could not finish',saved[-1]['warning'])

    def test_hook_word_limit_boundary_and_language(self):
        hook={'spoken':' '.join(['word']*18),'visual':'Open notebook.','overlay':'One idea','payoff':'Write an idea.'}
        self.assertEqual(writer.hook_usage_issues([hook],brief()),[])
        hook['spoken']+=' word'
        self.assertEqual(len(writer.hook_usage_issues([hook],brief())),1)
        self.assertEqual(writer.hook_usage_issues([hook],dict(brief(),language='Hindi')),[])

    def test_hook_repairs_invented_testimonial(self):
        hook={'angle':'demo','spoken':'Open a blank page.','visual':'Open notebook.','overlay':'One idea','payoff':'Write down an idea.'}
        bad=copy.deepcopy(hook);bad['spoken']='I once lost my best idea.'
        replies=iter([{'hooks':[bad]*5},{'hooks':[hook]*5}])
        result=writer.write_hooks(brief(),lambda prompt,tokens,label:{'issues':[]} if label.startswith('Hook critique') else next(replies))
        self.assertEqual(result[0]['spoken'],hook['spoken'])

    def test_hook_critique_drives_rewrite(self):
        hook={'angle':'demo','spoken':'Open a blank page.','visual':'Open notebook.','overlay':'One idea','payoff':'Write an idea.'}
        replies=iter([{'hooks':[hook]*5},{'issues':[{'index':1,'reason':'Payoff does not resolve premise.'}]},
                      {'hooks':[hook]*5},{'issues':[]}])
        prompts=[]
        def complete(prompt,*args):prompts.append(prompt);return next(replies)
        self.assertEqual(len(writer.write_hooks(brief(),complete)),5)
        self.assertIn('Payoff does not resolve premise.',prompts[2])

    def test_long_valid_critique_does_not_trigger_repair(self):
        note='This proposed visual needs evidence. '*25
        issues=writer.validate_hook_issues({'issues':[{'index':3,'reason':note}]})
        self.assertEqual(len(issues[0]['reason']),500)
        self.assertEqual(issues[0]['index'],3)
        raw=assessment(3);raw['criteria'][0]['reason']=note
        self.assertEqual(len(writer.validate_assessment(raw,script())['criteria'][0]['reason']),500)

    def test_hook_review_failure_preserves_drafts_without_claiming_reviewed(self):
        hook={'angle':'demo','spoken':'Open a blank page.','visual':'Open notebook.','overlay':'One idea','payoff':'Write an idea.'}
        saved=[]
        def complete(prompt,tokens,label):
            if label.startswith('Hook critique'):return {'issues':[{'index':1,'reason':''}]}
            return {'hooks':[hook]*5}
        result=writer.write_hooks(brief(),complete,lambda r:saved.append(copy.deepcopy(r)))
        self.assertEqual(len(result),5)
        self.assertEqual(saved[0]['review_status'],'pending')
        self.assertEqual(saved[-1]['review_status'],'unavailable')
        self.assertTrue(saved[-1]['warning'])

    def test_unresolved_hooks_saved_with_explicit_flags(self):
        hook={'angle':'demo','spoken':'Open a blank page.','visual':'Open notebook.','overlay':'One idea','payoff':'Write an idea.'}
        saved=[]
        def complete(prompt,tokens,label):
            if label.startswith('Hook critique'):return {'issues':[{'index':2,'reason':'Needs proof.'*100}]}
            return {'hooks':[hook]*5}
        writer.write_hooks(brief(),complete,lambda r:saved.append(copy.deepcopy(r)))
        self.assertEqual(saved[-1]['review_status'],'needs_review')
        self.assertEqual(saved[-1]['issues'][0]['index'],2)

    def test_compact_context_preserves_distinct_brand_rules(self):
        b=brief();b['brand_context']={'name':'Brand','documents':{'product_brief':b['facts'],'guidelines':'Never promise instant results.'}}
        compact=writer.compact_brief(b)
        self.assertNotIn('product_brief',compact['brand_context']['documents'])
        self.assertEqual(compact['brand_context']['documents']['guidelines'],'Never promise instant results.')
        self.assertEqual(b['brand_context']['documents']['product_brief'],b['facts'])
        self.assertLess(len(writer.reference_cards(b)),len(writer.library()['cards']))

    def test_scene_regeneration_requests_only_one_scene(self):
        budgets=[]
        def complete(prompt,tokens,label):
            budgets.append(tokens)
            if label.startswith('Draft'):return {'spoken':'A better opening.','visual':'Open notebook.','overlay':'Next idea'}
            return assessment(4)
        original=script()
        result=writer.optimize(brief(),complete,lambda r:None,lambda *a:None,previous_script=original,scene_index=0)
        self.assertEqual(budgets[0],450)
        self.assertEqual(result['best']['script']['scenes'][1:],original['scenes'][1:])

    def test_slogan_is_not_turned_into_unsupported_usage(self):
        b=brief();b['topic']='Shampoo';b['facts']="Shampoo. Brand slogan: Don't rinse it. Resolve it."
        hook={'spoken':"Don't rinse it. Resolve it.",'visual':'Show use as directed on the label.','overlay':'Brand slogan','payoff':'Show the bottle.'}
        self.assertEqual(writer.hook_usage_issues([hook],b),[])
        hook['visual']='Leave in for 60 seconds, then no rinse.'
        self.assertEqual(writer.hook_usage_issues([hook],b)[0]['index'],1)
        raw=script();raw['scenes'][0]['visual']='Apply shampoo; no rinse.'
        with self.assertRaisesRegex(ValueError,'label'):writer.validate_script(raw,b)


    def test_hook_rewrite_changes_only_flagged_option(self):
        hook={'angle':'demo','spoken':'Open a blank page.','visual':'Open notebook.','overlay':'One idea','payoff':'Write an idea.'}
        replacement=dict(hook,index=2,spoken='Try a new opening.')
        replies=iter([{'hooks':[hook]*5},{'issues':[{'index':2,'reason':'Improve this opening.'}]},
                      {'replacements':[replacement]},{'issues':[]}])
        budgets=[]
        def complete(prompt,tokens,label):budgets.append(tokens);return next(replies)
        result=writer.write_hooks(brief(),complete)
        self.assertEqual({k:result[0][k] for k in hook},hook)
        self.assertEqual(result[1]['spoken'],'Try a new opening.')
        self.assertEqual(budgets[2],430)

    def test_creative_routes_are_distinct_and_vary_by_seed(self):
        b=brief();b['generation_seed']=100
        routes=writer.creative_routes(b)
        self.assertEqual(len({r['id'] for r in routes}),5)
        self.assertTrue({'rant','curiosity'}.issubset({r['id'] for r in routes}))
        self.assertEqual(routes,writer.creative_routes(b))
        b['generation_seed']=101
        self.assertNotEqual(routes,writer.creative_routes(b))

    def test_staged_character_can_speak_without_fake_testimonial(self):
        hook={'angle':'Flake landlord','spoken':'I keep charging rent on this scalp.','visual':'Staged sketch: actor playing a dandruff flake presents an invoice.','overlay':'Rent due','payoff':'Reveal the product as the next scene.'}
        def complete(prompt,tokens,label):
            return {'issues':[]} if label.startswith('Hook critique') else {'hooks':[hook]*5}
        result=writer.write_hooks(brief(),complete)
        self.assertEqual(result[0]['spoken'],hook['spoken'])
        self.assertIn('creative_route',result[0])

    def test_two_character_beat_can_exceed_old_ten_word_limit(self):
        hook={'angle':'Courtroom sketch','spoken':'Judge: Why are you still here? Flake: I have a lease on this scalp.',
              'visual':'Staged sketch: two actors play judge and a flake.','overlay':'Scalp court','payoff':'The case leads into the product introduction.'}
        def complete(prompt,tokens,label):
            return {'issues':[]} if label.startswith('Hook critique') else {'hooks':[hook]*5}
        self.assertEqual(writer.write_hooks(brief(),complete)[0]['spoken'],hook['spoken'])

    def test_fictional_countdown_is_not_application_timing(self):
        hook={'spoken':'You have 3 seconds.','visual':'Staged sketch: a notebook is questioned in court.','overlay':'Answer now','payoff':'Reveal the missing grocery list.'}
        self.assertEqual(writer.hook_usage_issues([hook],brief()),[])

    def test_creative_preferences_validate(self):
        b=writer.brief_values(dict(brief(),creative_freedom='wild',creative_notes='Deadpan sketch; one actor.'))
        self.assertEqual(b['creative_notes'],'Deadpan sketch; one actor.')
        with self.assertRaises(ValueError):writer.brief_values(dict(brief(),creative_freedom='unknown'))

    def test_product_territory_changes_with_product(self):
        self.assertEqual(writer.creative_territory({'topic':'Anti-dandruff shampoo'})['category'],'Hair/scalp care')
        self.assertEqual(writer.creative_territory({'topic':'Cold coffee'})['category'],'Food/drink')
        self.assertEqual(writer.creative_territory(brief())['category'],'Ideas/productivity')

    def test_unscored_script_is_checkpointed_before_failed_review(self):
        drafts=[]
        def complete(prompt,tokens,label):
            return script() if label.startswith('Draft') else {'criteria':[]}
        with self.assertRaises(ValueError):
            writer.optimize(brief(),complete,lambda r:None,lambda *a:None,save_draft=lambda s:drafts.append(s))
        self.assertEqual(drafts[0]['title'],'Notebook')

    def test_missing_scene_repairs_only_one_criterion(self):
        raw=assessment(3);raw['criteria'][3].pop('scene')
        calls=[]
        def complete(prompt,tokens,label):
            calls.append((tokens,label))
            if len(calls)==1:return raw
            row=assessment(3)['criteria'][3];row['scene']=2;return row
        result=writer.assess_script(complete,'review',brief(),script(),1)
        self.assertEqual(result['score'],75)
        self.assertEqual(calls,[(1000,'Critique 1'),(280,'Critique 1: repair credibility')])


class WriterAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patches=[patch.object(server,'RESULTS_DIR',Path(self.temp.name)),patch.object(server,'_active_job',None),patch.object(server,'require_memory')]
        for p in self.patches:p.start()
        self.client=TestClient(server.app,base_url='http://127.0.0.1:8765')

    def tearDown(self):
        self.client.close()
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def test_hosted_selection_requires_explicit_credit_permission(self):
        b=dict(brief(),writer_backend='huggingface',hf_credits_allowed=False)
        with patch.object(server._executor,'submit') as submit:
            response=self.client.post('/api/scripts',json={'brief':b,'mode':'script'})
            self.assertEqual(response.status_code,422,response.text)
            self.assertIn('disabled',response.text)
            self.assertFalse(submit.called)
        self.assertIsNone(server._active_job)
        with patch('studio_script_hf.hf_token',return_value='hf_TESTSECRET'):
            response=self.client.get('/api/scripts/engines')
            self.assertTrue(response.json()['token_configured'])
            self.assertNotIn('hf_TESTSECRET',response.text)

    def test_hosted_generation_bypasses_gpu_and_retains_partial_work_on_quota_failure(self):
        from studio_script_hf import HostedWriterError
        b=dict(brief(),writer_backend='huggingface',hf_credits_allowed=True)
        with patch('studio_script_hf.hf_token',return_value='hf_TESTONLY'),patch.object(server._executor,'submit') as submit:
            response=self.client.post('/api/scripts',json={'brief':b,'mode':'script'})
            self.assertEqual(response.status_code,202,response.text)
            self.assertFalse(server.require_memory.called)
            process,sid,request=submit.call_args.args
        def quota_failure(path,request,progress):
            (path/'script_draft.json').write_text(json.dumps(script()))
            raise HostedWriterError('HF credits exhausted.')
        with patch('studio_script_hf.run_hf_writer',side_effect=quota_failure) as hosted,patch('studio_pipeline._run_worker') as gpu:
            process(sid,request)
            self.assertTrue(hosted.called)
            self.assertFalse(gpu.called)
        job=self.client.get('/api/scripts/'+sid).json()
        self.assertEqual(job['status'],'failed')
        self.assertIsNone(job['result']['best']['assessment']['score'])
        self.assertIsNone(server._active_job)

    def test_failed_hosted_job_can_retry_locally_with_saved_context(self):
        sid='c'*32;path=Path(self.temp.name)/'_scripts'/sid;path.mkdir(parents=True)
        b=dict(brief(),writer_backend='huggingface',hf_credits_allowed=True,generation_seed=123,brand_context={'name':'Brand'})
        (path/'state.json').write_text(json.dumps({'id':sid,'status':'failed','stage':'Stopped','brief':b}))
        (path/'review_input.json').write_text(json.dumps({'script_request':{'brief':b,'mode':'script','selected_hook':None}}))
        (path/'hf_writer_checkpoint.json').write_text('{"saved":true}')
        with patch('studio_script_local.resolve_local_model',return_value=('qwen35','Writer',Path('writer.gguf'))),patch('studio_script_hf.hf_token',side_effect=AssertionError('No hosted token needed')),patch.object(server._executor,'submit') as submit:
            response=self.client.post('/api/scripts/'+sid+'/retry',json={'writer_backend':'local','local_model':'qwen35'})
            self.assertEqual(response.status_code,202,response.text)
            self.assertTrue(submit.called)
        saved=json.loads((path/'review_input.json').read_text())['script_request']['brief']
        self.assertEqual(saved['writer_backend'],'local')
        self.assertFalse(saved['hf_credits_allowed'])
        self.assertEqual(saved['generation_seed'],123)
        self.assertEqual(saved['brand_context'],{'name':'Brand'})
        self.assertTrue((path/'hf_writer_checkpoint.json').exists())

    def test_revision_request_persists_parent_notes_and_manual_draft(self):
        parent='a'*32;path=Path(self.temp.name)/'_scripts'/parent;path.mkdir(parents=True)
        (path/'state.json').write_text(json.dumps({'id':parent,'status':'completed','brief':brief(),'stage':'Ready'}))
        original=script();original['scenes'][0]['spoken']='Keep this opening exactly as it is for this draft.'
        payload={'mode':'script','brief':brief(),'previous_script':original,'scene_index':2,'revision_notes':'Make only the ending funnier.','parent_script_id':parent}
        with patch.object(server._executor,'submit'):
            response=self.client.post('/api/scripts',json=payload)
        self.assertEqual(response.status_code,202,response.text)
        job=response.json();self.assertNotEqual(job['id'],parent)
        self.assertEqual(job['revision_notes'],payload['revision_notes'])
        request=json.loads((Path(self.temp.name)/'_scripts'/job['id']/'review_input.json').read_text())['script_request']
        self.assertEqual(request['previous_script'],original)
        self.assertEqual(request['parent_script_id'],parent)
        self.assertEqual(json.loads((path/'state.json').read_text())['status'],'completed')

    def test_revision_validation_live_snapshot_and_failure_preserves_original(self):
        self.assertEqual(self.client.post('/api/scripts',json={'brief':brief(),'revision_notes':'Change it'}).status_code,422)
        self.assertEqual(self.client.post('/api/scripts',json={'brief':brief(),'mode':'script','previous_script':script(),'revision_notes':'x'*1201}).status_code,422)
        sid='d'*32;path=Path(self.temp.name)/'_scripts'/sid;path.mkdir(parents=True)
        (path/'state.json').write_text(json.dumps({'id':sid,'status':'running','stage':'Writing','brief':brief()}))
        (path/'review_input.json').write_text(json.dumps({'script_request':{'previous_script':script(),'revision_notes':'Make it funnier','parent_script_id':'a'*32}}))
        (path/'script_live.json').write_text(json.dumps({'paragraphs':['A new ending is appearing'],'validated':False,'reviewed':False}))
        with patch.object(server,'_active_job',sid):
            result=self.client.get('/api/scripts/'+sid).json()
        self.assertEqual(result['live_draft']['paragraphs'],['A new ending is appearing'])
        self.assertNotIn('result',result)
        result=self.client.get('/api/scripts/'+sid).json()
        self.assertEqual(result['result']['stop_reason'],'requested_changes_not_completed')
        self.assertEqual(result['result']['best']['script'],script())
        self.assertIsNone(result['result']['best']['assessment']['score'])

    def test_page_library_experiments_and_busy_slot(self):
        self.assertEqual(self.client.get('/writer').status_code,200)
        self.assertEqual(len(self.client.get('/api/scripts/library').json()['cards']),22)
        values={'title':'Hook A/B','platform':'Reels','hypothesis':'Demo beats question','observations':'Too few impressions to decide.'}
        self.assertEqual(self.client.post('/api/scripts/experiments',json=values).status_code,201)
        self.assertEqual(len(self.client.get('/api/scripts/experiments').json()),1)
        with patch.object(server,'_active_job','other'):
            self.assertEqual(self.client.post('/api/scripts',json={'brief':brief()}).status_code,409)
        self.assertEqual(self.client.get('/api/scripts/not-a-job').status_code,404)

    def test_creation_uses_shared_worker_and_persists_input(self):
        with patch.object(server._executor,'submit') as submit:
            response=self.client.post('/api/scripts',json={'brief':brief(),'mode':'script','previous_script':script()})
            self.assertEqual(response.status_code,202,response.text)
            job=response.json();self.assertEqual(server._active_job,job['id'])
            self.assertTrue(submit.called)
            data=json.loads((Path(self.temp.name)/'_scripts'/job['id']/'review_input.json').read_text())
            self.assertEqual(data['script_request']['previous_script']['title'],'Notebook')

    def test_nvidia_dispatches_without_local_gpu_and_preserves_revision(self):
        b=dict(brief(),writer_backend='nvidia')
        with patch('studio_script_nvidia.nvidia_token',return_value='nvapi-TESTSECRET'), patch.object(server,'require_memory',side_effect=AssertionError('Hosted must skip GPU')), patch.object(server._executor,'submit') as submit:
            response=self.client.post('/api/scripts',json={'brief':b,'mode':'script','previous_script':script(),'revision_notes':'Make the ending funnier'})
            self.assertEqual(response.status_code,202,response.text)
            args=submit.call_args.args
            with patch('studio_script_nvidia.run_nvidia_writer') as run, patch('studio_pipeline._run_worker',side_effect=AssertionError('No local worker')):
                args[0](*args[1:])
                self.assertEqual(run.call_args.args[1]['revision_notes'],'Make the ending funnier')
                self.assertEqual(run.call_args.args[1]['previous_script']['title'],'Notebook')
            state=self.client.get('/api/scripts/'+response.json()['id']).json()
            self.assertEqual(state['status'],'completed')
            self.assertNotIn('nvapi-TESTSECRET',json.dumps(state))
            self.assertIsNone(server._active_job)

    def test_worker_completion_and_guard_failure_release_slot(self):
        for success in (True,False):
            with patch.object(server._executor,'submit') as submit:
                response=self.client.post('/api/scripts',json={'brief':brief(),'mode':'script'})
                self.assertEqual(response.status_code,202)
            args=submit.call_args.args
            with patch('studio_pipeline.stage_pause'), patch('studio_pipeline._run_worker',return_value=(success,3300,'GPU guard stopped the worker')):
                args[0](*args[1:])
            state=self.client.get('/api/scripts/'+response.json()['id']).json()
            self.assertEqual(state['status'],'completed' if success else 'failed')
            self.assertIsNone(server._active_job)

    def test_bad_scene_request_and_interrupted_job(self):
        response=self.client.post('/api/scripts',json={'brief':brief(),'mode':'script','scene_index':99})
        self.assertEqual(response.status_code,422)
        response=self.client.post('/api/scripts',json={'brief':brief(),'previous_script':{'scenes':['invalid']}})
        self.assertEqual(response.status_code,422)
        sid='d'*32;path=Path(self.temp.name)/'_scripts'/sid;path.mkdir(parents=True)
        (path/'state.json').write_text(json.dumps({'id':sid,'status':'running','brief':brief(),'stage':'Writing'}))
        self.assertEqual(self.client.get('/api/scripts/'+sid).json()['status'],'failed')

    def test_retry_preserves_input_and_checkpoint(self):
        sid='e'*32;path=Path(self.temp.name)/'_scripts'/sid;path.mkdir(parents=True)
        (path/'state.json').write_text(json.dumps({'id':sid,'status':'failed','brief':brief(),'stage':'Stopped'}))
        (path/'review_input.json').write_text(json.dumps({'script_request':{'brief':brief(),'mode':'hooks'}}))
        (path/'review_checkpoint.json').write_text('{"saved":true}')
        with patch.object(server._executor,'submit') as submit:
            response=self.client.post('/api/scripts/'+sid+'/retry')
            self.assertEqual(response.status_code,202,response.text)
            self.assertTrue(submit.called)
            self.assertEqual(server._active_job,sid)
            self.assertEqual((path/'review_checkpoint.json').read_text(),'{"saved":true}')
            self.assertEqual(self.client.post('/api/scripts/'+sid+'/retry').status_code,409)

    def test_spoken_only_hook_selection_api_and_persona_catalog(self):
        self.assertEqual(len(self.client.get('/api/scripts/personas').json()['personas']),24)
        hook={'angle':'Blank page','spoken':'Why is page one the hardest?','payoff':'Write one small thought.'}
        with patch.object(server._executor,'submit'):
            response=self.client.post('/api/scripts',json={'mode':'script','brief':dict(brief(),persona='fourth_wall'),'selected_hook':hook})
            self.assertEqual(response.status_code,202,response.text)
            self.assertEqual(response.json()['brief']['persona'],'fourth_wall')
            job=Path(self.temp.name)/'_scripts'/response.json()['id']/'review_input.json'
            self.assertEqual(json.loads(job.read_text())['script_request']['selected_hook']['spoken'],hook['spoken'])

    def test_editing_invalidates_export_score(self):
        sid='a'*32;path=Path(self.temp.name)/'_scripts'/sid;path.mkdir(parents=True)
        (path/'state.json').write_text(json.dumps({'id':sid,'status':'completed','brief':brief(),'stage':'Done'}))
        result={'best':{'script':script(),'assessment':writer.validate_assessment(assessment(4),script())},'history':[], 'stop_reason':'target_reached'}
        (path/'script_result.json').write_text(json.dumps(result))
        edited=script();edited['scenes'][0]['spoken']='Changed wording'
        self.assertEqual(self.client.put(f'/api/scripts/{sid}/draft',json=edited).status_code,200)
        exported=self.client.get(f'/api/scripts/{sid}/export').text
        self.assertNotIn('SHOT:',exported)
        self.assertNotIn('TEXT:',exported)
        self.assertIn('Changed wording',exported)
        self.assertNotIn('100/100',exported)
        edited['title']='<script>alert(1)</script>'
        self.client.put(f'/api/scripts/{sid}/draft',json=edited)
        self.assertNotIn('<script>alert(1)</script>',self.client.get(f'/api/scripts/{sid}/export?format=print').text)

    def test_failed_review_exposes_saved_unscored_script(self):
        sid='f'*32;path=Path(self.temp.name)/'_scripts'/sid;path.mkdir(parents=True)
        (path/'state.json').write_text(json.dumps({'id':sid,'status':'failed','brief':brief(),'stage':'Stopped'}))
        (path/'script_draft.json').write_text(json.dumps(script()))
        result=self.client.get('/api/scripts/'+sid).json()['result']
        self.assertIsNone(result['best']['assessment']['score'])
        self.assertFalse(result['target_met'])
        self.assertEqual(self.client.get('/api/scripts/'+sid+'/export').text,writer.export_text(result))
