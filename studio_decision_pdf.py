"""Three-page decision brief; optional fourth page for brand context."""
import html
import re
from studio_viewer_response import viewer_response_map
from pathlib import Path


def concise(value, limit=350):
    value=' '.join(str(value or '').split())
    if len(value)<=limit:return value
    # Prefer a complete sentence; otherwise make omission explicit.
    ends=[m.end() for m in re.finditer(r'[.!?।](?:\s|$)',value[:limit])]
    if ends and ends[-1]>limit*.45:return value[:ends[-1]].strip()
    return value[:limit].rsplit(' ',1)[0]+'…'


def decisive_reason(row):
    """Choose the sentence that explains the grade without dumping a long rationale."""
    rationale = ' '.join(str(row.get('rationale') or '').split())
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', rationale)
    sentences = [s for s in sentences if not re.search(
        r'\b(?:ocr|transcription)\b.{0,50}\b(?:error|misspell|misread|noise)', s, re.I)]
    if not sentences:
        return 'Check the cited evidence before editing.'
    if row.get('key') == 'hook' and 'supported by screen overlay' in sentences[0]:
        return concise(sentences[0].split(', supported by screen overlay')[0].rstrip(' ,.') + '.', 215)
    if row.get('grade', 0) < 3:
        for sentence in sentences:
            if re.search(r'\b(?:however|but|lack|missing|absent|unsupported|unverified|limited|static|repetit|no distinct|not backed|without|unclear|weak)\w*\b', sentence, re.I):
                return concise(sentence, 215)
    return concise(sentences[0], 215)


