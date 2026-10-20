"""GPT-OSS drafts, Gemma reviews; editorial scores never masquerade as TRIBE."""
import json
import sys
import urllib.request
import urllib.error
from studio_script_nvidia import nvidia_token as credential
from studio_script_hf import HostedWriterError

MODEL='openai/gpt-oss-20b'
GEMMA='google/gemma-4-31b-it'
NAME='GPT-OSS draft / Gemma review'
PROFILE='gptoss-gemma-v1-logic-only'
ENDPOINT='https://integrate.api.nvidia.com/v1/chat/completions'


def nvidia_token():return credential('GPT_OSS_API_KEY')


def ready():return bool(nvidia_token() and credential('GEMMA_API_KEY'))


def validate_configuration(brief):
    if not ready():raise ValueError('Set GPT_OSS_API_KEY and GEMMA_API_KEY on the server.')


def stage_model(label):
    return GEMMA if label.startswith(('Critique','Hook critique')) else MODEL


def chat_json(token,model,system,prompt,max_tokens,temperature,preview=None):
    body={'model':model,'messages':[{'role':'system','content':system},{'role':'user','content':prompt}],
        'temperature':.5 if model==GEMMA else 1,'top_p':.95 if model.startswith('meta/muse') else 1,
        'max_tokens':8192 if model.startswith('meta/muse') else 4096,'stream':False}
    request=urllib.request.Request(ENDPOINT,data=json.dumps(body,ensure_ascii=False).encode('utf-8'),
        headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST')
    try:
        with urllib.request.urlopen(request,timeout=120) as response:
            if response.status!=200:raise HostedWriterError('Writer response is pending. Saved drafts are retained.')
            data=json.loads(response.read(2_000_001))
        choice=data['choices'][0]
        if choice.get('finish_reason')=='length':raise ValueError('Model output reached its limit; return shorter JSON.')
        if choice.get('finish_reason')!='stop':raise HostedWriterError('Model could not complete this stage. Saved drafts are retained.')
        from studio_review_parts import decoded_json
        content=choice['message']['content']
        parsed=decoded_json(content)
        if not isinstance(parsed,dict):raise ValueError('Return the requested JSON object without commentary.')
        if preview:preview(content)
        return parsed,data.get('usage',{})
    except urllib.error.HTTPError as exc:
        raise HostedWriterError(f'Writing pipeline unavailable (HTTP {exc.code}). Check model access or quota. No provider fallback or automatic transport retry was used.') from None
    except (OSError,KeyError,IndexError,TypeError,AttributeError,json.JSONDecodeError):
        raise HostedWriterError('Writing pipeline connection failed or returned unreadable output. Saved drafts are retained.') from None


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
