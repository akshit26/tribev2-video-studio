"""Inspect a video locally, and optionally predict TRIBE v2 brain responses."""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent


def configure_environment():
    # Only load this project's token; never print it or pass it on a command line.
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip() == "HF_TOKEN" and value.strip():
                os.environ.setdefault("HF_TOKEN", value.strip().strip("\"'"))
    os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]


def inspect_video(video: Path, output: Path) -> dict:
    import cv2
    import numpy as np
    from moviepy import VideoFileClip
    from PIL import Image

    output.mkdir(parents=True, exist_ok=True)
    frames_dir = output / "frames"
    frames_dir.mkdir(exist_ok=True)
    rows, thumbnails = [], []
    with VideoFileClip(str(video)) as clip:
        info = {
            "video": str(video), "duration_seconds": clip.duration,
            "width": clip.w, "height": clip.h, "fps": clip.fps,
            "file_bytes": video.stat().st_size, "has_audio": clip.audio is not None,
        }
        capture = cv2.VideoCapture(str(video))
        metric_times = list(np.arange(0, clip.duration, 1.0))
        thumb_times = list(np.linspace(0, max(0, clip.duration - .1), 12))
        targets = sorted([('metric',i,float(t)) for i,t in enumerate(metric_times)] +
                         [('thumb',i,float(t)) for i,t in enumerate(thumb_times)], key=lambda x:x[2])
        sampled = {}
        target_index = frame_index = 0
        last_frame = None
        while target_index < len(targets):
            ok, frame = capture.read()
            if not ok: break
            last_frame = frame
            frame_time = frame_index / max(clip.fps, 1)
            while target_index < len(targets) and targets[target_index][2] <= frame_time + .5 / max(clip.fps,1):
                kind, index, second = targets[target_index]
                sampled[(kind,index)] = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                target_index += 1
            frame_index += 1
        capture.release()
        if last_frame is None:
            raise ValueError("Could not decode any video frames")
        # Phone containers can report a duration a few frames beyond the
        # decodable stream. Preserve requested trailing samples with the final
        # valid frame instead of failing the entire analysis.
        while target_index < len(targets):
            kind, index, second = targets[target_index]
            sampled[(kind,index)] = Image.fromarray(cv2.cvtColor(last_frame, cv2.COLOR_BGR2RGB))
            target_index += 1
        previous = None
        for i, second in enumerate(metric_times):
            frame = sampled[('metric',i)]
            gray = np.asarray(frame.resize((96, 96)).convert("L"), dtype=float)
            row = {"time_seconds": float(second), "brightness_0_255": float(gray.mean()),
                   "frame_difference_0_255": float(np.abs(gray - previous).mean()) if previous is not None else 0.0}
            previous = gray
            rows.append(row)
        for i, second in enumerate(thumb_times):
            frame = sampled[('thumb',i)]
            frame.thumbnail((288, 288))
            filename = f"frames/frame_{i:02d}.jpg"
            frame.save(output / filename)
            thumbnails.append(f'<figure><img src="{filename}"><figcaption>{second:.2f} s</figcaption></figure>')
        if clip.audio is not None:
            audio_samples = clip.audio.to_soundarray(fps=16000)
            for row in rows:
                second = row["time_seconds"]
                end = min(second + 1, clip.duration)
                samples = audio_samples[int(second * 16000):int(end * 16000)]
                row["audio_rms_dbfs"] = float(20 * np.log10(max(float(np.sqrt(np.mean(samples ** 2))), 1e-10)))
                row["audio_peak_dbfs"] = float(20 * np.log10(max(float(np.abs(samples).max()), 1e-10)))
    info["largest_sampled_visual_changes_seconds"] = [r["time_seconds"] for r in sorted(rows[1:], key=lambda r: r["frame_difference_0_255"], reverse=True)[:5]]
    (output / "video_info.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    with (output / "video_metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    table = "".join(f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>" for k, v in info.items())
    related = " | ".join(f'<a href="{name}">{label}</a>' for name, label in [
        ("CONTENT_ANALYSIS.md", "Written content review"), ("transcript.txt", "Automatic transcript"),
        ("subtitles.srt", "Subtitles"), ("brain_info.json", "Brain inference details")
    ] if (output / name).exists())
    report = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Video inspection</title>
<style>body{{font:16px system-ui;max-width:1100px;margin:40px auto;padding:20px;background:#111827;color:#e5e7eb}}th,td{{text-align:left;padding:8px;border-bottom:1px solid #374151}}.frames{{display:flex;flex-wrap:wrap}}figure{{margin:10px}}a{{color:#93c5fd}}</style>
<h1>Video inspection</h1><p>Measured file, image, and audio properties. These are not brain predictions or scores for attention, emotions, or engagement.</p>
<table>{table}</table><p><a href="video_metrics.csv">Per-second visual and audio measurements</a></p>
<p>Frame difference compares small grayscale frames sampled one second apart. It can reflect cuts, camera movement, or changing subjects; it is not a scene detector. Audio levels are digital levels (dBFS), not perceived loudness.</p>
<p>{related}</p><h2>Sampled frames</h2><div class="frames">{''.join(thumbnails)}</div></html>'''
    (output / "video_report.html").write_text(report, encoding="utf-8")
    print(json.dumps(info, indent=2))
    print(f"Video report: {output / 'video_report.html'}")
    return info


def transcribe_video(video: Path, output: Path, speech_model: str) -> dict:
    from faster_whisper import WhisperModel

    local_model = ROOT / "cache" / f"faster-whisper-{speech_model}"
    if (local_model / "model.bin").is_file():
        speech_model = str(local_model.resolve())
    transcript_path = output / "transcript.json"
    signature = {"path": str(video), "size": video.stat().st_size,
                 "mtime_ns": video.stat().st_mtime_ns, "speech_model": speech_model}
    if transcript_path.exists():
        cached = json.loads(transcript_path.read_text(encoding="utf-8"))
        if cached.get("source") == signature:
            return cached
    print(f"Transcribing with faster-whisper/{speech_model} on CPU (int8)...", flush=True)
    model = WhisperModel(speech_model, device="cpu", compute_type="int8", cpu_threads=4)
    segments, info = model.transcribe(str(video), word_timestamps=True, vad_filter=True)
    result = {"source": signature, "language": info.language,
              "language_probability": info.language_probability, "segments": []}
    for segment in segments:
        result["segments"].append({"start": segment.start, "end": segment.end, "text": segment.text,
            "words": [{"start": w.start, "end": w.end, "word": w.word, "probability": w.probability}
                      for w in (segment.words or [])]})
        print(f"{segment.start:.1f}-{segment.end:.1f}s: {segment.text}", flush=True)
    transcript_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    (output / "transcript.txt").write_text("\n".join(s["text"].strip() for s in result["segments"]), encoding="utf-8")
    def srt_time(seconds):
        milliseconds = round(seconds * 1000)
        hours, milliseconds = divmod(milliseconds, 3600000)
        minutes, milliseconds = divmod(milliseconds, 60000)
        seconds, milliseconds = divmod(milliseconds, 1000)
        return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"
    subtitles = [f"{i}\n{srt_time(s['start'])} --> {srt_time(s['end'])}\n{s['text'].strip()}\n"
                 for i, s in enumerate(result["segments"], 1)]
    (output / "subtitles.srt").write_text("\n".join(subtitles), encoding="utf-8")
    return result


def build_events(video: Path, transcript: dict | None):
    import pandas as pd
    from tribev2.demo_utils import get_audio_and_text_events
    base = {"timeline": "default", "subject": "default"}
    rows = [dict(base, type="Video", filepath=str(video), start=0)]
    if transcript is None:
        return get_audio_and_text_events(pd.DataFrame(rows))
    else:
        languages = {"en": "english", "fr": "french", "es": "spanish", "nl": "dutch", "zh": "chinese"}
        if transcript["language"] not in languages:
            raise ValueError("This runner's TRIBE text pipeline supports English, French, Spanish, Dutch, and Chinese; detected " + transcript["language"])
        for i, segment in enumerate(transcript["segments"]):
            for word in segment["words"]:
                rows.append(dict(base, type="Word", start=word["start"],
                    duration=word["end"] - word["start"], text=word["word"].strip(),
                    language=languages[transcript["language"]], sequence_id=i, sentence=segment["text"]))
        return get_audio_and_text_events(pd.DataFrame(rows), audio_only=len(rows) == 1)


def predict_brain(video: Path, output: Path, device: str, checkpoint: str, transcript: dict | None, low_memory: bool):
    import numpy as np
    import pandas as pd
    from tribev2 import TribeModel

    events = build_events(video, transcript)
    events.to_csv(output / "events.csv", index=False)
    words = events[events.type == "Word"].sort_values("start")
    if "text" in words and transcript is None:
        (output / "transcript.txt").write_text(" ".join(words.text.dropna().astype(str)), encoding="utf-8")
    overrides = {"data.batch_size": 1, "data.num_workers": 0,
                 "data.text_feature.batch_size": 1,
                 "data.video_feature.image.batch_size": 1}
    if low_memory:
        # The extractor's supported accelerate mode uses float16 + CPU offload.
        overrides["data.text_feature.device"] = "accelerate"
    model = TribeModel.from_pretrained(
        checkpoint, cache_folder=str(ROOT / "cache"), device=device,
        config_update=overrides,
    )
    predictions, segments = model.predict(events)
    np.save(output / "brain_predictions.npy", predictions)
    timeline = pd.DataFrame({
        "segment_start_seconds": [s.start for s in segments],
        "segment_duration_seconds": [s.duration for s in segments],
        "mean_prediction": predictions.mean(axis=1),
        "std_across_vertices": predictions.std(axis=1),
        "rms_prediction": np.sqrt((predictions ** 2).mean(axis=1)),
    })
    timeline.to_csv(output / "brain_timeline.csv", index=False)
    (output / "brain_info.json").write_text(json.dumps({
        "checkpoint": checkpoint, "shape": list(predictions.shape), "TR_seconds": model.data.TR,
        "mesh": "fsaverage5", "subject": "model average subject",
        "timing_note": "Upstream describes predictions as shifted 5 seconds into the past to compensate for hemodynamic lag. CSV stores model segment times without another shift.",
        "interpretation": "Predicted fMRI-like responses, not measured activity, emotion, attention, or virality scores.",
    }, indent=2), encoding="utf-8")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.plot(timeline.segment_start_seconds, timeline.rms_prediction)
    ax.set(xlabel="Model segment time (s)", ylabel="RMS across cortical vertices", title="TRIBE predicted response magnitude (not an engagement score)")
    fig.tight_layout()
    fig.savefig(output / "brain_timeline.png", dpi=150)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(12, 5))
    limit = float(np.percentile(np.abs(predictions), 99)) or 1
    im = ax.imshow(predictions.T, aspect="auto", origin="lower", cmap="RdBu_r", vmin=-limit, vmax=limit)
    ax.set(xlabel="Prediction row (times in brain_timeline.csv)", ylabel="Cortical vertex", title="TRIBE predicted cortical responses")
    fig.colorbar(im, ax=ax, label="Model output")
    fig.tight_layout()
    fig.savefig(output / "brain_heatmap.png", dpi=150)
    plt.close(fig)
    print(f"Saved predictions and brain plots to {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "my_video")
    parser.add_argument("--inspect-only", action="store_true", help="Inspect video without downloading AI model weights")
    parser.add_argument("--transcribe-only", action="store_true", help="Inspect and transcribe without TRIBE weights")
    parser.add_argument("--speech-model", default="small", help="Faster Whisper model size; default: small")
    parser.add_argument("--whisperx", action="store_true", help="Use the original large-v3 WhisperX pipeline for TRIBE")
    parser.add_argument("--low-memory", action="store_true", help="Use supported float16/CPU offload for the text encoder; may still exceed GPU memory")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--checkpoint", default="facebook/tribev2")
    args = parser.parse_args()
    video = args.video.expanduser().resolve()
    if not video.is_file():
        parser.error(f"Video does not exist: {video}")
    configure_environment()
    output = args.output.resolve()
    inspect_video(video, output)
    if not args.inspect_only:
        transcript = None if args.whisperx and not args.transcribe_only else transcribe_video(video, output, args.speech_model)
        if not args.transcribe_only:
            predict_brain(video, output, args.device, args.checkpoint, transcript, args.low_memory)


if __name__ == "__main__":
    main()
