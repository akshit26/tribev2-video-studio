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
