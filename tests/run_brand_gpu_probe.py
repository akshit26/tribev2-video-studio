"""Manual GPU integration check using synthetic brand data, never customer outcomes."""
import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studio_pipeline import _write_json, gpu_info, _terminate_worker
from studio_resources import require_memory, RESERVE_MB, GPU_BUDGET_MB, GPU_GUARD_MB, GPU_STOP_C


def worker(directory):
    from studio_review import semantic_worker
    report=json.loads((directory/'review_input.json').read_text(encoding='utf-8'))
    # Only the pre-existing generic rubric is a fixture. Brand checks and
    # reference comparison are real GPU model calls through the normal runtime.
    with patch('studio_review_parts.generate_parts',return_value=({},report['review'])):
        semantic_worker(directory,'cuda',4096)


if __name__=='__main__':
    directory=ROOT/'results/brand_gpu_validation'
    directory.mkdir(parents=True,exist_ok=True)
    if '--worker' in sys.argv:
        worker(directory)
        raise SystemExit
    from studio_brands import calibration
    source={'id':'S1','start':0,'end':6,'text':'Meet Willow shampoo. Comment LINK and we will send you the product details.'}
    ref={'job_id':'b'*32,'name':'Synthetic reference','language':'en','platform':'instagram','duration_seconds':12,'score':70,'dimensions':[], 'excerpts':[dict(source,id='S2')],'outcomes':{'views':1000,'distribution':'organic','notes':'Synthetic test data'}}
    report={'video':{'duration_seconds':6,'name':'Synthetic brand test'},'transcript':{'language':'en','segments':[source]},'review_context':{'platform':'instagram'},'scenes':[],
            'review':{'sources':[source],'estimate':{'score':60,'range':[50,70]},'overall_score':60},
            'brand_context':{'id':'a'*32,'name':'Synthetic Willow','version':1,'documents':{'guidelines':{'name':'guidelines.txt','text':'The video must mention Willow. Ask viewers to comment LINK for product details.'}},'references':[ref],'team_notes':[], 'calibration':calibration({}),'note':'Synthetic validation snapshot'}}
    _write_json(directory/'review_input.json',report)
    require_memory()
    before=gpu_info()
    if before['used_mb']>500 or before.get('temperature_c',99)>=76:
        raise RuntimeError('Wait for the current GPU job and cooling before this test.')
    with (directory/'probe.log').open('w',encoding='utf-8') as log:
        process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--worker'],stdout=log,stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0))
        peak=before['used_mb'];begun=time.monotonic()
        try:
            while process.poll() is None:
                require_memory(RESERVE_MB)
                info=gpu_info();peak=max(peak,info['used_mb'])
                if not info['available'] or info['used_mb']>GPU_BUDGET_MB-GPU_GUARD_MB or info.get('temperature_c',99)>=GPU_STOP_C or time.monotonic()-begun>600:
                    raise RuntimeError('GPU integration test stopped by resource/time guard')
                time.sleep(.5)
            if process.returncode:raise RuntimeError('GPU check failed; see results/brand_gpu_validation/probe.log')
        finally:
            if process.poll() is None:_terminate_worker(process)
    result=json.loads((directory/'review.json').read_text(encoding='utf-8'))['brand_review']
    assert result['checks'] and result['comparisons']
    _write_json(directory/'validation.json',{'peak_gpu_mb':peak,'checks':len(result['checks']),'comparisons':len(result['comparisons']),'score':result['overall_score']})
    print(json.dumps({'peak_gpu_mb':peak,'checks':len(result['checks']),'comparisons':len(result['comparisons'])}))
