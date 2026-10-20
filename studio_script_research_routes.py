"""Research runs remotely in its own single-job slot, independent of the GPU."""
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated
from fastapi import Body, HTTPException


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

    @app.get('/api/scripts/research/config')
    def config():
        from studio_script_nvidia import nvidia_token
        from studio_script_research import MODEL
        with lock:
            return {'model':MODEL,'configured':bool(nvidia_token('MUSE_API_KEY') or nvidia_token()),'active_id':active,
                'method':'Public search snippets + source-linked Muse synthesis. Not model-weight training.'}

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
        with lock:
            if active is not None:raise HTTPException(409,'A topic research job is already running.')
            research_id=uuid.uuid4().hex
            path=directory(research_id);path.mkdir(parents=True)
            _write_json(path/'state.json',{'id':research_id,'brief':brief,'status':'queued','stage':'Research queued'})
            active=research_id
            try:pool.submit(run,research_id,brief)
            except Exception:
                active=None
                raise
        return read(research_id)

    @app.get('/api/scripts/research/{research_id}')
    def detail(research_id: str):return read(research_id)

    return read
