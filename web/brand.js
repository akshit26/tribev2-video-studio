"use strict";
(() => {
  const make=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const api=async(url,options={})=>{const r=await fetch(url,options),data=await r.json();if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'Unable to save. Check the fields.');return data;};
  const json=value=>({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
  const field=(parent,title,type='text')=>{const label=make('label',title),input=make(type==='textarea'?'textarea':'input');if(type!=='textarea')input.type=type;input.setAttribute('aria-label',title);label.append(input);parent.append(label);return input;};
  function outcomeFields(parent,prefix){
    const grid=make('div',undefined,'brand-grid');parent.append(grid);const fields={};
    for(const [key,title,max] of [['team_rating','Team rating / 100',100],['views','Views',1e12],['retention_percent','Average viewed %',500],['conversions','Conversions',1e12],['spend','Ad spend (same currency)',1e10]]){
      const input=field(grid,`${prefix}${title}`,'number');input.min=0;input.max=max;input.step=key==='views'||key==='conversions'?'1':'0.1';fields[key]=input;
    }
    const label=make('label',`${prefix}Distribution`),select=make('select');select.setAttribute('aria-label',`${prefix}Distribution`);for(const value of ['unknown','organic','paid','mixed']){const o=make('option',value);o.value=value;select.append(o);}label.append(select);grid.append(label);fields.distribution=select;
    fields.notes=field(parent,`${prefix}What worked / what should change`,'textarea');fields.notes.maxLength=1500;fields.notes.rows=3;
    return {read:()=>Object.fromEntries(Object.entries(fields).filter(([k,v])=>v.value!==''||k==='notes').map(([k,v])=>[k,['notes','distribution'].includes(k)?v.value:Number(v.value)])),fill:data=>{for(const [key,input] of Object.entries(fields))input.value=data[key]??(key==='distribution'?'unknown':'');}};
  }
  let selected=null,profile=null,documents={},status,referenceList,purpose,referenceBox,referenceFields,host,loadGeneration=0;
  const message=text=>{status.textContent=text;};
  async function loadBrands(id){
    const rows=await api('/api/brands');selected.replaceChildren();const none=make('option','No brand context — general review');none.value='';selected.append(none);
    for(const row of rows){const option=make('option',row.name);option.value=row.id;selected.append(option);}selected.value=id||'';await loadProfile();
  }
  async function loadProfile(){
    const generation=++loadGeneration,id=selected.value;
    const loaded=id?await api(`/api/brands/${id}`):null;
    if(generation!==loadGeneration||id!==selected.value)return;
    profile=loaded;
    for(const [kind,inputs] of Object.entries(documents)){inputs.text.value=profile?.documents[kind]?.text||'';inputs.file.value='';inputs.saved.textContent=profile?.documents[kind]?`${profile.documents[kind].name} · ${profile.documents[kind].characters} characters saved`:'No document attached';}
    referenceList.replaceChildren();
    for(const ref of profile?.references||[]){
      const row=make('div',undefined,'brand-reference'),link=make('a',`Reference ${ref.job_id.slice(0,8)}`);link.href=`/?job=${ref.job_id}`;link.target='_blank';link.rel='noopener';row.append(link,make('p',formatOutcomes(ref.outcomes),'brief-note'));
      const remove=make('button','Remove reference','text-button');remove.type='button';remove.onclick=async()=>{try{await api(`/api/brands/${selected.value}/references/${ref.job_id}`,{method:'DELETE'});await loadProfile();}catch(e){message(e.message);}};row.append(remove);referenceList.append(row);
      const results=make('details');results.append(make('summary','Update reference results'));const values=outcomeFields(results,'Saved reference ');values.fill(ref.outcomes||{});const save=make('button','Save reference results','download');save.type='button';save.onclick=async()=>{save.disabled=true;try{await api(`/api/brands/${selected.value}/references`,json({job_id:ref.job_id,outcomes:values.read()}));await loadProfile();}catch(e){message(e.message);save.disabled=false;}};results.append(save);row.append(results);
      api(`/api/jobs/${ref.job_id}`).then(j=>{link.textContent=j.filename||link.textContent;}).catch(()=>{});
    }
    if(profile)message(`${profile.name} · version ${profile.version} · ${profile.references.length}/5 references · ${profile.calibration.sample_count} rated candidate videos. ${profile.calibration.active?'Feedback adjustment active.':'Learning needs 5 varied candidate ratings; successful references are excluded.'}`);
    else message('Everything here is optional. Create or select a brand to save context for future videos.');
    referenceBox.hidden=purpose.value!=='reference';
  }
  async function saveDocuments(){
    if(selected.value&&profile?.id!==selected.value)throw new Error('The selected brand is still loading. Wait for its documents before analyzing.');
    const pending=Object.entries(documents).filter(([kind,v])=>v.file.files.length||v.text.value.trim()!==(profile?.documents[kind]?.text||''));
    if(!pending.length)return;
    if(!selected.value)throw new Error('Create or select a brand before attaching documents.');
    ++loadGeneration;
    const states=Array.from(host.querySelectorAll('input,select,textarea,button'),n=>[n,n.disabled]);states.forEach(([n])=>n.disabled=true);
    try{
    for(const [kind,inputs] of pending){
      if(!inputs.file.files.length&&!inputs.text.value.trim())throw new Error('Use Remove document to clear a saved document.');
      const form=new FormData();if(inputs.file.files[0])form.append('file',inputs.file.files[0]);else form.append('text',inputs.text.value);
      profile=await api(`/api/brands/${selected.value}/documents/${kind}`,{method:'POST',body:form});inputs.file.value='';inputs.text.value=profile.documents[kind].text;inputs.saved.textContent=`${profile.documents[kind].name} · ${profile.documents[kind].characters} characters saved`;
    }
    message('Brand documents saved. New uploads will use this version.');
    }finally{states.forEach(([n,disabled])=>n.disabled=disabled);}
  }
  function formatOutcomes(o={}){return [o.team_rating!==undefined?`Team: ${o.team_rating}/100`:null,o.views!==undefined?`Views: ${o.views}`:null,o.retention_percent!==undefined?`Viewed: ${o.retention_percent}%`:null,o.conversions!==undefined?`Conversions: ${o.conversions}`:null,o.spend!==undefined?`Spend: ${o.spend}`:null,o.distribution&&o.distribution!=='unknown'?o.distribution:null].filter(Boolean).join(' · ')||'Success marked by your team; no measured results supplied.';}
  window.appendBrandContext=async form=>{await saveDocuments();if(purpose.value==='reference'&&!selected.value)throw new Error('Choose a brand for this successful reference.');form.append('brand_id',selected.value);form.append('purpose',purpose.value);if(purpose.value==='reference')form.append('outcomes',JSON.stringify(referenceFields.read()));};
  window.setBrandBusy=busy=>{if(host)host.querySelectorAll('input,select,textarea,button').forEach(n=>n.disabled=busy);};
  document.addEventListener('DOMContentLoaded',async()=>{
    host=make('section',undefined,'panel brand-panel');host.append(make('h2','Brand context and successful references (optional)'),make('p','Save guidelines, product facts and past examples per brand. New uploads use the selected brand’s saved version. Saved files stay on this computer; NVIDIA receives video and context for API analysis.','brief-note'));
    const label=make('label','Saved brand');selected=make('select');selected.id='brandSelect';selected.setAttribute('aria-label','Saved brand');label.append(selected);host.append(label);
    const createRow=make('div',undefined,'brand-grid'),name=field(createRow,'New brand name');name.maxLength=100;const create=make('button','Create brand','download');create.type='button';createRow.append(create);host.append(createRow);
    status=make('p','Loading brands…','brief-note');status.setAttribute('role','status');host.append(status);
    const purposeLabel=make('label','This upload is');purpose=make('select');purpose.id='uploadPurpose';purpose.setAttribute('aria-label','This upload is');for(const [value,text] of [['candidate','A new video to evaluate'],['reference','A successful reference to learn from']]){const o=make('option',text);o.value=value;purpose.append(o);}purposeLabel.append(purpose);host.append(purposeLabel);
    const details=make('details');details.append(make('summary','Optional brand guidelines and product brief'));
    for(const [kind,title] of [['guidelines','Video guidelines'],['product_brief','Product brief']]){
      const area=make('div',undefined,'brand-document');area.append(make('h3',title));const file=field(area,`${title} file`,'file');file.accept='.pdf,.docx,.txt,.md';const text=field(area,`${title} text (or paste/edit extracted text)`,'textarea');text.maxLength=12000;text.rows=4;
      file.onchange=()=>{if(file.files[0])text.value='';};text.oninput=()=>{file.value='';};const saved=make('p','No document attached','brief-note');area.append(saved);
      const remove=make('button','Remove document','text-button');remove.type='button';remove.onclick=async()=>{try{if(!selected.value)return;await api(`/api/brands/${selected.value}/documents/${kind}`,{method:'DELETE'});await loadProfile();}catch(e){message(e.message);}};area.append(remove);details.append(area);documents[kind]={file,text,saved};
    }
    details.append(make('p','PDF, DOCX, UTF-8 TXT or Markdown · 5 MB and 12,000 extracted characters per document. Scanned PDFs need selectable text or pasted instructions.','brief-note'));
    const save=make('button','Save brand documents','download');save.type='button';save.onclick=async()=>{try{await saveDocuments();}catch(e){message(e.message);}};details.append(save);host.append(details);
    referenceBox=make('div',undefined,'brand-document');referenceBox.hidden=true;referenceBox.append(make('h3','Why this reference worked'),make('p','Use the main video upload above. Studio analyzes the reference once and adds it to this brand after completion. These fields are optional.','brief-note'));referenceFields=outcomeFields(referenceBox,'Reference ');host.append(referenceBox);
    const refs=make('details');refs.append(make('summary','Saved successful references (up to 5)'));referenceList=make('div');refs.append(referenceList);
    const jobId=field(refs,'Or add an existing completed report ID');jobId.maxLength=32;const attach=make('button','Use completed video as reference','download');attach.type='button';attach.onclick=async()=>{try{if(!selected.value)throw new Error('Select a brand first.');await api(`/api/brands/${selected.value}/references`,json({job_id:jobId.value.trim()}));jobId.value='';await loadProfile();}catch(e){message(e.message);}};refs.append(attach);host.append(refs);
    document.getElementById('analysisForm').append(host);selected.onchange=()=>loadProfile().catch(e=>message(e.message));purpose.onchange=()=>referenceBox.hidden=purpose.value!=='reference';create.onclick=async()=>{try{const row=await api('/api/brands',json({name:name.value}));name.value='';await loadBrands(row.id);}catch(e){message(e.message);}};
    try{await loadBrands();}catch(e){message(e.message);}
  });
  window.renderBrandReview=(report,id,container)=>{
    if(selected?.value)loadProfile().catch(e=>message(e.message));
    const brand=report.review?.brand_review;
    if(brand){
      const section=make('section',undefined,'report-section');section.append(make('h2',`Brand fit · ${brand.brand_name}`),make('p',`Brand-aligned overall ${brand.overall_score}/100 · range ${brand.range.join('–')} · brand alignment ${brand.compliance_score??'not scored'}/100 · ${brand.checked}/${brand.total_checks} checks assessed`,'brief-note'),make('p',brand.scoring_note,'brief-note'),make('p',`Team feedback adjustment: ${brand.calibration.adjustment>0?'+':''}${brand.calibration.adjustment} points from ${brand.calibration.sample_count} rated candidates. ${brand.snapshot_note}`,'brief-note'));
      for(const check of brand.checks){const card=make('article',undefined,'panel review-card');card.append(make('h3',`${check.status.toUpperCase()} · ${check.requirement}`),make('blockquote',check.quote),make('p',`${check.document_name} · section ${check.section}`,'brief-note'),make('p',check.reason),make('p',`Change / check: ${check.change}`),make('p',`Video evidence: ${check.source_ids.join(', ')||'insufficient evidence'}`,'brief-note'));section.append(card);}container.append(section);
      const comparisons=make('section',undefined,'report-section');comparisons.append(make('h2','Compared with your successful videos'));
      if(!brand.comparisons.length)comparisons.append(make('p','No analyzed references were attached when this video was uploaded.','brief-note'));
      if(brand.team_advice){comparisons.append(make('h3','Applying saved team feedback'),make('p',brand.team_advice.guidance,'brief-note'));}
      for(const row of brand.comparisons){const card=make('article',undefined,'panel review-edit'),link=make('a',row.reference.name);link.href=`/?job=${row.reference.job_id}`;link.target='_blank';link.rel='noopener';card.append(link,make('p',formatOutcomes(row.reference.outcomes),'brief-note'));for(const [key,label] of [['similarities','What matches'],['differences','What differs'],['adapt','What to adapt'],['caution','What limits the comparison']])card.append(make('h4',label),make('p',row[key]));card.append(make('p',`Current evidence: ${row.source_ids.join(', ')} · Reference evidence: ${row.reference_source_ids.join(', ')}`,'brief-note'));comparisons.append(card);}container.append(comparisons);
    }
    const feedback=make('section',undefined,'report-section brand-panel');feedback.hidden=true;container.append(feedback);
    api(`/api/jobs/${id}/feedback`).then(data=>{
      if(!data.enabled)return;feedback.hidden=false;feedback.append(make('h2',`Teach future reviews · ${data.brand}`),make('p','Save your team’s rating and actual results after publishing. Feedback affects future uploads for this brand; it does not change this saved report or train model weights. A balanced set of strong and weak candidates is needed.','brief-note'));
      const values=outcomeFields(feedback,'Actual ');values.fill(data.feedback);const button=make('button','Save team feedback and results','download'),note=make('p','', 'brief-note');button.type='button';button.onclick=async()=>{button.disabled=true;try{const saved=await api(`/api/jobs/${id}/feedback`,json(values.read()));note.textContent=`Saved. ${saved.calibration.sample_count} rated candidates; ${saved.calibration.active?'brand score adjustment active':'score tuning starts after 5 distinct candidates with a rating spread of 20+ points'}.`;}catch(e){note.textContent=e.message;}finally{button.disabled=false;}};feedback.append(button,note);
    }).catch(()=>{});
  };
})();
