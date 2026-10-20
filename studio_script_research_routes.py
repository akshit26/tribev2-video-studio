"""Research runs remotely in its own single-job slot, independent of the GPU."""
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated
from fastapi import Body, HTTPException, UploadFile,File


def install(server):
    app=server.app
    pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='topic-research')
    lock=threading.Lock()
    active=None

    def directory(research_id):
        if not isinstance(research_id,str) or not server.JOB_ID.fullmatch(research_id):
            raise HTTPException(404,'Topic research not found.')
        return server.RESULTS_DIR/'_research'/research_id

    def read(research_id):
        path=directory(research_id)
        try:
            state=json.loads((path/'state.json').read_text(encoding='utf-8'))
        except (OSError,ValueError):
            raise HTTPException(404,'Topic research not found.') from None
        with lock:
            if state['status'] in {'queued','running'} and active!=research_id:
                state.update(status='failed',error='Research interrupted by server restart. Saved sources remain available.')
        for name,key in [('result.json','result'),('sources.json','source_snapshot')]:
            try:state[key]=json.loads((path/name).read_text(encoding='utf-8'))
            except (OSError,ValueError):pass
        return state

    def run(research_id,brief):
        nonlocal active
        from studio_pipeline import _write_json
        from studio_script_research import research
        path=directory(research_id)
        state={'id':research_id,'brief':brief,'status':'running','stage':'Starting Muse research'}
        def progress(stage):
            state['stage']=stage
            _write_json(path/'state.json',state)
        try:
            progress(state['stage'])
            if brief.get('research_mode')=='videos':
                from studio_video_learning import run_video_research,remember
                result=run_video_research(brief,path,server,lambda data:_write_json(path/'sources.json',data),progress)
                remember(server.RESULTS_DIR,research_id,brief,result)
            else:
                result=research(brief,lambda data:_write_json(path/'sources.json',data),progress)
            _write_json(path/'result.json',result)
            state.update(status='completed',stage='Topic research ready')
        except Exception as exc:
            state.update(status='failed',stage='Research stopped; saved sources are retained',error=server._safe_error(exc))
        finally:
            try:_write_json(path/'state.json',state)
            finally:
                with lock:
                    if active==research_id:active=None
                with server._lock:
                    if server._active_job==research_id:server._active_job=None

    @app.get('/api/scripts/research/config')
    def config():
        from studio_script_nvidia import nvidia_token
        from studio_script_research import MODEL
        with lock:
            return {'model':MODEL,'configured':bool(nvidia_token('MUSE_API_KEY') or nvidia_token()),'active_id':active,
                'method':'Actual video transcription -> Muse mechanisms with book references. Priority: YouTube Shorts, TikTok, Instagram. No template training.'}

    @app.post('/api/scripts/research/uploads',status_code=201)
    async def upload(video: Annotated[UploadFile,File()]):
        from pathlib import Path
        import math
        import cv2
        from studio_pipeline import _write_json
        extension=Path(video.filename or '').suffix.lower()
        if extension not in {'.mp4','.mov','.webm','.mkv','.avi'}:
            await video.close()
            raise HTTPException(415,'Upload a video reference clip.')
        uid=uuid.uuid4().hex;path=server.RESULTS_DIR/'_research_uploads'/uid;path.mkdir(parents=True)
        target=path/('input'+extension);size=0
        try:
            with target.open('wb') as stream:
                while chunk:=await video.read(1024*1024):
                    size+=len(chunk)
                    if size>50*1024**2:raise HTTPException(413,'Reference clips must be at most 50 MB.')
                    stream.write(chunk)
            capture=cv2.VideoCapture(str(target))
            try:
                fps=capture.get(cv2.CAP_PROP_FPS);frames=capture.get(cv2.CAP_PROP_FRAME_COUNT)
                duration=frames/fps if fps>0 else 0
            finally:capture.release()
            if not math.isfinite(duration) or not 5<=duration<=180:raise HTTPException(422,'Use a decodable 5–180 second reference clip.')
            _write_json(path/'metadata.json',{'file':target.name,'title':Path(video.filename or 'Reference').stem[:180],
                'duration':duration,'metrics_observed_at':None,'metrics_status':'Uploaded reference; public virality not verified.'})
            return {'id':uid,'duration':duration,'title':Path(video.filename or 'Reference').stem[:180]}
        except Exception:
            target.unlink(missing_ok=True)
            raise
        finally:await video.close()

    @app.get('/api/scripts/research')
    def listing():
        rows=[]
        for path in sorted((server.RESULTS_DIR/'_research').glob('*/state.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:30]:
            try:
                state=read(path.parent.name)
                rows.append({k:state[k] for k in ('id','brief','status','stage')})
            except HTTPException:pass
        return rows

    @app.post('/api/scripts/research',status_code=202)
    def create(raw: Annotated[dict,Body()]):
        nonlocal active
        from studio_script_research import values
        from studio_script_nvidia import nvidia_token
        from studio_pipeline import _write_json
        try:brief=values(raw)
        except (ValueError,TypeError,UnicodeError) as exc:raise HTTPException(422,str(exc)) from None
        if not (nvidia_token('MUSE_API_KEY') or nvidia_token()):
            raise HTTPException(422,'Set MUSE_API_KEY on the server to research topics.')
        for uid in brief.get('upload_ids',[]):
            if not (server.RESULTS_DIR/'_research_uploads'/uid/'metadata.json').is_file():raise HTTPException(422,'An uploaded reference clip is missing.')
        with lock:
            if active is not None:raise HTTPException(409,'A topic research job is already running.')
            research_id=uuid.uuid4().hex
            if brief.get('research_mode')=='videos':
                with server._lock:
                    if server._active_job is not None:raise HTTPException(409,'Video transcription needs the shared GPU slot. Wait for the active job.')
                    server._active_job=research_id
            active=research_id
            try:
                path=directory(research_id);path.mkdir(parents=True)
                _write_json(path/'state.json',{'id':research_id,'brief':brief,'status':'queued','stage':'Research queued'})
                pool.submit(run,research_id,brief)
            except Exception:
                active=None
                with server._lock:
                    if server._active_job==research_id:server._active_job=None
                raise
        return read(research_id)

    @app.get('/api/scripts/research/{research_id}')
    def detail(research_id: str):return read(research_id)

    return read
