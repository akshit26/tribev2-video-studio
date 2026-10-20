"""GPT-OSS drafts, Gemma reviews; editorial scores never masquerade as TRIBE."""
import json
import sys
from studio_script_nvidia import nvidia_token as credential
from studio_script_hf import HostedWriterError

MODEL='openai/gpt-oss-20b'
GEMMA='google/gemma-4-31b-it'
NAME='GPT-OSS draft / Gemma review'
PROFILE='gptoss-gemma-v2-bounded-stream'
ENDPOINT='https://integrate.api.nvidia.com/v1/chat/completions'


def nvidia_token():return credential('GPT_OSS_API_KEY')


def ready():return bool(nvidia_token() and credential('GEMMA_API_KEY'))


def validate_configuration(brief):
    if not ready():raise ValueError('Set GPT_OSS_API_KEY and GEMMA_API_KEY on the server.')


def stage_model(label):
    return GEMMA if label.startswith(('Critique','Hook critique')) else MODEL


def chat_json(token,model,system,prompt,max_tokens,temperature,preview=None):
    """Stream content with an overall deadline; never expose reasoning tokens."""
    import asyncio
    import httpx
    body={'model':model,'messages':[{'role':'system','content':system},{'role':'user','content':prompt}],
        'temperature':max(0,min(1,temperature)),'top_p':.95 if model.startswith('meta/muse') else 1,
        'max_tokens':8192 if model.startswith('meta/muse') else min(4096,max(1024,max_tokens+512)),
        'stream':True}
    if model==MODEL:body['reasoning_effort']='low'
    if model==GEMMA:body['chat_template_kwargs']={'enable_thinking':False}

    async def receive():
        content='';usage={};finished=False;size=0
        async with httpx.AsyncClient(timeout=httpx.Timeout(20,connect=5,write=10,pool=5)) as client:
            async with client.stream('POST',ENDPOINT,json=body,
                    headers={'Authorization':'Bearer '+token,'Accept':'text/event-stream'}) as response:
                if response.status_code!=200:
                    raise HostedWriterError(f'Writing pipeline unavailable (HTTP {response.status_code}). Check model access or quota. Saved drafts are retained.')
                async for line in response.aiter_lines():
                    size+=len(line.encode('utf-8'))
                    if size>2_000_000:raise HostedWriterError('Model response exceeded its size limit. Saved drafts are retained.')
                    if not line.startswith('data:'):continue
                    payload=line[5:].strip()
                    if payload=='[DONE]':break
                    chunk=json.loads(payload)
                    if chunk.get('error'):raise HostedWriterError('Model stream reported an error. Saved drafts are retained.')
                    if chunk.get('usage'):usage=chunk['usage']
                    choices=chunk.get('choices') or []
                    if not choices:continue
                    choice=choices[0];piece=(choice.get('delta') or {}).get('content')
                    if isinstance(piece,str):
                        content+=piece
                        if preview:preview(content)
                    reason=choice.get('finish_reason')
                    if reason=='length':raise ValueError('Model output reached its limit; return shorter JSON.')
                    if reason=='stop':finished=True
                    elif reason is not None:raise HostedWriterError('Model could not complete this stage. Saved drafts are retained.')
        if not finished:raise HostedWriterError('Model stream ended before completion. Saved drafts are retained.')
        from studio_review_parts import decoded_json
        parsed=decoded_json(content)
        if not isinstance(parsed,dict):raise ValueError('Return the requested JSON object without commentary.')
        return parsed,usage

    async def bounded():return await asyncio.wait_for(receive(),timeout=60)
    try:return asyncio.run(bounded())
    except (TimeoutError,httpx.TimeoutException):
        raise HostedWriterError(f'{model} timed out (20 seconds without data or 60 seconds total). Saved drafts are retained; retry later or select another engine.') from None
    except httpx.HTTPError:
        raise HostedWriterError(f'{model} connection failed. Saved drafts are retained; retry later or select another engine.') from None
    except (KeyError,IndexError,TypeError,AttributeError,json.JSONDecodeError,UnicodeError):
        raise HostedWriterError('Model returned an unreadable stream. Saved drafts are retained.') from None


def complete_stage(token,model,system,prompt,tokens,temperature,preview,label):
    selected=stage_model(label)
    key=credential('GEMMA_API_KEY') if selected==GEMMA else nvidia_token()
    return chat_json(key,selected,system,prompt,tokens,temperature,preview)


def voice_edit(token,result,request):
    from studio_script_nvidia import voice_edit as edit
    return edit(credential('GEMMA_API_KEY'),result,request,model_override=GEMMA,completion_override=chat_json)


def run_team_writer(output,request,progress):
    from studio_script_hf import run_hf_writer
    from studio_pipeline import _write_json
    run_hf_writer(output,request,progress,provider=sys.modules[__name__])
    path=output/'script_result.json'
    if path.exists():
        data=json.loads(path.read_text(encoding='utf-8'))
        data['pipeline']={'draft_model':MODEL,'analysis_model':GEMMA,'analysis_mode':'Spoken-script analysis and voice editing; no screenplay directions.'}
        from studio_script_tribe import draft_status
        data['tribe_v2']=draft_status()
        try:
            from studio_script_performance import validate_dataset,predict
            dataset=validate_dataset(json.loads((output.parent/'performance_data.json').read_text(encoding='utf-8')))
            spoken=' '.join(s['spoken'] for s in data['best']['script']['scenes'])
            data['performance_prediction']=dict(predict(dataset,request['brief'],spoken),status='estimated')
        except (OSError,ValueError,RuntimeError):
            data['performance_prediction']={'status':'not_available','probability':None,
                'reason':'Comparable real outcome history or Kumo access is unavailable. No score was invented; editorial review remains separate.'}
        _write_json(path,data)
