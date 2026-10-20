"""Single-block writer browser regression; all generation calls are mocked."""
import copy
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
BASE_URL=os.environ.get('WRITER_TEST_BASE_URL','http://127.0.0.1:8765')
from playwright.sync_api import sync_playwright
from studio_script_writer import brief_values


def main():
    sid='b'*32;errors=[];requests=[];saved={}
    text='My notebook has one job. [Hold notebook] Keep the ideas I forget between breakfast and finding my keys. I do not need another app asking me to organise my entire personality. I need a blank page where a shopping list can sit next to a ridiculous business idea without either one sending me a notification. That is the whole system. Write it down and get on with the day.'
    brief=brief_values({'topic':'Notebook','facts':'A notebook with 80 blank pages.','duration':30,'writer_backend':'team'})
    result={'reference_ids':['creator-emotion','creator-brand-bridge'],'final_script':text,'brief':brief,'best':{'script':{'final_script':text},'assessment':{'score':None,'criteria':[],'blockers':[]}},'history':[],'target_met':False,'stop_reason':'single_block_complete','selected_hook':None}
    state={'id':sid,'status':'completed','stage':'Script ready','brief':brief,'result':result}
    def handle(route):
        req=route.request;path=urlsplit(req.url).path
        if path=='/api/scripts':
            if req.method=='POST':
                body=req.post_data_json;requests.append(body);state['brief']=body['brief']
                if body.get('revision_notes'):
                    state['result']=copy.deepcopy(result)
                    revised=body['previous_script']['final_script']+' The ending is now funnier.'
                    state['result']['best']['script']={'final_script':revised};state['result']['final_script']=revised
                    state['result']['revision_notes']=body['revision_notes'];state['parent_script_id']=sid
                    saved.pop('draft',None)
                route.fulfill(status=202,json=state)
            else:route.fulfill(json=[])
        elif path==f'/api/scripts/{sid}':route.fulfill(json=state)
        elif path==f'/api/scripts/{sid}/draft':
            if req.method=='PUT':saved['draft']=req.post_data_json;route.fulfill(json={'saved':True,'score_status':'Edited draft is unscored.'})
            elif 'draft' in saved:route.fulfill(json=saved['draft'])
            else:route.fulfill(status=404,json={'detail':'No manual draft'})
        elif path==f'/api/scripts/{sid}/export':route.fulfill(content_type='text/plain',body=saved.get('draft',state['result']['best']['script'])['final_script'])
        else:route.continue_()
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True,args=['--disable-gpu'])
        page=browser.new_page(viewport={'width':1440,'height':1000})
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.route('**/api/scripts**',handle)
        page.goto(BASE_URL+'/writer');page.locator('#library .card').last.wait_for()
        page.locator('[name=topic]').fill('Notebook');page.locator('[name=facts]').fill(brief['facts'])
        page.locator('[name=writer_backend]').select_option('team')
        page.locator('#hooksButton').click()
        page.wait_for_function("document.getElementById('status').textContent==='Script ready'")
        assert requests[-1]['mode']=='script';assert requests[-1]['brief']['duration']==30
        assert page.locator('#sceneEditor textarea').count()==1
        assert page.locator('#sceneEditor .scene').count()==0
        assert page.locator('#finalScript').input_value()==text
        assert page.locator('#appliedReferences p').count()==2
        assert page.locator('#tribeStatus, #rateTribe').count()==0
        assert 'Creator' in page.title()
        assert page.locator('#revisionScope option').count()==1
        assert page.locator('#finalScript').evaluate('(e)=>e.scrollHeight<=e.clientHeight+2')
        page.context.grant_permissions(['clipboard-read','clipboard-write'],origin=BASE_URL)
        page.locator('#copyScript').click();page.wait_for_function("document.getElementById('editStatus').textContent==='Script copied.'")
        assert page.evaluate('navigator.clipboard.readText()')==text
        edited=text+' Keep this final thought.'
        page.locator('#finalScript').fill(edited);page.locator('#saveDraft').click()
        page.wait_for_function("document.getElementById('editStatus').textContent.includes('unscored')")
        assert saved['draft']=={'final_script':edited}
        assert page.evaluate('(url)=>fetch(url).then(r=>r.text())',f'/api/scripts/{sid}/export')==edited
        page.locator('#revisionNotes').fill('Make the ending funnier.')
        page.locator('#applyChanges').click()
        page.wait_for_function("document.getElementById('finalScript').value.includes('ending is now funnier')")
        assert requests[-1]['previous_script']=={'final_script':edited}
        assert requests[-1]['scene_index'] is None
        assert requests[-1]['revision_notes']=='Make the ending funnier.'
        assert page.locator('#openOriginal').is_visible()
        # Archived scene payloads open in the same single text area.
        state['result']['best']['script']={'title':'Archive','scenes':[{'spoken':'First saved paragraph.'},{'spoken':'Second saved paragraph.'}]}
        page.reload();page.wait_for_function("document.getElementById('finalScript').value==='First saved paragraph. Second saved paragraph.'")
        page.locator('#saveDraft').click();page.wait_for_function("document.getElementById('editStatus').textContent.includes('unscored')")
        assert saved['draft']=={'final_script':'First saved paragraph. Second saved paragraph.'}
        output=ROOT/'results/writer-browser';output.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(output/'desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert page.locator('#sceneEditor textarea').count()==1
        page.screenshot(path=str(output/'mobile.png'),full_page=True)
        browser.close()
    assert not errors,errors
    print(json.dumps({'browser_errors':errors,'mobile_overflow':False,'single_textarea':True,'save_copy_export':True,'revisions':True,'legacy_read':True}))

if __name__=='__main__':main()
