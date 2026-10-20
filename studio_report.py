"""Evidence-based video reports and paginated PDF exports.

This module deliberately does not infer emotions, audience retention, or brain
responses. AI captions and transcripts remain observations to verify.
"""
from __future__ import annotations

from datetime import datetime, timezone
import html
import math
from pathlib import Path, PureWindowsPath
import re
import statistics
import unicodedata


def _number(value, default=None):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError, OverflowError):
        return default


def _text(value) -> str:
    """Remove secrets and absolute local paths from printable report strings."""
    value = str(value or "")
    value = re.sub(r"hf_[A-Za-z0-9]+", "[redacted token]", value)
    value = re.sub(r"[A-Za-z]:[\\/][^\r\n\"<>|]*", "[local path]", value)
    value = re.sub(r"(?<![\w:])/(?:Users|home|tmp|var|mnt)/[^\s<>\"]+", "[local path]", value)
    # Joiners are meaningful in Indic and Urdu text, unlike control characters.
    return "".join(c for c in value if not unicodedata.category(c).startswith("C") or c in "\n\t\u200c\u200d").strip()


def _basename(value) -> str:
    return _text(PureWindowsPath(str(value or "Uploaded video")).name) or "Uploaded video"


def _timestamp(seconds) -> str:
    seconds = max(0, _number(seconds, 0))
    minutes, rest = divmod(seconds, 60)
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours:02}:{minutes:02}:{rest:04.1f}" if hours else f"{minutes:02}:{rest:04.1f}"


def _times(values, maximum=12) -> str:
    result = ", ".join(_timestamp(value) for value in values[:maximum])
    if len(values) > maximum:
        result += f", and {len(values) - maximum} more sampled windows"
    return result


def _relative_frame(value) -> str:
    path = PureWindowsPath(str(value or ""))
    if not value or path.is_absolute() or path.drive or ".." in path.parts:
        return ""
    return path.as_posix()


def _model_names(values) -> list[str]:
    result = []
    for value in values or []:
        if isinstance(value, dict):
            name = value.get("name") or value.get("model") or value.get("id") or "Model"
            details = [value[key] for key in ("device", "precision", "compute_type") if value.get(key)]
            name = str(name) + (" (" + ", ".join(map(str, details)) + ")" if details else "")
        else:
            name = value
        result.append(_text(name))
    return result


