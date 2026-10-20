"use strict";
(() => {
  let active=null,timer=null,generation=0;
  const make=(tag,text)=>{const el=document.createElement(tag);el.textContent=text;return el;};
  async function api(id,method='GET',model=''){
    const response=await fetch('/api/jobs/'+encodeURIComponent(id)+'/gemma-review'+(model?'?model='+encodeURIComponent(model):''),{method});
    const data=await response.json();if(!response.ok)throw new Error(data.detail||'Gemma review is unavailable.');return data;
  }
  window.renderGemmaVideoReview=async id=>{
    active=id;const version=++generation;clearTimeout(timer);
    let panel=document.getElementById('gemmaPanel');
    if(!panel){panel=make('section','');panel.id='gemmaPanel';panel.className='panel';document.getElementById('creative').prepend(panel);}
    panel.replaceChildren(make('h2','AI video review'),make('p','Send the original MP4 to NVIDIA for a separate AI assessment. Maximum 20 MB. Scores are uncalibrated editorial estimates, not measured odds of going viral.'));
    const models={'nvidia/nemotron-3.5-super-vl-120b-a12b':'Nemotron 3.5 Super VL (recommended)','google/gemma-4-31b-it':'Gemma 4 31B (manual retry)'};
    const select=document.createElement('select');select.id='videoReviewModel';select.setAttribute('aria-label','Video review model');for(const [value,label]of Object.entries(models))select.add(new Option(label,value));
    const button=make('button','Analyze video');button.type='button';button.id='gemmaAnalyze';
    const status=make('p','Loading saved assessment...');status.id='gemmaStatus';status.setAttribute('aria-live','polite');
    const output=make('div','');output.id='gemmaScores';status.style.overflowWrap='anywhere';panel.append(select,button,status,output);
    function render(state){
      const running=['queued','running'].includes(state.status);button.disabled=running||state.configured===false;select.disabled=running;
      status.textContent=running?(state.model||select.value)+' '+state.status+(state.elapsed_seconds?' | '+Math.round(state.elapsed_seconds)+'s elapsed':'')+' | request timeout: 600 seconds':state.status==='failed'?'Unavailable: '+state.error:state.status==='completed'?'Assessment complete':state.configured===false?'Set GEMMA_API_KEY on the server.':'Ready for a separate API video assessment.';
      output.replaceChildren();
      if(state.status==='completed'){
        const r=state.result;output.append(make('p','Scored by: '+(models[state.model]||state.model||'Unknown model (older saved result)')),make('strong',state.dashboard.status+' — creative readiness'),make('p','Hook: '+r.hook_score+'/100 | Pacing: '+r.pacing_score+'/100 | Overall estimate: '+r.overall_probability+'/100'),make('p',r.timestamped_revision_advice),make('p',state.dashboard.policy));
      }
      if(running)timer=setTimeout(refresh,1500);
    }
    async function refresh(){try{const state=await api(id);if(active===id&&generation===version)render(state);}catch(error){if(active===id&&generation===version){status.textContent=error.message;button.disabled=false;}}}
    button.onclick=async()=>{button.disabled=true;clearTimeout(timer);output.replaceChildren();status.textContent='Starting video review...';try{const state=await api(id,'POST',select.value);if(active===id&&generation===version)render(state);}catch(error){if(active===id&&generation===version){status.textContent=error.message;button.disabled=false;}}};
    await refresh();
  };
})();
