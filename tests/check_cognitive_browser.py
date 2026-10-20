"""UI evidence provenance, audit download and single-textarea regression."""
import json
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8765'
SID = 'd' * 32
COGNITIVE = dict(attention_retention_score=62, emotional_arousal_state='Low-arousal boredom (hypothesis)',
                 cognitive_load_warning=True, psychological_critique='Resolve the opening promise earlier.')
SCRIPT = 'A specific creator observation. A grounded product moment. One clear next action.'
RESULT = dict(approved=True, target_met=True, stop_reason='gate_approved', history=[],
              best=dict(script={'final_script': SCRIPT}, assessment=dict(score=85, blockers=[])),
              evaluation=dict(overall_score=85, critique='Specific and grounded.'),
              source_video_cognitive=COGNITIVE, source_video_pacing={'wpm': 128.5},
              source_video_job_id=SID, audit={'triggered': True, 'pdf_file': 'audit.pdf'})
STATE = dict(id=SID, status='completed', stage='Script ready', brief=dict(topic='Notebook', facts='Blank pages',
             content_duration='short', duration=30, writer_backend='team', language='English'), result=RESULT)

with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True, args=['--disable-gpu'])
    page = browser.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    def route(request):
        if request.request.url.endswith('/draft'):
            request.fulfill(status=404, json={'detail': 'No edited draft'})
        else:
            request.fulfill(json=STATE)
    page.route('**/api/scripts/' + SID + '*', route)
    page.goto(BASE + '/writer?script=' + SID)
    page.locator('#cognitiveMetrics').wait_for(state='visible')
    assert '128.5' in page.locator('#cognitiveMetrics').inner_text()
    assert 'source video, not the newly written script' in page.locator('#cognitiveMetrics').inner_text()
    assert page.locator('#auditDownload').get_attribute('href').endswith('/files/audit.pdf')
    assert page.locator('#sceneEditor textarea').count() == 1
    page.locator('#finalScript').fill(SCRIPT + ' Edit.')
    assert not page.locator('#cognitiveMetrics').is_visible()
    page.goto(BASE)
    report = dict(backend='nvidia', model='test-vision', dashboard=dict(status='Rejected', policy='Editorial estimate'),
                  result=dict(hook_score=60, pacing_score=60, overall_probability=60, timestamped_revision_advice='00:01: Tighten the opening.'),
                  cognitive=COGNITIVE, pacing={'wpm': 128.5, 'dead_air': [{'start': 1., 'end': 2.5}]},
                  audit=dict(triggered=True, pdf_file='audit.pdf', final_script=SCRIPT, rewrite_approved=False))
    page.evaluate('([report,id])=>{document.getElementById("report").hidden=false;window.renderCreative(report,id)}', [report, SID])
    assert '128.5' in page.locator('#remoteReview').inner_text()
    assert page.locator('#remoteReview textarea').get_attribute('readonly') is not None
    assert page.locator('#remoteReview a[href$="/files/audit.pdf"]').count() == 1
    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert not errors, errors
    browser.close()
print(json.dumps({'source_provenance': True, 'audit_download': True, 'single_textarea': True,
                  'unapproved_rewrite_labeled': True, 'browser_errors': errors}))
