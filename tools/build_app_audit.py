"""Build an evidence-labelled app audit PDF from a local JSON manifest.

Usage: python tools/build_app_audit.py results/app_audit/audit.json --output results/app_audit/app-audit.pdf
Private artifacts can stay in ignored results/. Sanitized manifests and reports
may be published under docs/reports/. No API calls.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable, ListFlowable, ListItem, PageBreak, Paragraph,
    SimpleDocTemplate, Spacer, Table, TableStyle,
)


def build(manifest: dict, output: Path) -> None:
    """Render factual content supplied by the caller; never calculate fake scores."""
    output.parent.mkdir(parents=True, exist_ok=True)
    normal, bold = "Helvetica", "Helvetica-Bold"
    font_dir = Path("C:/Windows/Fonts")
    if (font_dir / "segoeui.ttf").exists():
        pdfmetrics.registerFont(TTFont("AuditRegular", str(font_dir / "segoeui.ttf")))
        pdfmetrics.registerFont(TTFont("AuditBold", str(font_dir / "segoeuib.ttf")))
        normal, bold = "AuditRegular", "AuditBold"
    navy = colors.HexColor("#12283F")
    teal = colors.HexColor("#0B6A60")
    grey = colors.HexColor("#526176")
    light = colors.HexColor("#EDF3F7")
    styles = getSampleStyleSheet()
    for name in ("Normal", "BodyText"):
        styles[name].fontName = normal
        styles[name].fontSize = 9.5
        styles[name].leading = 14
        styles[name].textColor = navy
        styles[name].spaceAfter = 7
    for name in ("Title", "Heading1", "Heading2", "Heading3"):
        styles[name].fontName = bold
        styles[name].textColor = navy
    styles["Title"].fontSize = 28
    styles["Title"].leading = 33
    styles["Heading1"].fontSize = 20
    styles["Heading1"].leading = 25
    styles["Heading2"].fontSize = 12
    styles["Heading2"].leading = 16
    styles.add(ParagraphStyle("SmallAudit", parent=styles["BodyText"], fontSize=8, leading=11, textColor=grey))
    styles.add(ParagraphStyle("LabelAudit", parent=styles["BodyText"], fontName=bold, fontSize=8, textColor=teal))
    styles.add(ParagraphStyle("ScriptAudit", parent=styles["BodyText"], fontSize=11, leading=18, spaceAfter=13))

    def p(text, style="BodyText"):
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), styles[style])

    def bullets(items):
        return ListFlowable([ListItem(p(item), leftIndent=10) for item in items], bulletType="bullet", leftIndent=14, bulletFontName=normal, bulletFontSize=6, spaceAfter=10)

    def table(headers, rows, widths):
        cells = [[p(cell, "LabelAudit") for cell in headers]]
        cells.extend([[p(cell, "SmallAudit") for cell in row] for row in rows])
        result = Table(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
        result.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), light),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, 0), .6, teal),
            ("LINEBELOW", (0, 1), (-1, -1), .3, colors.HexColor("#DCE4EC")),
        ]))
        return result

    story = []

    def section(title, label=None):
        if story:
            story.append(PageBreak())
        if label:
            story.append(p(label.upper(), "LabelAudit"))
        story.extend([p(title, "Heading1"), Spacer(1, 8)])

    date = manifest.get("date", datetime.now().date().isoformat())
    story.extend([p("CREATOR VIDEO STUDIO / ENGINEERING AUDIT", "LabelAudit"), Spacer(1, 16),
                  p(manifest.get("title", "Reliability, speed and script quality"), "Title"),
                  p(f"{date} | {manifest.get('timezone', 'Asia/Calcutta')}", "SmallAudit"),
                  Spacer(1, 15), HRFlowable(width="100%", thickness=2, color=teal), Spacer(1, 16),
                  p(manifest.get("summary", "Audit in progress.")),
                  p("Scope", "Heading2"), p(manifest.get("scope", "")),
                  p("Release status", "Heading2"), p(manifest.get("release_status", "Pending final verification.")),
                  p("Key findings", "Heading2"), bullets(manifest.get("findings", [])),
                  p("Evidence standard", "Heading2"),
                  p("Live provider calls demonstrate one observed request at one point in time. Mocked regression tests exercise app logic without validating provider availability. Historical saved jobs establish past behaviour only. Editorial scores do not measure real audience retention, sales or virality.", "SmallAudit")])

    section("Endpoint diagnosis and measured latency", "01 / Live provider evidence")
    story.append(table(["Check", "Observed result", "Evidence type"],
                       [[r["check"], r["result"], r.get("type", "Live")]
                        for r in manifest.get("endpoint_checks", [])], [133, 264, 110]))
    story.extend([Spacer(1, 13), p("Why drafting felt slow", "Heading2"), bullets(manifest.get("latency_findings", [])),
                  p("Current model and deadline policy", "Heading2"), p(manifest.get("model_policy", "")),
                  p("Times include queueing and reasoning. Full-pipeline timings can include one rewrite and rescoring; unlike prompts do not establish a measured speedup.", "SmallAudit")])
    section("Application audit and fixes", "02 / Code and regression coverage")
    story.append(table(["Surface", "Coverage and outcome", "Evidence"],
                       [[r["surface"], r["outcome"], r.get("evidence", "")]
                        for r in manifest.get("coverage", [])], [110, 287, 110]))
    story.extend([Spacer(1, 13), p("Changes made", "Heading2"), bullets(manifest.get("fixes", [])),
                  p("Verification result", "Heading2"), p(manifest.get("test_result", "Awaiting final test run."))])

    section("Generated script and quality decision", "03 / Sample output")
    sample = manifest.get("sample", {})
    story.extend([p(sample.get("product", "No final sample supplied"), "Heading2"),
                  p(f"Evidence: {sample.get('evidence_type', 'Pending')} | Model: {sample.get('model', 'Not recorded')}", "SmallAudit"),
                  p(f"Duration: {sample.get('duration', 'Not recorded')} | Wall time: {sample.get('elapsed', 'Not recorded')} | Gate: {sample.get('status', 'Not assessed')}", "SmallAudit"),
                  p("Verified product facts", "Heading2"), p(sample.get("facts", "Not supplied.")),
                  p("Script", "Heading2"), p(sample.get("script", "No live final script was supplied at report build time."), "ScriptAudit"),
                  p("Independent assessment", "Heading2"), p(sample.get("assessment", "No approval or score inferred.")),
                  p("Creative judgement", "Heading2"), p(sample.get("editorial_review", "")),
                  p("A buy/no-buy or viral-success conclusion requires observed audience testing; the app's score is an editorial gate, not purchase intent or conversion evidence.", "SmallAudit")])

    section("Video review, trust and operating limits", "04 / Pipeline integrity")
    story.extend([p("Review pipeline", "Heading2"), bullets(manifest.get("pipeline", [])),
                  p("Safety and provenance checks", "Heading2"), bullets(manifest.get("integrity", [])),
                  p("Known limits and remaining work", "Heading2"), bullets(manifest.get("limitations", []))])

    section("Reproduction and evidence register", "05 / Audit trail")
    story.append(table(["Evidence", "What it establishes"],
                       [[r["path"], r["purpose"]] for r in manifest.get("evidence", [])], [240, 267]))
    story.extend([Spacer(1, 14), p("Commands used", "Heading2"), bullets(manifest.get("commands", [])),
                  p("Build this report", "Heading2"),
                  p(manifest.get("build_command", ".venv\\Scripts\\python.exe tools\\build_app_audit.py results\\app_audit\\audit.json --output results\\app_audit\\app-audit.pdf"), "SmallAudit"),
                  p("Repository revision", "Heading2"), p(manifest.get("revision", "Working tree under audit; see release commit in final delivery."), "SmallAudit")])
    source = manifest.get("nvidia_reasoning_source", "")
    if source.startswith("https://docs.nvidia.com/"):
        story.append(Paragraph('Primary source: <a href="' + escape(source, {'"': '&quot;'})
            + '">NVIDIA NIM model guide - Control Reasoning</a>. Medium effort retains reasoning with a shorter mode; high selects full reasoning.', styles["SmallAudit"]))

    doc = SimpleDocTemplate(str(output), pagesize=(595.28, 841.89), rightMargin=44, leftMargin=44,
                            topMargin=48, bottomMargin=46, title=manifest.get("title", "Creator Video Studio audit"),
                            author="Creator Video Studio engineering audit")

    def page_footer(canvas, document):
        canvas.saveState()
        canvas.setFont(normal, 8)
        canvas.setFillColor(grey)
        canvas.drawString(44, 25, f"Creator Video Studio | {date} | Evidence-led audit")
        canvas.drawRightString(551, 25, str(document.page))
        canvas.restoreState()

    doc.build(story, onFirstPage=page_footer, onLaterPages=page_footer)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, default=Path("results/app_audit/app-audit.pdf"))
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    build(manifest, args.output)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
