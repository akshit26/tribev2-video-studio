import tempfile,json,unittest
from pathlib import Path
from studio_script_writer import validate_final_script,write_final_script,run_writer,export_text,validate_script
TEXT='My notebook has one job. [Hold notebook] Keep the ideas I forget between breakfast and finding my keys. I do not need another app asking me to organise my entire personality. I need a blank page where a shopping list can sit next to a ridiculous business idea without either one sending me a notification. That is the whole system. Write it down and get on with the day.'
class FinalScriptTests(unittest.TestCase):
    def test_single_field_schema_and_round_trip(self):
        self.assertEqual(validate_final_script({'final_script':'One\n continuous block.'}),{'final_script':'One continuous block.'})
        for raw in ({'scenes':[]},{'final_script':'Hi','title':'Extra'},{'final_script':''}):
            with self.assertRaises(ValueError):validate_final_script(raw)
        self.assertEqual(validate_script({'final_script':TEXT},{}),{'final_script':TEXT})
    def test_both_entry_modes_generate_only_final_script_and_export_text(self):
        for mode in ('hooks','script'):
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp);brief={'topic':'Notebook','facts':'80 blank pages','duration':30,'language':'English'}
                (p/'review_input.json').write_text(json.dumps({'script_request':{'mode':mode,'brief':brief}}))
                calls=[]
                def complete(prompt,tokens,label):calls.append(prompt);return {'final_script':TEXT}
                run_writer(p,complete,lambda *args:None)
                result=json.loads((p/'script_result.json').read_text())
                self.assertEqual(result['best']['script'],{'final_script':TEXT})
                self.assertEqual(export_text(result),TEXT)
                self.assertFalse((p/'hooks.json').exists())
                self.assertEqual(len(calls),1)
    def test_revision_passes_entire_old_script_and_notes(self):
        saved=[];prompts=[]
        def complete(prompt,tokens,label):prompts.append(prompt);return {'final_script':TEXT}
        request={'brief':{'topic':'Notebook','facts':'80 blank pages','duration':30,'language':'English'},'previous_script':{'scenes':[{'spoken':'My archived script.'}]},'revision_notes':'Make the ending funnier.'}
        write_final_script(request,complete,saved.append,lambda *args:None)
        self.assertIn('My archived script.',prompts[0]);self.assertIn('Make the ending funnier.',prompts[0])
        self.assertEqual(set(saved[0]['best']['script']),{'final_script'})

class FinalScriptAPITests(unittest.TestCase):
    def test_save_reload_and_export_use_single_field(self):
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        import studio_server as server
        from studio_script_writer import brief_values
        with tempfile.TemporaryDirectory() as tmp,patch.object(server,'RESULTS_DIR',Path(tmp)),patch.object(server,'_active_job',None):
            sid='d'*32;p=Path(tmp)/'_scripts'/sid;p.mkdir(parents=True)
            brief=brief_values({'topic':'Notebook','facts':'80 blank pages','duration':30})
            result={'final_script':TEXT,'best':{'script':{'final_script':TEXT},'assessment':{'score':None,'criteria':[],'blockers':[]}},'history':[],'target_met':False,'stop_reason':'single_block_complete'}
            (p/'state.json').write_text(json.dumps({'id':sid,'status':'completed','brief':brief,'stage':'Script ready'}))
            (p/'script_result.json').write_text(json.dumps(result))
            with TestClient(server.app,base_url='http://127.0.0.1:8765') as client:
                self.assertEqual(client.get('/api/scripts/'+sid).status_code,200)
                edited={'final_script':TEXT+' [Smile]'}
                self.assertEqual(client.put('/api/scripts/'+sid+'/draft',json=edited).status_code,200)
                self.assertEqual(client.get('/api/scripts/'+sid+'/draft').json(),edited)
                self.assertEqual(client.get('/api/scripts/'+sid+'/export').text,edited['final_script'])
                self.assertIn('[Smile]',client.get('/api/scripts/'+sid+'/export?format=print').text)

