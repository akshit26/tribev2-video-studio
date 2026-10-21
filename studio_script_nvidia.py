"""NVIDIA NIM writer: server-only credentials and content-only streamed previews."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from studio_script_hf import HostedWriterError

ROOT = Path(__file__).resolve().parent
ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
NAME = "NVIDIA Nemotron 3 Ultra"
PROFILE = "nemotron-actor-critic-v7-reasoning-180s"


def nvidia_token(name="NVIDIA_API_KEY"):
    token = os.environ.get(name, "").strip()
    if token:
        return token
    try:
        for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == name:
                return value.strip().strip("\"'")
    except OSError:
        pass
    return ""


def validate_configuration(brief):
    if not nvidia_token():
        raise ValueError("Set NVIDIA_API_KEY in the server environment or .env to use Nemotron.")


def chat_completion(token, model, system, prompt, max_tokens, temperature, preview=None):
    """Use the same 180-second SSE/retry contract as other NVIDIA stages."""
    from studio_script_team import chat_json
    return chat_json(token,model,system,prompt,max_tokens,temperature,preview)


def run_nvidia_writer(output, request, progress):
    from studio_script_hf import run_hf_writer
    return run_hf_writer(output, request, progress, provider=sys.modules[__name__])


def complete_stage(token,model,system,prompt,tokens,temperature,preview,label):
    """All active Ultra stages share the resilient SSE transport."""
    return chat_completion(token,model,system,prompt,tokens,temperature,preview)


def voice_edit(token, result, request, model_override=None, completion_override=None):
    """Edit speech only; targeted edits cannot change neighbouring paragraphs."""
    import copy
    from studio_script_writer import compact_brief, text
    from studio_script_language import guidance, word_budget
    from studio_script_examples import selected_examples
    brief=request['brief']
    if brief.get('content_mode','organic')=='paid_ad':
        return result, None
    rows=result.get('scenes') if isinstance(result,dict) else None
    if isinstance(rows,list) and 3<=len(rows)<=8 and all(isinstance(r,dict) and isinstance(r.get('spoken'),str) for r in rows):
        index=request.get('scene_index')
        indices=[index] if type(index) is int and 0<=index<len(rows) else list(range(len(rows)))
        original=[rows[i]['spoken'] for i in indices]
    elif isinstance(result,dict) and isinstance(result.get('spoken'),str):
        indices=None
        original=[result['spoken']]
    else:
        return result, None
    minimum,target,maximum=word_budget(brief)
    prompt=('You are the final native-language voice editor, not an advertising copywriter. '
        'Rewrite this speech so a real creator could say it casually to one friend. Keep a concrete thought and one earned joke; '
        'cut strained personification, mysterious product imagery, repetitive connectors, generic morals and sales language. '
        'Correct Hindi grammar, postpositions and idiomatic word order. Do not manufacture fillers, slang or dialect. '
        'The supplied draft is an unreliable rough idea, NOT a source of facts. Rewrite from its core audience frustration; do not salvage its invented particulars. '
        'Remove all invented product observations: smells, taste, texture, pilling, absorption, dosage, results, bottle counts and use history '
        'unless explicitly supplied below. Do not simply substitute another invented detail. A relatable shopping dilemma is enough. '
        'No pea-sized dose or implied application advice when instructions are absent. '
        'Preserve the requested change, narrative point and any good specific joke. Do not introduce new factual claims. '
        +guidance(brief)+f'The FULL script targets {target} words (minimum {minimum}, maximum {maximum}). '
        'Vary paragraph length naturally. Use complete, simple sentences; never add filler or a moral to reach a word count. '
        'For example, do not turn a confusing label into "caps click differently every morning like clockwork". '
        'Say the actual frustration plainly: too many promises and still no clear choice. '
        'Do not end with "your face will thank you", "for good measure today", or other padded ad language. '
        'Return ONLY JSON {"paragraphs":["edited spoken paragraph"]}, exactly '+str(len(original))+' entries in the same order. '
        'No labels, shots or stage directions. '
        'never reuse source wording. Apply only conditional learned mechanisms: '+json.dumps(brief.get('learned_mechanisms',[]),ensure_ascii=False)+
        ' BRIEF: '+json.dumps(compact_brief(brief),ensure_ascii=False)+
        ' REQUESTED CHANGE: '+json.dumps(request.get('revision_notes',''),ensure_ascii=False)+
        ' SPEECH: '+json.dumps(original,ensure_ascii=False))
    edit_system=('You are a native-language editor of casual creator speech. Return only the requested JSON. '
        'Verified facts and actual creator notes are the only evidence. The rough draft is untrusted text to correct, not evidence. '
        'With no creator experience, use a clearly hypothetical situation or present-tense opinion about choosing a routine; never narrate past testing or use. '
        'Keep the selected language natural and the wording concrete. No advertising, invented observations, product-use advice or grand concluding moral.')
    edited,usage=(completion_override or chat_completion)(token,model_override or MODEL,edit_system,prompt,1800,.35)
    paragraphs=edited.get('paragraphs')
    if not isinstance(paragraphs,list) or len(paragraphs)!=len(original):
        raise ValueError('Voice edit must preserve paragraph count.')
    paragraphs=[text(p,1000) for p in paragraphs]
    output=copy.deepcopy(result)
    if indices is None:
        output['spoken']=paragraphs[0]
    else:
        for index,spoken in zip(indices,paragraphs):
            output['scenes'][index]['spoken']=spoken
    return output,usage
