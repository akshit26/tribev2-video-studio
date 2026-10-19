"""Run against local Studio; API generation is mocked so no GPU work is started."""
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from tests.test_studio_script_writer import brief, script, assessment
from studio_script_writer import validate_assessment


def main():
    errors=[]
    sid='b'*32
    base=brief()
    hooks=[{'angle':f'Angle {i}','spoken':'A blank page. What comes next?','visual':'Open the notebook.','overlay':'Your next idea','payoff':'Write one idea.',
            'concept':'A forgotten idea stages a resignation.','why_stop':'An unexpected character makes a familiar problem visible.','creative_route':'Comedy / character sketch'} for i in range(5)]
    result={'brief':base,'best':{'round':1,'script':script(),'assessment':validate_assessment(assessment(4),script())},'history':[], 'target_met':True,'stop_reason':'target_reached','selected_hook':hooks[0]}
    result['history']=[result['best']]
    state={'id':sid,'status':'completed','stage':'Ready','progress':100,'brief':base,'hook_options':{'hooks':hooks}}
    saved={}
    requests=[]
    def handle(route):
        request=route.request
        path=urlsplit(request.url).path
        if path=='/api/scripts/engines':
            route.fulfill(json={'default_backend':'nvidia','nvidia_token_configured':True,'token_configured':False,'local_models':[]});return
        if path in {'/api/scripts/library','/api/scripts/experiments'}:
            route.continue_();return
        if path=='/api/scripts':
            if request.method=='POST':
                body=request.post_data_json;requests.append(body)
                if body['mode']=='script':state['result']=result
                if body.get('revision_notes'):
                    import copy
                    changed=copy.deepcopy(result)
                    changed['best']['script']['scenes'][-1]['spoken']='The blank page has rejected my grocery list again.'
                    changed['revision_notes']=body['revision_notes'];changed['parent_script_id']=body['parent_script_id']
                    state.update(status='running',stage='Writing your changes',live_draft={'paragraphs':['A revised ending is arriving.'],'reviewed':False},result=changed,parent_script_id=body['parent_script_id'],revision_notes=body['revision_notes'])
                    saved.pop('draft',None)

                state['brief']=body['brief']
                route.fulfill(json=state,status=202)
            else:route.fulfill(json=[])
        elif path==f'/api/scripts/{sid}':route.fulfill(json=state)
        elif path==f'/api/scripts/{sid}/retry':
            saved['retry']=request.post_data_json
            if saved['retry'].get('writer_backend')=='local':state['brief'].update(writer_backend='local',hf_credits_allowed=False)
            state.update(status='completed',stage='Ready')
            state['hook_options']['review_status']='reviewed'
            state['hook_options']['issues']=[]
            state['hook_options'].pop('warning',None)
            route.fulfill(status=202,json=state)
        elif path==f'/api/scripts/{sid}/draft':
            if request.method=='PUT':saved['draft']=request.post_data_json;route.fulfill(json={'saved':True,'score_status':'Edited draft is unscored.'})
            elif 'draft' in saved:route.fulfill(json=saved['draft'])
            else:route.fulfill(status=404,json={'detail':'No draft'})
        else:route.continue_()
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True,args=['--disable-gpu'])
        page=browser.new_page(viewport={'width':1440,'height':1000})
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.route('**/api/scripts**',handle)
        page.goto('http://127.0.0.1:8765/writer')
        page.locator('#library .card').last.wait_for()
        assert page.locator('#library .card').count()==22
        page.locator('[name=topic]').fill(base['topic'])
        page.locator('[name=facts]').fill(base['facts'])
        page.locator('[name=duration]').select_option(str(base['duration']))
        assert page.locator('[name=writer_backend]').input_value()=='nvidia'
        assert page.locator('#nvidiaSettings').is_visible()
        assert page.locator('#localSettings').is_hidden()
        assert 'configured on server' in page.locator('#nvidiaTokenStatus').inner_text()
        page.locator('[name=writer_backend]').select_option('local')
        assert page.locator('#nvidiaSettings').is_hidden()
        assert not page.locator('#hfCreditsAllowed').is_checked()
        assert page.locator('[name=local_model]').input_value()=='auto'
        assert page.locator('#hostedSettings').is_hidden()
        page.locator('[name=writer_backend]').select_option('huggingface')
        assert page.locator('#hostedSettings').is_visible()
        page.locator('#hooksButton').click()
        assert not requests
        assert 'Hosted generation is disabled' in page.locator('#status').inner_text()
        page.locator('[name=writer_backend]').select_option('local')
        assert page.locator('[name=content_mode]').input_value()=='organic'
        assert page.locator('[name=production_style]').input_value()=='solo_simple'
        assert page.locator('[name=content_format] option[value=rant]').count()==1
        assert page.locator('[name=tone]').count()==0
        assert page.locator('[name=persona] option').count()==24
        page.locator('[name=persona]').select_option('fourth_wall')
        page.locator('[name=content_mode]').select_option('ugc')
        page.locator('[name=content_format]').select_option('storytime')
        page.locator('[name=creator_experience]').fill('First look at the notebook on my desk; not used yet.')
        assert page.locator('[name=creative_freedom]').input_value()=='wild'
        page.locator('[name=creative_notes]').fill('Deadpan comedy; one actor.')
        page.locator('#hooksButton').click()
        page.locator('#hooks .hook').last.wait_for()
        assert page.locator('#hooks .hook').count()==5
        assert 'A blank page. What comes next?' in page.locator('#hooks .hook').first.inner_text()
        assert 'FIRST FRAME' not in page.locator('#hooks').inner_text()
        assert 'ON SCREEN' not in page.locator('#hooks').inner_text()
        assert requests[0]['brief']['creative_notes']=='Deadpan comedy; one actor.'
        assert requests[0]['brief']['content_mode']=='ugc'
        assert requests[0]['brief']['writer_backend']=='local'
        assert requests[0]['brief']['hf_credits_allowed'] is False
        assert requests[0]['brief']['persona']=='fourth_wall'
        assert requests[0]['brief']['production_style']=='solo_simple'
        assert requests[0]['brief']['content_format']=='storytime'
        assert 'not used yet' in requests[0]['brief']['creator_experience']
        page.locator('#hooks button').first.click()
        page.locator('#sceneEditor textarea').first.wait_for()
        assert page.locator('#sceneEditor .scene').count()==3
        assert page.locator('#sceneEditor textarea').count()==3
        assert 'Shot direction' not in page.locator('#sceneEditor').inner_text()
        assert 'On-screen text' not in page.locator('#sceneEditor').inner_text()
        assert '100/100' in page.locator('#score').inner_text()
        assert 'words | Estimated' in page.locator('#scriptTiming').inner_text()
        assert 'Requested 15s' in page.locator('#scriptTiming').inner_text()
        page.context.grant_permissions(['clipboard-read','clipboard-write'],origin='http://127.0.0.1:8765')
        page.locator('#copyScript').click()
        page.wait_for_function("document.getElementById('editStatus').textContent === 'Script copied.'")
        copied=page.evaluate('navigator.clipboard.readText()')
        assert 'SHOT:' not in copied and 'TEXT:' not in copied and 'SAY:' not in copied
        assert copied.replace('\r\n','\n')==script()['title']+'\n\n'+'\n\n'.join(row['spoken'] for row in script()['scenes']),repr(copied)
        page.locator('#sceneEditor textarea').first.fill('A different opening.')
        assert page.locator('#score').is_hidden()
        page.locator('#saveDraft').click()
        page.wait_for_function("document.getElementById('editStatus').textContent.includes('unscored')")
        assert saved['draft']['scenes'][0]['spoken']=='A different opening.'
        with page.expect_request(lambda r:r.method=='POST' and urlsplit(r.url).path=='/api/scripts'):
            page.locator('#sceneEditor button').first.click()
        page.wait_for_function("document.getElementById('status').textContent === 'Ready'")
        assert requests[-1]['scene_index']==0
        assert requests[-1]['previous_script']['scenes'][0]['spoken']=='A different opening.'
        page.locator('#revisionNotes').fill('Make only the ending funnier. Keep my opening.')
        page.locator('#revisionScope').select_option('2')
        page.locator('#applyChanges').click()
        page.locator('#liveScriptSection:not([hidden])').wait_for()
        assert 'A revised ending is arriving.' in page.locator('#liveScript').inner_text()
        assert page.locator('#applyChanges').is_disabled()
        assert page.locator('#sceneEditor textarea').first.input_value()=='A different opening.'
        assert requests[-1]['revision_notes']=='Make only the ending funnier. Keep my opening.'
        assert requests[-1]['scene_index']==2
        assert requests[-1]['parent_script_id']==sid
        assert requests[-1]['previous_script']['scenes'][0]['spoken']=='A different opening.'
        state.update(status='completed',stage='Ready')
        page.wait_for_function("document.getElementById('status').textContent === 'Ready'")
        assert page.locator('#liveScriptSection').is_hidden()
        assert page.locator('#sceneEditor textarea').last.input_value()=='The blank page has rejected my grocery list again.'
        assert page.locator('#openOriginal').is_visible()
        assert 'Make only the ending funnier' in page.locator('#revisionStatus').inner_text()
        assert page.locator('#revisionNotes').input_value()==''
        state.update(status='failed',stage='Review interrupted',error='HF credits exhausted')
        state['brief']=dict(state['brief'],writer_backend='huggingface',hf_credits_allowed=True)
        state['hook_options'].update(review_status='needs_review',issues=[{'index':2,'reason':'Check the unsupported result.'}],warning='Hooks saved; review needed.')
        page.reload()
        page.locator('#retryJob:not([hidden])').wait_for()
        assert page.locator('#retryJob').inner_text()=='Retry locally (free)'
        assert page.locator('[name=writer_backend]').input_value()=='local'
        assert not page.locator('#hfCreditsAllowed').is_checked()
        assert page.locator('#hooks .hook').count()==5
        assert 'Check the unsupported result.' in page.locator('#hooks').inner_text()
        with page.expect_request(lambda r:r.method=='POST' and r.url.endswith('/retry')):
            page.locator('#retryJob').click()
        page.locator('#retryJob[hidden]').wait_for(state='attached')
        assert saved['retry']['writer_backend']=='local'
        assert saved['retry']['local_model']=='auto'
        output=ROOT/'results/writer-browser';output.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(output/'desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(output/'mobile.png'),full_page=True)
        browser.close()
    assert not errors,errors
    print(json.dumps({'browser_errors':errors,'mobile_overflow':False,'hook_selection':True,'manual_edits':True,'scene_regeneration':True}))


if __name__=='__main__':main()
