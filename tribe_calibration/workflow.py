"""Original-input export, descriptive diagnostics, and human-gated segment reports."""
import hashlib
from pathlib import Path

import numpy as np

from .core import fingerprint, read_json, write_json, roi_series, summarize, score_sample, metrics


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def export_prediction(model, video, output, atlas, language, text_weight, checkpoint_hash):
    """Use an already-loaded TRIBE instance; never loads another scoring model.

    Loading/resource provisioning is explicit because full stock TRIBE has not
    been validated under this workstation's 4 GiB target.
    """
    if not 0 <= text_weight <= 1 or not checkpoint_hash:
        raise ValueError("Provide text_weight in [0,1] and checkpoint provenance")
    if not language or language in {"auto","unknown"}:
        raise ValueError("Calibration exports need an explicitly identified original language")
    output = Path(output)
    if output.suffix != ".npz":
        raise ValueError("Prediction output must end in .npz")
    events = model.get_events_dataframe(video_path=str(video), language=language,
                                       include_text=text_weight > 0)
    if text_weight > 0 and not (events.type == "Word").any():
        raise ValueError("Full/weakened text experiment has no transcript words. Use an explicit AV-only export, not a mislabeled tri-modal result.")
    predictions, segments = model.predict(events=events, text_weight=text_weight)
    values, names = roi_series(predictions, atlas)
    starts = np.array([s.start for s in segments], dtype=float)
    durations = np.array([s.duration for s in segments], dtype=float)
    # Validate correspondence/coverage before persisting anything as usable data.
    summarize(values, starts, durations, names)
    transcript = [{"start":float(w.start),"end":float(w.start+w.duration),"text":w.text}
                  for w in events.loc[events.type == "Word"].itertuples()]
    protocol = {"model":"facebook/tribev2","checkpoint_sha256":checkpoint_hash,
                "atlas":atlas,"text_weight":text_weight,"pipeline":"original-language-v2",
                "time_basis":"stimulus segment times; no additional 5-second shift"}
    metadata = dict(protocol, signature=fingerprint(protocol),language=language,roi_names=names,
                    video_sha256=file_hash(video),transcript=transcript,
                    transcript_note="Original ASR words, not native-verified. Audio/video-only export has no generated transcript.")
    output.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(output,predictions=predictions,roi_values=values,starts=starts,durations=durations)
    write_json(output.with_suffix(".json"),metadata)
    return metadata


def comparison_report(manifest_path, output):
    """Descriptive matched ROI differences, never attribution to tone or causality."""
    manifest = read_json(manifest_path); base = Path(manifest_path).resolve().parent
    rows = []; seen=set()
    for entry in manifest.get("samples",[]):
        path = base / entry["prediction_file"]; meta = read_json(path.with_suffix(".json"))
        if not entry.get("match_id") or entry["language"] != meta["language"] or meta.get("model") != "facebook/tribev2":
            raise ValueError("Matched video IDs, language and TRIBE provenance are required")
        key=(entry["language"],entry["match_id"])
        if key in seen:raise ValueError("Duplicate language/match pair")
        seen.add(key)
        with np.load(path,allow_pickle=False) as a:
            x,names = summarize(a["roi_values"],a["starts"],a["durations"],meta["roi_names"])
        rows.append(dict(entry,x=x,feature_names=names,signature=meta["signature"]))
    if len({r['signature'] for r in rows})>1:
        raise ValueError("The comparison dataset mixes checkpoint/atlas/ablation settings")
    result = {"comparisons":{},"finding":"Descriptive differences alone do not identify raw-model bias or threshold bias. Match human quality/audience and inspect the actual score formula before attributing causality."}
    for lang in sorted({r["language"] for r in rows}-{"en"}):
        english={r["match_id"]:r for r in rows if r["language"]=="en"}
        regional={r["match_id"]:r for r in rows if r["language"]==lang}
        ids=sorted(english.keys() & regional.keys())
        if len(ids)<10: raise ValueError(f"{lang}: at least 10 matched English/regional pairs required")
        pairs=[(english[i],regional[i]) for i in ids]
        if any(a["signature"]!=b["signature"] or a["feature_names"]!=b["feature_names"] for a,b in pairs):
            raise ValueError("Compare identical checkpoint/atlas/ablation settings across languages")
        a=np.array([x["x"] for x,y in pairs]);b=np.array([y["x"] for x,y in pairs])
        stats={}
        for j,key in enumerate(pairs[0][0]["feature_names"]):
            difference=b[:,j]-a[:,j];sd=difference.std(ddof=1)
            stats[key]={"english_mean":float(a[:,j].mean()),"regional_mean":float(b[:,j].mean()),
                        "paired_difference":float(difference.mean()),"paired_standardized_difference":float(difference.mean()/sd) if sd>1e-12 else None}
        stages={}
        for stage in ("derived_score","thresholded_score"):
            if all(stage in x and stage in y for x,y in pairs):
                stages[stage]={"english_mean":float(np.mean([x[stage] for x,y in pairs])),
                               "regional_mean":float(np.mean([y[stage] for x,y in pairs]))}
        result["comparisons"][lang]={"matched_pairs":len(ids),"roi_features":stats,"supplied_score_stages":stages,
                                     "attribution":"Unresolved; no automatic inference that lower brain activity means worse tone."}
    if not result["comparisons"]:raise ValueError("No English/regional comparisons supplied")
    write_json(output,result)
    return result


