"""Isolated browser workflow test; analysis is a fixture, GPU is tested separately."""
import copy
import json
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import uvicorn
from playwright.sync_api import sync_playwright
from pypdf import PdfReader
import studio_server as server
from studio_brand_review import apply_brand_score
from studio_brief import build_brief
from studio_pipeline import _write_json
from studio_review_output import render_detailed_pdf


if __name__=='__main__':
    fixture_dir=ROOT/'results/studio/e7b8c788b3a8497fbd161c497eaca1fa'
    fixture=json.loads((fixture_dir/'report.json').read_text(encoding='utf-8'))
    artifacts=ROOT/'results/brand_ui_validation';artifacts.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        server.RESULTS_DIR=Path(tmp);server._jobs={};server._active_job=None;server.require_memory=lambda:None
        def analyze(video,output,budget_mb,vision,progress):
            report=copy.deepcopy(fixture);report['video']['name']='Browser test fixture'
            context_file=output/'brand_context.json'
            if context_file.exists():
                brand=json.loads(context_file.read_text(encoding='utf-8'));report['brand_context']=brand
                check={'document':'guidelines','document_name':'guidelines.txt','section':1,'requirement':'Mention the brand','quote':'Mention Willow.','status':'unknown','reason':'Fixture check','change':'Verify the source frame.','source_ids':[]}
                comparisons=[{'reference':r,'similarities':'Product story','differences':'Different opening','adapt':'Use a clearer CTA','caution':'Results are not causal','source_ids':['S1'],'reference_source_ids':[r['excerpts'][0]['id']]} for r in brand['references']]
                report['review']['brand_review']={'brand_id':brand['id'],'brand_name':brand['name'],'version':brand['version'],'checks':[check],'comparisons':comparisons,'calibration':brand['calibration'],'snapshot_note':brand['note']}
                apply_brand_score(report['review'])
            clips=report['brief']['clips'];report['brief']=build_brief(report);report['brief']['clips']=clips
            shutil.copytree(fixture_dir/'screenshots',output/'screenshots')
            _write_json(output/'report.json',report)
            return report
        server.run_analysis=analyze
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        application=uvicorn.Server(uvicorn.Config(server.app,host='127.0.0.1',port=port,log_level='error'))
        thread=threading.Thread(target=application.run,daemon=True);thread.start()
        try:
            for _ in range(100):
                if application.started:break
                time.sleep(.05)
            errors=[]
            with sync_playwright() as p:
                browser=p.chromium.launch(channel='msedge',headless=True,args=['--disable-gpu'])
                page=browser.new_page(viewport={'width':1440,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{port}');page.get_by_label('New brand name',exact=True).fill('Brand workflow test');page.get_by_role('button',name='Create brand',exact=True).click()
                page.wait_for_function("document.getElementById('brandSelect').value.length===32")
                brand_id=page.locator('#brandSelect').input_value()
                page.get_by_text('Optional brand guidelines and product brief',exact=True).click()
                page.get_by_label('Video guidelines file',exact=True).set_input_files({'name':'guidelines.txt','mimeType':'text/plain','buffer':b'Mention Willow.'})
                page.get_by_role('button',name='Save brand documents',exact=True).click();page.get_by_text('Brand documents saved. New uploads will use this version.',exact=True).wait_for()
                page.locator('.brand-panel').first.screenshot(path=str(artifacts/'brand_upload.png'))
                page.locator('#uploadPurpose').select_option('reference');page.get_by_label('Reference Team rating / 100',exact=True).fill('90');page.get_by_label('Reference Views',exact=True).fill('50000')
                page.locator('#videoInput').set_input_files({'name':'reference.mp4','mimeType':'video/mp4','buffer':b'fixture'})
                page.locator('#analyzeButton').click();page.locator('#report').wait_for(state='visible');page.wait_for_function("document.getElementById('analyzeButton').disabled===false")
                page.wait_for_function("document.querySelector('.brand-reference')!==null")
                page.get_by_text('Saved successful references (up to 5)',exact=True).click()
                page.get_by_text('Update reference results',exact=True).click()
                page.get_by_label('Saved reference Views',exact=True).fill('60000')
                page.get_by_role('button',name='Save reference results',exact=True).click()
                page.locator('.brand-reference').get_by_text('Views: 60000',exact=False).wait_for()
                page.locator('#uploadPurpose').select_option('candidate');page.locator('#videoInput').set_input_files({'name':'candidate.mp4','mimeType':'video/mp4','buffer':b'candidate fixture'})
                page.locator('#analyzeButton').click();page.get_by_role('heading',name='Brand fit · Brand workflow test',exact=True).wait_for()
                page.get_by_label('Actual Team rating / 100',exact=True).fill('65');page.get_by_label('Actual Views',exact=True).fill('12345');page.get_by_label('Actual Average viewed %',exact=True).fill('61')
                page.get_by_role('button',name='Save team feedback and results',exact=True).click();page.get_by_text('Saved. 1 rated candidates;',exact=False).wait_for()
                assert page.locator('#scoreLabel').inner_text()=='Brand-aligned overall'
                page.locator('#detailedReview').scroll_into_view_if_needed();page.screenshot(path=str(artifacts/'desktop.png'))
                page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');page.screenshot(path=str(artifacts/'mobile.png'))
                profile=json.loads((server.RESULTS_DIR/'_brands'/brand_id/'profile.json').read_text(encoding='utf-8'));assert len(profile['references'])==1 and profile['feedback'][0]['views']==12345
                assert profile['references'][0]['outcomes']['views']==60000
                candidate=next(j for j in server._jobs.values() if j.get('purpose')=='candidate')
                report=candidate['report'];job_dir=server.RESULTS_DIR/candidate['id']
                with ThreadPoolExecutor(max_workers=1) as pool:
                    pool.submit(render_detailed_pdf,report,job_dir).result()
                reader=PdfReader(job_dir/'report.pdf')
                assert sum(len(p.images) for p in reader.pages)>0
                assert not any(a.get_object().get('/Subtype')=='/Link' for page_ in reader.pages for a in page_.get('/Annots',[]))
                assert 'Brand fit' in ''.join(p.extract_text() for p in reader.pages)
                shutil.copy2(job_dir/'report.pdf',artifacts/'fixture_report.pdf')
                browser.close();assert not errors,errors
                print(json.dumps({'brand_workflow':'passed','feedback_saved':True,'reference_count':1,'mobile_overflow':False,'browser_errors':errors,'pdf_pages':len(reader.pages)}))
        finally:
            application.should_exit=True;thread.join(timeout=10)
