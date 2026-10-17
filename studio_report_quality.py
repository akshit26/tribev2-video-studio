"""Keep extraction limitations separate from creative judgments in exports."""
import re


def separate_recognition_notes(review):
    from studio_ocr import comment_link_ctas
    from studio_review_parts import reconcile_summary_cta
    reconcile_summary_cta(review, comment_link_ctas(review.get('sources', [])))
    summary = review.get("summary", "")
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', summary)
    pattern = re.compile(
        r'(?:inconsistent|noisy|fragmented|corrupted|garbled)\s+(?:OCR|recognition|transcription)'
        r'|(?:OCR|recognition|transcription)\b.{0,80}\b(?:errors?|noise|corruption|misrecognition)', re.I)
    removed = [s for s in sentences if pattern.search(s)]
    if not removed:
        return
    review.setdefault("summary_before_recognition_filter", summary)
    review["summary"] = ' '.join(s for s in sentences if s not in removed) or 'A reliable creative summary could not be established from the available evidence.'
    review.setdefault("summary_extraction_notes", []).extend(removed)
    note = 'Some extracted text needs verification; recognition errors are not evidence of poor creative quality.'
    if note not in review.setdefault("uncertainties", []):
        review["uncertainties"].append(note)