class FinalScriptAuditTests(unittest.TestCase):
    def run_text(self,content,language='English'):
        request={'brief':{'topic':'Notebook','facts':'80 blank pages','duration':30,'language':language}}
        return write_final_script(request,lambda *args:{'final_script':content},lambda row:None,lambda *args:None)
    def test_hindi_danda_is_a_sentence_boundary(self):
        content='\u092e\u0947\u0930\u0940 \u092c\u093e\u0924\u0964 '+(' \u0935\u093f\u091a\u093e\u0930'*60)
        self.assertIn('final_script',self.run_text(content,'Hindi')['best']['script'])
    def test_curly_apostrophe_filler_and_fullwidth_question_are_rejected(self):
        for content in ['Let\u2019s dive in. '+TEXT,'Why\uff1f '+TEXT]:
            result=self.run_text(content)
            self.assertEqual(result['quality_status'],'needs_review')
            self.assertTrue(result['best']['assessment']['blockers'])
    def test_corrupt_saved_metadata_cannot_break_saved_work_listing(self):
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        import studio_server as server
        with tempfile.TemporaryDirectory() as tmp,patch.object(server,'RESULTS_DIR',Path(tmp)):
            sid='f'*32;path=Path(tmp)/'_scripts'/sid;path.mkdir(parents=True)
            with TestClient(server.app,base_url='http://127.0.0.1:8765') as client:
                for invalid in [[],{}, {'status':'completed','brief':None}, {'status':'completed','brief':{}}]:
                    (path/'state.json').write_text(json.dumps(invalid))
                    self.assertEqual(client.get('/api/scripts/'+sid).status_code,404)
                    self.assertEqual(client.get('/api/scripts').status_code,200)

class RepairLifecycleTests(unittest.TestCase):
    def test_repair_contains_rejected_text_and_does_not_reuse_bad_cache(self):
        from unittest.mock import Mock
        from studio_script_writer import validated_completion
        complete=Mock(side_effect=[{'final_script':'Rejected opening?'},{'final_script':'A corrected opening.'}])
        complete.reject=Mock()
        def check(raw):
            if '?' in raw['final_script']:raise ValueError('No opening question.')
            return raw
        result=validated_completion(complete,'Write a script.',1200,'Draft',check)
        self.assertEqual(result['final_script'],'A corrected opening.')
        self.assertIn('Rejected opening?',complete.call_args_list[1].args[0])
        complete.reject.assert_called_once_with('Write a script.',1200,'Draft')
    def test_failed_quality_check_keeps_a_flagged_editable_draft(self):
        request={'brief':{'topic':'Notebook','facts':'80 blank pages','duration':30,'language':'English'}}
        saved=[]
        result=write_final_script(request,lambda *args:{'final_script':'A short opening.'},saved.append,lambda *args:None)
        self.assertEqual(result['quality_status'],'needs_review')
        self.assertIsNone(result['best']['assessment']['score'])
        self.assertTrue(result['best']['assessment']['blockers'])
        self.assertEqual(result['final_script'],'A short opening.')
    def test_facewash_claims_are_checked_without_the_word_skin_in_brief(self):
        from studio_script_writer import claim_issues
        brief={'topic':'Neem facewash','facts':'Promote our Himalya neem facewash','niche':'skincare'}
        self.assertTrue(claim_issues('No harsh chemicals, just a gentle cleanse.',brief))
    def test_stopped_gpt_job_can_explicitly_retry_with_fast_provider(self):
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        import studio_server as server
        from studio_script_writer import brief_values
        with tempfile.TemporaryDirectory() as tmp,patch.object(server,'RESULTS_DIR',Path(tmp)),patch.object(server,'_active_job',None),patch.object(server._executor,'submit'),patch('studio_script_fast.ready',return_value=True):
            sid='c'*32;p=Path(tmp)/'_scripts'/sid;p.mkdir(parents=True)
            b=brief_values({'topic':'Notebook','facts':'80 blank pages','writer_backend':'team'})
            (p/'state.json').write_text(json.dumps({'id':sid,'status':'failed','stage':'Stopped','brief':b}))
            (p/'review_input.json').write_text(json.dumps({'script_request':{'brief':b,'mode':'script'}}))
            with TestClient(server.app,base_url='http://127.0.0.1:8765') as client:
                response=client.post('/api/scripts/'+sid+'/retry',json={'writer_backend':'fast'})
                self.assertEqual(response.status_code,202,response.text)
                self.assertEqual(response.json()['brief']['writer_backend'],'fast')
