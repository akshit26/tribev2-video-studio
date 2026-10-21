"""Three selectable hooks, exact body preservation and saved-edit restoration."""
import copy,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from actor_critic_fixtures import BODY,HOOKS,SCRIPT

SID='d'*32
hooks=[dict(h,label=label,validated=True,issues=[]) for h,label in zip(HOOKS,('Problem-focused','Curiosity-focused','Contrarian / shock'))]
result=dict(pipeline_version='actor-critic-v1',pipeline=dict(kind='actor_critic',draft_model='Test Nemotron'),
    approved=True,evaluation=None,mechanical_critique={},ab_hooks=hooks,selected_hook_kind='problem',
    best=dict(script={'final_script':SCRIPT},assessment=dict(score=None,critique='Edited once.',criteria=[],blockers=[])),
    target_met=True,stop_reason='single_pass_complete',history=[],reference_ids=[])
state=dict(id=SID,status='completed',stage='Three hooks ready',brief=dict(topic='Shower catcher',facts='Reusable silicone catcher',
    language='English',content_duration='short',duration=30,writer_backend='fast'),result=result)
saved={}
def handle(route):
    if route.request.url.endswith('/draft'):
        if route.request.method=='PUT':
            saved.update(route.request.post_data_json)
            route.fulfill(json=dict(saved=True,score_status='Edited draft is unscored.'))
        elif saved:route.fulfill(json=saved)
        else:route.fulfill(status=404,json=dict(detail='No edits'))
    else:route.fulfill(json=state)

with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True,args=['--disable-gpu'])
    page=browser.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.route('**/api/scripts/'+SID+'**',handle)
    page.route('**/api/scripts',lambda route:route.fulfill(json=[]))
    page.goto('http://127.0.0.1:8765/writer?script='+SID)
    page.wait_for_function("document.querySelectorAll('#abHooks button').length===3")
    assert page.locator('#finalScript').input_value()==SCRIPT
    assert 'Edited script ready' in page.locator('#score').inner_text()
    assert '/100' not in page.locator('#score').inner_text()
    original_body=SCRIPT.split('\n',1)[1]
    for hook in hooks:
        button=page.locator('#abHooks button[data-hook-kind="'+hook['kind']+'"]');button.click()
        content=page.locator('#finalScript').input_value()
        assert content.split('\n',1)[1]==original_body
        assert content.split('\n',1)[0].endswith(hook['text'])
        assert content.startswith('[B-ROLL:')
        assert button.get_attribute('aria-pressed')=='true'
    # Preserve manual body edits while testing another opening.
    edited=page.locator('#finalScript').input_value().replace('next shower','next morning shower')
    page.locator('#finalScript').fill(edited)
    page.locator('#abHooks button[data-hook-kind="curiosity"]').click()
    changed=page.locator('#finalScript').input_value()
    assert changed.split('\n',1)[1]==edited.split('\n',1)[1]
    page.locator('#saveDraft').click()
    page.wait_for_function("document.getElementById('editStatus').textContent.includes('unscored')")
    assert saved['final_script']==changed
    page.reload()
    page.wait_for_function("document.getElementById('editStatus').textContent.includes('Saved manual edits')")
    assert page.locator('#finalScript').input_value()==changed
    assert page.locator('#abHooks button[data-hook-kind="curiosity"]').get_attribute('aria-pressed')=='true'
    page.set_viewport_size(dict(width=390,height=844))
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert page.locator('#finalScript').evaluate('(e)=>e.clientHeight>=e.scrollHeight-3')
    assert not errors,errors
    print(json.dumps(dict(three_hooks=True,body_preserved=True,opening_visual_preserved=True,
                          manual_body_preserved=True,saved_variant_restored=True,auto_expanding=True,mobile_overflow=False,browser_errors=errors)))
    browser.close()