def build_report(video_info: dict, measurements: list[dict], transcript: dict | None,
                 scenes: list[dict], processing: dict) -> dict:
    """Build a JSON-serializable report from measured and model-produced evidence.

    Pace is normalized by the entire video duration, not estimated speaking time.
    Thresholds below are editorial heuristics and are disclosed in each finding.
    """
    duration = max(0, _number(video_info.get("duration_seconds"), 0))
    video = {
        "name": _basename(video_info.get("name") or video_info.get("video") or video_info.get("path")),
        "duration_seconds": duration,
        "width": int(max(0, _number(video_info.get("width"), 0))),
        "height": int(max(0, _number(video_info.get("height"), 0))),
        "fps": max(0, _number(video_info.get("fps"), 0)),
        "file_bytes": int(max(0, _number(video_info.get("file_bytes"), 0))),
        "has_audio": bool(video_info.get("has_audio")),
    }
    process = {
        "device": _text(processing.get("device") or "unknown"),
        "gpu_name": _text(processing.get("gpu_name")),
        "budget_mb": _number(processing.get("budget_mb")),
        "peak_gpu_mb": _number(processing.get("peak_gpu_mb")),
        "peak_gpu_scope": _text(processing.get("peak_gpu_scope") or "device"),
        "models": _model_names(processing.get("models")),
        "warnings": [_text(warning) for warning in (processing.get("warnings") or [])],
        "brain_inference": False,
    }
    for key in ("elapsed_seconds", "gpu_total_mb", "sample_interval_seconds", "sample_count"):
        if key in processing:
            process[key] = _number(processing[key])
    if processing.get("memory_policy"):
        process["memory_policy"] = _text(processing["memory_policy"])

    normalized_transcript = {"language": _text((transcript or {}).get("language") or "unknown"), "segments": []}
    low_confidence, fast_captions = [], []
    word_count = 0
    for raw in (transcript or {}).get("segments", []):
        start = max(0, _number(raw.get("start"), 0))
        end = max(start, _number(raw.get("end"), start))
        segment = {"start": start, "end": end, "text": _text(raw.get("text")), "words": []}
        for word in raw.get("words") or []:
            if not isinstance(word, dict):
                continue
            word_start = max(0, _number(word.get("start"), start))
            probability = _number(word.get("probability"))
            normalized = {"word": _text(word.get("word")), "start": word_start,
                          "end": max(word_start, _number(word.get("end"), end)),
                          "probability": probability}
            segment["words"].append(normalized)
            if probability is not None and probability < 0.6:
                low_confidence.append(normalized)
        # Whitespace tokenization is transparent and does not require another model.
        word_count += len(re.findall(r"\S+", segment["text"]))
        if end > start and len(segment["text"]) / (end - start) > 20:
            fast_captions.append((start, end, len(segment["text"]) / (end - start)))
        normalized_transcript["segments"].append(segment)
    words_per_minute = round(word_count * 60 / duration, 1) if duration > 0 and transcript is not None else None

    rows = []
    for row in measurements:
        time = _number(row.get("time_seconds"))
        if time is not None and time >= 0:
            rows.append({key: _number(row.get(key)) for key in (
                "time_seconds", "brightness_0_255", "frame_difference_0_255", "audio_rms_dbfs", "audio_peak_dbfs")})
    rows.sort(key=lambda row: row["time_seconds"])
    rms = [row["audio_rms_dbfs"] for row in rows if row["audio_rms_dbfs"] is not None]
    peaks = [row["audio_peak_dbfs"] for row in rows if row["audio_peak_dbfs"] is not None]
    near_peak = [row["time_seconds"] for row in rows if row["audio_peak_dbfs"] is not None and row["audio_peak_dbfs"] >= -1]
    visual_rows = [row for row in rows if row["time_seconds"] > 0 and row["frame_difference_0_255"] is not None]
    visual_change = [row["time_seconds"] for row in visual_rows if row["frame_difference_0_255"] >= 25]
    quiet = [row["time_seconds"] for row in rows if row["audio_rms_dbfs"] is not None and row["audio_rms_dbfs"] < -40]
    metrics = {
        "word_count": word_count if transcript is not None else None,
        "words_per_minute": words_per_minute,
        "median_audio_rms_dbfs": round(statistics.median(rms), 2) if rms else None,
        "peak_audio_dbfs": round(max(peaks), 2) if peaks else None,
        "near_peak_seconds": near_peak,
        "visual_change_seconds": visual_change,
        "low_confidence_word_count": len(low_confidence),
        "quiet_window_seconds": quiet,
        "fast_caption_segment_count": len(fast_captions),
        "measurement_count": len(rows),
    }
    normalized_scenes = [{"time_seconds": max(0, _number(scene.get("time_seconds"), 0)),
                          "caption": _text(scene.get("caption")),
                          "frame_file": _relative_frame(scene.get("frame_file"))} for scene in scenes]
    summary = [f"{duration:.1f}-second video, {video['width']} x {video['height']} pixels, {video['fps']:.2f} frames/second."]
    if transcript is not None:
        summary.append(f"Automatic transcript: {word_count} whitespace-separated words; " +
                       (f"{words_per_minute:.1f} words/minute across the full clip." if words_per_minute is not None else "pace unavailable for a zero-duration clip."))
    elif video["has_audio"]:
        summary.append("The video has an audio stream; an automatic transcript was not available.")
    else:
        summary.append("No audio stream was detected in the video.")
    if rms:
        summary.append(f"Sampled median audio level: {metrics['median_audio_rms_dbfs']:.1f} dBFS RMS; maximum sampled peak: {metrics['peak_audio_dbfs']:.1f} dBFS." if peaks else
                       f"Sampled median audio level: {metrics['median_audio_rms_dbfs']:.1f} dBFS RMS.")
    summary.append((f"{len(visual_change)} sampled visual changes exceeded the declared threshold" if visual_rows else
                    "Visual change measurements are unavailable") + f"; {len(normalized_scenes)} frames are included for review.")
    if process["peak_gpu_mb"] is not None:
        scope = "process" if process["peak_gpu_scope"] == "process" else "whole GPU (including other apps)"
        summary.append(f"Observed peak GPU memory: {process['peak_gpu_mb']:.0f} MiB for the {scope}.")

    findings = []
    def finding(category, title, detail, evidence, priority="info"):
        findings.append({"category": category, "title": title, "detail": detail, "evidence": evidence, "priority": priority})

    if transcript is None and video["has_audio"]:
        finding("speech", "Speech analysis unavailable", "Audio measurements remain available. Check processing warnings for the transcription status.",
                "An audio stream exists, but no transcript was supplied.", "review")
    elif transcript is not None and not word_count:
        finding("speech", "No words recognized", "This does not establish that the clip contains no speech. Music, accents, noise, language support, and low levels can affect recognition.",
                "The transcription model returned no text.", "review")
    elif words_per_minute is not None:
        if words_per_minute > 180:
            finding("speech", "Dense speech across the clip", "Consider shorter sentences or pauses around the main message. Preview captions on a small screen and split long phrases where necessary. The >180 words/minute threshold is an editorial heuristic, not an audience response prediction.",
                    f"{word_count} transcript words / {duration:.2f} seconds = {words_per_minute:.1f} words/minute, including pauses.", "review")
        else:
            finding("speech", "Measured speech pace", "Pace uses the full clip, including non-speech portions. It is a descriptive estimate; there is no universally correct delivery speed.",
                    f"{word_count} transcript words / {duration:.2f} seconds = {words_per_minute:.1f} words/minute.")
    if low_confidence:
        samples = "; ".join(f"{_timestamp(word['start'])}: {word['word']!r} ({word['probability']:.2f})" for word in low_confidence[:12])
        finding("speech", "Verify uncertain transcript words", "Listen again at the listed times before publishing subtitles. Word probability <0.60 is a review heuristic; model probabilities are not calibrated correctness percentages.",
                f"{len(low_confidence)} word(s) below the threshold. {samples}" + (". Additional words are marked in the transcript data." if len(low_confidence) > 12 else ""), "review")
    if fast_captions:
        evidence = "; ".join(f"{_timestamp(start)}-{_timestamp(end)}: {speed:.1f} characters/s" for start, end, speed in fast_captions[:12])
        finding("accessibility", "Review subtitle reading time", "Some automatic transcript segments exceed 20 characters/second, including spaces (editorial heuristic). Re-segment or extend subtitle timing where speech and adjacent captions allow. Existing on-screen captions were not detected or assessed.",
                f"{len(fast_captions)} segment(s). {evidence}", "review")
    if near_peak:
        finding("audio", "Audio peaks approach full scale", "Review these windows for audible distortion before adding gain. Peaks >= -1 dBFS are a conservative headroom heuristic, not proof of clipping; encoded audio and decoding can also change peaks.",
                f"{len(near_peak)} sampled window(s) at {_times(near_peak)}; maximum sampled peak {max(peaks):.2f} dBFS.", "review")
    elif peaks:
        finding("audio", "Sampled peak headroom", "The sampled maximum stays below the -1 dBFS review threshold. This is a sample-peak measurement and does not measure true peak, LUFS, dialogue intelligibility, or perceived loudness.",
                f"Maximum sampled peak: {max(peaks):.2f} dBFS.")
    if quiet:
        finding("audio", "Quiet audio windows", "Check whether these windows are intentional pauses or sections that need a level adjustment. RMS < -40 dBFS is a heuristic for quiet digital audio, not verified silence or a speech detector.",
                f"{len(quiet)} of {len(rms)} measured audio windows: {_times(quiet)}.")
    if visual_change:
        finding("visual", "Review larger sampled visual changes", "These timestamps may correspond to cuts, camera motion, overlays, or changing subjects. Mean absolute grayscale frame difference >=25 on a 0-255 scale is a heuristic. Compare the video around each time; one-second sampling can miss short events.",
                f"{len(visual_change)} sampled transitions: {_times(visual_change)}.")
    elif visual_rows:
        finding("visual", "No large sampled changes at this threshold", "No measured transition reached a mean grayscale difference of 25/255 (heuristic). This does not mean the video is static; short cuts and movement between samples may be missed.",
                f"{len(rows)} measurement windows; visual differences compare successive sampled frames.")
    dark = [row["time_seconds"] for row in rows if row["brightness_0_255"] is not None and row["brightness_0_255"] < 40]
    bright = [row["time_seconds"] for row in rows if row["brightness_0_255"] is not None and row["brightness_0_255"] > 215]
    if dark or bright:
        finding("visual", "Review extreme average brightness", "Inspect these frames for readable subjects and text. Mean grayscale below 40 or above 215 is a heuristic and may simply reflect deliberate styling; it does not establish exposure or contrast problems.",
                (f"Dark frame samples: {_times(dark)}. " if dark else "") + (f"Bright frame samples: {_times(bright)}." if bright else ""))
    if any(scene["caption"] and scene["caption"] != "Sampled video frame" for scene in normalized_scenes):
        finding("content", "Automatic frame descriptions are available", "Use the frame gallery to inspect recurring subjects and presentation. Captions describe individual sampled frames and can misidentify objects or text; they do not establish actions, claims, speaker identity, or the meaning of the entire video.",
                f"{len(normalized_scenes)} sampled frames, from {_timestamp(normalized_scenes[0]['time_seconds'])} to {_timestamp(normalized_scenes[-1]['time_seconds'])}.")
    for warning in process["warnings"]:
        finding("processing", "Processing note", warning, "Reported by the local analysis pipeline.", "review")

    limitations = [
        "This memory-conscious report uses media measurements, speech recognition, and optional sampled-frame captions. Scores describe editorial and media observations.",
        "No measured or predicted brain activity, emotion, attention, retention, virality, authenticity, or medical conclusions are provided.",
        "Transcripts and frame captions are automatic model outputs and can be inaccurate. Verify names, numbers, claims, and uncertain words against the original video.",
        "Word counts use whitespace-separated transcript tokens. This measure is less meaningful for languages that do not separate words with spaces. Pace uses total video duration.",
        "Visual measurements use sampled, resized grayscale frames. They can miss short events, fine detail, and changes in color. Frame captions do not assess all frames or read all on-screen text.",
        "Audio values are digital sample levels in dBFS, not perceived loudness, LUFS, or true-peak measurements. Only the sampled windows were measured.",
        "Pace, reading-speed, brightness, visual-change, confidence, and audio thresholds are disclosed heuristics for review; they are not validated quality scores.",
        "The memory setting is an application budget, not an operating-system GPU partition. Observed GPU samples may miss brief peaks, and other applications can use GPU memory.",
    ]
    return {"title": "Video analysis report", "created_at": datetime.now(timezone.utc).isoformat(),
            "video": video, "processing": process, "summary": summary, "metrics": metrics,
            "findings": findings, "transcript": normalized_transcript, "scenes": normalized_scenes,
            "limitations": limitations}


