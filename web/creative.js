"use strict";
window.renderCreative = function(report,id) {
  const byId=id=>document.getElementById(id);
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);if(cls)n.className=cls;return n;};
  const data=report.brief;
  const asset=filename=>`/api/jobs/${encodeURIComponent(id)}/files/${filename.split('/').map(encodeURIComponent).join('/')}`;
  byId('overallScore').textContent=data?.overall_score??'N/A';
  byId('scoreLabel').textContent=report.review?.estimate?'Estimated creative score':'Creative score';
  byId('scoreRange').textContent=report.review?.estimate?`${report.review.estimate.range[0]}–${report.review.estimate.range[1]} sensitivity range`:'';
  if(report.review?.brand_review){byId('scoreLabel').textContent='Brand-aligned overall';byId('scoreRange').textContent=report.review.brand_review.range.join('–')+' sensitivity range';}
  const viral=report.review?.virality;
  byId('viralityCard').hidden=!viral;
  byId('briefOverview').classList.toggle('without-virality',!viral);
  byId('viralityScore').textContent=viral?.score??'';
  byId('briefVerdict').textContent=data?.verdict||'This older report needs a fresh analysis';
  byId('briefSummary').textContent=data?.summary||'Upload the video again to generate the concise review and playable excerpts.';
  byId('briefScoreNote').textContent=data?.score_note||'';
  for(const [key,target] of [['strengths','briefStrengths'],['changes','briefChanges']]){
    byId(target).replaceChildren();
    for(const item of data?.[key]||[]){const li=node('li');li.append(node('strong',item.title),node('p',item.detail));byId(target).append(li);}
    if(key==='strengths'&&!data?.strengths?.length)byId(target).append(node('li','No clear strengths could be established from the available evidence.'));
  }
  byId('briefClips').replaceChildren();
  for(const clip of data?.clips||[]){
    const card=node('article',undefined,'panel brief-clip');
    if(clip.file){
      const video=node('video');video.controls=true;video.preload='metadata';video.playsInline=true;video.src=asset(clip.file);video.setAttribute('aria-label',`${clip.title} excerpt`);
      video.addEventListener('play',()=>{for(const other of byId('briefClips').querySelectorAll('video'))if(other!==video)other.pause();});
      video.addEventListener('error',()=>{video.hidden=true;card.prepend(node('p','Clip playback unavailable. Download the clip to play it locally.','brief-note'));},{once:true});
      card.append(video);
    }
    const text=node('div',undefined,'brief-clip-copy');text.append(node('h3',clip.title),node('span',`${Number(clip.start).toFixed(1)} - ${Number(clip.end).toFixed(1)}s of original video`,'brief-time'),node('p',clip.reason));
    if(clip.file){const link=node('a','Download clip','download');link.href=asset(clip.file);link.download=`${clip.title.toLowerCase()}.mp4`;text.append(link);}
    else text.append(node('p',clip.error||'Clip unavailable.','brief-note'));
    card.append(text);byId('briefClips').append(card);
  }
  const detailed=byId('detailedReview');detailed.replaceChildren();
  const review=report.review;if(!review?.available)return;
  if(review.transcript_quality)detailed.append(node('p',review.transcript_quality.note,review.transcript_quality.withhold_score?'notice':'brief-note'));
  const sources=new Map(review.sources.map(s=>[s.id,s]));
  const refs=ids=>{const details=node('details',undefined,'review-evidence');details.append(node('summary','Speech / screen-text evidence'));for(const id of ids||[]){const s=sources.get(id);if(s)details.append(node('p',`${id} | ${s.start.toFixed(1)} - ${s.end.toFixed(1)}s: ${s.text}`));}return details;};
  const section=title=>{const s=node('section',undefined,'report-section');s.append(node('h2',title));detailed.append(s);return s;};
  if(viral){
    const check=section('Virality checker');
    check.append(node('p',`${viral.score}/100 creative spread index. ${viral.note}`,'brief-note'));
    const leverGrid=node('div',undefined,'review-score-grid');
    for(const lever of viral.levers){const card=node('article',undefined,'panel review-card');card.append(node('h3',lever.label),node('strong',`${lever.score}/100`,'review-grade'),node('p',lever.question),node('p',`Main constraint: ${lever.bottleneck}`,'brief-note'),refs(lever.source_ids));leverGrid.append(card);}
    check.append(leverGrid);
    for(const priority of viral.priorities){if(!priority.edit)continue;check.append(node('p',`Improve ${priority.lever} at ${priority.edit.start.toFixed(1)}–${priority.edit.end.toFixed(1)}s: ${priority.edit.instruction}`,'brief-note'));}
  }
  if(report.evaluation){
    const narrative=section('Creative structure');
    for(const [key,value] of Object.entries(report.evaluation.narrative_breakdown||{}))narrative.append(node('h3',key.charAt(0).toUpperCase()+key.slice(1)),node('p',value));
    const link=node('a','Download evaluation JSON','download');link.href=asset('evaluation.json');link.download='evaluation.json';narrative.append(link);
    const screen=section('On-screen text and labels');
    screen.append(node('p',report.ocr?.language_coverage||'Verify uncertain recognition against the frames.','brief-note'));
    for(const item of report.ocr?.sources||[]){const row=node('details',undefined,'panel review-card');row.append(node('summary',`${item.start.toFixed(1)} - ${item.end.toFixed(1)}s: ${item.text}`));const img=node('img');img.src=asset(item.frame_file);img.alt=`Source frame at ${item.start.toFixed(1)} seconds`;img.loading='lazy';img.style.maxWidth='100%';img.style.maxHeight='360px';row.append(img);screen.append(row);}
    const language=section('Language review');language.append(node('p',report.evaluation.linguistic_review.spoken_accuracy));
    for(const expression of report.evaluation.linguistic_review.noted_slang||[])language.append(node('p',expression));
  }
  window.renderBrandReview?.(report,id,detailed);
  const estimate=review.estimate;
  if(estimate){
    const adjustment=section('Language uncertainty adjustment');
    adjustment.append(node('h3',`${estimate.score}/100 estimated · sensitivity range ${estimate.range[0]}–${estimate.range[1]}`),node('p',`Before adjustment: ${estimate.raw_score}/100. Evidence weight: ${estimate.evidence_weight_percent}% — not transcription accuracy.`,'brief-note'),node('p',estimate.method,'brief-note'),node('p',estimate.range_note,'brief-note'));
  }
  const scoreSection=section('Why this score');scoreSection.append(node('p',`${review.content_language} | ${review.model}`,'brief-note'),node('p',review.anchors,'brief-note'));
  if(review.dimensions.some(r=>['whole_transcript_absence_check','supplied_evidence_absence_check'].includes(r.evidence_scope)))scoreSection.append(node('p','For a grade-zero absence assessment, the cited evidence is the search scope, not positive evidence of an absent feature. Recognition errors and unobserved visuals still need verification.','brief-note'));
  const grid=node('div',undefined,'review-score-grid');
  for(const row of review.dimensions){const card=node('article',undefined,'panel review-card');card.append(node('h3',row.label),node('strong',`${row.grade}/4`,'review-grade'),node('p',`${row.points} of ${row.weight} points before adjustment`,'brief-time'),node('p',row.rationale),refs(row.source_ids));const adjusted=estimate?.dimensions.find(d=>d.key===row.key);if(adjusted){card.append(node('p',`Adjusted: ${adjusted.estimated_points} / ${row.weight} points · evidence weight ${Math.round(adjusted.reliability*100)}%`,'brief-note'));if(adjusted.recognition_concern)card.append(node('p','The reviewer identified possible transcription errors in this category; its judgment has reduced weight.','brief-note'));}grid.append(card);}scoreSection.append(grid);
  if(review.viewer_response?.length){
    const response=section('Likely viewer-response bottlenecks');
    response.append(node('p','Editing hypotheses derived from the creative grades. Brain activity and actual audience response were not measured.','brief-note'));
    const responseGrid=node('div',undefined,'review-score-grid');
    for(const item of review.viewer_response){const card=node('article',undefined,'panel review-card');card.append(node('h3',item.label),node('strong',item.status,'review-grade'),node('p',`Limited by ${item.bottleneck} (${item.bottleneck_grade}/4). ${item.meaning}`),refs(item.source_ids));responseGrid.append(card);}
    response.append(responseGrid);
  }
  const plan=section(`Exact edit plan - target ${review.target.score}/100`);plan.append(node('p',review.target.explanation,'brief-note'));
  if(review.target.needs_improvement){
    plan.append(node('h3','Rubric priorities to work toward 75'));
    const priorities=node('ol');
    for(const item of review.target.priorities||[]){const li=node('li');li.append(node('strong',`${item.label}: ${item.grade}/4 now, aim for ${item.goal_grade}/4`),node('p',item.reason),node('p',`Apply edits ${item.edit_numbers.join(', ')} below, then check their acceptance criteria.`));priorities.append(li);}
    plan.append(priorities);
  }
  for(const [index,edit] of review.edits.entries()){
    const card=node('article',undefined,'panel review-edit');card.append(node('span',`${edit.start.toFixed(1)} - ${edit.end.toFixed(1)}s in source | ${edit.operation.toUpperCase()}`,'brief-time'),node('h3',`${index+1}. ${edit.title}`),node('p',edit.instruction));
    const replacement=node('blockquote',edit.replacement);replacement.lang=report.transcript?.language||'';card.append(node('h4','Exact replacement / edit'),replacement,node('p',`English meaning: ${edit.english_gloss}`),node('p',`Why: ${edit.why}`),node('p',`Acceptance check: ${edit.verify}`,'acceptance'),refs(edit.source_ids));plan.append(card);
  }
  const uncertainty=section('What to verify');const notes=node('ul',undefined,'brief-list');for(const note of review.uncertainties)notes.append(node('li',note));notes.append(node('li','Have a fluent speaker verify the transcript and suggested lines, especially mixed speech, dialects, product names and claims.'));uncertainty.append(notes);
  const spokenSources=review.sources.filter(s=>s.kind!=='ocr');
  const transcript=section('Original-language transcript');const details=node('details',undefined,'panel review-card');details.append(node('summary',`${spokenSources.length} timestamped segments - check these before relying on the score`));for(const s of spokenSources){const row=node('p');row.append(node('strong',`${s.id} | ${s.start.toFixed(1)} - ${s.end.toFixed(1)}s`),node('br'),node('span',s.text));details.append(row);}transcript.append(details);
  const corrections=node('details',undefined,'panel review-card');corrections.append(node('summary','Correct transcription errors and regenerate the review'),node('p','Correct what was actually spoken. This preserves source timestamps and reruns the review; it does not edit your video. The original transcript is kept locally.'));
  const fields=[];for(const s of spokenSources){const label=node('label',`${s.id} | ${s.start.toFixed(1)} - ${s.end.toFixed(1)}s`),input=node('textarea');input.value=s.text;input.rows=3;input.maxLength=3000;input.setAttribute('aria-label',`Correct segment ${s.id}`);label.append(input);fields.push(input);corrections.append(label);}
  const save=node('button','Save corrections and re-analyze','primary-button'),status=node('p');save.type='button';save.addEventListener('click',async()=>{save.disabled=true;status.textContent='Saving corrected transcript...';try{const response=await fetch(`/api/jobs/${encodeURIComponent(id)}/correct-transcript`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({texts:fields.map(f=>f.value)})});const result=await response.json();if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'Unable to save corrections.');location.href=`/?job=${encodeURIComponent(id)}`;}catch(error){status.textContent=error.message;save.disabled=false;}});corrections.append(save,status);transcript.append(corrections);
  const process=report.processing||{};detailed.append(node('p',`Observed total GPU peak: ${process.peak_gpu_mb??'unavailable'} MiB / target ${process.budget_mb??'unavailable'} MiB. Review device: ${review.device||'unavailable'}. The target is monitored, not a hard system-wide cap.`,'brief-note'));
};
