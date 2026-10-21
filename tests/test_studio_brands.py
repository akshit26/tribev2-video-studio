import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from fastapi.testclient import TestClient
import studio_server as server
import studio_brands as brands
from studio_brand_review import apply_brand_score, generate_brand_review, split_text, validate_checks
from studio_brand_output import brand_html


class BrandTests(unittest.TestCase):
    def test_unified_cognitive_review_can_supply_reference_and_feedback(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);brand=brands.new_brand(root,'Creator product')
            job_id='f'*32;output=root/job_id;output.mkdir()
            report=dict(backend='nvidia',video={'name':'creator.mp4','duration_seconds':12},result={},
                cognitive=dict(attention_retention_score=77,emotional_arousal_state='Curiosity',cognitive_load_warning=False,
                    psychological_critique='Opening shows the product.',visual_observations=[dict(timestamp=1.,observation='Creator holds the product.')]),
                pacing=dict(available=True,text='Real creator words.',language='en',duration_seconds=12),context={})
            (output/'report.json').write_text(json.dumps(report),encoding='utf-8')
            brands.register_reference(root,brand['id'],job_id,{'views':100})
            reference=brands.snapshot(root,brand['id'])['references'][0]
            self.assertEqual(reference['score'],77)
            self.assertIn('Creator holds the product.',str(reference))
            profile=brands.save_feedback(root,brand['id'],'e'*32,report,{'team_rating':80})
            self.assertEqual(profile['feedback'][0]['base_score'],77)

    def test_cloud_reference_registration_snapshot_and_feedback_use_real_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);brand=brands.new_brand(root,'Creator product')
            job_id='f'*32;output=root/job_id;output.mkdir()
            report=dict(backend='nvidia',video={'name':'creator.mp4','duration_seconds':12},
                result=dict(hook_score=85,pacing_score=80,overall_probability=82,
                            timestamped_revision_advice='00:01: The label is visible.'),
                pacing=dict(available=True,text='Real creator words.',language='hi',duration_seconds=12),
                visual_frames=[dict(timestamp=1.,observation='Creator holds the product.'),
                               dict(timestamp=90.,observation='Out-of-range observation.')],
                context={'platform':'instagram'})
            (output/'report.json').write_text(json.dumps(report),encoding='utf-8')
            brands.register_reference(root,brand['id'],job_id,{'views':100})
            references=brands.snapshot(root,brand['id'])['references']
            self.assertEqual(len(references),1)
            ref=references[0]
            self.assertEqual(ref['score'],82)
            self.assertEqual(ref['language'],'hi')
            self.assertEqual(len(ref['excerpts']),2)
            self.assertEqual(ref['excerpts'][0]['text'],'Real creator words.')
            self.assertNotIn('Out-of-range',str(ref))
            profile=brands.save_feedback(root,brand['id'],'e'*32,report,{'team_rating':90})
            self.assertEqual(profile['feedback'][0]['base_score'],82)

    def test_text_docx_pdf_extraction_and_no_silent_truncation(self):
        from reportlab.pdfgen.canvas import Canvas
        self.assertEqual(brands.extract_document('notes.txt', 'தமிழ் हिन्दी'.encode()), 'தமிழ் हिन्दी')
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as z:
            z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Say the brand</w:t></w:r></w:p></w:body></w:document>')
        self.assertEqual(brands.extract_document('brief.docx',data.getvalue()),'Say the brand')
        pdf=io.BytesIO();canvas=Canvas(pdf);canvas.drawString(50,750,'Mention the product');canvas.save()
        self.assertIn('Mention the product',brands.extract_document('brief.pdf',pdf.getvalue()))
        for name,content in [('x.exe',b'x'),('x.txt',b''),('x.txt',b'x'*(brands.MAX_TEXT+1))]:
            with self.assertRaises(ValueError):brands.extract_document(name,content)

    def test_calibration_requires_varied_candidates_excludes_winners_and_self(self):
        rows=[dict(job_id=str(i),base_score=40,team_rating=40+i*10,purpose='candidate') for i in range(5)]
        p={'feedback':rows}
        c=brands.calibration(p)
        self.assertTrue(c['active']);self.assertAlmostEqual(c['adjustment'],6.7)
        self.assertFalse(brands.calibration(p,exclude_job='0')['active'])
        p['reference_history']=['0'];self.assertFalse(brands.calibration(p)['active'])
        p={'feedback':[dict(r,team_rating=95) for r in rows]};self.assertFalse(brands.calibration(p)['active'])
        p={'feedback':[dict(r,purpose='reference') for r in rows]};self.assertEqual(brands.calibration(p)['sample_count'],0)

    def test_metrics_validation(self):
        for payload in [{'team_rating':101},{'views':1.2},{'retention_percent':float('nan')},{'spend':True},{'notes':'x'*1501}]:
            with self.assertRaises(ValueError):brands.outcome_values(payload)
        self.assertEqual(brands.outcome_values({'views':200,'conversions':3})['views'],200)

    def test_reuploaded_identical_video_is_not_a_new_training_example(self):
        p={'feedback':[dict(job_id=str(i),video_hash='same',base_score=40,team_rating=40+i*10,purpose='candidate') for i in range(6)]}
        self.assertEqual(brands.calibration(p)['sample_count'],1)
        self.assertEqual(brands.calibration(p,exclude_fingerprint='same')['sample_count'],0)
        p['reference_hashes']=['same'];self.assertEqual(brands.calibration(p)['sample_count'],0)

    def test_unknown_brand_check_widens_range_without_missing_penalty(self):
        review={'estimate':{'score':80,'range':[72,88]},'brand_review':{'checks':[{'status':'unknown'}],'calibration':{'adjustment':0}},'target':{'score':75}}
        apply_brand_score(review)
        self.assertEqual(review['overall_score'],71)
        self.assertEqual(review['brand_review']['compliance_score'],50)
        self.assertEqual(review['brand_review']['range'],[50,92])
        self.assertEqual(review['target']['gap'],4)
        self.assertIn('brand checks',review['target']['explanation'])
        review['brand_review']['checks']=[];apply_brand_score(review);self.assertEqual(review['overall_score'],80)

    def test_quotes_and_source_ids_are_grounded(self):
        row={'requirement':'Name the brand','quote':'Mention Plum','status':'meets','reason':'Spoken','change':'No change','source_ids':['S1']}
        self.assertEqual(len(validate_checks({'checks':[row]},'Mention Plum.',{'S1'})),1)
        self.assertEqual(validate_checks({'checks':[dict(row,quote='Invented')]},'Mention Plum.',{'S1'})[0]['quote'],'Mention Plum.')
        with self.assertRaises(ValueError):
            validate_checks({'checks':[dict(row,source_ids=['S99'])]},'Mention Plum.',{'S1'})
        self.assertEqual(validate_checks({'checks':[dict(row,source_ids=[])]},'Mention Plum.',{'S1'})[0]['status'],'unknown')
        self.assertEqual(validate_checks({'checks':[dict(row,status='unknown',source_ids=[])]},'Mention Plum.',{'S1'})[0]['status'],'unknown')

    def test_chunking_keeps_every_character(self):
        text=('हिन्दी தமிழில் text.\n'*100)
        chunks=split_text(text,len,limit=100)
        self.assertEqual(''.join(chunks),text);self.assertTrue(all(len(c)<=100 for c in chunks))

    def test_generation_processes_documents_and_references_with_independent_ids(self):
        reference={'job_id':'b'*32,'name':'Winner','language':'hi','platform':'instagram','duration_seconds':20,'excerpts':[{'id':'S7','text':'Try it'}],'outcomes':{'views':10000}}
        context={'id':'a'*32,'name':'Brand <unsafe>','version':2,'documents':{'guidelines':{'name':'brief.txt','text':'Mention Plum.'}},'references':[reference],'team_notes':[], 'calibration':brands.calibration({}),'note':'Snapshot'}
        report={'video':{'duration_seconds':20},'brand_context':context,'transcript':{'language':'hi'}}
        review={'sources':[{'id':'S1','start':0,'end':3,'text':'Plum'}],'estimate':{'score':60,'range':[50,70]}}
        calls=[]
        def complete(prompt,tokens,label):
            calls.append(label)
            if label.startswith('Brand'):
                return {'checks':[{'requirement':'Name brand','quote':'Mention Plum','status':'meets','reason':'S1 names Plum','change':'No change','source_ids':['S1']}]}
            self.assertIn('"reference_source_ids": ["S7"]',prompt)
            return {'similarities':'Product topic','differences':'Different hook','adapt':'Show the payoff earlier','caution':'Views are not causal','source_ids':['S1'],'reference_source_ids':['S7']}
        generate_brand_review(report,review,review['sources'],complete,len,lambda *_:None)
        self.assertEqual(len(calls),2);self.assertEqual(review['overall_score'],72)
        document=brand_html(review['brand_review'])
        self.assertIn('Brand &lt;unsafe&gt;',document);self.assertNotIn('href=',document)
        reference['excerpts'][0]['text']='Plum'
        generate_brand_review(report,review,review['sources'],complete,len,lambda *_:None)
        self.assertIn('already match',review['brand_review']['comparisons'][0]['adapt'])

    def test_reference_missing_citation_retries_with_actual_ids_but_rejects_invented_ids(self):
        ref={'job_id':'b'*32,'excerpts':[{'id':'S7','text':'Reference words'}],'outcomes':{}}
        report={'video':{'duration_seconds':5},'brand_context':{'id':'a'*32,'name':'Brand','version':1,'references':[ref],'calibration':brands.calibration({}),'note':'Snapshot'}}
        review={'sources':[{'id':'S2','text':'Current words'}],'estimate':{'score':60,'range':[50,70]}}
        result={'source_ids':['S2'],'similarities':'Product topic','differences':'Different hook','adapt':'Show payoff earlier','caution':'No causal evidence'}
        calls=[]
        def complete(prompt,*_):
            calls.append(prompt)
            if len(calls)==1:return dict(result)
            self.assertIn('reference_source_ids is required: a nonempty list using only reference IDs: S7',prompt)
            return dict(result,reference_source_ids=['S7'])
        generate_brand_review(report,review,review['sources'],complete,len,lambda *_:None)
        self.assertEqual(len(calls),2)
        with self.assertRaisesRegex(ValueError,'reference_source_ids is required'):
            generate_brand_review(report,review,review['sources'],lambda *_:dict(result,reference_source_ids=['S99']),len,lambda *_:None)


class BrandAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.results=Path(self.temp.name)
        self.patches=[patch.object(server,'RESULTS_DIR',self.results),patch.object(server,'_jobs',{}),patch.object(server,'_active_job',None),patch.object(server,'require_memory')]
        for p in self.patches:p.start()
        self.client=TestClient(server.app,base_url='http://127.0.0.1:8765')
        self.brand=self.client.post('/api/brands',json={'name':'Brand A'}).json()
    def tearDown(self):
        self.client.close()
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def test_optional_documents_snapshot_and_private_assets(self):
        url=f'/api/brands/{self.brand["id"]}/documents/guidelines'
        response=self.client.post(url,files={'file':('brief.txt',b'Mention Plum.','text/plain')})
        self.assertEqual(response.status_code,200)
        captured={}
        with patch.object(server._executor,'submit') as submit:
            response=self.client.post('/api/jobs',files={'video':('v.mp4',b'video','video/mp4')},data={'brand_id':self.brand['id']})
            self.assertEqual(response.status_code,202);job=response.json()['id']
        snap=json.loads((self.results/job/'brand_context.json').read_text(encoding='utf-8'))
        self.client.post(url,data={'text':'Changed instruction.'})
        self.assertEqual(snap['documents']['guidelines']['text'],'Mention Plum.')
        self.assertEqual(self.client.get(f'/api/jobs/{job}/files/brand_context.json').status_code,404)
        self.assertEqual(self.client.get('/api/brands')['Content-Type'] if False else len(self.client.get('/api/brands').json()),1)
    def test_reference_requires_brand_and_documents_have_clear_errors(self):
        with patch.object(server._executor,'submit'):
            r=self.client.post('/api/jobs',files={'video':('v.mp4',b'x','video/mp4')},data={'purpose':'reference'})
            self.assertEqual(r.status_code,422)
        url=f'/api/brands/{self.brand["id"]}/documents/guidelines'
        self.assertEqual(self.client.post(url,files={'file':('x.exe',b'x')}).status_code,422)
        self.assertEqual(self.client.post(url,data={'text':'x'*12001}).status_code,422)
    def test_feedback_updates_one_record_and_is_isolated_per_brand(self):
        job_id='c'*32;d=self.results/job_id;d.mkdir()
        report={'review':{'estimate':{'score':50}}}
        (d/'report.json').write_text(json.dumps(report))
        server._jobs[job_id]={'id':job_id,'status':'completed','brand_id':self.brand['id'],'purpose':'candidate'}
        for rating in (60,70):
            r=self.client.post(f'/api/jobs/{job_id}/feedback',json={'team_rating':rating,'views':5000,'notes':'Shorter intro'})
            self.assertEqual(r.status_code,200)
        p=brands.read_brand(self.results,self.brand['id']);self.assertEqual(len(p['feedback']),1);self.assertEqual(p['feedback'][0]['team_rating'],70)
        other=brands.new_brand(self.results,'Brand B');self.assertEqual(brands.calibration(other)['sample_count'],0)
        self.assertEqual(self.client.get(f'/api/jobs/{job_id}/feedback').json()['feedback']['views'],5000)
