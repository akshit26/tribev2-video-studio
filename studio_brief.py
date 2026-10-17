"""Concise, evidence-based review and CPU-encoded review excerpts."""
from __future__ import annotations

import html
import re
import subprocess
from pathlib import Path


def build_brief(report: dict) -> dict:
    creative = report.get("creative", {})
    scores = {c["key"]: c.get("value") for c in creative.get("cards", [])}
    duration = float(report["video"]["duration_seconds"])
    metrics = report.get("metrics", {})
    score = scores.get("virality")
    strengths, changes = [], []
    opening = creative.get("opening_text", "")
    if re.search(r"\b(you|your|whenever|problem|struggle)\b", opening, re.I):
        strengths.append({"title": "A relatable opening", "detail": f'The first five seconds connect to a familiar situation: “{opening.strip()}”.'})
    elif scores.get("hook") is not None and scores["hook"] >= 70:
        strengths.append({"title": "Clear opening cues", "detail": "The spoken opening contains several useful attention cues in the first five seconds."})
    actions = creative.get("cta_matches", [])
    closing = [a for a in actions if a["time_seconds"] >= max(0, duration - 10)]
    if closing:
        action = closing[0]
        strengths.append({"title": "An explicit closing action", "detail": f'At {action["time_seconds"]:.1f}s, the spoken “{action["action"]}” cue gives the viewer a next step.'})
    if metrics.get("visual_change_seconds"):
        strengths.append({"title": "Visual variety", "detail": "Visible changes across the sampled frames break up the presentation. Watch the middle excerpt to check that each change supports the message."})
    if scores.get("hook") is not None and scores["hook"] < 70:
        changes.append({"title": "1. Sharpen the first five seconds", "detail": "Test a shorter problem-to-benefit opening. Put the payoff in the first sentence, then move straight into the demonstration."})
    pace = metrics.get("words_per_minute")
    if pace is not None and pace > 180:
        changes.append({"title": f"{len(changes)+1}. Give the key claim room", "detail": f"Speech averages {pace:.0f} words/min. Cut repeated setup and add a small pause around the benefit and final action."})
    if scores.get("cta") is not None and scores["cta"] < 80:
        changes.append({"title": f"{len(changes)+1}. Make the next step explicit", "detail": "End with one action and explain what the viewer receives or where to go. Reinforce it with readable on-screen text."})
    if metrics.get("low_confidence_word_count") and len(changes) < 3:
        changes.append({"title": f"{len(changes)+1}. Check the captions", "detail": "The transcript contains uncertain words. Verify product names, numbers, and claims against the original audio before publishing."})
    if len(changes) < 3:
        changes.append({"title": f"{len(changes)+1}. Test a second opening", "detail": "Keep the body and CTA the same; compare two opening versions using actual watch time and actions per view."})
    if score is None:
        verdict = "Not enough evidence for an overall score"
        summary = "Review the excerpts manually. A complete score requires supported English speech plus pacing and visual measurements; missing evidence is left unscored."
    else:
        verdict = "Promising structure; refine before posting" if score >= 65 else "Revise the creative before posting"
        summary = "The closing action is a strength. " if closing else "The next step for viewers needs a careful check. "
        summary += "The opening is the clearest opportunity to improve engagement." if scores.get("hook", 100) < 70 else "The opening has useful verbal cues; focus the edit on clarity and pacing."
    clips = []
    if duration > 0:
        windows = [("Opening", 0, min(6, duration), "Check how quickly the problem and payoff become clear.")]
        if duration >= 20:
            windows.append(("Middle", duration / 2 - 3, duration / 2 + 3, "Check the main message, visual support, and pace."))
        if duration >= 12:
            windows.append(("Closing", max(6, duration - 7), duration, "Check the final action and whether there is enough time to follow it."))
        for title, start, end, reason in windows:
            clips.append({"title": title, "start": round(start, 2), "end": round(end, 2), "reason": reason})
    review = report.get("review")
    if review and review.get("available"):
        from studio_report_quality import separate_recognition_notes
        separate_recognition_notes(review)
        return {"version": 2, "overall_score": review["overall_score"], "verdict": review["verdict"],
                "summary": review["summary"], "strengths": review["strengths"],
                "changes": [{"title": e["title"], "detail": f'{e["start"]:.1f}-{e["end"]:.1f}s: {e["instruction"]}'} for e in review["edits"]],
                "clips": clips, "score_note": review["score_note"]}
    if not creative:
        summary = "A usable transcript and completed semantic review are required. Check the processing notes; no replacement keyword score has been assigned."
    return {"version": 1, "overall_score": score, "verdict": verdict, "summary": summary,
            "strengths": strengths[:3], "changes": changes[:3], "clips": clips,
            "score_note": "A heuristic creative score, not a prediction of views or virality. Actual performance depends on the audience and distribution."}