def decision_html(report, directory=None):
    from studio_screenshots import screenshot_html
    esc=lambda s:html.escape(str(s or ''),quote=True)
    text=lambda s,n=350:esc(concise(s,n))
    review=report.get('review') or {};brief=report.get('brief') or {};video=report['video']
    score=review.get('overall_score',brief.get('overall_score'));brand=review.get('brand_review')
    from studio_virality import check_virality
    virality=review.get('virality') or check_virality(review)
    estimate=review.get('estimate',{});interval=(brand or estimate).get('range')
    source={s['id']:s for s in review.get('sources',[])}
    def span(ids):
        selected=[source[i] for i in ids if i in source]
        return f"{min(s['start'] for s in selected):.1f}–{max(s['end'] for s in selected):.1f}s" if selected else ''
    def moments(ids):
        times=sorted({round(source[i]['start'],1) for i in ids if i in source})
        if len(times)>3:times=[times[0],times[len(times)//2],times[-1]]
        return ', '.join(f'{t:.1f}s' for t in times)
    def frame_html(frames,limit=1):
        return screenshot_html(frames[:limit],Path(directory)) if directory and frames else ''
    def sheet(number,title,body):
        return f'<section class="sheet"><div class="content"><div class="eyebrow">VIDEO DECISION BRIEF <span>{text(video.get("name","Video"),85)}</span></div><h1>{title}</h1>{body}</div><footer>{video["duration_seconds"]:.1f}s · {text(review.get("content_language",report.get("transcript",{}).get("language","")),45)}<span>{number} / 4</span></footer></section>'
    # Keep the reader oriented using actual source images, not generated artwork.
    frames=[]
    for clip in brief.get('clips',[]):
        for f in clip.get('screenshots',[]):
            if f.get('file') and all(v.get('file')!=f['file'] for v in frames):frames.append(f)
    if report.get('ocr',{}).get('sources'):
        available=report['ocr']['sources'];picks=[available[0],available[len(available)//2],available[-1]]
        frames=[{'file':s['frame_file'],'time_seconds':s['start'],'label':f"{s['start']:.1f}s"} for s in picks]
    strengths=review.get('strengths',brief.get('strengths',[]))[:3]
    summary=review.get('summary',brief.get('summary','The available evidence is insufficient for a creative assessment.'))
    by_key={row['key']:row for row in review.get('dimensions',[])}
    if review.get('available'):
        if by_key.get('cta',{}).get('grade',4)<=1 and not re.search(r'\b(?:cta|next action|viewer action)\b',summary,re.I):
            summary+=' The close needs one clear viewer action and destination.'
        if by_key.get('visual',{}).get('grade',4)<=2 and not re.search(r'\b(?:visual|shot|frame|footage)\b',summary,re.I):
            summary+=' '+decisive_reason(by_key['visual'])
    provisional=bool(interval and interval[1]-interval[0]>30)
    status='Verify wording first' if provisional else ('Revise before publishing' if score is not None and score<70 else 'Ready for final checks' if score is not None else 'More evidence needed')
    hero=f'<div class="hero"><div class="hero-score"><div class="score">{score if score is not None else "—"}<small>/100</small></div><small>Overall rating</small></div>'
    if virality:
        hero+=f'<div class="hero-score viral-score"><div class="score">{virality["score"]}<small>/100</small></div><small>Virality checker</small></div>'
    hero+=f'<div><h2>{status}</h2><p>{text(review.get("verdict","Creative assessment"),160)}</p><p class="small">Estimated creative quality'+(f' · sensitivity range {interval[0]}–{interval[1]}' if interval else '')+'. Virality is an editing index, not predicted views.</p></div></div>'
    bars=[];adjusted={r['key']:r for r in estimate.get('dimensions',[])}
    for row in review.get('dimensions',[]):
        value=max(0,min(100,adjusted.get(row['key'],{}).get('estimated_score',row.get('score',row.get('grade',0)*25))))
        bars.append(f'<div class="barrow"><label>{esc(row["label"])}</label><div class="track"><i style="width:{value}%"></i></div><b>{value:.0f}</b></div>')
    wins=''.join(f'<article class="win"><h3>{text(s.get("title","Strength"),90)}</h3><p>{text(s.get("detail",""),210)}</p><small>{span(s.get("source_ids",[]))}</small></article>' for s in strengths)
    viral_strip=''
    if virality:
        checks=''.join(f'<div><b>{text(row["label"],27)}</b><strong>{row["score"]}</strong></div>' for row in virality['levers'])
        weak=virality['priorities'][0] if virality['priorities'] else None
        priority=(f'<p class="small viral-priority"><b>First virality fix:</b> {text(weak["lever"],35)}'
                  + (f' at {weak["edit"]["start"]:.1f}s: {text(weak["edit"]["instruction"],105)}' if weak and weak['edit'] else f' — strengthen {text(weak["bottleneck"],40)}')
                  + '</p>') if weak else ''
        viral_strip=f'<div class="viral-strip">{checks}</div>'+priority+'<p class="small">Virality checker compares creative spread signals only. It is not a chance of going viral or a forecast of views.</p>'
    p1=hero+viral_strip+f'<p class="lead">{text(summary,750)}</p><div class="columns"><div><h2>Creative scorecard</h2>'+''.join(bars)+'</div><div><h2>Best things to keep</h2>'+wins+'</div></div><h2>The video at a glance</h2><div class="storyboard">'+''.join(frame_html([f]) for f in frames[:3])+'</div>'
    pages=[sheet(1,'The decision in one view',p1)]
    narrative=review.get('narrative_breakdown',{})
    if not narrative:
        narrative={'hook':'Opening: '+(source.get('S1',{}).get('text') or 'No usable opening speech.'),
                   'problem':summary,'product':'Product identity must be supported by the spoken name or a legible label.',
                   'resolution':next((s['text'] for s in reversed(list(source.values())) if s.get('kind')!='ocr'),'No usable closing speech.')}
    rows=''.join(f'<article class="beat"><div class="step">{i}</div><div><h3>{key.title()}</h3><p>{text(narrative.get(key,"Not established by the available evidence."),300)}</p></div></article>' for i,key in enumerate(('hook','problem','product','resolution'),1))
    ocr=report.get('ocr',{}).get('sources',[])
    from studio_ocr import CTA,PRODUCT,reading_text
    priority=sorted(ocr,key=lambda s:(not bool(CTA.search(s['text'])),not bool(PRODUCT.search(s['text']))))[:6]
    overlays=''.join(f'<tr><td>{s["start"]:.1f}–{s["end"]:.1f}s</td><td>{text(reading_text(s["text"]),150)}</td></tr>' for s in priority)
    lang=review.get('linguistic_review',{})
    observed=lang.get('noted_slang',[])
    note=lang.get('spoken_accuracy') or ('Speech needs a fluent-speaker check before acting on detailed wording.' if provisional else 'Keep the original language and natural delivery; verify names and product claims.')
    p2='<p class="sub">What the audience encounters, from the first frame to the final action.</p>'+rows+'<h2>On-screen evidence</h2>'+(f'<table><thead><tr><th>Time</th><th>Observed text / label</th></tr></thead><tbody>{overlays}</tbody></table>' if overlays else '<p class="muted">No reliable OCR evidence was saved for this review. This does not establish that overlays are absent.</p>')+f'<div class="callout"><b>Language and delivery</b><p>{text(note,270)}</p>'+(f'<p>Natural expressions: {text("; ".join(map(str,observed)),160)}</p>' if observed else '')+'</div>'
    order={'hook':0,'clarity':1,'voice':2,'visual':3,'structure':4,'credibility':5,'emotion':6,'cta':7}
    dimensions=sorted(review.get('dimensions',[]),key=lambda row:order.get(row['key'],99))
    def diagnosis_card(row):
        at=moments(row.get('source_ids',[])) or 'supplied evidence'
        return (f'<article class="diagnosis"><div class="diaghead"><b>{text(row["label"],55)}</b>'
                f'<strong>{row["grade"]}/4</strong></div><p>{text(decisive_reason(row),220)}</p>'
                f'<small>Evidence near {esc(at)}</small></article>')
    def response_html():
        response=review.get('viewer_response') or viewer_response_map(dimensions)
        if not response:return ''
        return '<h2>Likely viewer-response bottlenecks</h2><div class="response-grid">'+''.join(
            f'<div class="response"><b>{text(r["label"],30)} · {text(r["status"],20)}</b>'
            f'<span>Limited by {text(r["bottleneck"],35)} ({r["bottleneck_grade"]}/4)</span></div>'
            for r in response)+'</div><p class="small">Editing hypotheses from creative grades; brain activity and audience behavior were not measured.</p>'
    if brand and dimensions:
        key_rows=[r for r in dimensions if r['key'] in {'clarity','voice','visual'}]
        p2+='<h2>Script, voice and visuals</h2><div class="diagnosis-grid compact-diagnosis">'+''.join(diagnosis_card(r) for r in key_rows)+'</div>'
    pages.append(sheet(2,'The story and the evidence',p2))
    edits=review.get('edits',[])
    if score is not None and score<70:
        cards=[]
        for i,e in enumerate(edits[:3],1):
            pictures=frame_html(e.get('screenshots',[]))
            cards.append(f'<article class="edit"><div class="edithead"><b>{i}. {text(e["title"],105)}</b><span>{e["start"]:.1f}–{e["end"]:.1f}s · {esc(e["operation"].upper())}</span></div><div class="editbody">{pictures}<div><p><b>Do:</b> {text(e["instruction"],280)}</p><blockquote>{text(e["replacement"],360)}</blockquote><p class="small"><b>Meaning:</b> {text(e.get("english_gloss",""),170)}</p><p><b>Check:</b> {text(e["verify"],180)}</p></div></div></article>')
        p3='<p class="sub">Make these priority changes, then assess the revised cut. A score above 70 is an editing target, not a promised result.</p>'+''.join(cards)
        if not cards:p3+='<p>Verify the missing evidence before prescribing edits.</p>'
    else:
        p3='<p class="lead">Preserve the effective opening, product message and CTA. Make only changes supported by the evidence.</p>'+wins+'<h2>Final publishing check</h2><ul><li>Product name and claims match the approved brief.</li><li>Closing speech or overlay gives one clear action and preserves the exact response keyword.</li><li>On-screen text is legible; names and regional wording are correct.</li></ul>'
    concerns=[c for c in review.get('uncertainties',[]) if c][:2]
    p3+='<div class="callout"><b>Before approving the cut</b><p>'+text(' '.join(concerns) or 'Verify product claims before publishing.',300)+'</p><p>Have a fluent speaker approve replacement wording before sharing it with the creator.</p></div>'
    pages.append(sheet(3,'Priority edits for the next cut' if score is not None and score<70 else 'Keep, verify, publish',p3))
    if brand:
        checks=sorted(brand.get('checks',[]),key=lambda c:{'conflicts':0,'missing':1,'partial':2,'unknown':3,'meets':4}[c['status']])
        checklist=''.join(f'<tr><td>{esc(c["status"].upper())}</td><td><b>{text(c["requirement"],100)}</b><br>{text(c["change"],145)}</td></tr>' for c in checks[:8])
        refs=''.join(f'<article class="win"><h3>{text(r["reference"]["name"],80)}</h3><p>{text(r["adapt"],220)}</p><p class="small">{text(r["caution"],130)}</p></article>' for r in brand.get('comparisons',[])[:2])
        p4=f'<p class="lead">{text(brand["brand_name"],90)} · brand fit {brand.get("compliance_score","—")}/100 · {brand.get("checked",0)}/{brand.get("total_checks",0)} checks assessed</p><table><thead><tr><th>Status</th><th>Requirement and action</th></tr></thead><tbody>{checklist}</tbody></table>'+response_html()+'<h2>Lessons from successful references</h2>'+(refs or '<p>No successful references were attached.</p>')+f'<p class="small">Showing the {min(8,len(checks))} highest-priority checks of {len(checks)}. Unknown evidence is not a confirmed failure. Reference success does not guarantee the same result.</p>'
        pages.append(sheet(4,'Brand fit and reference lessons',p4))
    else:
        visual_frames=[v for v in report.get('ocr',{}).get('sources',[]) if v.get('frame_file')]
        sampled=[{'file':v['frame_file'],'time_seconds':v['start'],'label':f"{v['start']:.1f}s"}
                 for v in visual_frames]
        picks=[sampled[len(sampled)//3],sampled[2*len(sampled)//3]] if len(sampled)>2 else sampled[:2]
        if not picks:
            picks=[f for clip in brief.get('clips',[]) for f in clip.get('screenshots',[])][:2]
        p4='<p class="sub">Each grade is tied to the cited part of the original video. A grade of 2/4 means functional with clear weaknesses; 3/4 needs strong execution.</p>'
        p4+='<div class="diagnosis-grid">'+''.join(diagnosis_card(r) for r in dimensions)+'</div>'
        from studio_ocr import PRODUCT
        def cited_source(key, *, latest=False, quantified=False):
            row=by_key.get(key,{})
            candidates=[source[i] for i in row.get('source_ids',[]) if i in source and source[i]['kind'] in {'speech','ocr'}]
            if quantified:
                measured=[s for s in candidates if re.search(r'\d|%',s['text'])]
                if measured:candidates=measured
            if not candidates:return None
            return sorted(candidates,key=lambda s:s['start'])[-1 if latest else 0]
        product=next((s for s in sorted(source.values(),key=lambda s:s['start'])
                      if s['kind']=='speech' and PRODUCT.search(s['text'])),None)
        moments_rows=[]
        for label,item,note in (
            ('Opening',cited_source('hook'),'The opening states the reason to keep watching.'),
            ('Product',product,'The product is named here; check the pack and approved wording.'),
            ('Claim',cited_source('credibility',quantified=True),'A specific efficacy claim needs approved substantiation.'),
            ('Close',cited_source('cta',latest=True),
             'The closing slogan lacks a viewer action or destination.' if by_key.get('cta',{}).get('grade',4)<=1
             else 'The final viewer action appears here.')):
            if item:
                quote=item['text']
                if label=='Claim' and item['kind']=='speech' and not re.search(r'[.!?]$',quote.strip()):
                    following=next((s for s in source.values() if s['kind']=='speech' and
                                    0<=s['start']-item['end']<=.25),None)
                    if following:quote+=' '+following['text']
                quote=re.sub(r'(?<=\d)\s*\.\s*(?=\d)', '.', quote)
                quote=re.sub(r'(?<=\d)\s+%', '%', quote)
                moments_rows.append(f'<tr><td>{esc(label)}<br><small>{item["start"]:.1f}s</small></td>'
                                    f'<td>{text(quote,125)}</td><td>{text(note,105)}</td></tr>')
        if moments_rows:
            p4+='<h2>Key moments in the original cut</h2><table class="moment-table"><thead><tr><th>Beat</th><th>Original speech or overlay</th><th>What it shows</th></tr></thead><tbody>'+''.join(moments_rows)+'</tbody></table>'
        p4+=response_html()
        if picks:p4+='<h2>Frames behind the visual grade</h2><div class="evidence-frames">'+frame_html(picks,2)+'</div>'
        p4+='<p class="small">Sampled frames and audio measurements cannot establish every shot, authentic emotion, or future view counts. Check the actual cut before making final claim and delivery decisions.</p>'
        pages.append(sheet(4,'Why each grade was given',p4))
    css='''@page{size:A4;margin:0}*{box-sizing:border-box}body{margin:0;color:#182c39;font:10pt/1.4 "Segoe UI","Nirmala UI",sans-serif}.sheet{width:210mm;height:297mm;padding:12mm 14mm;position:relative;break-after:page;background:#fff}.sheet:last-child{break-after:auto}.content{height:263mm}.eyebrow{font-size:8px;letter-spacing:1.7px;color:#62767e;border-bottom:1px solid #d9e4e7;padding-bottom:10px}.eyebrow span{float:right;letter-spacing:0;font-size:9px;max-width:65%}h1{font-size:27px;line-height:1.2;margin:17px 0}h2{font-size:16px;margin:16px 0 9px}h3{font-size:12px;line-height:1.3;margin:0 0 4px}p{margin:6px 0;overflow-wrap:anywhere}.lead{font-size:12px;line-height:1.5}.sub,.small,small{font-size:10px;line-height:1.4;color:#52666f}.hero{display:flex;gap:24px;background:#edf5f4;border-radius:12px;padding:18px;align-items:center}.hero h2{margin:0;font-size:19px}.hero-score{min-width:90px;text-align:center}.hero-score>.score{line-height:1}.hero-score>small{display:block;white-space:nowrap;font-size:9px}.viral-score{border-left:1px solid #cbdcda;padding-left:18px}.viral-score .score{color:#ae6827}.viral-strip{display:grid;grid-template-columns:repeat(5,1fr);gap:5px;margin-top:9px}.viral-strip>div{display:flex;justify-content:space-between;gap:4px;padding:5px 6px;background:#f5eee5;border-radius:5px;font-size:8px}.viral-strip strong{color:#9a5c22}.score{font-size:57px;font-weight:700;color:#176c62;white-space:nowrap}.score small{font-size:15px;margin-left:4px}.columns{display:grid;grid-template-columns:1fr 1fr;gap:24px}.barrow{display:grid;grid-template-columns:95px 1fr 25px;gap:7px;align-items:center;margin:13px 0;font-size:10px}.track{height:9px;border-radius:7px;background:#e5edee}.track i{display:block;background:#238b7c;height:9px;border-radius:7px}.win{border-bottom:1px solid #dce5e6;padding:10px 0;font-size:11px}.storyboard{display:flex;gap:18px;margin-top:12px}.screenshots{display:flex;gap:10px;margin:0}.storyboard>.screenshots{flex:1}.screenshots figure{margin:0}.screenshots img{height:155px;max-width:180px;object-fit:contain;display:block;border-radius:7px}.screenshots figcaption{font-size:9px;color:#69777b;margin-top:4px}.beat{display:flex;gap:14px;padding:12px;background:#f4f7f8;border-radius:8px;margin:10px 0}.step{border-radius:50%;background:#dfebe9;color:#176c62;min-width:28px;height:28px;text-align:center;padding-top:5px;font-weight:bold}.beat p{font-size:11px}.callout{padding:12px 14px;border-left:3px solid #d49734;background:#fff7e8;margin-top:17px;font-size:11px}table{width:100%;border-collapse:collapse;font-size:10px}th{text-align:left;background:#eaf1f3}th,td{padding:8px;border-bottom:1px solid #dbe5e8;vertical-align:top}td:first-child{width:90px;white-space:nowrap}.edit{border:1px solid #dce5e6;border-radius:9px;margin:14px 0;padding:13px}.edithead{display:flex;justify-content:space-between;gap:16px;font-size:12px}.edithead span{font-size:9px;white-space:nowrap}.editbody{display:flex;gap:15px;margin-top:10px;font-size:11px}.editbody>.screenshots{flex:0 0 98px}.editbody .screenshots img{max-width:98px;height:120px}.editbody>div:last-child{flex:1}.edit blockquote{font-size:12px;margin:8px 0;padding:9px;background:#edf6f3;border-left:3px solid #298c7b;overflow-wrap:anywhere}footer{position:absolute;bottom:8mm;left:14mm;right:14mm;border-top:1px solid #dce5e6;padding-top:7px;color:#60727b;font-size:9px}footer span{float:right}.compact{font-size:9pt}.compact .beat{padding:9px}.compact .edit{margin:10px 0;padding:10px}.compact .editbody{font-size:10px}.compact .edit blockquote{font-size:11px}.compact .lead{font-size:11px}.compact th,.compact td{padding:6px}.diagnosis-grid{display:grid;grid-template-columns:1fr 1fr;gap:9px 12px;margin-top:12px}.diagnosis{border:1px solid #dce5e6;border-radius:8px;padding:9px 10px;break-inside:avoid;background:#f9fbfb}.diaghead{display:flex;justify-content:space-between;gap:8px;font-size:11px}.diaghead strong{color:#176c62}.diagnosis p{font-size:10px;line-height:1.3;margin:4px 0}.diagnosis small{font-size:8.5px;color:#60727b}.evidence-frames .screenshots img{height:115px;max-width:140px}.compact-diagnosis{grid-template-columns:repeat(3,1fr);gap:7px}.compact-diagnosis .diagnosis{padding:7px}.compact-diagnosis .diagnosis p{font-size:9px}.moment-table{font-size:9px;margin-top:7px}.moment-table th,.moment-table td{padding:5px 7px;line-height:1.25}.moment-table td:first-child{width:56px;white-space:normal}.moment-table td:nth-child(2){width:38%}.moment-table small{font-size:8px}.response-grid{display:grid;grid-template-columns:1fr 1fr;gap:5px 12px}.response{padding:4px 7px;background:#edf5f4;border-radius:5px;font-size:9px;display:flex;justify-content:space-between;gap:5px}.response span{color:#52666f}.sheet:last-child .diagnosis-grid{gap:5px 8px;margin-top:7px}.sheet:last-child .diagnosis{padding:6px 8px}.sheet:last-child h2{margin:9px 0 5px}.sheet:last-child .evidence-frames .screenshots img{height:95px}'''
    return '<!doctype html><html><head><meta charset="utf-8"><style>'+css+'</style></head><body>'+''.join(pages)+'</body></html>'
