"""Language-neutral uncertainty adjustment; not a learned performance predictor."""
import math
import re


def language_uncertainty(rationale):
    """Catch explicit review admissions of ASR trouble, including confident ASR errors."""
    pattern = r"(?:transcription|speech recognition|recognition) (?:errors?|uncertainty|inaccuracies)|(?:misheard|mistranscribed|misrecognition|misrendering)"
    for match in re.finditer(pattern, rationale.lower()):
        prefix = rationale[max(0, match.start() - 25):match.start()].lower()
        if not re.search(r"(?:\bno|\bwithout|\bnot affected by)\s+(?:\w+\s+){0,2}$", prefix):
            return True
    return False


def recognition_weight(segment, corrected=False):
    if corrected:
        return 1.0
    values = [w.get("probability") for w in segment.get("words", [])]
    values = [p for p in values if type(p) in (int, float) and math.isfinite(p) and 0 <= p <= 1]
    if not values:
        return .5  # Missing confidence is unknown, not failed speech.
    mean = sum(values) / len(values)
    low_fraction = sum(p < .6 for p in values) / len(values)
    return max(0., min(1., (mean - .35) / .45, 2 * (1 - low_fraction)))


def estimate_score(dimensions, transcript, ocr=None):
    """Shrink uncertain cited evidence toward 50, equally for every language.

    The interval is a sensitivity envelope, NOT a statistical confidence interval.
    Unknown evidence can contribute anywhere from 0 to 100. An additional 8-point
    editorial allowance acknowledges that even perfect ASR does not validate an LLM.
    """
    corrected = bool(transcript.get("manually_corrected"))
    sources = {f"S{i+1}": recognition_weight(s, corrected)
               for i, s in enumerate(transcript.get("segments", []))}
    sources.update({s['id']:max(0.,min(1.,(float(s.get('confidence',.575))-.35)/.45))
                    for s in (ocr or {}).get('sources',[])})
    adjusted, low, high, coverage = 0., 0., 0., 0.
    rows = []
    for dimension in dimensions:
        ids = dimension["source_ids"]
        # Each cited source counts equally, so tokenization of Indian scripts
        # cannot outweigh a shorter segment or an English source.
        reliability = sum(sources.get(s, .5) for s in ids) / len(ids) if ids else .5
        recognition_concern = not corrected and any(s.startswith('S') for s in ids) and language_uncertainty(dimension.get("rationale", ""))
        if recognition_concern:
            reliability = min(reliability, .5)
        raw = dimension["grade"] * 25
        value = reliability * raw + (1 - reliability) * 50
        weight = dimension["weight"] / 100
        adjusted += value * weight
        low += reliability * raw * weight
        high += (reliability * raw + (1 - reliability) * 100) * weight
        coverage += reliability * weight
        rows.append({"key": dimension["key"], "reliability": round(reliability, 3),
                     "estimated_score": round(value, 1), "estimated_points": round(value * weight, 2),
                     "recognition_concern": recognition_concern})
    return {"version": 1, "score": round(adjusted),
            "raw_score": round(sum(d["grade"] / 4 * d["weight"] for d in dimensions)),
            "range": [max(0, math.floor(low - 8)), min(100, math.ceil(high + 8))],
            "evidence_weight_percent": round(coverage * 100), "neutral_prior": 50,
            "dimensions": rows, "label": "Estimated creative score",
            "method": "For each category: evidence weight × assessed score + (1 − evidence weight) × 50. Weights come from confidence in cited speech and OCR, or a team-corrected transcript. Explicit recognition-error concerns in a category rationale cap its evidence weight at 50%, even when the recognizer is confident. Language names never affect the calculation. Weak recognition reduces both penalties and praise; 50 is a neutral assumption, not a measured company average.",
            "range_note": "Sensitivity range, not a statistical confidence interval or a views forecast. It allows uncertain evidence to score anywhere from 0 to 100, plus an 8-point editorial allowance. These assumptions are not calibrated against campaign results. Confident mistranscription and cultural misunderstanding can still occur."}


def apply_estimate(review, report):
    estimate = estimate_score(review["dimensions"], report.get("transcript", {}), report.get("ocr"))
    review["estimate"] = estimate
    review["overall_score"] = estimate["score"]
    review["target"]["gap"] = max(0, review["target"]["score"] - estimate["score"])
    review["target"]["explanation"] = (
        "A grade of 3/4 in every dimension totals a raw rubric score of 75/100. "
        "The estimated overall also depends on speech and OCR reliability; verify uncertain speech before acting on provisional edits. "
        "Apply the edit plan, check its acceptance criteria, then upload the edited video to assess the result. "
        "No automatic point increases or viral performance are assumed.")
    review["score_note"] = (f"Estimated creative score {estimate['score']}/100; sensitivity range "
                            f"{estimate['range'][0]}–{estimate['range'][1]}. "
                            "Uncertain speech is treated as unknown, using a neutral 50-point assumption. "
                            "This is an uncalibrated creative assessment, not a probability of virality or predicted views.")
    return review