def _font_setup():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import importlib.util
    import os

    candidates = []
    spec = importlib.util.find_spec("matplotlib")
    if spec and spec.origin:
        fontdir = Path(spec.origin).parent / "mpl-data" / "fonts" / "ttf"
        candidates.append((fontdir / "DejaVuSans.ttf", fontdir / "DejaVuSans-Bold.ttf"))
    win_fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    candidates += [(win_fonts / "arial.ttf", win_fonts / "arialbd.ttf"),
                   (win_fonts / "segoeui.ttf", win_fonts / "segoeuib.ttf"),
                   (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))]
    for normal, bold in candidates:
        if normal.is_file() and bold.is_file():
            try:
                if "StudioRegular" not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont("StudioRegular", str(normal)))
                    pdfmetrics.registerFont(TTFont("StudioBold", str(bold)))
                    pdfmetrics.registerFontFamily("StudioRegular", normal="StudioRegular", bold="StudioBold", italic="StudioRegular", boldItalic="StudioBold")
                regular_face = pdfmetrics.getFont("StudioRegular").face
                bold_face = pdfmetrics.getFont("StudioBold").face
                return "StudioRegular", "StudioBold", set(regular_face.charToGlyph).intersection(bold_face.charToGlyph)
            except (OSError, ValueError):
                continue
    return "Helvetica", "Helvetica-Bold", set(range(32, 127))


