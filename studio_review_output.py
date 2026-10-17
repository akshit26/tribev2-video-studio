"""Detailed PDF export using browser font shaping for Indian scripts."""
from pathlib import Path
import html


def detailed_html(report: dict, job_id: str, directory: Path | None = None) -> str:
    from studio_report import _text
    from studio_screenshots import screenshot_html
    def screenshots(item):
        return screenshot_html(item.get("screenshots", []), directory) if directory else ''
    esc = lambda value: html.escape(_text(value), quote=True)
    review = report["review"]
    score_label = "brand-aligned overall" if review.get("brand_review") else "estimated creative score"
    sources = {s["id"]: s for s in review["sources"]}
    def references(ids):
        return "".join(f'<blockquote>{esc(i)} | {sources[i]["start"]:.1f}-{sources[i]["end"]:.1f}s: {esc(sources[i]["text"])}</blockquote>' for i in ids if i in sources)
    chunks = [f'<h1>Detailed creative review</h1><p>{esc(report["video"]["name"])} | {report["video"]["duration_seconds"]:.1f}s | {esc(review["content_language"])}</p>',
              f'<div class="score">{review["overall_score"] if review["overall_score"] is not None else "Unavailable"}<small> / 100 {score_label}</small></div>',
              f'<h2>{esc(review["verdict"])}</h2><p>{esc(review["summary"])}</p>',
              f'<p class="note">{esc(review["score_note"])}</p><p class="note">{esc(review.get("transcript_quality", {}).get("note", ""))}</p><h2>What works well</h2>']
    overview = ''.join(screenshots(clip) for clip in report["brief"]["clips"])
    if overview:
        chunks.insert(2, '<div class="overview"><h2>Video at a glance</h2><div class="screenshotstrip">' + overview + '</div></div>')
    for strength in review["strengths"]:
        chunks.append(f'<article><h3>{esc(strength["title"])}</h3><p>{esc(strength["detail"])}</p>{references(strength["source_ids"])}</article>')
    estimate = review.get("estimate")
    if estimate:
        chunks.append(f'<h2>Language uncertainty adjustment</h2><p><b>Estimate: {estimate["score"]}/100 | sensitivity range: {estimate["range"][0]}–{estimate["range"][1]}</b></p><p>Before adjustment: {estimate["raw_score"]}/100. Speech evidence weight: {estimate["evidence_weight_percent"]}% (not transcription accuracy).</p><p>{esc(estimate["method"])}</p><p class="note">{esc(estimate["range_note"])}</p>')
    chunks.append('<h2>Score breakdown before uncertainty adjustment</h2><p>' + esc(review["anchors"]) + '</p>')
    for row in review["dimensions"]:
        if row.get("evidence_scope") == "whole_transcript_absence_check":
            chunks.append('<p class="note">Absence assessment: the full transcript below is the search scope, not a quote proving an absent feature. Visual-only evidence and recognition errors still require verification.</p>')
        chunks.append(f'<article><h3>{esc(row["label"])}: {row["grade"]}/4 | {row["points"]:g} of {row["weight"]} overall points</h3><p>{esc(row["rationale"])}</p><p class="note">Criterion: {esc(row["criterion"])}</p>{references(row["source_ids"])}</article>')
        adjusted = next((r for r in (estimate or {}).get("dimensions", []) if r["key"] == row["key"]), None)
        if adjusted:
            chunks.append(f'<p class="note">After uncertainty adjustment: {adjusted["estimated_points"]:g} of {row["weight"]} points; evidence weight {adjusted["reliability"] * 100:.0f}%.</p>')
            if adjusted.get("recognition_concern"):
                chunks.append('<p class="note">Possible transcription errors were identified in this category; its judgment has reduced weight.</p>')
    if review.get("brand_review"):
        from studio_brand_output import brand_html
        chunks.append(brand_html(review["brand_review"], directory))
    target = review["target"]
    chunks.append(f'<h2>Plan toward {target["score"]}/100</h2><p>{esc(target["explanation"])}</p>')
    if target.get("needs_improvement"):
        chunks.append('<h3>Rubric priorities to work toward 75</h3><ol>')
        for item in target.get("priorities", []):
            numbers = ", ".join(str(n) for n in item["edit_numbers"])
            chunks.append(f'<li><b>{esc(item["label"])}: {item["grade"]}/4 now; aim for {item["goal_grade"]}/4.</b> {esc(item["reason"])} Apply edits {numbers} and check their acceptance criteria.</li>')
        chunks.append('</ol>')
    for index, edit in enumerate(review["edits"], 1):
        chunks.append(f'<article class="edit"><h3>{index}. {esc(edit["title"])} | {edit["start"]:.1f}-{edit["end"]:.1f}s</h3>{screenshots(edit)}<p><b>{esc(edit["operation"].upper())}:</b> {esc(edit["instruction"])}</p><p><b>Exact replacement / edit:</b> {esc(edit["replacement"])}</p><p><b>English meaning:</b> {esc(edit["english_gloss"])}</p><p><b>Why:</b> {esc(edit["why"])}</p><p><b>Acceptance check:</b> {esc(edit["verify"])}</p>{references(edit["source_ids"])}</article>')
    chunks.append('<h2>Video screenshots</h2><p class="note">Actual source frames are embedded in this PDF. Edit screenshots show the existing video, not a preview of proposed changes. Playable clips remain available in Studio.</p>')
    for clip in report["brief"]["clips"]:
        text = f'{esc(clip["title"])} | {clip["start"]:.1f}-{clip["end"]:.1f}s'
        chunks.append(f'<article><h3>{text}</h3>{screenshots(clip)}<p>{esc(clip.get("reason", ""))}</p></article>')
    chunks.append('<h2>What needs human verification</h2><ul>')
    notes = review.get("uncertainties", []) + report.get("processing", {}).get("warnings", [])
    notes += ["A fluent speaker should check the transcript and suggested lines, especially code switching, dialects, names and claims. The visual model supplies only sampled captions; it does not read every on-screen word."]
    chunks.extend('<li>' + esc(note) + '</li>' for note in notes)
    chunks.append('</ul><h2>Original-language transcript</h2>')
    chunks.extend(f'<p><b>{esc(s["id"])} | {s["start"]:.1f}-{s["end"]:.1f}s</b><br>{esc(s["text"])}</p>' for s in sources.values())
    process = report["processing"]
    chunks.append(f'<p class="note">Model: {esc(review["model"])}. Processing: {esc(process.get("device"))}. Observed total GPU peak: {esc(process.get("peak_gpu_mb"))} MiB; target: {esc(process.get("budget_mb"))} MiB. Not a hard system-wide cap. Raw score = sum of grade / 4 x category weight, rounded; estimated overall applies the uncertainty adjustment above. The old English keyword score is not used.</p>')
    return '<!doctype html><html><head><meta charset="utf-8"><style>@page{size:A4;margin:16mm}body{font:11px/1.65 "Segoe UI","Nirmala UI",sans-serif;color:#243329}h1{font-size:26px}h2{font-size:18px;margin-top:25px;break-after:avoid}h3{font-size:13px;margin-bottom:6px;break-after:avoid}.score{font-size:48px;color:#2d633b}.score small{font-size:13px}.note{font-size:10px;color:#5b675e}article{margin:15px 0;padding:12px;background:#f4f7f3;border-left:3px solid #819e6d;break-inside:avoid}blockquote{font-size:10px;color:#4b604f;border-left:2px solid #c4d2bd;padding-left:10px;margin:8px 0}p{margin:7px 0;overflow-wrap:anywhere}a{color:#276132}.edit{background:#f8f5eb;break-inside:auto}.overview{break-inside:avoid}.screenshotstrip{display:flex;gap:24px}.screenshotstrip figure{max-width:100%}.screenshotstrip img{height:130px}.screenshots{display:flex;gap:12px;align-items:flex-start;break-inside:avoid;margin:12px 0}figure{margin:0;max-width:46%;break-inside:avoid}figure img{display:block;max-width:100%;height:165px;object-fit:contain;object-position:left}figcaption{font-size:9px;color:#58645a;line-height:1.5;margin-top:4px}</style></head><body>' + ''.join(chunks) + '</body></html>'


def render_detailed_pdf(report: dict, output: Path) -> Path:
    from playwright.sync_api import sync_playwright
    path = output if output.suffix.lower() == ".pdf" else output / "report.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    from studio_decision_pdf import decision_html
    document = decision_html(report, path.parent)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True, args=['--disable-gpu'])
        try:
            page = browser.new_page()
            page.set_content(document, wait_until="load")
            page.evaluate("document.fonts.ready")
            overflowing=lambda:page.evaluate("Array.from(document.querySelectorAll('.content')).some(e=>e.scrollHeight>e.clientHeight+2)")
            if overflowing():page.evaluate("document.body.classList.add('compact')")
            if overflowing():raise ValueError('The concise PDF layout overflowed; no clipped report was exported.')
            temporary=path.with_name(path.stem+'.rendering.pdf')
            page.pdf(path=str(temporary), format="A4", print_background=True, prefer_css_page_size=True)
            from pypdf import PdfReader
            if not 3<=len(PdfReader(temporary).pages)<=4:
                raise ValueError('The concise report exceeded its 3–4 page limit.')
            temporary.replace(path)
        finally:
            browser.close()
    return path
