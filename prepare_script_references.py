"""Download public reference pages locally; source pages stay out of Git."""
import hashlib
import json
import re
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from studio_script_examples import catalog

ROOT=Path(__file__).resolve().parent


def main():
    folder=ROOT/'cache'/'writer'/'reference_sources'
    folder.mkdir(parents=True,exist_ok=True)
    sources={s['url']:s for s in catalog()['sources']}
    def fetch(pair):
        url,source=pair
        row={'id':source['id'],'url':url,'retrieved_at':datetime.now(timezone.utc).isoformat()}
        path=folder/(source['id']+'.html')
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; TribeReferenceReader/1.0)'})
            with urllib.request.urlopen(req,timeout=25) as response:
                data=response.read(4_000_001)
                if len(data)>4_000_000:
                    raise ValueError('Page exceeds 4 MB limit')
            path.write_bytes(data)
            title=re.search(r'<title[^>]*>(.*?)</title>',data.decode('utf-8',errors='replace'),re.S|re.I)
            row.update(status='downloaded',file=path.name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),page_title=re.sub(r'\s+',' ',title[1]).strip() if title else '')
        except (OSError,ValueError) as exc:
            row.update(status='unavailable',error='HTTP '+str(exc.code) if isinstance(exc,urllib.error.HTTPError) else type(exc).__name__)
        return row
    with ThreadPoolExecutor(max_workers=4) as pool:
        manifest=list(pool.map(fetch,sources.items()))
    (folder/'manifest.json').write_text(json.dumps({'note':'Downloaded source pages, not video transcripts. Full page files are local-only; curated notes and original scripts are in script_examples.json.','sources':manifest},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'downloaded':sum(r['status']=='downloaded' for r in manifest),'total_unique_pages':len(manifest),'unavailable':[r['id'] for r in manifest if r['status']!='downloaded'],'manifest':str(folder/'manifest.json')}))


if __name__=='__main__':
    main()
