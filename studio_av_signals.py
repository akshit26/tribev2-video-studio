"""Small, language-independent audio and sampled-frame observations.

These are production clues, not emotion recognition or an aesthetic score.
"""
from __future__ import annotations

import math
from pathlib import Path


def extract_audio(video, destination):
    """Decode one mono PCM16 track; bounded FFmpeg, no model or GPU allocation."""
    import subprocess
    import imageio_ffmpeg
    destination = Path(destination)
    result = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-nostdin', '-y', '-v', 'error',
        '-i', str(video), '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(destination)],
        capture_output=True, timeout=180, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise ValueError('No decodable audio track. Audio pacing is unavailable.')
    return destination


def pacing_from_words(words, duration):
    """Speech-free intervals, not acoustic silence: background music may remain."""
    if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
        raise ValueError('Audio duration must be positive.')
    cleaned = []
    for word in words:
        start, end = word.get('start'), word.get('end')
        if (type(start) not in (int, float) or type(end) not in (int, float)
                or not math.isfinite(start) or not math.isfinite(end) or not 0 <= start <= end <= duration + .1):
            raise ValueError('Invalid Whisper word timestamp.')
        if str(word.get('word', '')).strip():
            cleaned.append(dict(start=start, end=min(end, duration), word=str(word['word']).strip()))
    cleaned.sort(key=lambda w: (w['start'], w['end']))
    gaps, cursor = [], 0.
    for word in cleaned:
        if word['start'] - cursor > 1.:
            gaps.append({'start': round(cursor, 3), 'end': round(word['start'], 3)})
        cursor = max(cursor, word['end'])
    if duration - cursor > 1.:
        gaps.append({'start': round(cursor, 3), 'end': round(duration, 3)})
    return {'available': True, 'duration_seconds': round(duration, 3), 'word_count': len(cleaned),
            'wpm': round(len(cleaned) * 60 / duration, 1), 'dead_air': gaps,
            'words': cleaned, 'text': ' '.join(w['word'] for w in cleaned),
            'note': 'WPM uses full clip duration. Gaps are ASR speech-free intervals; music/noise may remain.'}


def transcribe_pacing(video, output, language='auto'):
    """Use Groq if explicitly configured; otherwise an already-cached local Whisper."""
    import json
    import subprocess
    import sys
    import wave
    from studio_script_nvidia import nvidia_token
    output = Path(output)
    wav = extract_audio(video, output / 'audit_audio.wav')
    with wave.open(str(wav), 'rb') as stream:
        duration = stream.getnframes() / stream.getframerate()
    if duration > 900:
        raise ValueError('Audio analysis supports clips up to 15 minutes.')
    if language not in {'auto','en','hi'}:
        language = {'English':'en','Hindi':'hi','Hinglish':'hi','Hindi (Roman)':'hi'}.get(language,'auto')
    token = nvidia_token('GROQ_API_KEY')
    if token:
        from openai import OpenAI
        with OpenAI(base_url='https://api.groq.com/openai/v1', api_key=token, timeout=180, max_retries=0) as client, wav.open('rb') as audio:
            response = client.audio.transcriptions.create(model='whisper-large-v3', file=audio,
                response_format='verbose_json', timestamp_granularities=['word'],
                **({'language': language} if language != 'auto' else {}))
        words = response.model_dump().get('words')
        if not isinstance(words, list):
            raise ValueError('Whisper returned no word timestamps; pacing cannot be calculated.')
        model = 'groq/whisper-large-v3'
    else:
        root = Path(__file__).resolve().parent
        candidates = [root / 'cache' / ('faster-whisper-' + name) for name in ('small', 'tiny', 'medium')]
        local = next((p for p in candidates if (p / 'model.bin').is_file()), None)
        if local is None:
            raise ValueError('Configure GROQ_API_KEY or install a local Whisper model for audio pacing.')
        # A separate process gives local ASR a real cancellation/deadline boundary.
        target = output / 'audit_words.json'
        subprocess.run([sys.executable, str(Path(__file__).resolve()), '--audit-asr', str(wav),
                        str(local), str(target), language], check=True, capture_output=True,
                       timeout=180, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        words = json.loads(target.read_text(encoding='utf-8'))
        model = 'local/' + local.name
    result = pacing_from_words(words, duration)
    result.update(model=model, language=language)
    return result


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


if __name__ == '__main__':
    import sys, json
    if len(sys.argv) != 6 or sys.argv[1] != '--audit-asr':
        raise SystemExit('This worker is invoked by the audio pacing pipeline.')
    from faster_whisper import WhisperModel
    model = WhisperModel(sys.argv[3], device='cpu', compute_type='int8', cpu_threads=4, local_files_only=True)
    segments, info = model.transcribe(sys.argv[2], word_timestamps=True, beam_size=1,
        language=None if sys.argv[5]=='auto' else sys.argv[5], vad_filter=True)
    words = [dict(start=w.start, end=w.end, word=w.word) for segment in segments for w in (segment.words or [])]
    Path(sys.argv[4]).write_text(json.dumps(words, ensure_ascii=False), encoding='utf-8')
