"""Small cached sparse-vector retriever over the authoritative persona desk.

TF-IDF cosine retrieval needs no model download, GPU, network call or vector DB.
Explicit persona selection wins over automatic similarity ranking.
"""
from collections import Counter
from functools import lru_cache
import math
from pathlib import Path
import re

SOURCE=Path(__file__).with_name('SCRIPT_PERSONAS.md')


def tokens(value):
    return re.findall(r'[\w]+',value.casefold())


@lru_cache(maxsize=2)
def index(text):
    rows=[]
    for line in text.splitlines():
        columns=[part.strip() for part in line.strip().strip('|').split('|')]
        if not line.startswith('|') or len(columns)!=3 or columns[0] in {'Persona','Best fit for this brief'} or set(columns[0])<=set('- '):
            continue
        rows.append(dict(name=columns[0],best_for=columns[1],direction=columns[2],source='SCRIPT_PERSONAS.md'))
    counts=[Counter(tokens(' '.join(row.values()))) for row in rows]
    frequencies=Counter(word for count in counts for word in count)
    idf={word:math.log((1+len(rows))/(1+count))+1 for word,count in frequencies.items()}
    def vector(count):
        values={word:(1+math.log(n))*idf[word] for word,n in count.items() if word in idf}
        norm=math.sqrt(sum(v*v for v in values.values())) or 1
        return {word:v/norm for word,v in values.items()}
    return rows,[vector(count) for count in counts],idf


def retrieve_personas(brief,limit=2):
    from studio_script_writer import personas
    rows,vectors,idf=index(SOURCE.read_text(encoding='utf-8'))
    selected=next((p for p in personas() if p['id']==brief.get('persona')),None)
    if selected and selected['id']!='auto':
        return [row for row in rows if row['name']==selected['name']][:1]
    query=' '.join(str(brief.get(k,'')) for k in ('topic','niche','audience','content_format','creative_notes','pain_point'))
    count=Counter(tokens(query))
    vector={word:(1+math.log(n))*idf[word] for word,n in count.items() if word in idf}
    norm=math.sqrt(sum(v*v for v in vector.values())) or 1
    ranked=sorted(zip(rows,vectors),key=lambda item:sum(vector.get(word,0)*value/norm for word,value in item[1].items()),reverse=True)
    return [row for row,_ in ranked[:max(1,min(3,limit))]]
