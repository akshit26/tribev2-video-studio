"""Explicit TRIBE boundary: do not fabricate an fMRI-based text quality score."""


def draft_status():
    return {'model':'facebook/tribev2','status':'requires_authentic_predictions_and_calibration','score':None,
        'reason':'TRIBE encodes brain responses to stimuli, including text; it has no native script-quality or virality scale. This Studio supports calibrated TRIBE exports from recorded media. No fitted script-rating calibration is configured, and a text-only estimate cannot stand in for a recorded performance.',
        'guide':'TRIBE_CALIBRATION_GUIDE.md','editorial_score_is_tribe':False}


def rate_recording(directory,media,language):
    import json
    import hashlib
    from pathlib import Path
    import zipfile
    import numpy as np
    from studio_script_nvidia import nvidia_token
    from tribe_calibration.core import summarize,score_sample
    configured=nvidia_token('TRIBE_CALIBRATION_ARTIFACT')
    if not configured:raise ValueError('Configure TRIBE_CALIBRATION_ARTIFACT with a genuinely fitted calibration. No TRIBE rating was invented.')
    prediction=directory/'tribe_prediction.npz';metadata=directory/'tribe_prediction.json'
    if not prediction.is_file() or not metadata.is_file():raise ValueError('Export authentic TRIBE predictions for this recording as tribe_prediction.npz/json using the calibration workflow.')
    artifact=json.loads(Path(configured).read_text(encoding='utf-8'))
    meta=json.loads(metadata.read_text(encoding='utf-8'))
    if meta.get('model')!='facebook/tribev2' or artifact.get('model')!='TRIBE ROI ridge calibration':raise ValueError('Authentic TRIBE provenance and a fitted ROI calibration are required.')
    if meta.get('language')!=language or artifact.get('unit')!='video':raise ValueError('The TRIBE language or whole-video scoring unit does not match. No language fallback was used.')
    digest=hashlib.sha256()
    with media.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    if meta.get('video_sha256')!=digest.hexdigest():raise ValueError('TRIBE predictions belong to another recording.')
    with zipfile.ZipFile(prediction) as archive:
        for name in ('roi_values.npy','starts.npy','durations.npy'):
            if archive.getinfo(name).file_size>32*1024**2:raise ValueError('TRIBE ROI export exceeds the compact rating limit.')
    with np.load(prediction,allow_pickle=False) as data:
        features,names=summarize(data['roi_values'],data['starts'],data['durations'],meta['roi_names'])
    if names!=artifact['feature_names']:raise ValueError('TRIBE features do not match the fitted calibration.')
    dimensions=score_sample(artifact,language,features,meta['signature'],'video',artifact['guideline_version'])
    return {'model':'facebook/tribev2','status':'rated_recording','score':None,'dimensions':dimensions,
        'language':language,'checkpoint_sha256':meta.get('checkpoint_sha256'),
        'reason':'Calibrated dimensions apply to this recorded stimulus, not an unrecorded draft or a guaranteed viral outcome.',
        'editorial_score_is_tribe':False}
