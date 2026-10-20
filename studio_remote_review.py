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
    from studio_gemma_video import analyze_virality, dashboard_state, NEMOTRON
    start = time.time()
    progress(10, 'NVIDIA is reviewing the uploaded video (up to 180 seconds)')
    result = asyncio.run(analyze_virality(video, NEMOTRON, include_evidence=True))
    visual_frames = result.pop('visual_frames', [])
    dashboard = dashboard_state(result)
    elapsed = round(time.time() - start, 1)
    state = dict(status='completed', model=NEMOTRON, result=result, dashboard=dashboard,
                 elapsed_seconds=elapsed, video_sha256=hashlib.sha256(video.read_bytes()).hexdigest())
    write_json(output / 'gemma_review.json', state)
    report = dict(backend='nvidia', model=NEMOTRON, result=result, dashboard=dashboard,
                  video={'name':video.name}, processing={'elapsed_seconds':elapsed,
                  'warnings':['Visual assessment only: this model cannot hear the audio. Scores are uncalibrated editorial estimates.']})
    try:
        from studio_pipeline import run_cognitive_audit
        unified = run_cognitive_audit(video, output, visual_frames, progress)
        report.update(unified)
        report['processing']['warnings'] = [
            'Cognitive scores are uncalibrated editorial hypotheses, not measured retention or emotion.',
            unified['pacing']['note']] + unified.get('evidence_warnings',[])
    except Exception as exc:
        report['cognitive_status'] = 'unavailable'
        report['processing']['warnings'].append('Cognitive/audio audit unavailable: ' + type(exc).__name__ + '. Visual scores remain separate.')
    report['processing']['elapsed_seconds']=round(time.time()-start,1)
    write_json(output / 'report.json', report)
    progress(99, 'NVIDIA assessment ready')
    return report
