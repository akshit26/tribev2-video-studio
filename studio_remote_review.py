"""Cloud visual review with bounded Whisper pacing and cognitive audit."""
import asyncio
import hashlib
import json
import time
from pathlib import Path


def write_json(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    for attempt in range(20):
        try:
            temporary.replace(path)
            break
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(.05)


def review_video(video, output, progress):
    """One unified cloud review, after concurrent frame/audio extraction."""
    from studio_pipeline import run_cognitive_audit
    from studio_virality import DEFAULT_COGNITIVE_MODEL
    start=time.time()
    output=Path(output)
    fingerprint=hashlib.sha256(Path(video).read_bytes()).hexdigest()
    def read_metadata(filename):
        try:
            value=json.loads((output/filename).read_text(encoding='utf-8'))
            return value if isinstance(value,dict) else {}
        except (OSError,ValueError):return {}
    upload=read_metadata('upload_info.json')
    brand=read_metadata('brand_context.json')
    brief={k:upload[k] for k in ('language','platform','audience') if k in upload}
    if brand:
        product_brief=brand.get('documents',{}).get('product_brief',{})
        facts=product_brief.get('text','') if isinstance(product_brief,dict) else str(product_brief or '')
        brief.update(brand_context=brand,topic=brand.get('name','Uploaded creator video'),
            facts=facts or 'No independently verified product facts supplied.')
    report={'backend':'nvidia','model':DEFAULT_COGNITIVE_MODEL,'result':{},
        'video':{'name':upload.get('original_name',video.name)},'video_sha256':fingerprint,'context':brief,'visual_frames':[],
        'processing':{'warnings':[]},'dashboard':{'status':'Review unavailable',
            'policy':'Uncalibrated editorial simulation; no measured retention or emotion.'}}
    try:
        unified=run_cognitive_audit(video,output,[],progress,brief=brief)
        if hashlib.sha256(Path(video).read_bytes()).hexdigest()!=fingerprint:
            raise ValueError('Recording changed during cognitive review. Analyze the current recording again.')
        report.update(unified)
        report['dashboard']['status']='Audit generated' if unified['audit']['triggered'] else 'Review ready'
        report['processing']['warnings']=[unified['pacing']['note']]+unified.get('evidence_warnings',[])
    except Exception as exc:
        report['cognitive_status']='unavailable'
        report['processing']['warnings'].append('Unified cognitive review unavailable: '+type(exc).__name__+'. No score was assigned.')
        pacing=read_metadata('transcript.json')
        if isinstance(pacing.get('available'),bool) and isinstance(pacing.get('text'),str):
            report['pacing']=pacing
            if type(pacing.get('duration_seconds')) in (int,float):report['video']['duration_seconds']=pacing['duration_seconds']
        report['processing']['elapsed_seconds']=round(time.time()-start,1)
        write_json(output/'report.json',report)
        raise RuntimeError('Unified cognitive review unavailable; completed speech evidence and upload are retained.') from exc
    pacing=report.get('pacing',{})
    duration=pacing.get('duration_seconds')
    if type(duration) in (int,float) and duration>0:report['video']['duration_seconds']=duration
    report['processing']['elapsed_seconds']=round(time.time()-start,1)
    write_json(output/'report.json',report)
    progress(99,'Unified audio-visual cognitive review ready')
    return report
