"""Local, versioned brand evidence and conservative feedback calibration."""
from pathlib import Path
import io
import json
import math
import re
import uuid
import zipfile
import xml.etree.ElementTree as ET

MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
MAX_TEXT = 12000


def brand_path(results, brand_id):
    if not re.fullmatch(r"[a-f0-9]{32}", brand_id):
        raise ValueError("Choose a saved brand.")
    return Path(results) / "_brands" / brand_id / "profile.json"


def read_brand(results, brand_id):
    return json.loads(brand_path(results, brand_id).read_text(encoding="utf-8"))


def save_brand(results, profile):
    from studio_pipeline import _write_json
    path = brand_path(results, profile["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    profile["version"] = profile.get("version", 0) + 1
    _write_json(path, profile)
    return profile


def new_brand(results, name):
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100:
        raise ValueError("Brand name must be 1–100 characters.")
    return save_brand(results, {"id": uuid.uuid4().hex, "name": name.strip(),
                               "documents": {}, "references": [], "feedback": []})


def extract_document(filename, content):
    if not content or len(content) > MAX_DOCUMENT_BYTES:
        raise ValueError("Each document must be non-empty and at most 5 MB.")
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md"}:
        text = content.decode("utf-8-sig")
    elif suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted or len(reader.pages) > 40:
            raise ValueError("Use an unlocked PDF with at most 40 pages.")
        text = "\n\n".join(p.extract_text() or "" for p in reader.pages)
    elif suffix == ".docx":
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if sum(i.file_size for i in archive.infolist()) > 20 * 1024 * 1024:
                raise ValueError("DOCX expands beyond the 20 MB limit.")
            root = ET.fromstring(archive.read("word/document.xml"))
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            text = "\n".join("".join(t.text or "" for t in p.findall(".//w:t", ns))
                             for p in root.findall(".//w:p", ns))
    else:
        raise ValueError("Use PDF, DOCX, UTF-8 TXT or Markdown.")
    text = text.replace("\x00", "").strip()
    if not text:
        raise ValueError("No selectable text was found. Paste the brand instructions instead; scanned PDFs need OCR first.")
    if len(text) > MAX_TEXT:
        raise ValueError(f"Document contains {len(text):,} characters; use a focused brief of at most {MAX_TEXT:,}. Nothing was silently truncated.")
    return text


def outcome_values(data):
    limits = {"team_rating": 100, "views": 10**12, "retention_percent": 500,
              "conversions": 10**12, "spend": 10**10}
    result = {}
    for key, maximum in limits.items():
        value = data.get(key)
        if value in (None, ""):
            continue
        if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= maximum:
            raise ValueError(f"Invalid {key}.")
        if key in {"views", "conversions"} and value != int(value):
            raise ValueError(f"{key} must be a whole number.")
        result[key] = value
    distribution = data.get("distribution", "unknown")
    if distribution not in {"unknown", "organic", "paid", "mixed"}:
        raise ValueError("Choose organic, paid, mixed or unknown distribution.")
    notes = data.get("notes", "")
    if not isinstance(notes, str) or len(notes) > 1500:
        raise ValueError("Feedback notes must be at most 1,500 characters.")
    result.update(distribution=distribution, notes=notes.strip())
    return result


def calibration(profile, exclude_job=None, exclude_fingerprint=None):
    # Use distinct evaluated submissions, not handpicked successful references.
    rows = [r for r in profile.get("feedback", []) if r.get("job_id") != exclude_job
            and r.get("job_id") not in profile.get("reference_history", [])
            and not (exclude_fingerprint and r.get("video_hash") == exclude_fingerprint)
            and not (r.get("video_hash") and r["video_hash"] in profile.get("reference_hashes", []))
            and r.get("purpose") != "reference" and "team_rating" in r
            and isinstance(r.get("base_score"), (int, float))]
    rows = list({r.get("video_hash") or r["job_id"]: r for r in rows}.values())
    scores = [r["team_rating"] for r in rows]
    enough = len(rows) >= 5 and max(scores, default=0) - min(scores, default=0) >= 20
    delta = sum(r["team_rating"] - r["base_score"] for r in rows) / len(rows) if rows else 0
    adjustment = max(-10, min(10, delta * len(rows) / (len(rows) + 10))) if enough else 0
    return {"sample_count": len(rows), "active": enough, "adjustment": round(adjustment, 1),
            "method": "Brand-specific team-rating correction: mean(team rating − uncalibrated brand overall) × n/(n+10), capped at ±10. Starts after 5 distinct non-reference videos with a rating spread of at least 20 points. Successful references and the video being assessed are excluded. Views and conversions are reported as observations, not training labels. This adapts scoring; it does not train model weights or establish predictive accuracy."}


def reference_review(report):
    """Normalize saved cloud evidence without inventing a semantic review."""
    review=report.get('review',{})
    if review.get('available') and review.get('sources'):
        return review
    if report.get('backend')!='nvidia':
        return {}
    from studio_gemma_video import validate_result
    try:
        if report.get('cognitive'):
            from studio_virality import validate_cognitive_response
            cognitive=report['cognitive']
            duration=report.get('video',{}).get('duration_seconds',report.get('pacing',{}).get('duration_seconds'))
            fields={k:v for k,v in cognitive.items() if k not in {'model','interpretation'}}
            score=validate_cognitive_response(fields,duration)['attention_retention_score']
        else:
            score=validate_result(json.dumps(report.get('result')))['overall_probability']
    except (ValueError,RuntimeError,TypeError):
        return {}
    pacing=report.get('pacing',{})
    duration=report.get('video',{}).get('duration_seconds',pacing.get('duration_seconds'))
    if type(duration) not in (int,float) or not math.isfinite(duration) or duration<=0:
        return {}
    sources=[]
    if pacing.get('available') is True and isinstance(pacing.get('text'),str) and pacing['text'].strip():
        sources.append(dict(id='S1',kind='speech',start=0.,end=duration,text=pacing['text']))
    frames=report.get('cognitive',{}).get('visual_observations',[]) or report.get('visual_frames',[])
    for frame in frames[:8]:
        timestamp=frame.get('timestamp')
        observation=frame.get('observation')
        if (type(timestamp) in (int,float) and math.isfinite(timestamp) and 0<=timestamp<duration
                and isinstance(observation,str) and observation.strip()):
            sources.append(dict(id=f'V{len(sources)+1}',kind='visual',start=timestamp,
                end=min(duration,timestamp+1),text='Visual-model observation (may be wrong): '+observation))
    return dict(available=bool(sources),sources=sources,context=report.get('context',{}),
                estimate={'score':score},dimensions=[])


def snapshot(results, brand_id, exclude_job=None, exclude_fingerprint=None):
    profile = read_brand(results, brand_id)
    references = []
    for item in profile.get("references", []):
        job_id = item["job_id"]
        if job_id == exclude_job or (exclude_fingerprint and item.get("video_hash") == exclude_fingerprint):
            continue
        try:
            report = json.loads((Path(results) / job_id / "report.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        review = reference_review(report)
        if not review.get("available"):
            continue
        sources = review.get("sources", [])
        # Explicitly bounded excerpts, not a claim to inspect every reference frame.
        excerpts = sources[:2] + sources[-2:] if len(sources) > 4 else sources
        references.append({"job_id": job_id, "name": report["video"].get("name", "Reference"),
                           "language": report.get("transcript", {}).get("language",report.get('pacing',{}).get('language')),
                           "platform": review.get("context", {}).get("platform", "general"),
                           "duration_seconds": report["video"].get("duration_seconds",report.get('pacing',{}).get('duration_seconds')),
                           "score": review.get("estimate", {}).get("score", review.get("overall_score")),
                           "dimensions": [{"key": d["key"], "grade": d["grade"]} for d in review.get("dimensions", [])],
                           "excerpts": [dict(s, text=s["text"][:600]) for s in excerpts],
                           "outcomes": item.get("outcomes", {})})
    return {"id": brand_id, "name": profile["name"], "version": profile["version"],
            "documents": profile.get("documents", {}), "references": references,
            "calibration": calibration(profile, exclude_job, exclude_fingerprint),
            "team_notes": [{"rating": r.get("team_rating"), "notes": r["notes"]}
                           for r in profile.get("feedback", [])[-8:]
                           if r.get("job_id") != exclude_job and r.get("notes")
                           and not (exclude_fingerprint and r.get("video_hash") == exclude_fingerprint)],
            "note": "This is an upload-time snapshot. Future brand changes and feedback do not silently rescore saved reports."}


def register_reference(results, brand_id, job_id, outcomes):
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise ValueError("Choose a completed report ID.")
    report = json.loads((Path(results) / job_id / "report.json").read_text(encoding="utf-8"))
    review=reference_review(report)
    if not review.get("available") or not review.get("sources"):
        raise ValueError("A reference needs a completed review with usable transcript or visual evidence.")
    info_path = Path(results) / job_id / "upload_info.json"
    info = json.loads(info_path.read_text(encoding="utf-8")) if info_path.exists() else {}
    fingerprint = info.get("video_hash")
    profile = read_brand(results, brand_id)
    refs = [r for r in profile.get("references", []) if r["job_id"] != job_id]
    if len(refs) >= 5:
        raise ValueError("Keep at most 5 active reference videos per brand; remove one before adding another.")
    profile["references"] = refs + [{"job_id": job_id, "outcomes": outcomes, "video_hash": fingerprint}]
    profile["reference_history"] = list(dict.fromkeys(profile.get("reference_history", []) + [job_id]))
    if fingerprint:
        profile["reference_hashes"] = list(dict.fromkeys(profile.get("reference_hashes", []) + [fingerprint]))
    return save_brand(results, profile)


def save_feedback(results, brand_id, job_id, report, outcomes, purpose="candidate", video_hash=None):
    profile = read_brand(results, brand_id)
    row = dict(outcomes, job_id=job_id, purpose=purpose, video_hash=video_hash,
               base_score=report.get("review", {}).get("brand_review", {}).get("uncalibrated_overall",
                   report.get("review", {}).get("estimate", {}).get("score",report.get('cognitive',{}).get('attention_retention_score',report.get('result',{}).get('overall_probability')))))
    profile["feedback"] = [r for r in profile.get("feedback", []) if r["job_id"] != job_id] + [row]
    profile["feedback"] = profile["feedback"][-200:]
    for ref in profile.get("references", []):
        if ref["job_id"] == job_id:
            ref["outcomes"] = outcomes
    return save_brand(results, profile)
