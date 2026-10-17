"""Download pinned original TRIBE/AV weights with checksum verification."""
from pathlib import Path
import json
from analyze_video import configure_environment
from prepare_gpu import fetch_verified

ROOT=Path(__file__).resolve().parent

if __name__=='__main__':
    configure_environment()
    from huggingface_hub import HfApi, hf_hub_download
    api=HfApi();manifest={}
    repos=['facebook/tribev2','facebook/w2v-bert-2.0','facebook/vjepa2-vitg-fpc64-256']
    for repo in repos:
        info=api.model_info(repo,files_metadata=True)
        folder=ROOT/'cache/tribe-budget'/repo;folder.mkdir(parents=True,exist_ok=True)
        files=[]
        for item in info.siblings:
            if '/' in item.rfilename or not (item.rfilename.endswith(('.json','.yaml','.txt','.safetensors','.ckpt')) or item.rfilename=='LICENSE'):
                continue
            target=folder/item.rfilename
            if item.rfilename.endswith(('.ckpt','.safetensors')):
                fetch_verified(f'https://huggingface.co/{repo}/resolve/{info.sha}/{item.rfilename}',target,item.lfs.sha256)
            else:
                path=hf_hub_download(repo,item.rfilename,revision=info.sha)
                target.write_bytes(Path(path).read_bytes())
            files.append({'name':item.rfilename,'bytes':item.size,'sha256':item.lfs.sha256 if item.lfs else None})
        manifest[repo]={'revision':info.sha,'folder':folder.as_posix(),'files':files}
        (ROOT/'cache/tribe-budget/manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        print('Ready: '+repo,flush=True)