def create_clips(video: Path, output: Path, brief: dict) -> None:
    import imageio_ffmpeg
    from studio_video import clip_command, run_gpu_render
    directory = output / "clips"
    directory.mkdir(parents=True, exist_ok=True)
    for index, clip in enumerate(brief["clips"]):
        relative = f"clips/clip_{index:02d}.mp4"
        destination = output / relative
        command = clip_command(imageio_ffmpeg.get_ffmpeg_exe(), video, destination,
                               clip["start"], clip["end"] - clip["start"])
        try:
            run_gpu_render(command, output / f"render_clip_{index:02}.log")
            clip["file"] = relative
            clip["renderer"] = "NVIDIA NVDEC / CUDA scale / NVENC H.264"
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            destination.unlink(missing_ok=True)
            clip["error"] = str(exc) + ". No CPU video encoder was started."


def render_brief_pdf(report: dict, output: Path) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, KeepTogether, Image
    from reportlab.lib.utils import ImageReader
    from studio_screenshots import screenshot_path
    from studio_report import _font_setup, _text

    output = Path(output)
    path = output if output.suffix.lower() == ".pdf" else output / "report.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    regular, bold, _ = _font_setup()
    styles = {"body": ParagraphStyle("body", fontName=regular, fontSize=9, leading=13, spaceAfter=6),
              "title": ParagraphStyle("title", fontName=bold, fontSize=22, leading=27, spaceAfter=10),
              "heading": ParagraphStyle("heading", fontName=bold, fontSize=12, leading=16, spaceBefore=10, spaceAfter=6),
              "small": ParagraphStyle("small", fontName=regular, fontSize=8, leading=11, textColor=colors.HexColor("#526053"), spaceAfter=5)}
    def p(text, style="body"):
        return Paragraph(html.escape(_text(text)), styles[style])
    brief = report["brief"]
    score = brief["overall_score"]
    story = [p("Your video review", "title"), p(report["video"].get("name", "Uploaded video"), "small"),
             p(f"Overall creative score: {score} / 100" if score is not None else "Overall creative score: unavailable", "heading"),
             p(brief["verdict"]), p(brief["summary"])]
    for label, key in [("What works well", "strengths"), ("Changes to make first", "changes")]:
        story.append(p(label, "heading"))
        items = brief[key]
        if not items:
            story.append(p("No clear strengths could be established from the available evidence."))
        for item in items:
            story.append(KeepTogether([p(item["title"]), p(item["detail"], "small")]))
    story.append(p("Video screenshots", "heading"))
    for clip in brief["clips"]:
        label = f'{clip["title"]} | {clip["start"]:.1f}-{clip["end"]:.1f}s'
        content = [p(label), p(clip["reason"], "small")]
        for frame in clip.get("screenshots", []):
            image_path = screenshot_path(frame, path.parent)
            if image_path:
                width, height = ImageReader(str(image_path)).getSize()
                scale = min(200 / width, 140 / height)
                content.append(Image(str(image_path), width=width * scale, height=height * scale, hAlign="LEFT"))
                content.append(p(f'Source frame near {frame["time_seconds"]:.2f}s', "small"))
            else:
                content.append(p("Screenshot unavailable; check the source video.", "small"))
        story.append(KeepTogether(content))
    story.extend([Spacer(1, 8), p("Screenshots are embedded in this PDF. Playable excerpts remain available in Studio.", "small"), p(brief["score_note"], "small")])
    if report.get("processing", {}).get("warnings"):
        story.append(p("Some analysis was unavailable; see the processing note in Studio.", "small"))
    SimpleDocTemplate(str(path), pagesize=A4, topMargin=32, bottomMargin=30, leftMargin=40, rightMargin=40,
                      title="Video creative review", author="Local Video Studio").build(story)
    return path
