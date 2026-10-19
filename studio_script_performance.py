"""Optional Kumo estimates from comparable real post outcomes, never editorial grades."""
from __future__ import annotations
import json
import math
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

from studio_script_examples import NICHES, niche_for
from studio_script_language import normalize_language, AI_PHRASES
from studio_script_nvidia import nvidia_token
from studio_script_hf import HostedWriterError

ENDPOINT = "https://ai.api.nvidia.com/v1/structured-data/nvidia/kumo-relational/predictions"
MIN_ROWS = 20
MAX_ROWS = 500
FEATURE_VERSION = "speech-counts-v1"


def timestamp(value):
    if not isinstance(value,str):
        raise ValueError("Supply timezone-aware published_at and observed_at timestamps.")
    try:
        dt = datetime.fromisoformat(value.replace('Z','+00:00'))
        if dt.tzinfo is None:
            raise ValueError()
        return dt.astimezone(timezone.utc)
    except ValueError:
        raise ValueError("Use timezone-aware ISO timestamps, such as 2026-01-01T10:00:00Z.") from None


def clean_string(value, limit, field):
    if not isinstance(value,str) or not value.strip() or len(value)>limit or '\ufffd' in value:
        raise ValueError(f"Supply valid {field} (up to {limit} characters).")
    return value.strip()


def validate_dataset(raw, now=None):
    if not isinstance(raw,dict):
        raise ValueError("Import a JSON object with account, outcome_definition, measurement_window_hours and rows.")
    now = now or datetime.now(timezone.utc)
    account = clean_string(raw.get('account'),100,'account')
    definition = clean_string(raw.get('outcome_definition'),500,'outcome_definition')
    window = raw.get('measurement_window_hours')
    if type(window) not in {int,float} or not math.isfinite(window) or not 1<=window<=720:
        raise ValueError("Choose an outcome measurement window of 1–720 hours.")
    if not isinstance(raw.get('rows'),list) or not 1<=len(raw['rows'])<=MAX_ROWS:
        raise ValueError(f"Import 1–{MAX_ROWS} real posts; each comparable cohort needs at least {MIN_ROWS}.")
    seen, rows = set(), []
    for row in raw['rows']:
        if not isinstance(row,dict):
            raise ValueError("Each post must be an object.")
        post_id = clean_string(row.get('post_id'),150,'unique post_id')
        if post_id in seen:
            raise ValueError("Duplicate post_id. Import each post only once.")
        seen.add(post_id)
        if row.get('niche') not in NICHES or row.get('niche')=='auto':
            raise ValueError("Each post needs a specific niche: skincare, fashion, arcade, food_drinks or fmcg.")
        duration = row.get('duration')
        if type(duration) not in {int,float} or not math.isfinite(duration) or not 5<=duration<=180:
            raise ValueError("Each post duration must be 5–180 seconds.")
        if type(row.get('label')) is not bool:
            raise ValueError("Each real outcome label must be a JSON boolean, never an editorial score.")
        published, observed = timestamp(row.get('published_at')), timestamp(row.get('observed_at'))
        if observed>now or observed<published+timedelta(hours=window):
            raise ValueError("Outcomes must be observed in the past, after the full measurement window.")
        rows.append({'post_id':post_id,'niche':row['niche'],
            'language':normalize_language(clean_string(row.get('language'),80,'language')),
            'platform':clean_string(row.get('platform'),80,'platform'), 'duration':duration,
            'script_text':clean_string(row.get('script_text'),6000,'original pre-publication script_text'),
            'label':row['label'],'published_at':published.isoformat(),'observed_at':observed.isoformat()})
    return {'version':1,'account':account,'outcome_definition':definition,'measurement_window_hours':window,'rows':rows}


def cohort(dataset, brief):
    return [r for r in dataset['rows'] if r['niche']==niche_for(brief)
            and r['language']==normalize_language(brief.get('language','English'))
            and r['platform'].casefold()==brief.get('platform','Instagram Reels').casefold()
            and abs(r['duration']-brief['duration'])<=5]


def features(spoken, duration):
    words = spoken.split()
    sentences = [s for s in re.split(r'[.!?।]+',spoken) if s.strip()]
    opening = sentences[0].split() if sentences else words
    lower = spoken.casefold()
    return [float(duration), len(words), len(opening), len(words)/max(1,len(sentences)),
            spoken.count('?'), sum(p in lower for p in AI_PHRASES),
            bool(re.search(r'\b(?:i|my|mujhe|mera|meri|main)\b|मैं|मुझे|मेरा|मेरी',lower))]


