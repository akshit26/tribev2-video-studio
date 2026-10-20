"""Optional API-only review with a working Nemotron default and explicit Gemma option."""
import asyncio
import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from fastapi import HTTPException
from fastapi.responses import FileResponse


def video_digest(video):
    from studio_gemma_video import MAX_VIDEO_BYTES
    try:
        if video.stat().st_size>MAX_VIDEO_BYTES:return None
        digest=hashlib.sha256();size=0
        with video.open('rb') as stream:
            while chunk:=stream.read(1024*1024):
                size+=len(chunk)
                if size>MAX_VIDEO_BYTES:return None
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:return None


def install(server):
    pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='gemma-video')
    lock=threading.RLock();active=None
    def path_for(job_id):
        server._load_job(job_id)
        return server._job_dir(job_id)/'gemma_review.json'
    def read(job_id):
        from studio_script_nvidia import nvidia_token
        path=path_for(job_id)
        with lock:
            try:state=json.loads(path.read_text(encoding='utf-8'))
            except (OSError,ValueError):state={'status':'not_started'}
            if not isinstance(state,dict) or state.get('status') not in {'not_started','queued','running','completed','failed'}:
                state={'status':'failed','error':'Saved Gemma assessment is unreadable. Retry the review.'}
            if state['status'] in {'queued','running'} and active!=job_id:
                state={'status':'failed','error':'Gemma review was interrupted by a server restart. Retry when ready.'}
            if state['status']=='completed':
                try:
                    from studio_gemma_video import validate_result,dashboard_state
                    result=validate_result(json.dumps(state.get('result')))
                    if not state.get('video_sha256') or video_digest(path.parent/'input.mp4')!=state['video_sha256']:
                        raise ValueError('Recording changed')
                    state['result']=result;state['dashboard']=dashboard_state(result)
                except (ValueError,RuntimeError,TypeError):
                    state={'status':'failed','error':'Saved Gemma assessment does not match the current video or has invalid scores. Analyze this recording again.'}
            from studio_gemma_video import NEMOTRON,MODELS
            state['configured']=bool(nvidia_token('GEMMA_API_KEY') or nvidia_token())
            state['default_model']=NEMOTRON;state['models']=MODELS
            if state.get('started_at') and state['status']=='running':
                state['elapsed_seconds']=round(time.time()-state['started_at'],1)
            return state
    def run(job_id,video,model):
        nonlocal active
        from studio_remote_review import write_json as _write_json
        from studio_gemma_video import analyze_virality,dashboard_state,MODEL
        start=time.time();path=server._job_dir(job_id)/'gemma_review.json'
        state={'status':'running','started_at':start,'model':model}
        try:
            _write_json(path,state)
            digest=video_digest(video)
            if not digest:raise ValueError('Original MP4 is missing or exceeds the review size limit.')
            result=asyncio.run(analyze_virality(video,model))
            if video_digest(video)!=digest:raise ValueError('The MP4 changed during review. Analyze the current recording again.')
            state['video_sha256']=digest
            state.update(status='completed',result=result,dashboard=dashboard_state(result))
        except Exception as exc:
            state.update(status='failed',error=server._safe_error(exc),diagnostics=getattr(exc,'diagnostics',{}))
        finally:
            state['elapsed_seconds']=round(time.time()-start,1)
            try:_write_json(path,state)
            finally:
                with lock:
                    if active==job_id:active=None
    @server.app.get('/gemma.js')
    def javascript():
        return FileResponse(server.ROOT/'web/gemma.js',media_type='text/javascript',headers={'Cache-Control':'no-store'})
    @server.app.get('/api/jobs/{job_id}/gemma-review')
    def get_review(job_id: str):return read(job_id)
    @server.app.post('/api/jobs/{job_id}/gemma-review',status_code=202)
    def create_review(job_id: str,model: str='nvidia/nemotron-3.5-super-vl-120b-a12b'):
        nonlocal active
        from studio_remote_review import write_json as _write_json
        from studio_script_nvidia import nvidia_token
        from studio_gemma_video import MAX_VIDEO_BYTES,MODELS
        if model not in MODELS:raise HTTPException(422,'Choose an available video review model.')
        job=server._load_job(job_id)
        if job['status'] not in server.TERMINAL_STATES:raise HTTPException(409,'Wait for the current video analysis to finish.')
        if not (nvidia_token('GEMMA_API_KEY') or nvidia_token()):raise HTTPException(422,'Set GEMMA_API_KEY on the server.')
        video=server._job_dir(job_id)/'input.mp4'
        if not video.is_file():raise HTTPException(422,'Direct Gemma review requires the original MP4 upload.')
        if video.stat().st_size>MAX_VIDEO_BYTES:raise HTTPException(413,'Use an MP4 up to 20 MB for direct Gemma review.')
        with lock:
            if active is not None:raise HTTPException(409,'Another Gemma video review is running.')
            path=path_for(job_id)
            _write_json(path,{'status':'queued','model':model})
            active=job_id
            try:pool.submit(run,job_id,video,model)
            except Exception:
                active=None
                _write_json(path,{'status':'failed','error':'Could not start Gemma review. Retry when ready.'})
                raise
        return read(job_id)
