"""Portable brand-check and reference-comparison PDF sections."""
import html
import json
import re
from studio_screenshots import screenshot_html


def brand_html(brand, directory=None):
    esc = lambda value: html.escape(str(value), quote=True)
    chunks = [f'<h2>Brand fit: {esc(brand["brand_name"])}</h2><p><b>Brand-aligned overall: {brand["overall_score"]}/100 | sensitivity range {brand["range"][0]}–{brand["range"][1]}</b></p>',
              f'<p>Brand alignment: {brand["compliance_score"] if brand["compliance_score"] is not None else "Not scored"}/100. Assessed checks: {brand["checked"]}/{brand["total_checks"]}; unknown: {brand["unknown"]}.</p>',
              f'<p class="note">{esc(brand["scoring_note"])}</p><p class="note">{esc(brand["snapshot_note"])} Brand version {brand["version"]}.</p>',
              f'<p>Team-rating adjustment: {brand["calibration"]["adjustment"]:+g} points; {brand["calibration"]["sample_count"]} rated candidates.</p><p class="note">{esc(brand["calibration"]["method"])}</p>']
    for check in brand["checks"]:
        chunks.append(f'<article><h3>{esc(check["status"].upper())}: {esc(check["requirement"])}</h3><blockquote>{esc(check["quote"])}</blockquote><p class="note">{esc(check["document_name"])} | section {check["section"]}</p><p>{esc(check["reason"])}</p><p><b>Change / verify:</b> {esc(check["change"])}</p><p class="note">Current video evidence: {esc(", ".join(check["source_ids"]) or "Unknown")}</p></article>')
    chunks.append('<h2>Comparison with successful reference videos</h2>')
    if not brand["comparisons"]:
        chunks.append('<p>No analyzed references were attached to this upload.</p>')
    for row in brand["comparisons"]:
        ref = row["reference"]
        chunks.append(f'<article class="edit"><h3>{esc(ref["name"])}</h3><p class="note">Language: {esc(ref["language"])} | platform: {esc(ref["platform"])} | duration {ref["duration_seconds"]:.1f}s</p>')
        if directory and re.fullmatch(r"[a-f0-9]{32}", ref["job_id"]):
            ref_dir = directory.parent / ref["job_id"]
            try:
                saved = json.loads((ref_dir / "report.json").read_text(encoding="utf-8"))
                frames = [f for c in saved.get("brief", {}).get("clips", []) for f in c.get("screenshots", [])][:3]
                chunks.append(screenshot_html(frames, ref_dir))
            except (OSError, ValueError):
                chunks.append('<p class="note">Reference screenshots unavailable.</p>')
        outcomes = ref.get("outcomes", {})
        chunks.append('<p class="note">Team-supplied outcomes: ' + esc("; ".join(f'{k.replace("_", " ")}: {v}' for k,v in outcomes.items() if k != "notes") or "Not supplied") + '</p>')
        for key, label in (("similarities", "What matches"), ("differences", "What differs"), ("adapt", "What to adapt"), ("caution", "Comparison limits")):
            chunks.append(f'<p><b>{label}:</b> {esc(row[key])}</p>')
        chunks.append(f'<p class="note">Current source IDs: {esc(", ".join(row["source_ids"]))}; reference excerpt IDs: {esc(", ".join(row["reference_source_ids"]))}. IDs refer to separate videos.</p></article>')
    if brand.get("team_advice"):
        chunks.append('<h2>Applying saved team feedback</h2><p>' + esc(brand["team_advice"]["guidance"]) + '</p>')
    return ''.join(chunks)