def build_payload(dataset, brief, spoken, now=None):
    now = now or datetime.now(timezone.utc)
    rows = sorted(cohort(dataset,brief),key=lambda r:r['published_at'])[-200:]
    positives = sum(r['label'] for r in rows)
    if len(rows)<MIN_ROWS or min(positives,len(rows)-positives)<5:
        raise ValueError(f"Kumo needs at least {MIN_ROWS} comparable real posts, including 5 successes and 5 misses, for this niche, language, platform and duration. Found {len(rows)} ({positives} successes).")
    columns = ['duration','word_count','opening_words','words_per_sentence','questions','ad_phrases','first_person']
    def col(dtype, stype, nullable=False):
        return {'dtype':dtype,'stype':stype,'nullable':nullable}
    instance_cols = {'instance_id':col('int64','ID'),'anchor_time':col('timestamp[us]','timestamp'),
                     'script_id':col('int64','ID'),'label':col('bool','categorical',True)}
    script_cols = {'instance_id':col('int64','ID'),'script_id':col('int64','ID')}
    script_cols.update({name:col('bool' if name=='first_person' else 'float64','categorical' if name=='first_person' else 'numerical') for name in columns})
    def table(names, data):
        return {'format':'arrays','columns':names,'rows':data}
    index_cols=['instance_id','anchor_time','script_id']
    feature_cols=['instance_id','script_id']+columns
    qid=len(rows)
    payload={'model':'kumo-relational',
        'task':{'kind':'binary_classification','target':{'column_name':'label','dtype':'bool','classes':['false','true'],'positive_class':'true'},'entity_table_names':['scripts'],'anchor_time_column':'anchor_time'},
        'schema':{'instance_table':{'columns':instance_cols,'primary_key':'instance_id'},
            'related_tables':{'scripts':{'columns':script_cols,'primary_key':['instance_id','script_id']}},
            'relationships':[{'source_columns':['instance_id','script_id'],'target_table':'scripts','target_columns':['instance_id','script_id']}]},
        'context':{'instance_table':table(index_cols+['label'],[[i,r['published_at'],i,r['label']] for i,r in enumerate(rows)]),
            'related_tables':{'scripts':table(feature_cols,[[i,i]+features(r['script_text'],r['duration']) for i,r in enumerate(rows)])}},
        'predict':{'instance_table':table(index_cols,[[qid,now.isoformat(),qid]]),
            'related_tables':{'scripts':table(feature_cols,[[qid,qid]+features(spoken,brief['duration'])])}},
        'output':{'fields':['prediction','probabilities']}}
    return payload, {'context_rows':len(rows),'successes':positives,'base_rate':positives/len(rows),
        'account':dataset['account'],'outcome_definition':dataset['outcome_definition'],
        'feature_version':FEATURE_VERSION,'niche':niche_for(brief),'language':brief.get('language','English')}


def probability_from_response(data):
    items = data.get('predictions')
    if not isinstance(items,list) or len(items)!=1 or items[0].get('row_index')!=0:
        raise HostedWriterError("Kumo returned an unexpected prediction structure. No estimate was applied.")
    probabilities = items[0].get('probabilities')
    value = None
    if isinstance(probabilities,dict):
        value = probabilities.get('true')
    elif isinstance(probabilities,list):
        # Class order is explicit in the request; labeled response entries may also be returned.
        if all(type(p) in {int,float} for p in probabilities) and len(probabilities)==2:
            value=probabilities[1]
        else:
            for entry in probabilities:
                if isinstance(entry,dict) and str(entry.get('class',entry.get('label',''))).lower()=='true':
                    value=entry.get('probability')
    if type(value) not in {int,float} or not math.isfinite(value) or not 0<=value<=1:
        raise HostedWriterError("Kumo did not return a valid positive-class probability. No estimate was applied.")
    return value


def predict(dataset, brief, spoken):
    payload, details = build_payload(dataset,brief,spoken)
    token = nvidia_token('KUMO_API_KEY') or nvidia_token()
    if not token:
        raise ValueError("Configure KUMO_API_KEY or NVIDIA_API_KEY on the server.")
    request = urllib.request.Request(ENDPOINT,data=json.dumps(payload).encode('utf-8'),
        headers={'Authorization':'Bearer '+token,'Accept':'application/json','Content-Type':'application/json'},method='POST')
    try:
        with urllib.request.urlopen(request,timeout=90) as response:
            if response.status!=200:
                raise HostedWriterError("Kumo did not return a completed prediction. No estimate was applied.")
            data=json.loads(response.read(1_000_001))
        probability=probability_from_response(data)
    except urllib.error.HTTPError as exc:
        raise HostedWriterError(f"Kumo request unavailable (HTTP {exc.code}). Check model access, quota or try later; your script is unchanged.") from None
    except (OSError,ValueError,TypeError,AttributeError):
        raise HostedWriterError("Kumo connection failed or response was invalid. Your script is unchanged; retry manually.") from None
    return dict(details,probability=probability,calibrated=False,
        method="Experimental Kumo in-context estimate from pre-publication speech features. Not validated on held-out posts; no guarantee of virality. Public reference examples and editorial scores are never labels.")
