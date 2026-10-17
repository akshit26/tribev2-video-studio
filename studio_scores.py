"""Transparent creative-review indices; no calibrated audience predictions."""
from __future__ import annotations

import math
import re
import statistics


def creative_scores(report: dict, emotion: dict | None = None) -> dict:
    duration = report["video"]["duration_seconds"]
    transcript = report.get("transcript") or {}
    segments = transcript.get("segments") or []
    words = [w for segment in segments for w in segment.get("words", []) if w.get("word")]
    english = transcript.get("language") in {"en", "english"}
    spoken = bool(words) and english
    opening = [w for w in words if w["start"] < 5]
    opening_text = " ".join(w["word"] for w in opening)
    full_text = " ".join(segment["text"] for segment in segments)
    first_speech = min((w["start"] for w in words), default=None)
    questions = bool(re.search(r"\b(?:why|how|what if|did you|have you|ever|imagine|secret|mistake)\b|\?", opening_text, re.I))
    relevance = bool(re.search(r"\b(?:you|your|whenever|struggle|problem|tired of|hate|don't like|do not like|can't|cannot)\b", opening_text, re.I))
    benefit = bool(re.search(r"\b(?:learn|save|fix|solution|improve|better|easy|easier|without|stop|avoid)\b", opening_text, re.I))
    onset = 20 if first_speech is not None and first_speech <= .75 else 10 if first_speech is not None and first_speech <= 2 else 0
    opening_wpm = len(opening) / min(5, max(duration, .1)) * 60
    density = 20 if 80 <= opening_wpm <= 180 else 10 if 40 <= opening_wpm <= 220 else 0
    hook_parts = [
        {"input": "Speech begins within 0.75 s", "points": onset, "maximum": 20},
        {"input": "Audience/problem cue in first 5 s (English keyword rule)", "points": 25 if relevance else 0, "maximum": 25},
        {"input": "Question/curiosity cue in first 5 s (English keyword rule)", "points": 20 if questions else 0, "maximum": 20},
        {"input": "Benefit cue in first 5 s (English keyword rule)", "points": 15 if benefit else 0, "maximum": 15},
        {"input": "Opening pace 80-180 words/min (review heuristic)", "points": density, "maximum": 20},
    ]
    hook = sum(p["points"] for p in hook_parts) if spoken else None

    actions = []
    pattern = re.compile(r"\b(comment|subscribe|follow|click|tap|share|save|visit|buy|shop|download|sign up|dm|message)\b", re.I)
    for segment in segments if spoken else []:
        for match in pattern.finditer(segment["text"]):
            verb = match.group(1).lower()
            # "Save time/money" describes a benefit, not a platform action.
            if verb in {"save", "share"} and not re.match(
                r"\s+(?:this|the|my|our|it|video|post|reel)\b", segment["text"][match.end():], re.I
            ):
                continue
            timestamp = next((w["start"] for w in segment.get("words", []) if verb in w["word"].lower()), segment["start"])
            actions.append({"action": verb, "time_seconds": timestamp, "text": segment["text"]})
    final_actions = [a for a in actions if a["time_seconds"] >= max(0, duration - 10)]
    action_text = " ".join(a["text"] for a in actions)
    reward = bool(re.search(r"\b(link|bio|profile|description|send|get|receive|free|website|dm|dms)\b", action_text, re.I))
    focused = len({a["action"] for a in final_actions or actions}) == 1
    cta_parts = [
        {"input": "Spoken action cue detected (keyword rule)", "points": 50 if actions else 0, "maximum": 50},
        {"input": "Action cue in final 10 s", "points": 20 if final_actions else 0, "maximum": 20},
        {"input": "Destination/reward cue accompanies action", "points": 15 if actions and reward else 0, "maximum": 15},
        {"input": "One distinct action in closing CTA", "points": 15 if focused else 0, "maximum": 15},
    ]
    cta = sum(p["points"] for p in cta_parts) if spoken else None
    metrics = report.get("metrics", {})
    wpm = metrics.get("words_per_minute")
    pace = None
    if spoken and wpm is not None:
        pace = round(max(0, 100 - (120 - wpm) if wpm < 120 else 100 - (wpm - 180) if wpm > 180 else 100))
    transitions = len(metrics.get("visual_change_seconds", []))
    windows = max(0, int(math.ceil(duration)) - 1)
    rate = transitions / windows if windows else None
    visual = None if rate is None else round(max(0, min(100, 30 + rate * 700 if rate < .1 else 100 if rate <= .35 else 100 - (rate - .35) * 100)))
    probabilities = [w["probability"] for w in words if isinstance(w.get("probability"), (int, float))]
    transcription_confidence = round(statistics.mean(probabilities) * 100) if probabilities else None
    inputs = [
        {"name": "First spoken word", "value": first_speech, "unit": "seconds"},
        {"name": "Opening spoken words (first 5 s)", "value": len(opening), "unit": "words"},
        {"name": "Opening speech pace", "value": round(opening_wpm, 1) if words else None, "unit": "words/min"},
        {"name": "Opening audience/problem cue", "value": relevance if spoken else None, "unit": "keyword match"},
        {"name": "Opening curiosity cue", "value": questions if spoken else None, "unit": "keyword match"},
        {"name": "Opening benefit cue", "value": benefit if spoken else None, "unit": "keyword match"},
        {"name": "Detected spoken CTA cues", "value": len(actions) if spoken else None, "unit": "matches"},
        {"name": "First CTA cue", "value": actions[0]["time_seconds"] if actions else None, "unit": "seconds"},
        {"name": "CTA in last 10 s", "value": bool(final_actions) if spoken else None, "unit": "keyword match"},
        {"name": "CTA destination/reward cue", "value": reward if spoken else None, "unit": "keyword match"},
        {"name": "Whole-video speech pace", "value": wpm, "unit": "words/min"},
        {"name": "Transcript word count", "value": metrics.get("word_count"), "unit": "words"},
        {"name": "Low-confidence words (<0.60)", "value": metrics.get("low_confidence_word_count"), "unit": "words"},
        {"name": "Fast subtitle segments (>20 characters/s)", "value": metrics.get("fast_caption_segment_count"), "unit": "segments"},
        {"name": "Large sampled visual changes (>=25/255)", "value": transitions, "unit": "transitions"},
        {"name": "Large-change fraction", "value": round(rate * 100, 1) if rate is not None else None, "unit": "% of sampled transitions"},
        {"name": "Median audio RMS", "value": metrics.get("median_audio_rms_dbfs"), "unit": "dBFS"},
        {"name": "Maximum decoded audio peak", "value": metrics.get("peak_audio_dbfs"), "unit": "dBFS"},
        {"name": "Near-full-scale audio windows", "value": len(metrics.get("near_peak_seconds", [])), "unit": "seconds"},
        {"name": "Duration", "value": duration, "unit": "seconds"},
    ]
    factors = [("hook", hook, .35), ("cta", cta, .25), ("pacing", pace, .20), ("visual", visual, .20)]
    # Never impute unavailable evidence to make a complete-looking viral score.
    viral = round(sum(value * weight for _, value, weight in factors)) if all(value is not None for _, value, _ in factors) else None
    cards = [
        {"key": "virality", "label": "Virality readiness", "value": viral,
         "method": "Unvalidated creative-review index: 35% hook + 25% CTA + 20% speech pacing + 20% visual variation. Not a probability of going viral or a prediction of views.",
         "evidence": "Calculated only when all four inputs are available.",
         "components": [{"input": key, "value": value, "weight": weight} for key, value, weight in factors]},
        {"key": "hook", "label": "Opening hook", "value": hook,
         "method": "English spoken-hook rubric for the first 5 seconds. It does not assess an on-screen-only or visual hook.",
         "evidence": opening_text or "No timed spoken opening available.", "components": hook_parts if spoken else []},
        {"key": "cta", "label": "Spoken CTA", "value": cta,
         "method": "English action/destination keyword rubric. Mentions can be false positives; on-screen CTAs are not read.",
         "evidence": " | ".join(f"{a['time_seconds']:.1f}s: {a['text']}" for a in actions[:4]) or "No spoken action cue detected.",
         "components": cta_parts if spoken else []},
        {"key": "pacing", "label": "Speech pacing", "value": pace,
         "method": "Review heuristic: 100 at 120-180 words/min, falling one point per word/min outside that band, clipped to 0-100. No universal ideal pace is assumed.",
         "evidence": f"Whole-video pace: {wpm} words/min.", "components": []},
        {"key": "visual", "label": "Visual variation", "value": visual,
         "method": "Frame-change heuristic: rises 30 to 100 at 0-10% large transitions, stays 100 at 10-35%, falls above 35%. Motion and overlays can count; these are not confirmed cuts or retention.",
         "evidence": f"{transitions} of {windows} sampled transitions have grayscale difference >=25/255.", "components": []},
        {"key": "transcription", "label": "ASR confidence", "value": transcription_confidence,
         "method": "Mean speech recognizer word probability x100; not calibrated transcription accuracy or viewer comprehension.",
         "evidence": f"{len(probabilities)} timed words with recognizer probabilities.", "components": []},
    ]
    emotion = emotion or {"available": False, "distribution": {}, "timeline": [], "reason": "Language-tone model output unavailable."}
    recommendations = []
    if hook is not None and hook < 70:
        recommendations.append("Test a more explicit opening benefit or question in the first five seconds. The rubric missed one or more verbal cues; a strong visual opening can still work.")
    if cta is not None and cta < 80:
        recommendations.append("Test one clear closing action and its destination or reward. Check on-screen instructions too; this score only reads speech.")
    if pace is not None and pace < 80:
        recommendations.append("Test shorter sentences or pauses around the key claim and CTA; the full-clip speech pace falls outside this rubric's preferred band.")
    if metrics.get("low_confidence_word_count", 0):
        recommendations.append("Review low-confidence names, numbers, and benefit claims before publishing the automatically generated subtitles.")
    recommendations.append("A/B test the revised opening and CTA with your actual audience. Compare platform retention, shares per view, saves per view, and conversions; these are not inferred from the video file.")
    return {"version": "creative-rubric-1.0", "scale": "0-100 review indices, not audience-outcome probabilities",
            "cards": cards, "opening_text": opening_text, "cta_matches": actions, "inputs": inputs,
            "emotion": emotion, "recommendations": recommendations,
            "unavailable": ["Expected views", "Probability of going viral", "Actual retention / completion", "Share or conversion rate", "Actual viewer emotions"],
            "method_note": "Scores are transparent, uncalibrated, unvalidated review heuristics. Compare variants cautiously; gameable keyword matches and domain differences can distort them. English speech is required for hook, CTA, and composite scoring."}
