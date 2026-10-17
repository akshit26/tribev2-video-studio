"""Small, language-independent audio and sampled-frame observations.

These are production clues, not emotion recognition or an aesthetic score.
"""
from __future__ import annotations

import math
from pathlib import Path


def voice_observations(samples, sample_rate=16000, seconds_per_span=10):
    import numpy as np

    audio = np.asarray(samples, dtype=np.float32)
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    if not len(audio):
        return {"available": False, "sources": [], "note": "No decoded audio samples."}
    frame_size = max(256, round(sample_rate * .08))
    frame_count = len(audio) // frame_size
    if not frame_count:
        return {"available": False, "sources": [], "note": "Audio is too short for delivery measurements."}
    frames = audio[:frame_count * frame_size].reshape(frame_count, frame_size)
    rms = np.sqrt(np.mean(frames * frames, axis=1) + 1e-12)
    db = 20 * np.log10(np.maximum(rms, 1e-8))
    active_floor = max(-46., float(np.percentile(db, 80)) - 20.)
    active = db >= active_floor
    pitch = np.full(frame_count, np.nan)
    low_lag, high_lag = max(1, round(sample_rate / 350)), min(frame_size - 1, round(sample_rate / 75))
    for index in np.flatnonzero(active):
        frame = frames[index] - frames[index].mean()
        if float(np.sqrt(np.mean(frame * frame))) < .006:
            continue
        spectrum = np.fft.rfft(frame * np.hanning(frame_size), n=frame_size * 2)
        correlation = np.fft.irfft(spectrum * spectrum.conj())[:frame_size]
        if correlation[0] <= 1e-8:
            continue
        lag = low_lag + int(np.argmax(correlation[low_lag:high_lag + 1]))
        if correlation[lag] / correlation[0] >= .45:
            pitch[index] = sample_rate / lag
    duration = len(audio) / sample_rate
    sources = []
    for start in range(0, math.ceil(duration), seconds_per_span):
        end = min(duration, start + seconds_per_span)
        lo, hi = int(start / .08), min(frame_count, int(math.ceil(end / .08)))
        levels = db[lo:hi]
        voiced = pitch[lo:hi]
        voiced = voiced[np.isfinite(voiced)]
        active_levels = levels[levels >= active_floor]
        if not len(levels):
            continue
        dynamic = float(np.percentile(active_levels, 90) - np.percentile(active_levels, 10)) if len(active_levels) >= 4 else None
        pitch_span = float(12 * np.log2(np.percentile(voiced, 90) / np.percentile(voiced, 10))) if len(voiced) >= 8 else None
        # Very wide ranges from a short ad usually mix voice, music, and octave
        # tracking errors. Do not present those as expressive vocal delivery.
        if pitch_span is not None and pitch_span > 14:
            pitch_span = None
        quiet = float(np.mean(levels < active_floor))
        values = {"start": round(float(start), 2), "end": round(float(end), 2),
                  "quiet_fraction": round(quiet, 2),
                  "level_span_db": round(dynamic, 1) if dynamic is not None else None,
                  "pitch_span_semitones": round(pitch_span, 1) if pitch_span is not None else None,
                  "median_level_dbfs": round(float(np.median(active_levels)), 1) if len(active_levels) else None}
        pieces = [f"Audio {start:.0f}-{end:.0f}s: {round((1-quiet)*100)}% above the local quiet threshold"]
        if dynamic is not None:
            pieces.append(f"active-level span {dynamic:.1f} dB")
        if pitch_span is not None:
            pieces.append(f"estimated pitch span {pitch_span:.1f} semitones")
        pieces.append("music/noise may affect these measures")
        sources.append(dict(values, id=f"A{len(sources)+1}", kind="audio", text="; ".join(pieces)))
    return {"available": True, "sources": sources,
            "note": "Measured loudness/pitch variation and quiet intervals are delivery proxies, not recognized emotion. Music, noise, and multiple speakers can distort them."}


def voice_from_video(video: Path):
    samples = decode_pcm(video)
    if not len(samples):
        return {"available": False, "sources": [], "note": "No decodable audio stream."}
    return voice_observations(samples)


def decode_pcm(video: Path, sample_rate=16000):
    """Decode the actual waveform; a long MoviePy to_soundarray call can repeat one sample."""
    import subprocess
    import numpy as np
    import imageio_ffmpeg

    command = [imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-v", "error", "-i", str(video),
               "-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "pipe:1"]
    result = subprocess.run(command, capture_output=True, check=True, timeout=180)
    return np.frombuffer(result.stdout, dtype="<f4")


def visual_observations(output: Path, scenes: list[dict], duration: float, limit=8):
    import cv2
    import numpy as np

    if not scenes:
        return {"available": False, "sources": [], "note": "No sampled frames."}
    chosen = [scenes[round(i * (len(scenes) - 1) / (min(limit, len(scenes)) - 1))]
              for i in range(min(limit, len(scenes)))] if len(scenes) > 1 else scenes
    sources = []
    for scene in chosen:
        path = output / scene["frame_file"]
        frame = cv2.imread(str(path))
        if frame is None:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean())
        contrast = float(gray.std())
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        caption = str(scene.get("caption", "")).strip()
        if caption in {"Selected source frame", "Sampled video frame"}:
            caption = "No frame description"
        text = (f"Frame at {scene['time_seconds']:.1f}s; automatic description (may be wrong): {caption}; "
                f"measured brightness {brightness:.0f}/255, contrast {contrast:.0f}, sharpness {sharpness:.0f}")
        sources.append({"id": f"V{len(sources)+1}", "kind": "visual", "start": float(scene["time_seconds"]),
                        "end": min(float(duration), float(scene["time_seconds"]) + 1),
                        "frame_file": scene["frame_file"], "text": text,
                        "brightness": round(brightness, 1), "contrast": round(contrast, 1),
                        "sharpness": round(sharpness, 1)})
    return {"available": bool(sources), "sources": sources,
            "note": "Frame descriptions are fallible; brightness, contrast and sharpness are measured only on sampled images. They do not prove aesthetic quality or reveal every shot."}