def transcript_quality(manifest_path, output):
    """WER/CER against human transcripts; no translation or ASR confidence proxy."""
    import unicodedata
    from Levenshtein import distance
    data=read_json(manifest_path);report={}
    for language in sorted({s["language"] for s in data["samples"]}):
        rows=[s for s in data["samples"] if s["language"]==language]
        if len({r["video_id"] for r in rows})<10:raise ValueError(f"Need 10 distinct native-reviewed samples for {language}")
        errors=[];words=chars=word_errors=char_errors=0
        for row in rows:
            if not row.get("native_reviewer") or not row.get("reference_text","").strip():
                raise ValueError("A native reviewer and nonempty original-language reference transcript are required")
            ref=unicodedata.normalize("NFC",row["reference_text"])
            hyp=unicodedata.normalize("NFC",row["hypothesis_text"])
            # Preserve script, punctuation, case and code-switching. CER supplements
            # whitespace WER, which is unsuitable alone for some regional scripts.
            a,b=ref.split(),hyp.split();we=distance(a,b);ce=distance(ref,hyp)
            words+=len(a);chars+=len(ref);word_errors+=we;char_errors+=ce
            errors.append({"video_id":row["video_id"],"wer":we/len(a),"cer":ce/len(ref)})
        report[language]={"samples":len(rows),"wer":word_errors/words,"cer":char_errors/chars,"sample_errors":errors,
                          "note":"NFC only; no translation, romanization or English normalization. Native semantic/name/code-switch review is still required."}
    write_json(output,report);return report


def ablation_report(manifest_path, output):
    """Compare temporal raw-ROI variation on the exact same inputs/time windows."""
    data=read_json(manifest_path);base=Path(manifest_path).resolve().parent;rows=[]
    seen=set(); matched={}
    for sample in data["samples"]:
        path=base/sample["prediction_file"];meta=read_json(path.with_suffix(".json"))
        if meta.get("model")!="facebook/tribev2":raise ValueError("Only TRIBE prediction artifacts are accepted")
        key=(meta["video_sha256"],meta["text_weight"])
        if key in seen:raise ValueError("Duplicate ablation input/weight")
        seen.add(key)
        with np.load(path,allow_pickle=False) as a:
            v=a["roi_values"];starts=a["starts"];durations=a["durations"]
            summarize(v,starts,durations,meta["roi_names"])
            if len(v)<2:raise ValueError("Need at least two time steps for temporal variation")
            compatibility={k:meta[k] for k in ("checkpoint_sha256","atlas","language","pipeline")}
            compatibility.update(starts=starts.tolist(),durations=durations.tolist(),roi_names=meta["roi_names"])
            previous=matched.setdefault(meta["video_sha256"],fingerprint(compatibility))
            if previous!=fingerprint(compatibility):raise ValueError("Ablations must use the same video, checkpoint, atlas and time windows")
            variation=np.mean(np.abs(np.diff(v,axis=0))/np.diff(starts)[:,None],axis=0)
        rows.append({"video_sha256":meta["video_sha256"],"language":meta["language"],"text_weight":meta["text_weight"],
                     "roi_mean_absolute_change_per_second":dict(zip(meta["roi_names"],variation.tolist()))})
    for video in matched:
        weights={r["text_weight"] for r in rows if r["video_sha256"]==video}
        if not {0,1}.issubset(weights):raise ValueError("Every video needs both full and audio/video-only predictions")
    result={"raw_temporal_stability":rows,
            "scoring_stability":"Not inferred without separately validated calibrations for each ablation.",
            "interpretation":"Less temporal variation is not better tone accuracy: a constant output is perfectly stable but uninformative. Use native held-out agreement to select a scoring configuration."}
    write_json(output,result);return result


