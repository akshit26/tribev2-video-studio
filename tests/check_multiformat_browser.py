"""Gate approval/rejection and duration controls; API responses are controlled."""
import copy,json
from playwright.sync_api import sync_playwright
BASE='http://127.0.0.1:8765';SID='c'*32
text='Drain hair looks like a tiny swamp creature. A silicone catcher sits over the drain and catches loose hair. Lift it, remove the hair, rinse it, and reuse it. Buy a hair catcher for your shower.'
brief={'topic':'Hair catcher','facts':'Reusable silicone catcher','content_duration':'long','duration':600,'writer_backend':'fast','language':'English'}
assessment={'score':87,'critique':'Specific hook and grounded purchase CTA.','criteria':[],'blockers':[]}
result={'approved':True,'evaluation':{'overall_score':87,'critique':assessment['critique']},'best':{'script':{'final_script':text},'assessment':assessment},'history':[],'target_met':True,'stop_reason':'gate_approved'}
state={'id':SID,'status':'completed','stage':'Script approved','brief':brief,'result':result}
saved={};revisions=[]
def handle(route):
    if route.request.url.endswith('/draft'):
        if route.request.method=='PUT':
            saved['draft']=route.request.post_data_json
            route.fulfill(json={'saved':True,'score_status':'Edited draft is unscored.'})
        elif 'draft' in saved:route.fulfill(json=saved['draft'])
        else:route.fulfill(status=404,json={'detail':'No edited draft'})
        return
    route.fulfill(json=state)
def collection(route):
    if route.request.method=='POST':
        revisions.append(route.request.post_data_json);route.fulfill(status=202,json=state)
    else:route.fulfill(json=[])
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True,args=['--disable-gpu'])
    page=browser.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.route('**/api/scripts/'+SID+'**',handle)
    page.route('**/api/scripts',collection)
    page.goto(BASE+'/writer?script='+SID)
    page.wait_for_function("document.getElementById('score').textContent.includes('87/100')")
    assert page.locator('#contentDuration').input_value()=='long'
    assert page.locator('#finalScript').is_visible()
    assert assessment['critique'] in page.locator('#score').inner_text()
    for kind,seconds in [('short',30),('mid',60),('long',600)]:
        page.locator('#contentDuration').select_option(kind)
        payload=page.evaluate('getBrief()');assert payload['content_duration']==kind and payload['duration']==seconds
    state['result']=copy.deepcopy(result);state['result'].update(approved=False,target_met=False,quality_status='needs_review',stop_reason='gate_rejected')
    state['result']['evaluation']['overall_score']=72;state['result']['best']['assessment']['score']=72
    page.reload();page.wait_for_function("document.getElementById('score').textContent.includes('72/100')")
    assert page.locator('#finalScript').is_visible()
    assert not page.locator('#textExport').is_visible()
    assert page.locator('#finalScript').input_value()==text
    assert 'Unapproved' in page.locator('#scriptTitle').inner_text()
    assert page.locator('#copyScript').is_disabled()
    assert page.locator('#saveDraft').is_enabled()
    assert page.locator('#applyChanges').is_enabled()
    edited=text+' Keep the useful details.'
    page.locator('#finalScript').fill(edited)
    page.locator('#saveDraft').click()
    page.wait_for_function("document.getElementById('editStatus').textContent.includes('unscored')")
    page.reload();page.wait_for_function("document.getElementById('editStatus').textContent.includes('Saved manual edits')")
    assert page.locator('#finalScript').input_value()==edited
    assert 'Unapproved' in page.locator('#scriptTitle').inner_text()
    assert 'original score does not apply' in page.locator('#score').inner_text()
    assert not page.locator('#textExport').is_visible()
    page.locator('#revisionNotes').fill('Make the opening sharper and fix the flagged issues.')
    page.locator('#applyChanges').click()
    page.wait_for_function("document.getElementById('revisionNotes').value===''")
    assert len(revisions)==1
    assert revisions[0]['previous_script']=={'final_script':edited}
    assert revisions[0]['parent_script_id']==SID
    assert revisions[0]['revision_notes']=='Make the opening sharper and fix the flagged issues.'
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert not errors,errors
    print(json.dumps({'approval_score_and_critique':True,'rejected_script_recoverable':True,'rejected_export_disabled':True,'rejected_manual_edits_restored':True,'durations_restored_and_submitted':True,'mobile_overflow':False,'browser_errors':errors}))
    browser.close()
