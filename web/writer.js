"use strict";
const $ = id => document.getElementById(id);
const make = (tag, content, cls) => { const e=document.createElement(tag); if(content!==undefined)e.textContent=String(content); if(cls)e.className=cls; return e; };
let personaCatalog=[],engineConfig=null,exampleCatalog=null;
let researchActive=null,researchCurrent=null,researchTimer=null;
let active=null, current=null, library=null, editorBase=null, dirty=false, busy=false, pollTimer=null, shownHooks='', shownLive='', pollFailures=0;
async function api(url, options={}) {
  const response=await fetch(url, {...options, headers:{"Content-Type":"application/json",...(options.headers||{})}});
  const data=await response.json();
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail||data));
  return data;
}
function status(message,error=false){$('status').textContent=message;$('status').classList.toggle('error',error);}
function lock(value){busy=value;for(const b of document.querySelectorAll('#predictPerformance,#briefForm button,#hooks button,#abHooks button,#sceneEditor button,#saveDraft,#reviseDraft,#retryJob,#applyChanges,#openOriginal,#revisionNotes,#revisionScope,#sceneEditor textarea'))b.disabled=value||b.dataset.validated==='false';}
function getBrief(){const b=Object.fromEntries(new FormData($('briefForm')));b.duration=({short:30,mid:60,long:600})[b.content_duration]||30;b.hf_credits_allowed=$('hfCreditsAllowed').checked;b.research_id=$('useResearch').checked&&researchCurrent?.status==='completed'?researchCurrent.id:'';return b;}
function setBrief(brief){for(const [key,value] of Object.entries({content_duration:brief.content_duration||(brief.duration===60?'mid':'short'),content_mode:'organic',content_format:'auto',production_style:'solo_simple',persona:'auto',creator_experience:'',niche:'auto',writer_backend:'local',local_model:'auto',hf_model:'deepseek-ai/DeepSeek-V4.1-Flash',hf_credits_allowed:false,...brief})){const field=$('briefForm').elements.namedItem(key);if(field){if(field.type==='checkbox')field.checked=value===true;else field.value=value;}}updateContentMode();updatePersona();updateEngine();$('useResearch').checked=false;if(brief.research_id)openResearch(brief.research_id,true);}
function updateContentMode(){
  const hints={organic:'Story, humor or useful discovery first. Product presence stays natural; the scoring gate still requires one clear CTA.',ugc:'Creator voice, phone footage and everyday context. Add real experience above; otherwise the writer uses a first look, observation or staged scene.',paid_ad:'Product-led communication with supported benefits and your chosen CTA.'};
  $('contentModeHint').textContent=hints[$('contentMode').value];
}
$('contentMode').addEventListener('change',updateContentMode);
function updateEngine(){$('fastSettings').hidden=$('writerBackend').value!=='fast';$('teamSettings').hidden=$('writerBackend').value!=='team';const hosted=$('writerBackend').value==='huggingface';$('hostedSettings').hidden=!hosted;$('localSettings').hidden=$('writerBackend').value!=='local';$('nvidiaSettings').hidden=$('writerBackend').value!=='nvidia';$('nvidiaTokenStatus').textContent=engineConfig?.nvidia_token_configured?'NVIDIA key configured on server.':'Set NVIDIA_API_KEY in the server environment or .env.';const installed=(engineConfig?.local_models||[]).filter(m=>m.installed);$('localModelStatus').textContent=installed.length?'Installed: '+installed.map(m=>m.name).join(', ')+'. Runs on this PC without HF inference credits.':'Local model status unavailable.';$('hfTokenStatus').textContent=engineConfig?.token_configured?'HF token detected on server. Inference Providers permission is required.':'Set HF_TOKEN in the server environment or .env, or use hf auth login. No token is stored in this browser.';}
$('writerBackend').addEventListener('change',updateEngine);
function updatePersona(){const p=personaCatalog.find(p=>p.id===$('personaSelect').value);if($('personaHint'))$('personaHint').textContent=p?p.direction+' Best for: '+p.best_for:'';}
$('personaSelect').addEventListener('change',updatePersona);
async function start(mode,hook=null,previous=null,sceneIndex=null,revisionNotes=""){
  if(!$('briefForm').reportValidity())return;
  if($('writerBackend').value==='huggingface'&&!$('hfCreditsAllowed').checked){status('Hosted generation is disabled. Use Local for free writing, or explicitly allow HF credit usage.',true);return;}
  if(dirty&&!window.confirm('Starting another generation will replace the editor. Save or copy your edits first. Continue?'))return;
  lock(true);
  $('hooksSection').hidden=true;
  try{
    clearTimeout(pollTimer);
    const job=await api('/api/scripts',{method:'POST',body:JSON.stringify({mode,brief:getBrief(),selected_hook:hook,use_experiments:$('useExperiments').checked,previous_script:previous,scene_index:sceneIndex,revision_notes:revisionNotes,parent_script_id:previous?active:null})});
    active=job.id;localStorage.setItem('creator-writer-active',active);dirty=false;shownHooks='';shownLive='';$('retryJob').hidden=true;$('liveScriptSection').hidden=true;
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
    $('retryJob').textContent='Retry saved job';
    $('retryJob').dataset.localRetry='false';
    $('retryJob').dataset.fastRetry='false';
    $('retryJob').hidden=job.status!=='failed'&&!(job.status==='completed'&&(['needs_review','unavailable'].includes(job.hook_options?.review_status)||job.result?.quality_status==='needs_review'));
    if(job.hook_options&&shownHooks!==JSON.stringify(job.hook_options)){
      renderHooks(job.hook_options.hooks,job.hook_options);shownHooks=JSON.stringify(job.hook_options);
    }
    $('progress').hidden=!['queued','running'].includes(job.status);$('progress').value=job.progress||0;
    if(['queued','running'].includes(job.status)){
      if(!job.brief?.content_duration&&job.live_draft?.paragraphs?.length){const key=JSON.stringify(job.live_draft.paragraphs);if(key!==shownLive){$('liveScript').replaceChildren(...job.live_draft.paragraphs.map(p=>make('p',p)));shownLive=key;}$('liveScriptSection').hidden=false;}
      lock(true);pollTimer=setTimeout(poll,1000);return;
    }
    $('liveScriptSection').hidden=true;

    current=job;lock(false);dirty=false;
    if(!job.hook_options&&!job.result)$('hooks').replaceChildren(make('p','No hooks are ready yet. Retry this saved job or start from the brief.','muted'));
    if(job.result){renderResult(job.result);try{const draft=await api('/api/scripts/'+active+'/draft');renderScript(draft);showEditStatus('Saved manual edits loaded. This edited draft is unscored.');}catch(e){/* No manually edited draft is normal. */}}
    await loadSaved().catch(e=>status('Work is saved, but the saved-work list could not refresh. '+e.message,true));
  }catch(e){
    if(requestedId!==active)return;
    status('Connection interrupted. Reconnecting to your saved job… '+e.message,true);
    if(++pollFailures<=3)pollTimer=setTimeout(poll,2500);else{lock(false);status('Connection unavailable. Reload to reconnect to your saved job.',true);}
  }
}
function renderHooks(hooks,review={}){
  $('hooksSection').hidden=false;
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
  $('performanceResult').textContent='';
  const words=scriptText(script).replace(/\[[^\]]*\]/g,'').replace(/[—–]/g,' ').trim().split(/\s+/).filter(Boolean).length;
  const language=(brief.language||'English').toLowerCase();
  const rates={english:[120,160,2],en:[120,160,2],hindi:[108,168,1.8],'hindi (roman)':[108,168,1.8],hinglish:[120,180,2]};
  const rate=rates[language];
  const seconds=Number(brief.duration);
  $('scriptTiming').textContent=rate?`${words} words | Estimated ${Math.round(words*60/rate[1])}-${Math.round(words*60/rate[0])} seconds in ${brief.language} | Requested ${seconds}s. ${!brief.content_duration&&words<Math.floor(seconds*rate[2])?'Too short: develop the story. ':''}Approximate; read aloud to confirm.`:`${words} words | Requested ${seconds}s. Read aloud in the selected language to check timing.`;
}
function scriptText(script){return typeof script.final_script==='string'?script.final_script:(script.scenes||[]).map(row=>row.spoken||'').join(' ');}
function resizeScript(){const area=$('finalScript');area.style.height='auto';area.style.height=Math.max(220,area.scrollHeight)+'px';}
function updateABSelection(){
  const opening=$('finalScript').value.split('\n')[0].replace(/^\s*(?:\[[^\]]+\]\s*)+/,'').trim();
  for(const button of $('abHooks').children)button.setAttribute('aria-pressed',String(button.dataset.hookText===opening));
}
function renderABHooks(result){
  const panel=$('abHooksPanel'),buttons=$('abHooks');buttons.replaceChildren();
  const hooks=result.ab_hooks||[];panel.hidden=hooks.length!==3;
  for(const hook of hooks){
    const button=make('button',hook.label+': '+hook.text);button.type='button';
    button.dataset.hookKind=hook.kind;button.dataset.hookText=hook.text;button.dataset.validated=String(hook.validated!==false);
    const opening=$('finalScript').value.split('\n')[0].replace(/^\s*(?:\[[^\]]+\]\s*)+/,'').trim();
    button.setAttribute('aria-pressed',String(opening===hook.text));
    button.disabled=hook.validated===false;
    button.onclick=()=>{
      if(busy)return;
      const content=$('finalScript').value,split=content.indexOf('\n');
      if(split<0){status('Keep the opening on its own first line before swapping hooks.',true);return;}
      const prefix=content.slice(0,split).match(/^(\s*(?:\[[^\]]+\]\s*)+)/)?.[1]||'';
      $('finalScript').value=prefix+hook.text+'\n'+content.slice(split+1);
      dirty=true;
      for(const node of buttons.children)node.setAttribute('aria-pressed',String(node===button));
      showEditStatus('Hook selected. Your body and inline cues are unchanged. Save this variant to export it.');
      updateScriptTiming(editedScript());resizeScript();
    };
    buttons.append(button);
  }
}
function renderScript(script){
  editorBase={final_script:scriptText(script)};$('performanceResult').textContent='';
  const rejected=current?.result?.approved===false;
  $('scriptTitle').textContent=rejected?'Unapproved draft — revise before use':'Your script';$('finalScript').value=editorBase.final_script;
  $('finalScript').setAttribute('aria-label',rejected?'Unapproved script draft':'Final script');
  $('revisionScope').replaceChildren(new Option('Whole script',''));
  updateScriptTiming(editorBase);resizeScript();
  updateABSelection();
}
function editedScript(){return {final_script:$('finalScript').value};}
function showEditStatus(message){
  $('editStatus').textContent=message;
  const rejected=current?.result?.approved===false;
  $('score').hidden=!rejected;
  if(rejected){$('score').replaceChildren(make('p','Unapproved manual draft. The original score does not apply to these edits.'));
    const critique=current.result.evaluation?.critique||current.result.best?.assessment?.critique;
    if(critique)$('score').append(make('p','Original feedback: '+critique));}
}
$('finalScript').addEventListener('input',()=>{dirty=true;$('cognitiveMetrics').hidden=true;$('auditDownload').hidden=true;showEditStatus('Unsaved changes. A fresh assessment is required.');updateScriptTiming(editedScript());resizeScript();updateABSelection();});
window.addEventListener('resize',resizeScript);
function renderResult(result){
  $('resultSection').hidden=false;$('score').hidden=false;
  $('revisionStatus').textContent=result.revision_notes?'Requested: '+result.revision_notes:'';const parent=current?.parent_script_id||result.parent_script_id;$('openOriginal').hidden=!parent;$('openOriginal').dataset.scriptId=parent||'';
  $('pipelineStatus').textContent=result.pipeline?.kind==='actor_critic'?'Actor → mechanical critic → editor · '+result.pipeline.draft_model:result.pipeline?result.pipeline.draft_model+(result.pipeline.analysis_model?' drafts | '+result.pipeline.analysis_model+' reviews':' writes your script'):'';
  const cognitive=result.source_video_cognitive;const metrics=$('cognitiveMetrics');metrics.replaceChildren();metrics.hidden=!cognitive;
  if(cognitive){metrics.append(make('strong','Source video ? cognitive simulation'),make('p','Attention estimate: '+cognitive.attention_retention_score+'/100 | Emotion hypothesis: '+cognitive.emotional_arousal_state+' | WPM: '+(result.source_video_pacing?.wpm??'Unavailable')),make('p',cognitive.psychological_critique),make('p','These estimates describe the source video, not the newly written script.','muted small'));}
  $('auditDownload').hidden=!(result.audit?.pdf_file==='audit.pdf'&&result.source_video_job_id);
  if(!$('auditDownload').hidden)$('auditDownload').href='/api/jobs/'+encodeURIComponent(result.source_video_job_id)+'/files/audit.pdf';
  renderScript(result.best.script);
  renderABHooks(result);
  const assessment=result.best.assessment;
  const line=make('div',undefined,'score-line');line.append(make('strong',typeof assessment.score==='number'?assessment.score+'/100':'Unscored','score-number'),make('p',result.target_met?'Editorial target reached. Review the wording and supplied proof before use.':'Best saved draft. Target not reached: '+result.stop_reason.replaceAll('_',' ')));
  if(assessment.score===null)line.replaceChildren(make('p',assessment.blockers?.length?'Draft saved. Revise the flagged issues before use.':'Script ready. Copy, edit or suggest changes below.'));
  if(result.evaluation){line.replaceChildren(make('strong',result.evaluation.overall_score+'/100','score-number'),make('p',result.approved?'Approved by pre-scoring gatekeeper':'Not approved - one rewrite limit reached'),make('p',result.evaluation.critique));}
  else if(result.approved===false){line.replaceChildren(make('p','Not approved - review the flagged issues'),make('p',assessment.critique||''));}
  if(result.pipeline_version==='actor-critic-v1'){
    line.replaceChildren(make('strong',result.approved?'Edited script ready':'Draft retained — review checks'),
      make('p','One actor draft, one mechanical critique and one editor pass. No extra scoring or regeneration loop.'));
    const critique=result.mechanical_critique;
    if(critique&&Object.values(critique).some(value=>Array.isArray(value)&&value.length))line.append(make('p','Initial-draft critique applied by the editor:'));
    if(critique)for(const key of ['hook_velocity','visual_pacing','no_fluff','direct_response_strength','safety_issues']){
      for(const issue of critique[key]||[])line.append(make('p',key.replaceAll('_',' ')+': '+issue));
    }
  }
  const rejected=result.approved===false;
  $('sceneEditor').hidden=false;
  for(const id of ['saveDraft','reviseDraft','applyChanges'])$(id).disabled=false;
  for(const id of ['copyScript','textExport','printExport'])$(id).disabled=rejected;
  $('textExport').hidden=rejected;$('printExport').hidden=rejected;
  $('score').replaceChildren(line);for(const issue of assessment.blockers||[])$('score').append(make('p','Needs revision: '+issue,'status')); $('editStatus').textContent=rejected?'Unapproved draft retained for editing. Save changes or suggest a revision; export requires an approved revision.':'Best generated draft shown. Edits will need a fresh assessment.';
  $('history').replaceChildren();
  for(const round of result.history||[]){const d=make('details');d.append(make('summary',`Round ${round.round} · ${round.assessment.score}/100`));for(const c of round.assessment.criteria)d.append(make('p',`${c.key}: ${c.grade}/4 · Paragraph ${c.scene} · ${c.reason} Next: ${c.improvement}`));for(const v of round.assessment.blockers)d.append(make('p','Proof gap: '+v));const button=make('button','View this round');button.onclick=()=>{renderScript(round.script);dirty=true;$('score').hidden=true;$('editStatus').textContent=`Round ${round.round} loaded into editor. Save it to export this version.`;};d.append(button);$('history').append(d);}
  for(const round of result.gate_history||[]){const d=make('details');d.append(make('summary',`Gate attempt ${round.attempt} | ${round.evaluation?.overall_score??'Unavailable'}`));if(round.evaluation)d.append(make('p',round.evaluation.critique));for(const issue of round.blockers||[])d.append(make('p',issue));$('history').append(d);}
  $('appliedReferences').replaceChildren();for(const card of library.cards.filter(c=>(result.reference_ids||result.best.script.reference_ids||[]).includes(c.id)))$('appliedReferences').append(make('p',card.title+' · '+card.application,'muted small'));
    if(assessment.requested_changes)$('revisionStatus').textContent+=' | '+assessment.requested_changes.reason;
    $('textExport').href='/api/scripts/'+active+'/export';$('printExport').href='/api/scripts/'+active+'/export?format=print';
}
async function saveDraft(){if(!current?.result)return;const response=await api('/api/scripts/'+active+'/draft',{method:'PUT',body:JSON.stringify(editedScript())});dirty=false;showEditStatus(response.score_status);return response;}
async function loadSaved(){const rows=await api('/api/scripts');$('savedWork').replaceChildren();for(const row of rows.reverse()){const b=make('button',row.brief.topic+' · '+row.status);b.onclick=async()=>{if(busy)return;if(dirty&&!confirm('Discard unsaved edits and open this draft?'))return;active=row.id;shownHooks='';localStorage.setItem('creator-writer-active',active);setBrief(row.brief);$('resultSection').hidden=true;$('hooks').replaceChildren();await poll();};$('savedWork').append(b);}if(!rows.length)$('savedWork').append(make('p','Your hooks and scripts will appear here.','muted small'));}
async function loadExperiments(){const rows=await api('/api/scripts/experiments');$('experiments').replaceChildren();for(const row of rows.reverse()){const d=make('details');d.append(make('summary',row.title+' · '+row.platform),make('p',row.hypothesis),make('p',row.observations),make('p',row.evidence_type,'muted small'));$('experiments').append(d);}}
$('briefForm').onsubmit=e=>{e.preventDefault();start('script');};
$('directButton').onclick=()=>start('script');
$('retryJob').onclick=async()=>{try{if(dirty&&!confirm('Retry generation? Save or copy your edits first.'))return;lock(true);const localRetry=$('retryJob').dataset.localRetry==='true',fastRetry=$('retryJob').dataset.fastRetry==='true';await api('/api/scripts/'+active+'/retry',{method:'POST',body:JSON.stringify(fastRetry?{writer_backend:'fast'}:localRetry?{writer_backend:'local',local_model:$('localModel').value}:{})});if(fastRetry){$('writerBackend').value='fast';updateEngine();}if(localRetry){$('writerBackend').value='local';$('hfCreditsAllowed').checked=false;updateEngine();}$('retryJob').hidden=true;shownHooks='';poll();}catch(e){status(e.message,true);lock(false);}};
$('revisionForm').onsubmit=async e=>{
  e.preventDefault();if(busy||!current?.result||!$('revisionForm').reportValidity())return;
  const notes=$('revisionNotes').value.trim();if(!notes){status('Describe the changes you want.',true);return;}
  const draft=editedScript(),hook=current.result.selected_hook,scope=$('revisionScope').value;
  lock(true);try{await saveDraft();const started=await start('script',hook,draft,scope===''?null:Number(scope),notes);if(started)$('revisionNotes').value='';else lock(false);}catch(error){lock(false);status(error.message,true);}
};
$('openOriginal').onclick=async()=>{if(busy)return;if(dirty&&!confirm('Save or copy your edits before opening the original. Continue?'))return;try{const id=$('openOriginal').dataset.scriptId;const job=await api('/api/scripts/'+id);active=id;current=job;shownHooks='';shownLive='';localStorage.setItem('creator-writer-active',id);setBrief(job.brief);await poll();}catch(error){status(error.message,true);}};
$('saveDraft').onclick=()=>saveDraft().catch(e=>status(e.message,true));
$('reviseDraft').onclick=async()=>{try{const draft=editedScript();await saveDraft();await start('script',current.result.selected_hook,draft);}catch(e){status(e.message,true);}};
$('copyScript').onclick=async()=>{try{const s=editedScript();await navigator.clipboard.writeText(s.final_script);$('editStatus').textContent='Script copied.';}catch(e){status('Clipboard unavailable. Save edits and download the text file.',true);}};
for(const id of ['textExport','printExport'])$(id).addEventListener('click',e=>{if(dirty){e.preventDefault();status('Save your edits before exporting.',true);}});
$('experimentForm').onsubmit=async e=>{e.preventDefault();try{await api('/api/scripts/experiments',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(e.target)))});e.target.reset();await loadExperiments();status('Experiment observation saved.');}catch(error){status(error.message,true);}};
async function init(){
  try{
    const results=await Promise.allSettled([api('/api/scripts/library'),api('/api/brands'),loadSaved(),loadExperiments(),api('/api/scripts/personas'),api('/api/scripts/engines'),api('/api/scripts/examples'),loadPerformance()]);
    if(results[0].status==='rejected')throw results[0].reason;
    library=results[0].value;
    for(const c of library.cards){const card=make('article',undefined,'card');card.append(make('span',c.kind,'kicker'),make('h3',c.title),make('p',c.author),make('p',c.principle),make('p','Apply: '+c.application),make('p','Limit: '+c.caution));if(c.url){const a=make('a','Read the source ↗');a.href=c.url;a.target='_blank';a.rel='noopener';card.append(a);}$('library').append(card);}
    if(results[1].status==='fulfilled')for(const b of results[1].value){const o=make('option',b.name);o.value=b.id;$('brandSelect').append(o);}
    for(const r of results.slice(1))if(r.status==='rejected')status(r.reason.message,true);
    if(results[4].status==='fulfilled'){personaCatalog=results[4].value.personas;updatePersona();}
    if(results[5].status==='fulfilled'){engineConfig=results[5].value;if(engineConfig.team_configured)engineConfig.default_backend='team';$('writerBackend').value=engineConfig.default_backend||'local';}updateEngine();
    if(results[6].status==='fulfilled'){exampleCatalog=results[6].value;renderReferences();}
    active=new URLSearchParams(location.search).get('script')||localStorage.getItem('creator-writer-active');if(active){try{current=await api('/api/scripts/'+active);setBrief(current.brief);await poll();}catch(e){localStorage.removeItem('creator-writer-active');}}
    const sourceVideo=new URLSearchParams(location.search).get('video');if(sourceVideo&&/^[a-f0-9]{32}$/.test(sourceVideo))document.querySelector('[name=source_job_id]').value=sourceVideo;
    if(!new URLSearchParams(location.search).has('script')&&!busy&&engineConfig?.default_backend==='team'){$('writerBackend').value='team';updateEngine();}
  }catch(e){status(e.message,true);}
}