def render_pdf(report: dict, output: Path) -> Path:
    """Render a complete report, using only image files inside its output folder."""
    if report.get("review", {}).get("available"):
        from studio_review_output import render_detailed_pdf
        return render_detailed_pdf(report, Path(output))
    if report.get("brief"):
        from studio_brief import render_brief_pdf
        return render_brief_pdf(report, output)
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    output = Path(output)
    pdf_path = output if output.suffix.lower() == ".pdf" else output / "report.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    base_dir = pdf_path.parent.resolve()
    regular, bold, glyphs = _font_setup()
    replaced_glyphs = set()

    def printable(value):
        text = _text(value)
        result = []
        for char in text:
            if char in "\n\t" or ord(char) in glyphs:
                result.append(char)
            else:
                replaced_glyphs.add(char)
                result.append("[?]")
        return "".join(result)

    styles = {
        "body": ParagraphStyle("body", fontName=regular, fontSize=9, leading=13, textColor=colors.HexColor("#25334B"), spaceAfter=7, splitLongWords=True, alignment=TA_LEFT),
        "title": ParagraphStyle("title", fontName=bold, fontSize=23, leading=28, textColor=colors.HexColor("#12213D"), spaceAfter=12),
        "section": ParagraphStyle("section", fontName=bold, fontSize=14, leading=18, textColor=colors.HexColor("#164C71"), spaceBefore=14, spaceAfter=8, keepWithNext=True),
        "finding": ParagraphStyle("finding", fontName=bold, fontSize=10, leading=14, textColor=colors.HexColor("#12213D"), spaceBefore=8, spaceAfter=5, keepWithNext=True),
        "small": ParagraphStyle("small", fontName=regular, fontSize=8, leading=11, textColor=colors.HexColor("#5B677A"), spaceAfter=6, splitLongWords=True),
    }
    def paragraph(value, style="body"):
        return Paragraph(html.escape(printable(value)).replace("\n", "<br/>"), styles[style])

    width, height = A4
    document = SimpleDocTemplate(str(pdf_path), pagesize=A4, rightMargin=43, leftMargin=43,
                                 topMargin=46, bottomMargin=45,
                                 title=printable(report.get("title", "Video analysis report")), author="Local Video Studio")
    usable_width = width - 86
    story = [paragraph(report.get("title", "Video analysis report"), "title"),
             paragraph(report["video"]["name"], "finding"),
             paragraph(f"Generated {report.get('created_at', '')} | Local analysis", "small")]

    def section(title):
        story.append(paragraph(title, "section"))

    def table(rows):
        data = [[paragraph(label, "small"), paragraph(value)] for label, value in rows]
        obj = Table(data, colWidths=[usable_width * .36, usable_width * .64], hAlign="LEFT")
        obj.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                                ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#F1F5F9"), colors.white])]))
        story.append(obj)

    creative = report.get("creative")
    if creative:
        section("Creative scorecard")
        story.append(paragraph(creative.get("method_note", ""), "small"))
        table([(score["label"], f"{score['value']} / 100" if score.get("value") is not None else "Unavailable")
               for score in creative.get("cards", [])])
        section("Hook, CTA, and score evidence")
        for score in creative.get("cards", []):
            story.append(paragraph(score["label"], "finding"))
            story.append(paragraph(score.get("evidence", "")))
            story.append(paragraph(score.get("method", ""), "small"))
            for component in score.get("components", []):
                value = (f"{component.get('value')} / 100, weight {component['weight'] * 100:.0f}%"
                         if "weight" in component else f"{component['points']} / {component['maximum']} points")
                story.append(paragraph(f"{component['input']}: {value}", "small"))
        emotion = creative.get("emotion") or {}
        section("Emotional-language values")
        story.append(paragraph(emotion.get("interpretation") or emotion.get("reason") or "Model output unavailable.", "small"))
        if emotion.get("distribution"):
            table([(label.title(), f"{value:.2f}% classifier score")
                   for label, value in sorted(emotion["distribution"].items(), key=lambda item: -item[1])])
        for moment in emotion.get("timeline", []):
            dominant = moment["dominant"]
            story.append(paragraph(f"{_timestamp(moment['start'])}-{_timestamp(moment['end'])}: {dominant}, {moment['scores'][dominant]:.1f}%", "small"))
        section("Priority editing experiments")
        for recommendation in creative.get("recommendations", []):
            story.append(paragraph(recommendation))
        section("All score inputs")
        def input_value(item):
            value = item.get("value")
            return "Unavailable" if value is None else f"{value} {item.get('unit', '')}"
        table([(item["name"], input_value(item)) for item in creative.get("inputs", [])])
        story.append(paragraph("Not inferred from this file: " + "; ".join(creative.get("unavailable", [])), "small"))

    section("Summary")
    for item in report.get("summary", []):
        story.append(paragraph(item))
    section("Measured properties")
    video, metrics, process = report["video"], report.get("metrics", {}), report.get("processing", {})
    def number(value, digits=1, unit=""):
        value = _number(value)
        return "Unavailable" if value is None else f"{value:,.{digits}f}{unit}"
    table([
        ("Duration", number(video.get("duration_seconds"), 2, " seconds")),
        ("Dimensions / frame rate", f"{video.get('width', 0)} x {video.get('height', 0)} / {number(video.get('fps'), 2, ' fps')}"),
        ("File size / audio stream", f"{number(video.get('file_bytes', 0) / (1024 * 1024), 2, ' MiB')} / {'present' if video.get('has_audio') else 'absent'}"),
        ("Transcript word count", number(metrics.get("word_count"), 0)),
        ("Words/minute (full clip)", number(metrics.get("words_per_minute"))),
        ("Median sampled audio RMS", number(metrics.get("median_audio_rms_dbfs"), 2, " dBFS")),
        ("Maximum sampled audio peak", number(metrics.get("peak_audio_dbfs"), 2, " dBFS")),
        ("Near-full-scale windows", str(len(metrics.get("near_peak_seconds", [])))),
        ("Larger sampled visual changes", str(len(metrics.get("visual_change_seconds", [])))),
        ("Low-confidence transcript words", str(metrics.get("low_confidence_word_count", 0))),
    ])
    section("Findings and practical review steps")
    for finding in report.get("findings", []):
        prefix = f"{str(finding.get('category', 'review')).upper()} | "
        story.append(paragraph(prefix + finding.get("title", "Finding"), "finding"))
        story.append(paragraph(finding.get("detail", "")))
        evidence = finding.get("evidence", "")
        if isinstance(evidence, list):
            evidence = "; ".join(map(str, evidence))
        story.append(paragraph("Evidence: " + str(evidence), "small"))

    if not report.get("creative"):
        section("Sampled frame gallery")
        story.append(paragraph("Descriptions below are automatic model observations. Inspect the thumbnails and original video to verify them.", "small"))
        if not report.get("scenes"):
            story.append(paragraph("No sampled frames are available."))
        for scene in report.get("scenes", []):
            story.append(paragraph(f"Frame at {_timestamp(scene.get('time_seconds'))}", "finding"))
            frame_name = _relative_frame(scene.get("frame_file"))
            candidate = (base_dir / frame_name).resolve() if frame_name else None
            if candidate and candidate.is_relative_to(base_dir) and candidate.is_file() and candidate.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                try:
                    image_width, image_height = ImageReader(str(candidate)).getSize()
                    scale = min((usable_width * .8) / image_width, 185 / image_height)
                    image = Image(str(candidate), width=image_width * scale, height=image_height * scale)
                    image.hAlign = "LEFT"
                    story.append(image)
                    story.append(Spacer(1, 6))
                except (OSError, ValueError, ZeroDivisionError):
                    story.append(paragraph("Thumbnail could not be loaded.", "small"))
            else:
                story.append(paragraph("Thumbnail unavailable.", "small"))
            story.append(paragraph(scene.get("caption") or "No automatic description is available."))

    section("Timestamped transcript")
    transcript = report.get("transcript") or {}
    story.append(paragraph(f"Detected language: {transcript.get('language', 'unknown')}. Automatic transcription; verify before publishing.", "small"))
    for segment in transcript.get("segments", []):
        story.append(paragraph(f"{_timestamp(segment.get('start'))} - {_timestamp(segment.get('end'))}", "finding"))
        story.append(paragraph(segment.get("text", "")))
    if not transcript.get("segments"):
        story.append(paragraph("No transcript is available."))

    section("Processing and memory")
    table([
        ("Selected processing device", process.get("device", "unknown")),
        ("GPU", process.get("gpu_name") or "Not available"),
        ("Configured memory budget", number(process.get("budget_mb"), 0, " MiB")),
        ("Observed peak GPU memory", number(process.get("peak_gpu_mb"), 0, " MiB")),
        ("GPU measurement scope", "Process" if process.get("peak_gpu_scope") == "process" else "Whole device, including other applications"),
    ])
    for model in process.get("models", []):
        story.append(paragraph("Model: " + str(model), "small"))
    if process.get("memory_policy"):
        story.append(paragraph(process["memory_policy"]))
    for warning in process.get("warnings", []):
        story.append(paragraph("Processing note: " + str(warning), "small"))
    section("Method and limitations")
    for limitation in report.get("limitations", []):
        story.append(paragraph(limitation, "small"))
    if replaced_glyphs:
        story.append(paragraph("Some characters are not supported by the installed PDF font and appear as [?]. Use the downloadable transcript for the original Unicode text.", "small"))

    def page_footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D9E1EA"))
        canvas.line(43, 33, width - 43, 33)
        canvas.setFont(regular, 8)
        canvas.setFillColor(colors.HexColor("#5B677A"))
        canvas.drawString(43, 21, "Local Video Studio | Automatic analysis - verify against the original")
        canvas.drawRightString(width - 43, 21, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=page_footer, onLaterPages=page_footer)
    return pdf_path