def segment_report(prediction_path, calibration_path, clips_path, rules_path, output):
    path=Path(prediction_path);meta=read_json(path.with_suffix(".json"));artifact=read_json(calibration_path)
    clips=read_json(clips_path);rules=read_json(rules_path)
    if artifact["unit"]!="segment":raise ValueError("Segment flags require a calibration fitted to native segment ratings, not video-level labels")
    if rules["guideline_version"]!=artifact["guideline_version"]:raise ValueError("Rulebook guideline version differs from calibration")
    report={"language":meta["language"],"guideline_version":artifact["guideline_version"],
            "video_sha256":meta["video_sha256"],"status":"internal_native_review_required","clips":[],
            "note":"TRIBE temporal context limits localization. Threshold crossings are review flags, not verified guideline violations. Each creator-facing fix requires native approval."}
    with np.load(path,allow_pickle=False) as data:
        for i,clip in enumerate(clips):
            start,end=float(clip["start"]),float(clip["end"])
            x,names=summarize(data["roi_values"],data["starts"],data["durations"],meta["roi_names"],start,end)
            if names!=artifact["feature_names"]:raise ValueError("Feature ordering differs from calibration")
            scores=score_sample(artifact,meta["language"],x,meta["signature"],"segment",rules["guideline_version"])
            # In AV-only mode humans can supply reviewed original-language spans.
            words=meta.get("transcript",[])
            text=" ".join(w["text"] for w in words if w["start"]<end and w["end"]>start)
            if not text and clip.get("native_transcript") and clip.get("transcript_reviewer"):
                text=clip["native_transcript"]
            flags=[]
            for dim,score in scores.items():
                spec=artifact["dimensions"][dim];low,high=spec["target"]
                direction="low" if score<low else "high" if score>high else None
                if direction is None:continue
                options=[r for r in rules["rules"] if r["dimension"]==dim and r["direction"]==direction
                         and r["guideline_id"]==spec["guideline_id"] and r["language"]==meta["language"]]
                rule=options[0] if len(options)==1 else {}
                ready=bool(rule.get("native_text") and rule.get("english_explanation") and rule.get("native_reviewer"))
                flags.append({"id":f"clip-{i}:{dim}","dimension":dim,"score":score,"target":[low,high],"direction":direction,
                              "guideline_id":spec["guideline_id"],"original_transcript":text or None,
                              "native_suggestion":rule.get("native_text") if ready else None,
                              "english_explanation":rule.get("english_explanation") if ready else "A native-reviewed rule for this guideline/direction is required.",
                              "template_reviewer":rule.get("native_reviewer") if ready else None,
                              "native_review":None})
            report["clips"].append({"start":start,"end":end,"scores":scores,"flags":flags})
    write_json(output,report);return report


def creator_export(reviewed_report, output):
    report=read_json(reviewed_report)
    for clip in report["clips"]:
        for flag in clip["flags"]:
            approval=flag.get("native_review") or {}
            # Approval signs the exact content, preventing stale approval after edits.
            content={k:flag.get(k) for k in ("id","original_transcript","native_suggestion","english_explanation","guideline_id")}
            content.update(start=clip["start"],end=clip["end"],video_sha256=report["video_sha256"],guideline_version=report["guideline_version"])
            if not flag.get("native_suggestion") or not flag.get("original_transcript") or not approval.get("reviewer") or approval.get("language")!=report["language"] or approval.get("approved") is not True or approval.get("content_sha256")!=fingerprint(content):
                raise ValueError(f"Native-speaker approval is missing/stale for {flag['id']}; creator export withheld")
    report["status"]="native_reviewed"
    write_json(output,report)
