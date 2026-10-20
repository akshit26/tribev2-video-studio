"""Gemma dashboard browser regression with mocked inference outcomes."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
BASE='http://127.0.0.1:8765';JOB='9890e0cb55b743d48172e24763ad3921'
errors=[];state={'status':'not_started','configured':True};submitted=[]
def handle(route):
    if route.request.method=='POST':
        submitted.append(1)
        if len(submitted)==1:state.update(status='running',elapsed_seconds=2)
        else:
            route.fulfill(status=503,json={'detail':'NVIDIA unavailable'});return
    route.fulfill(status=202 if route.request.method=='POST' else 200,json=state)
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True,args=['--disable-gpu'])
    page=browser.new_page(viewport={'width':1440,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
    page.route('**/api/jobs/*/gemma-review*',handle)
    page.goto(BASE+'/?job='+JOB);page.locator('#gemmaAnalyze').wait_for()
    page.wait_for_function("document.getElementById('gemmaStatus').textContent.startsWith('Ready')")
    page.locator('#gemmaAnalyze').click();page.wait_for_function("document.getElementById('gemmaAnalyze').disabled")
    state.update(status='completed',model='nvidia/nemotron-3.5-super-vl-120b-a12b',result={'hook_score':85,'pacing_score':80,'overall_probability':82,'timestamped_revision_advice':'00:02-00:04: Trim the repeated opening.'},dashboard={'status':'Approved','policy':'Editing policy only; no viral guarantee.'})
    page.wait_for_function("document.getElementById('gemmaScores').textContent.includes('85/100')")
    assert 'Approved' in page.locator('#gemmaScores').inner_text()
    assert 'Nemotron 3.5 Super VL' in page.locator('#gemmaScores').inner_text()
    assert page.locator('#videoReviewModel').input_value()=='nvidia/nemotron-3.5-super-vl-120b-a12b'
    page.locator('#gemmaAnalyze').click();page.wait_for_function("document.getElementById('gemmaStatus').textContent.includes('NVIDIA unavailable')")
    assert page.locator('#gemmaScores').inner_text()==''
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    out=Path('results/gemma-browser');out.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(out/'mobile.png'),full_page=True)
    browser.close()
assert not errors,errors
print(json.dumps({'browser_errors':errors,'background_polling':True,'scoring_dashboard':True,'failure_has_no_verdict':True,'mobile_overflow':False}))