function renderReferences(){
  if(!exampleCatalog)return;
  const niche=$('referenceNiche').value,language=$('referenceLanguage').value;
  $('creatorReferences').replaceChildren();
  for(const row of exampleCatalog.examples.filter(r=>r.niche===niche)){
    const card=make('article',undefined,'card');card.append(make('h3',row.pattern),make('p',row.scripts[language]),make('p','Avoid: '+row.avoid,'muted small'));
    for(const id of row.source_ids){const source=exampleCatalog.sources.find(s=>s.id===id);if(!source)continue;const link=make('a',source.title);link.href=source.url;link.target='_blank';link.rel='noopener';card.append(link,make('p',source.kind+' ? '+source.evidence,'muted small'));}
    $('creatorReferences').append(card);
  }
}
$('referenceNiche').onchange=renderReferences;$('referenceLanguage').onchange=renderReferences;
$('nicheSelect').onchange=()=>{if($('nicheSelect').value!=='auto'){$('referenceNiche').value=$('nicheSelect').value;renderReferences();}};
$('briefForm').elements.namedItem('language').addEventListener('change',e=>{if(['English','Hindi','Hinglish'].includes(e.target.value)){$('referenceLanguage').value=e.target.value;renderReferences();}});
async function loadPerformance(){const data=await api('/api/scripts/performance-data');$('performanceStatus').textContent=(data.configured?'Kumo key configured. ':'Set KUMO_API_KEY on the server. ')+(data.rows?`${data.rows} real posts imported for ${data.account}. Outcome: ${data.outcome_definition}`:'No real outcomes imported yet.')+(data.error?' '+data.error:'');return data;}
$('importPerformance').onclick=async()=>{const button=$('importPerformance');try{const file=$('performanceFile').files[0];if(!file)throw new Error('Choose your post-outcomes JSON file first.');if(file.size>4_000_000)throw new Error('Keep the import below 4 MB.');button.disabled=true;await api('/api/scripts/performance-data',{method:'PUT',body:await file.text()});await loadPerformance();}catch(e){$('performanceStatus').textContent=e.message;}finally{button.disabled=false;}};
$('predictPerformance').onclick=async()=>{if(busy||!editorBase||!current?.result)return;const requestId=active,submitted=JSON.stringify(editedScript());const button=$('predictPerformance');button.disabled=true;$('performanceResult').textContent='Comparing with your real post history?';try{const data=await api('/api/scripts/'+requestId+'/predict',{method:'POST',body:JSON.stringify({script:JSON.parse(submitted)})});if(active!==requestId||JSON.stringify(editedScript())!==submitted){$('performanceResult').textContent='Draft changed while estimating. Run a new estimate for the current words.';return;}$('performanceResult').textContent=`Experimental estimate: ${Math.round(data.probability*100)}% for your defined outcome, ?${data.outcome_definition}?. Historical base rate: ${Math.round(data.base_rate*100)}% across ${data.context_rows} comparable posts. Uncalibrated; not a viral score. `+data.method;}catch(e){$('performanceResult').textContent=e.message;}finally{button.disabled=busy;}};


