"use strict";
const $ = id => document.getElementById(id);
const make = (tag, content, cls) => { const e=document.createElement(tag); if(content!==undefined)e.textContent=String(content); if(cls)e.className=cls; return e; };
let personaCatalog=[],engineConfig=null;
let active=null, current=null, library=null, editorBase=null, dirty=false, busy=false, pollTimer=null, shownHooks='', shownLive='', pollFailures=0;
async function api(url, options={}) {
  const response=await fetch(url, {...options, headers:{"Content-Type":"application/json",...(options.headers||{})}});
  const data=await response.json();
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail||data));
  return data;
}
function status(message,error=false){$('status').textContent=message;$('status').classList.toggle('error',error);}
function lock(value){busy=value;for(const b of document.querySelectorAll('#briefForm button,#hooks button,#sceneEditor button,#saveDraft,#reviseDraft,#retryJob,#applyChanges,#openOriginal,#revisionNotes,#revisionScope,#sceneEditor textarea'))b.disabled=value;}
function getBrief(){const b=Object.fromEntries(new FormData($('briefForm')));b.duration=Number(b.duration);b.hf_credits_allowed=$('hfCreditsAllowed').checked;return b;}
function setBrief(brief){for(const [key,value] of Object.entries({content_mode:'organic',content_format:'auto',production_style:'solo_simple',persona:'auto',creator_experience:'',writer_backend:'local',local_model:'auto',hf_model:'deepseek-ai/DeepSeek-V4.1-Flash',hf_credits_allowed:false,...brief})){const field=$('briefForm').elements.namedItem(key);if(field){if(field.type==='checkbox')field.checked=value===true;else field.value=value;}}updateContentMode();updatePersona();updateEngine();}
function updateContentMode(){
  const hints={organic:'Story, humor or useful discovery first. Product presence stays natural; leave CTA blank for a story ending.',ugc:'Creator voice, phone footage and everyday context. Add real experience above; otherwise the writer uses a first look, observation or staged scene.',paid_ad:'Product-led communication with supported benefits and your chosen CTA.'};
  $('contentModeHint').textContent=hints[$('contentMode').value];
}
$('contentMode').addEventListener('change',updateContentMode);
function updateEngine(){const hosted=$('writerBackend').value==='huggingface';$('hostedSettings').hidden=!hosted;$('localSettings').hidden=$('writerBackend').value!=='local';$('nvidiaSettings').hidden=$('writerBackend').value!=='nvidia';$('nvidiaTokenStatus').textContent=engineConfig?.nvidia_token_configured?'NVIDIA key configured on server.':'Set NVIDIA_API_KEY in the server environment or .env.';const installed=(engineConfig?.local_models||[]).filter(m=>m.installed);$('localModelStatus').textContent=installed.length?'Installed: '+installed.map(m=>m.name).join(', ')+'. Runs on this PC without HF inference credits.':'Local model status unavailable.';$('hfTokenStatus').textContent=engineConfig?.token_configured?'HF token detected on server. Inference Providers permission is required.':'Set HF_TOKEN in the server environment or .env, or use hf auth login. No token is stored in this browser.';}
$('writerBackend').addEventListener('change',updateEngine);
function updatePersona(){const p=personaCatalog.find(p=>p.id===$('personaSelect').value);if($('personaHint'))$('personaHint').textContent=p?p.direction+' Best for: '+p.best_for:'';}
$('personaSelect').addEventListener('change',updatePersona);
async function start(mode,hook=null,previous=null,sceneIndex=null,revisionNotes=""){
  if(!$('briefForm').reportValidity())return;
  if($('writerBackend').value==='huggingface'&&!$('hfCreditsAllowed').checked){status('Hosted generation is disabled. Use Local for free writing, or explicitly allow HF credit usage.',true);return;}
  if(dirty&&!window.confirm('Starting another generation will replace the editor. Save or copy your edits first. Continue?'))return;
  lock(true);
  try{
    clearTimeout(pollTimer);
    const job=await api('/api/scripts',{method:'POST',body:JSON.stringify({mode,brief:getBrief(),selected_hook:hook,use_experiments:$('useExperiments').checked,previous_script:previous,scene_index:sceneIndex,revision_notes:revisionNotes,parent_script_id:previous?active:null})});
    active=job.id;localStorage.setItem('tribe-writer-active',active);dirty=false;shownHooks='';shownLive='';$('retryJob').hidden=true;$('liveScriptSection').hidden=true;
    $('resultSection').hidden=!previous;if(previous){$('score').hidden=true;$('revisionStatus').textContent='Applying your changes. The original remains visible while the new draft generates.';}else $('hooks').replaceChildren(make('p','Working on your next draft…','muted'));
    status('Queued for the writer…');poll();return true;
  }catch(e){status(e.message,true);lock(false);return false;}
}
async function poll(){
  clearTimeout(pollTimer);
  const requestedId=active;
  try{
    const job=await api('/api/scripts/'+requestedId);
    if(requestedId!==active)return;
    pollFailures=0;
    const elapsed=job.elapsed_seconds?` · ${Math.round(job.elapsed_seconds)}s elapsed`:'';
    status(job.stage+elapsed+(job.error?' · '+job.error:''),job.status==='failed');
    if(job.status==='failed'&&['huggingface','nvidia'].includes(job.brief?.writer_backend)){$('writerBackend').value='local';$('hfCreditsAllowed').checked=false;updateEngine();}
    $('retryJob').textContent=['huggingface','nvidia'].includes(job.brief?.writer_backend)?'Retry locally (free)':'Retry saved job';
    $('retryJob').dataset.localRetry=['huggingface','nvidia'].includes(job.brief?.writer_backend)?'true':'false';
    $('retryJob').hidden=job.status!=='failed'&&!(job.status==='completed'&&['needs_review','unavailable'].includes(job.hook_options?.review_status));
    if(job.hook_options&&shownHooks!==JSON.stringify(job.hook_options)){
      renderHooks(job.hook_options.hooks,job.hook_options);shownHooks=JSON.stringify(job.hook_options);
    }
    $('progress').hidden=!['queued','running'].includes(job.status);$('progress').value=job.progress||0;
    if(['queued','running'].includes(job.status)){
      if(job.live_draft?.paragraphs?.length){const key=JSON.stringify(job.live_draft.paragraphs);if(key!==shownLive){$('liveScript').replaceChildren(...job.live_draft.paragraphs.map(p=>make('p',p)));shownLive=key;}$('liveScriptSection').hidden=false;}
      lock(true);pollTimer=setTimeout(poll,1000);return;
    }
    $('liveScriptSection').hidden=true;

    current=job;lock(false);dirty=false;
    if(!job.hook_options&&!job.result)$('hooks').replaceChildren(make('p','No hooks are ready yet. Retry this saved job or start from the brief.','muted'));
    if(job.result){renderResult(job.result);try{const draft=await api('/api/scripts/'+active+'/draft');renderScenes(draft);$('score').hidden=true;$('editStatus').textContent='Saved manual edits loaded. This edited draft is unscored.';}catch(e){/* No manually edited draft is normal. */}}
    await loadSaved().catch(e=>status('Work is saved, but the saved-work list could not refresh. '+e.message,true));
  }catch(e){
    if(requestedId!==active)return;
    status('Connection interrupted. Reconnecting to your saved job… '+e.message,true);
    if(++pollFailures<=3)pollTimer=setTimeout(poll,2500);else{lock(false);status('Connection unavailable. Reload to reconnect to your saved job.',true);}
  }
}
function renderHooks(hooks,review={}){
  $('hooks').replaceChildren();
  if(review.review_status==='pending')$('hooks').append(make('p','Draft hooks saved. Automated review is in progress.','muted small'));
  if(review.warning)$('hooks').append(make('p',review.warning,'status'));
  hooks.forEach((hook,i)=>{
    const card=make('article',undefined,'hook');
    card.append(make('span',String(i+1).padStart(2,'0')+' / '+(hook.creative_route||hook.angle),'kicker'),make('h3',hook.angle),make('strong',hook.spoken));
    if(hook.concept&&hook.concept!==hook.angle)card.append(make('p',hook.concept,'muted'));
    for(const issue of review.issues||[])if(issue.index===i+1)card.append(make('p','REVIEW NOTE · '+issue.reason,'status'));
    const b=make('button','Build this script ↗');b.onclick=()=>start('script',hook);card.append(b);$('hooks').append(card);
  });
}
function updateScriptTiming(script){
  const brief=current?.brief||getBrief();
  const words=script.scenes.reduce((n,row)=>n+row.spoken.trim().split(/\s+/).filter(Boolean).length,0);
  const english=['english','en'].includes((brief.language||'English').toLowerCase());
  const seconds=Number(brief.duration);
  $('scriptTiming').textContent=english?`${words} words | Estimated ${Math.round(words*60/160)}-${Math.round(words*60/120)} seconds at 120-160 words/minute | Requested ${seconds}s. ${words<seconds*2?'Too short: develop the story. ':''}Read aloud to confirm.`:`${words} words | Requested ${seconds}s. Read aloud in the selected language to check timing.`;
}
function renderScenes(script){
  editorBase=structuredClone(script);
  $('scriptTitle').textContent=script.title;$('sceneEditor').replaceChildren();
  updateScriptTiming(script);const scope=$('revisionScope').value;$('revisionScope').replaceChildren(new Option('Whole script',''));script.scenes.forEach((_,i)=>$('revisionScope').add(new Option('Paragraph '+(i+1),String(i))));$('revisionScope').value=scope;
  script.scenes.forEach((scene,index)=>{
    const card=make('article',undefined,'scene');
    card.append(make('span',`PARAGRAPH ${index+1}`,'kicker'));
    for(const [key,label]of [['spoken','Script']]){
      const l=make('label',label),t=make('textarea');t.value=scene[key];t.maxLength=1000;t.dataset.scene=index;t.dataset.field=key;
      t.addEventListener('input',()=>{dirty=true;$('editStatus').textContent='Edited draft is unscored. Save your changes or refine to reassess.';$('score').hidden=true;updateScriptTiming(editedScript());});
      l.append(t);card.append(l);
    }
    const regenerate=make('button','Rewrite this paragraph');
    regenerate.onclick=async()=>{try{const draft=editedScript();await saveDraft();await start('script',current.result.selected_hook,draft,index);}catch(e){status(e.message,true);}};
    card.append(regenerate);$('sceneEditor').append(card);
  });
}
function editedScript(){const s=structuredClone(editorBase);for(const t of $('sceneEditor').querySelectorAll('textarea'))s.scenes[Number(t.dataset.scene)][t.dataset.field]=t.value;for(const paragraph of s.scenes){paragraph.visual='';paragraph.overlay='';}s.title=$('scriptTitle').textContent;return s;}
function renderResult(result){
  $('resultSection').hidden=false;$('score').hidden=false;
  $('revisionStatus').textContent=result.revision_notes?'Requested: '+result.revision_notes:'';const parent=current?.parent_script_id||result.parent_script_id;$('openOriginal').hidden=!parent;$('openOriginal').dataset.scriptId=parent||'';
  renderScenes(result.best.script);
  const assessment=result.best.assessment;
  const line=make('div',undefined,'score-line');line.append(make('strong',typeof assessment.score==='number'?assessment.score+'/100':'Unscored','score-number'),make('p',result.target_met?'Editorial target reached. Review the wording and supplied proof before use.':'Best saved draft. Target not reached: '+result.stop_reason.replaceAll('_',' ')));
  $('score').replaceChildren(line);for(const issue of assessment.blockers||[])$('score').append(make('p','Needs revision: '+issue,'status')); $('editStatus').textContent='Best generated draft shown. Edits will need a fresh assessment.';
  $('history').replaceChildren();
  for(const round of result.history){const d=make('details');d.append(make('summary',`Round ${round.round} · ${round.assessment.score}/100`));for(const c of round.assessment.criteria)d.append(make('p',`${c.key}: ${c.grade}/4 · Paragraph ${c.scene} · ${c.reason} Next: ${c.improvement}`));for(const v of round.assessment.blockers)d.append(make('p','Proof gap: '+v));const button=make('button','View this round');button.onclick=()=>{renderScenes(round.script);dirty=true;$('score').hidden=true;$('editStatus').textContent=`Round ${round.round} loaded into editor. Save it to export this version.`;};d.append(button);$('history').append(d);}
  $('appliedReferences').replaceChildren();for(const card of library.cards.filter(c=>result.best.script.reference_ids.includes(c.id)))$('appliedReferences').append(make('p',card.title+' · '+card.application,'muted small'));
    if(assessment.requested_changes)$('revisionStatus').textContent+=' | '+assessment.requested_changes.reason;
    $('textExport').href='/api/scripts/'+active+'/export';$('printExport').href='/api/scripts/'+active+'/export?format=print';
}
async function saveDraft(){if(!current?.result)return;const response=await api('/api/scripts/'+active+'/draft',{method:'PUT',body:JSON.stringify(editedScript())});dirty=false;$('score').hidden=true;$('editStatus').textContent=response.score_status;return response;}
async function loadSaved(){const rows=await api('/api/scripts');$('savedWork').replaceChildren();for(const row of rows.reverse()){const b=make('button',row.brief.topic+' · '+row.status);b.onclick=async()=>{if(busy)return;if(dirty&&!confirm('Discard unsaved edits and open this draft?'))return;active=row.id;shownHooks='';localStorage.setItem('tribe-writer-active',active);setBrief(row.brief);$('resultSection').hidden=true;$('hooks').replaceChildren();await poll();};$('savedWork').append(b);}if(!rows.length)$('savedWork').append(make('p','Your hooks and scripts will appear here.','muted small'));}
async function loadExperiments(){const rows=await api('/api/scripts/experiments');$('experiments').replaceChildren();for(const row of rows.reverse()){const d=make('details');d.append(make('summary',row.title+' · '+row.platform),make('p',row.hypothesis),make('p',row.observations),make('p',row.evidence_type,'muted small'));$('experiments').append(d);}}
$('briefForm').onsubmit=e=>{e.preventDefault();start('hooks');};
$('directButton').onclick=()=>start('script');
$('retryJob').onclick=async()=>{try{if(dirty&&!confirm('Retry generation? Save or copy your edits first.'))return;lock(true);const localRetry=$('retryJob').dataset.localRetry==='true';await api('/api/scripts/'+active+'/retry',{method:'POST',body:JSON.stringify(localRetry?{writer_backend:'local',local_model:$('localModel').value}:{})});if(localRetry){$('writerBackend').value='local';$('hfCreditsAllowed').checked=false;updateEngine();}$('retryJob').hidden=true;shownHooks='';poll();}catch(e){status(e.message,true);lock(false);}};
$('revisionForm').onsubmit=async e=>{
  e.preventDefault();if(busy||!current?.result||!$('revisionForm').reportValidity())return;
  const notes=$('revisionNotes').value.trim();if(!notes){status('Describe the changes you want.',true);return;}
  const draft=editedScript(),hook=current.result.selected_hook,scope=$('revisionScope').value;
  lock(true);try{await saveDraft();const started=await start('script',hook,draft,scope===''?null:Number(scope),notes);if(started)$('revisionNotes').value='';else lock(false);}catch(error){lock(false);status(error.message,true);}
};
$('openOriginal').onclick=async()=>{if(busy)return;if(dirty&&!confirm('Save or copy your edits before opening the original. Continue?'))return;try{const id=$('openOriginal').dataset.scriptId;const job=await api('/api/scripts/'+id);active=id;current=job;shownHooks='';shownLive='';localStorage.setItem('tribe-writer-active',id);setBrief(job.brief);await poll();}catch(error){status(error.message,true);}};
$('saveDraft').onclick=()=>saveDraft().catch(e=>status(e.message,true));
$('reviseDraft').onclick=async()=>{try{const draft=editedScript();await saveDraft();await start('script',current.result.selected_hook,draft);}catch(e){status(e.message,true);}};
$('copyScript').onclick=async()=>{try{const s=editedScript();await navigator.clipboard.writeText(s.title+'\n\n'+s.scenes.map(v=>v.spoken).join('\n\n'));$('editStatus').textContent='Script copied.';}catch(e){status('Clipboard unavailable. Save edits and download the text file.',true);}};
for(const id of ['textExport','printExport'])$(id).addEventListener('click',e=>{if(dirty){e.preventDefault();status('Save your edits before exporting.',true);}});
$('experimentForm').onsubmit=async e=>{e.preventDefault();try{await api('/api/scripts/experiments',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(e.target)))});e.target.reset();await loadExperiments();status('Experiment observation saved.');}catch(error){status(error.message,true);}};
async function init(){
  try{
    const results=await Promise.allSettled([api('/api/scripts/library'),api('/api/brands'),loadSaved(),loadExperiments(),api('/api/scripts/personas'),api('/api/scripts/engines')]);
    if(results[0].status==='rejected')throw results[0].reason;
    library=results[0].value;
    for(const c of library.cards){const card=make('article',undefined,'card');card.append(make('span',c.kind,'kicker'),make('h3',c.title),make('p',c.author),make('p',c.principle),make('p','Apply: '+c.application),make('p','Limit: '+c.caution));if(c.url){const a=make('a','Read the source ↗');a.href=c.url;a.target='_blank';a.rel='noopener';card.append(a);}$('library').append(card);}
    if(results[1].status==='fulfilled')for(const b of results[1].value){const o=make('option',b.name);o.value=b.id;$('brandSelect').append(o);}
    for(const r of results.slice(1))if(r.status==='rejected')status(r.reason.message,true);
    if(results[4].status==='fulfilled'){personaCatalog=results[4].value.personas;updatePersona();}
    if(results[5].status==='fulfilled'){engineConfig=results[5].value;$('writerBackend').value=engineConfig.default_backend||'local';}updateEngine();
    active=localStorage.getItem('tribe-writer-active');if(active){try{current=await api('/api/scripts/'+active);setBrief(current.brief);await poll();}catch(e){localStorage.removeItem('tribe-writer-active');}}
  }catch(e){status(e.message,true);}
}
init();
