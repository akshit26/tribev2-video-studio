"""Offline, timestamped screen-text evidence with bounded CPU/RAM use."""
import json
import re
from pathlib import Path

CTA = re.compile(r"\b(comment|dm|link|shop|buy|order|subscribe|follow|whatsapp|scan)\b",re.I)
PRODUCT = re.compile(r"\b(shampoo|conditioner|serum|hair|scalp|ml|ingredients|duo)\b",re.I)


def reading_text(value):
    # The pipe is our line separator, not a visible character or creative defect.
    return ' '.join(str(value).replace(' | ',' ').split())


def comment_link_ctas(sources):
    pattern=re.compile(r"\bcomment\s+[\"']?([\w-]{1,24})[\"']?\s*for\s+link\b",re.I)
    detected=[]
    for source in sources:
        if source.get('kind')!='ocr':continue
        match=pattern.search(reading_text(source['text']))
        if match:
            detected.append({'source_id':source['id'],'action':'comment',
                             'keyword':match.group(1),'response':'link',
                             'recognized_text':match.group(0)})
    return detected


def trusted_groups(frames, duration, minimum_confidence=.90):
    """Weak small-label readings stay in the archive, not in scoring evidence."""
    groups=[];last_key=None
    for frame in frames:
        lines=[line for line in frame['lines'] if line['confidence']>=minimum_confidence]
        text=' | '.join(line['text'] for line in lines)
        key=reading_text(text).casefold();t=frame['time_seconds']
        if text:
            if groups and key==last_key and t-groups[-1]['end']<=1.5:
                groups[-1]['end']=min(duration,t+1)
            else:
                groups.append({'start':t,'end':min(duration,t+1),'text':text,
                               'confidence':round(sum(line['confidence'] for line in lines)/len(lines),3),
                               'frame_file':frame['frame_file']})
        last_key=key
    return groups


def select_evidence(rows, duration, limit=24):
    from difflib import SequenceMatcher
    # Prioritize CTA/product labels and opening/closing overlays without discarding
    # the complete OCR archive. No text here is an instruction to the reviewer.
    ranked=sorted(rows,key=lambda r:(not bool(CTA.search(r['text'])),
                  not bool(PRODUCT.search(r['text'])),not (r['start']<5 or r['end']>duration-6),-r['confidence']))
    chosen=[]
    for row in ranked:
        # Nearby frames of the same overlay should not consume the whole budget.
        if any(abs(row['start']-old['start'])<4 and
               SequenceMatcher(None,reading_text(row['text']).casefold(),reading_text(old['text']).casefold()).ratio()>.82
               for old in chosen):continue
        chosen.append(row)
        if len(chosen)==limit:break
    chosen=sorted(chosen,key=lambda r:r['start'])
    return [dict(r,id=f'O{i+1}',kind='ocr') for i,r in enumerate(chosen)]


def run_ocr(video, output, progress=lambda *_:None):
    import cv2
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR
    from studio_resources import require_memory, RESERVE_MB
    from studio_pipeline import _write_json
    cv2.setNumThreads(2)
    engine=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1,
                    det_use_cuda=False,cls_use_cuda=False,rec_use_cuda=False,
                    det_limit_side_len=960,rec_batch_num=4,text_score=.55)
    video,output=Path(video),Path(output);frames=output/'ocr_frames';frames.mkdir(exist_ok=True)
    capture=cv2.VideoCapture(str(video))
    duration=capture.get(cv2.CAP_PROP_FRAME_COUNT)/max(capture.get(cv2.CAP_PROP_FPS),1)
    if not 0<duration<=600:raise ValueError('Cannot sample this video for OCR')
    times=list(np.arange(0,duration,1.25)) + [max(0,duration-.15)]
    # Extra probes around measured scene changes improve short overlay coverage.
    try:
        import csv
        with (output/'video_metrics.csv').open(encoding='utf-8') as f:
            measured=list(csv.DictReader(f))
        candidates=sorted(measured,key=lambda r:float(r.get('frame_difference_0_255',0)),reverse=True)
        # Camera motion is not a scene cut. Bound extra probes to the largest
        # changes instead of tripling OCR work throughout moving footage.
        for row in candidates[:min(12,max(3,int(duration/8)))]:
            if float(row.get('frame_difference_0_255',0))>15:
                t=float(row.get('time_seconds',0));times.extend([max(0,t-.35),min(duration-.1,t+.35)])
    except (OSError,ValueError):pass
    times=sorted(set(round(float(t),3) for t in times if t>=0))
    observations=[]
    try:
        for i,t in enumerate(times):
            require_memory(RESERVE_MB)
            capture.set(cv2.CAP_PROP_POS_MSEC,t*1000);ok,frame=capture.read()
            if not ok:continue
            ratio=min(1,1280/max(frame.shape[:2]));frame=cv2.resize(frame,None,fx=ratio,fy=ratio)
            relative=f'ocr_frames/frame_{i:04d}.jpg';cv2.imwrite(str(output/relative),frame,[cv2.IMWRITE_JPEG_QUALITY,88])
            result,_=engine(frame)
            lines=[]
            for box,text,confidence in result or []:
                if confidence>=.55 and str(text).strip():
                    lines.append({'text':str(text).strip(),'confidence':round(float(confidence),3),
                                  'box':np.asarray(box,dtype=float).round(1).tolist()})
            lines.sort(key=lambda r:(min(p[1] for p in r['box']),min(p[0] for p in r['box'])))
            observations.append({'time_seconds':t,'frame_file':relative,'lines':lines})
            progress((i+1)/len(times),f'Reading on-screen text ({i+1}/{len(times)})')
    finally:capture.release()
    groups=trusted_groups(observations,duration)
    result={'available':True,'frames':observations,'sources':select_evidence(groups,duration),
            'sampling':'0.8 fps plus scene-change probes and final frame; unsampled overlays can be missed',
            'engine':'RapidOCR / ONNX Runtime / CPU','language_coverage':'Latin/English and Chinese recognizer; Indic script overlays require a native check. Hinglish Latin text is retained without translation.',
            'evidence_min_confidence':.90,'sampled_frames':len(observations),'all_text_groups':len(groups),'text_groups':groups}
    _write_json(output/'ocr.json',result)
    return result