function attachResearch(){if(!$('useResearch').checked||researchCurrent?.status!=='completed')return;$('briefForm').elements.namedItem('topic').value=researchCurrent.brief.topic;$('nicheSelect').value=researchCurrent.brief.niche;$('referenceNiche').value=researchCurrent.brief.niche;renderReferences();}
$('useResearch').onchange=attachResearch;
function renderResearch(state){
  const result=state.result, snapshot=result||state.source_snapshot;
  $('researchResult').replaceChildren();
  $('researchStatus').textContent=state.stage+(state.error?' ? '+state.error:'');
  $('useResearch').disabled=state.status!=='completed';
  if(state.status!=='completed')$('useResearch').checked=false;
  if(!snapshot)return;
  if(result){
    $('researchResult').append(make('p',result.summary),make('p',result.method,'muted small'));
    for(const rule of result.rules||[]){const card=make('article',undefined,'card');card.append(make('h3',rule.rule),make('p',rule.explanation),make('p','Limits: '+rule.limits),make('p','Books: '+rule.book_ids.join(', '),'muted small'));for(const e of rule.evidence||[])card.append(make('p',e.video_id+' | '+e.start+'?'+e.end+'s | '+e.observation,'muted small'));$('researchResult').append(card);}
    for(const [key,label,field] of [['findings','Source observations','observation'],['angles','Creative angles to test','idea']]){
      $('researchResult').append(make('h3',label));
      for(const row of result[key]||[])$('researchResult').append(make('p',row[field]+' ['+row.source_ids.join(', ')+']'));
    }
    for(const [key,label] of [['questions','Questions to explore'],['avoid','Claims and assumptions to avoid']]){$('researchResult').append(make('h3',label));for(const text of result[key]||[])$('researchResult').append(make('p',text));}
  }
  for(const warning of snapshot.warnings||[])$('researchResult').append(make('p',warning,'muted small'));
  $('researchResult').append(make('h3','Sources and evidence limits'));
  for(const source of snapshot.sources||[]){const card=make('article',undefined,'card');const link=make(source.url?'a':'strong',source.id+' | '+source.title);if(source.url){link.href=source.url;link.target='_blank';link.rel='noopener';}card.append(link,make('p',source.excerpt),make('p',(source.published_at?source.published_at+' ? ':'')+source.evidence,'muted small'));$('researchResult').append(card);}
}
async function loadResearchHistory(){const rows=await api('/api/scripts/research');$('researchHistory').replaceChildren();for(const row of rows.slice(0,10)){const button=make('button',row.brief.topic+' ? '+row.status);button.type='button';button.onclick=()=>openResearch(row.id);$('researchHistory').append(button);}}
async function openResearch(id,attach=false){if(researchActive!==id&&!attach)$('useResearch').checked=false;researchActive=id;localStorage.setItem('creator-research-active',id);clearTimeout(researchTimer);try{const state=await api('/api/scripts/research/'+id);if(researchActive!==id)return;researchCurrent=state;renderResearch(state);const running=['queued','running'].includes(state.status);$('researchStart').disabled=running;if(running){researchTimer=setTimeout(()=>openResearch(id,attach),1200);}else{if(attach&&state.status==='completed'){$('useResearch').checked=true;attachResearch();}await loadResearchHistory();await loadLearning();}}catch(e){$('researchStatus').textContent=e.message;$('researchStart').disabled=false;}}
$('researchForm').onsubmit=async e=>{e.preventDefault();const b=getBrief();const topic=$('researchTopicInput').value.trim()||b.topic;try{if(!topic)throw new Error('Enter a topic in the brief or research box.');$('researchStart').disabled=true;$('useResearch').checked=false;$('researchStatus').textContent='Starting Muse topic research...';const files=[...$('researchClips').files];if(files.length>3)throw new Error('Choose at most 3 clips.');const upload_ids=[];for(const file of files){if(file.size>50*1024**2)throw new Error('Keep each clip below 50 MB.');const form=new FormData();form.append('video',file);const response=await fetch('/api/scripts/research/uploads',{method:'POST',body:form});const uploaded=await response.json();if(!response.ok)throw new Error(uploaded.detail||'Upload failed.');upload_ids.push(uploaded.id);}const video_urls=$('researchVideoUrls').value.split(/\n/).map(v=>v.trim()).filter(Boolean);const state=await api('/api/scripts/research',{method:'POST',body:JSON.stringify({topic,niche:b.niche,language:b.language,platform:b.platform,research_mode:'videos',video_urls,upload_ids})});await openResearch(state.id,true);}catch(error){$('researchStatus').textContent=error.message;$('researchStart').disabled=false;}};
async function initResearch(){try{const config=await api('/api/scripts/research/config');$('researchStatus').textContent=config.configured?'Muse configured on server. Ready to research a topic.':'Set MUSE_API_KEY on the server.';await loadResearchHistory();if(!researchActive){const saved=config.active_id||localStorage.getItem('creator-research-active');if(saved)await openResearch(saved);}}catch(e){$('researchStatus').textContent=e.message;}}

init();
initResearch();
async function loadLearning(){try{const data=await api("/api/scripts/learning");$("learnedLogic").replaceChildren(...data.rules.map(r=>make("p",r.language+" / "+r.niche+": "+r.rule.rule,"muted small")));}catch(e){$("learnedLogic").textContent=e.message;}}
loadLearning();
