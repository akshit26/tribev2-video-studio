import copy,json,unittest
from unittest.mock import Mock,patch
import studio_script_writer as writer
from studio_editor import validate_editor_output,compose_script
from studio_persona_lookup import retrieve_personas,index
from actor_critic_fixtures import BODY,HOOKS,EDIT,CRITIQUE,SCRIPT


class ActorCriticTests(unittest.TestCase):
    def brief(self,**changes):
        values=dict(topic='Reusable shower hair catcher',facts='Silicone insert sits over the shower drain and catches loose hair. Lift it, remove collected hair, rinse and reuse.',
                    content_duration='short',language='English',writer_backend='fast',content_mode='ugc')
        values.update(changes)
        return writer.brief_values(values)

    def run_pipeline(self,responses=None,**request):
        complete=Mock(side_effect=copy.deepcopy(responses if responses is not None else [{'final_script':SCRIPT},CRITIQUE,EDIT]))
        saved=[];drafts=[]
        result=writer.write_final_script(dict(brief=self.brief(),**request),complete,saved.append,lambda *a:None,drafts.append)
        return result,complete,saved,drafts

    def test_exactly_three_stages_no_final_remote_grade_or_regeneration(self):
        with patch('studio_pipeline.score_draft_script') as old_score:
            result,complete,saved,drafts=self.run_pipeline()
        old_score.assert_not_called()
        self.assertTrue(result['approved'],result['best']['assessment']['blockers'])
        self.assertEqual([call.args[2] for call in complete.call_args_list],['Draft 1','Internal critique','Editor and A/B hooks'])
        self.assertEqual(len(result['ab_hooks']),3)
        self.assertIsNone(result['best']['assessment']['score'])
        self.assertEqual(result['pipeline']['model_calls_completed'],3)
        self.assertEqual(saved[-1],result)
        self.assertEqual(drafts[-1],result['best']['script'])

    def test_editor_applies_critique_once_and_never_creates_another_loop(self):
        feedback=dict(CRITIQUE,hook_velocity=['Trim the opening to eleven words.'])
        result,complete,_,_=self.run_pipeline([{'final_script':'Drain hair is the worst.'},feedback,EDIT])
        self.assertTrue(result['approved'])
        self.assertEqual(complete.call_count,3)
        self.assertIn('Trim the opening',complete.call_args.args[0])
        self.assertIn('bland hook',complete.call_args.args[0])

    def test_failure_retains_completed_draft_without_extra_calls(self):
        for responses,calls in [([{'final_script':SCRIPT},RuntimeError('Critic offline')],2),
                                ([{'final_script':SCRIPT},CRITIQUE,RuntimeError('Editor offline')],3)]:
            result,complete,_,_=self.run_pipeline(responses)
            self.assertFalse(result['approved'])
            self.assertEqual(result['final_script'],SCRIPT)
            self.assertEqual(complete.call_count,calls)

    def test_first_stage_timeout_keeps_the_provider_diagnosis(self):
        with self.assertRaisesRegex(ValueError,'NVIDIA did not return output within 180 seconds'):
            self.run_pipeline([RuntimeError('NVIDIA did not return output within 180 seconds.')])

    def test_unsafe_alternate_hook_blocks_approval_without_a_retry(self):
        bad=copy.deepcopy(EDIT);bad['hooks'][2]['text']='This catcher catches every strand.'
        result,complete,_,_=self.run_pipeline([{'final_script':SCRIPT},CRITIQUE,bad])
        self.assertFalse(result['approved'])
        self.assertEqual(complete.call_count,3)
        self.assertIn('Unsupported universal collection',' '.join(result['best']['assessment']['blockers']))
        self.assertFalse(result['ab_hooks'][2]['validated'])
        complete.reject_last.assert_called_once_with('Editor and A/B hooks')

    def test_hook_schema_distinctness_and_strict_twelve_word_boundary(self):
        for update in [dict(EDIT,hooks=HOOKS[:2]),dict(EDIT,hooks=[HOOKS[0]]*3)]:
            with self.assertRaises(ValueError):validate_editor_output(update)
        for words,valid in [(11,True),(12,False)]:
            raw=copy.deepcopy(EDIT);raw['hooks'][0]['text']=' '.join(['word']*words)
            if valid:validate_editor_output(raw)
            else:
                with self.assertRaises(ValueError):validate_editor_output(raw)

    def test_swap_composition_preserves_body_and_opening_visual(self):
        variants=[compose_script(h['text'],BODY) for h in HOOKS]
        self.assertTrue(all(v.splitlines()[0].startswith('[B-ROLL:') for v in variants))
        self.assertEqual(len({v.split('\n',1)[1] for v in variants}),1)
        self.assertEqual(writer.validate_final_script({'final_script':variants[0]})['final_script'],variants[0])

    def test_persona_lookup_is_bounded_and_explicit_choice_wins(self):
        query=self.brief(topic='Cotton outfit styling',niche='fashion')
        found=retrieve_personas(query)
        self.assertLessEqual(len(found),2)
        self.assertTrue(any('Fashion' in p['best_for'] for p in found))
        choice=next(p for p in writer.personas() if p['name']=='Deadpan observer')
        selected=retrieve_personas(dict(query,persona=choice['id']))
        self.assertEqual([row['name'] for row in selected],['Deadpan observer'])
        before=index.cache_info().hits;retrieve_personas(query)
        self.assertGreater(index.cache_info().hits,before)

    def test_revision_and_selected_hook_are_data_in_actor_context(self):
        result,complete,_,_=self.run_pipeline(selected_hook={'spoken':'A safe opening idea.'},revision_notes='Make it sharper.',previous_script={'final_script':'My old wording.'})
        context=json.loads(complete.call_args_list[0].args[0].split('\nBRIEF: ',1)[1])
        self.assertEqual(context['revision_notes'],'Make it sharper.')
        self.assertEqual(context['previous_script']['final_script'],'My old wording.')
        self.assertTrue(context['persona_references'])
        self.assertIn('Make it sharper.',complete.call_args.args[0])

    def test_missing_cta_invented_link_and_anti_selling_are_not_exportable(self):
        for closing in ('This is ready for another shower.','Check the link below to grab one.',"Do not buy this product."):
            bad=copy.deepcopy(EDIT)
            bad['script_body']=BODY.replace('Grab one before your next shower.',closing)
            result,complete,_,_=self.run_pipeline([{'final_script':SCRIPT},CRITIQUE,bad])
            self.assertFalse(result['approved'])
            self.assertEqual(complete.call_count,3)

    def test_live_regressions_natural_closings_and_unsupported_hook_claims(self):
        for closing in ('Keep one in your shower for the next wash.', 'Get one before your next shower.'):
            self.assertEqual(writer.creator_closing_issues(BODY.replace('Grab one before your next shower.',closing),self.brief()),[])
        for opening in ('Cleaning a drain can actually take seconds.', 'Your drain stays clear with this catcher.', 'Why do we still touch drain hair?', 'Who knew a ring could stop drain chaos', 'I never expected a silicone trap would save me.'):
            bad=copy.deepcopy(EDIT);bad['hooks'][1]['text']=opening
            result,complete,_,_=self.run_pipeline([{'final_script':SCRIPT},CRITIQUE,bad])
            self.assertFalse(result['approved'],opening)
            self.assertEqual(complete.call_count,3)
        from studio_evaluation import sterile_cleanup_sequence
        self.assertTrue(sterile_cleanup_sequence('You lift it, remove collected hair, rinse it and reuse it.'))
        self.assertTrue(writer.claim_issues('[B-ROLL: Remove hair, rinse, show clean drain]',self.brief()))

    def test_invalid_cached_editor_is_evicted_for_a_manual_retry(self):
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from studio_script_hf import run_hf_writer
        calls=[]
        def send(token,model,system,prompt,tokens,temperature,preview,label):
            calls.append((label,system))
            if label=='Draft 1':return {'final_script':SCRIPT},{}
            if label=='Internal critique':return copy.deepcopy(CRITIQUE),{}
            if sum(stage[0].startswith('Editor') for stage in calls)==1:
                return {'script_body':BODY,'hooks':HOOKS[:2]},{}
            return copy.deepcopy(EDIT),{}
        provider=SimpleNamespace(MODEL='test-model',NAME='Test provider',PROFILE='actor-test',
                                 nvidia_token=lambda:'test',complete_stage=send)
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder);request={'brief':self.brief(),'mode':'script'}
            (output/'review_input.json').write_text(json.dumps({'script_request':request}))
            with patch('studio_script_hf.validate_configuration'):
                run_hf_writer(output,request,lambda *a:None,provider=provider)
                self.assertFalse(json.loads((output/'script_result.json').read_text())['approved'])
                run_hf_writer(output,request,lambda *a:None,provider=provider)
            self.assertTrue(json.loads((output/'script_result.json').read_text())['approved'])
            usage=json.loads((output/'fast_writer_usage.json').read_text())
            self.assertEqual(usage['cache_hits'],2)
            self.assertEqual(usage['calls_this_run'],1)
        self.assertEqual(len(calls),4)
        self.assertIn('mechanical critic',calls[1][1])
        self.assertIn('final editor',calls[2][1])

    def test_manual_retry_reuses_actor_and_critic_but_not_unsafe_editor(self):
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from studio_script_hf import run_hf_writer
        unsafe=copy.deepcopy(EDIT);unsafe['hooks'][2]['text']='This catcher catches every strand.'
        send=Mock(side_effect=[({'final_script':SCRIPT},{}),(CRITIQUE,{}),(unsafe,{}),(EDIT,{})])
        provider=SimpleNamespace(MODEL='test-model',NAME='Test',PROFILE='retry-test',nvidia_token=lambda:'test',complete_stage=send)
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder);request={'brief':self.brief(),'mode':'script'}
            (output/'review_input.json').write_text(json.dumps({'script_request':request}))
            with patch('studio_script_hf.validate_configuration'):
                run_hf_writer(output,request,lambda *a:None,provider=provider)
                self.assertFalse(json.loads((output/'script_result.json').read_text())['approved'])
                run_hf_writer(output,request,lambda *a:None,provider=provider)
            self.assertTrue(json.loads((output/'script_result.json').read_text())['approved'])
            usage=json.loads((output/'fast_writer_usage.json').read_text())
            self.assertEqual(usage['cache_hits'],2)
            self.assertEqual(usage['calls_this_run'],1)
        self.assertEqual(send.call_count,4)


if __name__=='__main__':unittest.main()
