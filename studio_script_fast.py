"""Fast API-only single-block writer; GPT-OSS remains a separate explicit option."""
import json
import sys
from studio_script_team import chat_json as chat_completion
MODEL='nvidia/nemotron-3.5-super-vl-120b-a12b'
NAME='Nemotron 3.5 Super (fast writer)'
PROFILE='fast-text-v1'
def nvidia_token():
    from studio_script_nvidia import nvidia_token as credential
    return credential('FAST_WRITER_API_KEY') or credential('GEMMA_API_KEY') or credential('NVIDIA_API_KEY') or credential('GPT_OSS_API_KEY')
def ready():return bool(nvidia_token())
def validate_configuration(brief):
    if not ready():raise ValueError('Set a NVIDIA API credential on the server for fast writing.')
def voice_edit(token,result,request):return result,None
def run_fast_writer(output,request,progress):
    from studio_script_hf import run_hf_writer
    from studio_pipeline import _write_json
    run_hf_writer(output,request,progress,provider=sys.modules[__name__])
    path=output/'script_result.json'
    if path.exists():
        result=json.loads(path.read_text(encoding='utf-8'))
        result['pipeline']={'draft_model':MODEL,'analysis_model':None,'analysis_mode':'Single-block script; no local model or extra critique call.'}
        _write_json(path,result)
