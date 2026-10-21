"""Compact local video analysis with sequential GPU workers and memory monitoring."""
from __future__ import annotations

import argparse
import csv
from functools import lru_cache
import gc
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Callable

from studio_resources import (CPU_THREADS, RESERVE_MB, GPU_BUDGET_MB, GPU_GUARD_MB, maximum_gpu_budget,
                              GPU_PAUSE_C, GPU_STOP_C, ResourcePressureError,
                              limit_cpu_threads, memory_info, require_memory)

limit_cpu_threads()

ROOT = Path(__file__).resolve().parent
MAX_DURATION = 600
_DLL_HANDLES = []


def _write_json(path: Path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    # Windows readers/virus scanners can briefly hold the destination open.
    for attempt in range(20):
        try:
            temporary.replace(path)
            break
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(.05)


def gpu_info() -> dict:
    """Observe total GPU use; WDDM does not reliably report per-process usage."""
    from studio_gpu_monitor import read_gpu
    direct = read_gpu()
    if direct is not None:
        return direct
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,temperature.gpu", "--format=csv,noheader,nounits", "--id=0"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode == 0:
            name, total, used, temperature = [value.strip() for value in result.stdout.strip().splitlines()[0].split(",")]
            return {"available": True, "name": name, "total_mb": int(total), "used_mb": int(used),
                    "temperature_c": int(temperature)}
    except (OSError, ValueError, subprocess.TimeoutExpired, IndexError):
        pass
    return {"available": False, "name": "No NVIDIA GPU detected", "total_mb": 0, "used_mb": 0}


@lru_cache(maxsize=1)
def _cuda_ready() -> bool:
    try:
        # Do not load PyTorch/CUDA into the long-lived web server just to
        # display status. Workers verify CUDA availability before model use.
        return "+cu" in importlib.metadata.version("torch")
    except importlib.metadata.PackageNotFoundError:
        return False


def get_system_info() -> dict:
    gpu = gpu_info()
    max_budget = maximum_gpu_budget(gpu["total_mb"]) if gpu["available"] else 0
    return {
        "gpu": gpu, "cuda_ready": _cuda_ready(), "default_budget_mb": max_budget,
        "max_budget_mb": max_budget, "max_duration_seconds": MAX_DURATION,
        "profiles": [{"id": "compact", "name": "Multilingual creative review", "models": ["Faster Whisper large-v3-turbo", "Qwen3 4B Q4", "BLIP base"], "brain_inference": False}],
        "ram": memory_info(), "review_device": "cuda", "gpu_only": False,
        "stage_devices": {"speech":"cuda", "ocr":"cpu", "captions":"cuda", "review":"cuda"},
        "memory_note": f"Automatic maximum GPU target: {max_budget/1024:g} GiB, with 512 MiB reserved for the desktop and a further 256 MiB worker margin. Models run sequentially. Temperature-aware pacing and the 82 C stop remain active. Allocating more memory alone does not make hosted models faster.",
    }


def _prepare_cuda(budget_mb: int):
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available in the installed PyTorch build.")
    total_mb = torch.cuda.get_device_properties(0).total_memory / 1024**2
    # Leave space for driver context, non-PyTorch libraries, and the desktop.
    allowance = max(256, budget_mb - 1024)
    torch.cuda.set_per_process_memory_fraction(min(0.85, allowance / total_mb), device=0)
    torch.set_num_threads(CPU_THREADS)
    lib = Path(torch.__file__).parent / "lib"
    if os.name == "nt" and lib.is_dir():
        os.environ["PATH"] = str(lib) + os.pathsep + os.environ.get("PATH", "")
        _DLL_HANDLES.append(os.add_dll_directory(str(lib)))
    # CTranslate2 has its own allocator, so the outer watchdog also observes it.
    # Keep CTranslate2's supported default allocator; it is released at worker exit.


def _transcript_files(result: dict, output: Path):
    _write_json(output / "transcript.json", result)
    (output / "transcript.txt").write_text("\n".join(s["text"].strip() for s in result["segments"]), encoding="utf-8")
    def stamp(seconds):
        value = max(0, round(float(seconds) * 1000))
        hours, value = divmod(value, 3600000)
        minutes, value = divmod(value, 60000)
        seconds, value = divmod(value, 1000)
        return f"{hours:02}:{minutes:02}:{seconds:02},{value:03}"
    text = "\n".join(f"{i}\n{stamp(s['start'])} --> {stamp(s['end'])}\n{s['text'].strip()}\n"
                     for i, s in enumerate(result["segments"], 1))
    (output / "subtitles.srt").write_text(text, encoding="utf-8")


def timed_speech_segments(start, end, text, words, max_seconds=5):
    """Keep recognized words intact while exposing useful edit-sized spans."""
    import re
    if not words:return [{'start':start,'end':end,'text':text,'words':[]}]
    rows, current = [], []
    def finish():
        rows.append({'start':current[0]['start'],'end':current[-1]['end'],
                     'text':' '.join(w['word'] for w in current),'words':list(current)})
        current.clear()
    for word in words:
        if current and word['end']-current[0]['start']>max_seconds:finish()
        current.append(word)
        if re.search(r'[.!?।॥]$',word['word']):finish()
    if current:finish()
    return rows


def _speech_worker(video: Path, output: Path, device: str, budget_mb: int):
    from analyze_video import configure_environment
    configure_environment()
    if device != "cuda":
        raise ValueError("Speech inference is GPU-only.")
    # CTranslate2 owns the speech CUDA allocator. Loading PyTorch as well only
    # creates an unused context and consumes scarce Windows RAM.
    lib = Path(importlib.metadata.distribution("torch").locate_file("torch/lib"))
    if os.name == "nt" and lib.is_dir():
        os.environ["PATH"] = str(lib) + os.pathsep + os.environ.get("PATH", "")
        _DLL_HANDLES.append(os.add_dll_directory(str(lib)))
    import ctranslate2
    if ctranslate2.get_cuda_device_count() < 1:
        raise RuntimeError("CUDA is unavailable for speech recognition.")
    from faster_whisper import WhisperModel
    from studio_review import settings
    chosen = settings(output)["language"]
    local = ROOT / "cache" / "faster-whisper-large-v3-turbo"
    source = str(local) if (local / "model.bin").exists() else "dropbox-dash/faster-whisper-large-v3-turbo"
    precision = "int8_float16" if device == "cuda" else "int8"
    model = WhisperModel(source, device=device, compute_type=precision, cpu_threads=CPU_THREADS, num_workers=1)
    # Use Whisper's own silence checks; the optional Silero VAD is a CPU model.
    regional_prompt = "Indian English and Hinglish conversation. Natural expressions may include paisa vasool and salon bhaiya. Preserve the original spoken language, names and code-switching."
    segments, info = model.transcribe(str(video), task="transcribe", word_timestamps=True, vad_filter=False, beam_size=3, chunk_length=15, temperature=0,
        language=None if chosen == "auto" else chosen, multilingual=chosen == "auto",
        initial_prompt=regional_prompt if chosen in {"auto","en","hi"} else None,
        hotwords="paisa vasool, salon bhaiya" if chosen in {"auto","en","hi"} else None,
        condition_on_previous_text=False, language_detection_segments=3)
    result = {"language": info.language, "language_probability": float(info.language_probability),
              "model": "Faster Whisper large-v3-turbo", "requested_language": chosen,
              "device": device, "precision": precision, "segments": []}
    for segment in segments:
        words=[{"start":float(w.start),"end":float(w.end),"word":w.word.strip(),"probability":float(w.probability)} for w in (segment.words or [])]
        result["segments"].extend(timed_speech_segments(float(segment.start),float(segment.end),segment.text.strip(),words))
        _write_json(output / "worker_progress.json", {"fraction": min(1, segment.end / max(info.duration, 1)), "stage": "Transcribing speech"})
        stage_pause(lambda value, label: _write_json(output / "worker_progress.json", {"fraction": value, "stage": label}),
                    min(1, segment.end / max(info.duration, 1)), "Pausing between speech segments")
    _transcript_files(result, output)
    del model
    gc.collect()


def _vision_worker(output: Path, device: str, budget_mb: int):
    from analyze_video import configure_environment
    configure_environment()
    import torch
    if device == "cuda":
        _prepare_cuda(budget_mb)
    else:
        torch.set_num_threads(CPU_THREADS)
    from transformers import BlipForConditionalGeneration, BlipProcessor
    from PIL import Image
    local = ROOT / "cache" / "blip-image-captioning-base"
    source = str(local) if (local / "pytorch_model.bin").exists() else "Salesforce/blip-image-captioning-base"
    dtype = torch.float16 if device == "cuda" else torch.float32
    processor = BlipProcessor.from_pretrained(source)
    model = BlipForConditionalGeneration.from_pretrained(source, torch_dtype=dtype, low_cpu_mem_usage=True).to(device).eval()
    manifest = json.loads((output / "scene_manifest.json").read_text(encoding="utf-8"))
    scenes = []
    with torch.inference_mode():
        for index, scene in enumerate(manifest):
            with Image.open(output / scene["frame_file"]) as image:
                inputs = processor(images=image.convert("RGB"), return_tensors="pt").to(device)
            if device == "cuda":
                inputs["pixel_values"] = inputs["pixel_values"].to(dtype=dtype)
            generated = model.generate(**inputs, max_new_tokens=36, num_beams=1, do_sample=False)
            caption = processor.decode(generated[0], skip_special_tokens=True).strip()
            scenes.append(dict(scene, caption=caption, caption_source="BLIP base automatic caption"))
            del inputs, generated
            _write_json(output / "worker_progress.json", {"fraction": (index + 1) / len(manifest), "stage": "Describing sampled frames"})
            stage_pause(lambda value, label: _write_json(output / "worker_progress.json", {"fraction": value, "stage": label}),
                        (index + 1) / len(manifest), "Pausing between sampled frames")
    _write_json(output / "scenes.json", {"device": device, "precision": str(dtype), "model": "BLIP image-captioning base", "scenes": scenes})


def _emotion_worker(output: Path, device: str, budget_mb: int):
    from analyze_video import configure_environment
    configure_environment()
    import torch
    if device == "cuda":
        _prepare_cuda(budget_mb)
    else:
        torch.set_num_threads(CPU_THREADS)
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    transcript = json.loads((output / "transcript.json").read_text(encoding="utf-8"))
    local = ROOT / "cache" / "emotion-english-distilroberta-base"
    source = str(local) if (local / "pytorch_model.bin").exists() else "j-hartmann/emotion-english-distilroberta-base"
    tokenizer = AutoTokenizer.from_pretrained(source)
    model = AutoModelForSequenceClassification.from_pretrained(
        source, torch_dtype=torch.float16 if device == "cuda" else torch.float32).to(device).eval()
    timeline, weighted, total = [], {}, 0.0
    segments = transcript["segments"]
    with torch.inference_mode():
        for i, segment in enumerate(segments):
            inputs = tokenizer(segment["text"], return_tensors="pt", truncation=True, max_length=256).to(device)
            probs = model(**inputs).logits.float().softmax(dim=-1)[0].cpu().tolist()
            values = {str(model.config.id2label[j]).lower(): value * 100 for j, value in enumerate(probs)}
            weight = max(.1, segment["end"] - segment["start"])
            for label, value in values.items():
                weighted[label] = weighted.get(label, 0) + weight * value
            total += weight
            timeline.append({"start": segment["start"], "end": segment["end"], "text": segment["text"],
                             "scores": {k: round(v, 2) for k, v in values.items()}, "dominant": max(values, key=values.get)})
            _write_json(output / "worker_progress.json", {"fraction": (i + 1) / max(1, len(segments)), "stage": "Analyzing language tone"})
    distribution = {key: round(value / total, 2) for key, value in weighted.items()} if total else {}
    _write_json(output / "emotion.json", {"available": bool(distribution), "device": device,
        "model": "j-hartmann/emotion-english-distilroberta-base", "distribution": distribution,
        "dominant": max(distribution, key=distribution.get) if distribution else None, "timeline": timeline,
        "interpretation": "Duration-weighted classifier scores for emotional language in English speech. Not actual speaker feelings or viewer emotional responses; ignores voice tone and facial expressions."})


def _terminate_worker(process):
    if os.name == "nt":
        # Kill only the tree we spawned (venv python.exe can create a child).
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def _fresh_cooling_heartbeat(output: Path) -> bool:
    progress_file = output / "worker_progress.json"
    try:
        return (time.time() - progress_file.stat().st_mtime < 2 and
                json.loads(progress_file.read_text(encoding="utf-8"))
                .get("stage", "").startswith("Pausing for GPU cooling"))
    except (OSError, ValueError, KeyError):
        return False


def _temperature_stop_required(temperature: int, cooling: bool) -> bool:
    return temperature >= GPU_STOP_C + (2 if cooling else 0)


def _run_worker(task: str, video: Path, output: Path, device: str, budget_mb: int,
                progress: Callable, start: int, end: int) -> tuple[bool, int, str]:
    if device != "cuda":
        raise ValueError("Studio model inference is GPU-only; CPU fallback is disabled.")
    require_memory()
    info = gpu_info()
    maximum = maximum_gpu_budget(info['total_mb']) if info['available'] else 0
    budget_mb = min(budget_mb or maximum, maximum)
    command = [sys.executable, str(Path(__file__).resolve()), "worker", task, "--video", str(video),
               "--output", str(output), "--device", device, "--budget-mb", str(budget_mb)]
    expected_mb = 3300 if task in {"review", "review_probe"} else 1536
    if not info["available"] or info["used_mb"] > budget_mb - GPU_GUARD_MB - expected_mb:
        return False, info["used_mb"], "Insufficient free GPU budget before starting the model."
    if info.get("temperature_c", GPU_STOP_C) >= GPU_PAUSE_C:
        return False, info["used_mb"], "GPU is too warm to start another model. Let it cool and try again."
    _write_json(output / "worker_progress.json", {"fraction": 0, "stage": "Loading " + task + " model"})
    peak, reason, begun = info["used_mb"], "", time.monotonic()
    peak_temperature = info.get("temperature_c")
    (output / f"worker_{task}_error.json").unlink(missing_ok=True)
    log_path = output / f"worker_{task}_{device}.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
            cwd=str(ROOT), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
        try:
            last_progress = None
            while process.poll() is None:
                # Raising aborts the whole job; do not retry on CPU under
                # system memory pressure. The exception handler kills our tree.
                require_memory(RESERVE_MB)
                if device == "cuda":
                    observed = gpu_info()
                    if not observed["available"]:
                        reason = "GPU memory monitoring became unavailable."
                        _terminate_worker(process)
                        break
                    peak = max(peak, observed["used_mb"])
                    if observed.get("temperature_c") is not None:
                        peak_temperature = max(peak_temperature or 0, observed["temperature_c"])
                    temperature = observed.get("temperature_c", GPU_STOP_C)
                    cooling = (task in {"review", "review_probe"} and
                               temperature >= GPU_STOP_C and _fresh_cooling_heartbeat(output))
                    # An idle reviewer may briefly peak after work stops. Do
                    # not destroy saved progress while its fresh cooling
                    # heartbeat proves no inference is in flight. Abort if it
                    # reaches 84 C even then, or at 82 C during active work.
                    if _temperature_stop_required(temperature, cooling):
                        reason = "GPU temperature guard stopped the model. Let the GPU cool before retrying."
                        _terminate_worker(process)
                        break
                    if observed["used_mb"] > budget_mb - GPU_GUARD_MB:
                        reason = "GPU memory guard stopped the model before reaching the selected target."
                        _terminate_worker(process)
                        break
                if time.monotonic() - begun > 1800:
                    reason = "The analysis stage exceeded its 30-minute time limit."
                    _terminate_worker(process)
                    break
                try:
                    state = json.loads((output / "worker_progress.json").read_text(encoding="utf-8"))
                    value = min(end, start + round((end - start) * state["fraction"]))
                    current = (value, state["stage"] + (" on GPU" if device == "cuda" else " on CPU"))
                    if current != last_progress:
                        progress(*current)
                        last_progress = current
                except (OSError, ValueError, KeyError):
                    pass
                time.sleep(0.25)
        except BaseException:
            if process.poll() is None:
                _terminate_worker(process)
            raise
        finally:
            _write_json(output / f"telemetry_{task}.json", {
                "elapsed_seconds": round(time.monotonic() - begun, 2),
                "sampled_total_gpu_peak_mb": peak, "sampled_peak_temperature_c": peak_temperature,
                "budget_mb": budget_mb, "guard_mb": budget_mb - GPU_GUARD_MB,
                "sampling_note": "Sampled total GPU use; instantaneous peaks and thermal throttling are not proven absent."})
    if process.returncode != 0 and not reason:
        try:
            failure = json.loads((output / f"worker_{task}_error.json").read_text(encoding="utf-8"))
            reason = f"{task.title()} failed: " + str(failure["error"])[:1500]
        except (OSError, ValueError, KeyError):
            reason = f"{task.title()} worker exited; details saved in its local worker log."
    return process.returncode == 0 and not reason, peak, reason


def stage_pause(progress, value, label="Releasing GPU memory before the next stage", *, pause_at=75, resume_at=72):
    """Pause only near the thermal stop; use hysteresis to avoid rapid cycling."""
    cooling = False
    for _ in range(240):
        require_memory(RESERVE_MB)
        info = gpu_info()
        if not info["available"]:
            raise RuntimeError("GPU monitoring unavailable; CPU fallback is disabled.")
        temperature = info.get("temperature_c", GPU_STOP_C)
        cooling = cooling or temperature >= pause_at
        if temperature < pause_at and (not cooling or temperature <= resume_at):
            return info
        progress(value, "Pausing for GPU cooling before the next part")
        time.sleep(.5)
    raise RuntimeError("GPU did not cool within two minutes. Let it cool, then try again.")


def _charts(measurements: list[dict], output: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    audio = "audio_rms_dbfs" in measurements[0]
    fig, axes = plt.subplots(2 if audio else 1, 1, figsize=(11, 6 if audio else 3.5), squeeze=False)
    times = [row["time_seconds"] for row in measurements]
    axes[0, 0].plot(times, [row["frame_difference_0_255"] for row in measurements], color="#087f8c")
    axes[0, 0].set(xlabel="Time (seconds)", ylabel="Frame difference (0-255)", title="Sampled visual changes (not attention)")
    if audio:
        axes[1, 0].plot(times, [row["audio_rms_dbfs"] for row in measurements], color="#6941c6", label="RMS")
        axes[1, 0].plot(times, [row["audio_peak_dbfs"] for row in measurements], color="#e07a35", alpha=.8, label="Peak")
        axes[1, 0].set(xlabel="Time (seconds)", ylabel="Digital audio level (dBFS)", title="Audio level over time")
        axes[1, 0].legend()
    fig.tight_layout()
    fig.savefig(output / "charts.png", dpi=140)
    plt.close(fig)


def _run_cpu_stage(task, video, output, progress):
    """Release decoder/plotting/ONNX host allocations at the stage boundary."""
    require_memory()
    error_path=output/f"worker_{task}_error.json"
    error_path.unlink(missing_ok=True)
    _write_json(output/'worker_progress.json',{'fraction':0,'stage':f'Starting {task}'})
    command=[sys.executable,str(Path(__file__).resolve()),'worker',task,'--video',str(video),
             '--output',str(output),'--device','cpu']
    begun=time.monotonic()
    with (output/f'worker_{task}_cpu.log').open('w',encoding='utf-8') as log:
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,cwd=str(ROOT),
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)|getattr(subprocess,'BELOW_NORMAL_PRIORITY_CLASS',0))
        try:
            previous=None
            while process.poll() is None:
                require_memory(RESERVE_MB)
                if time.monotonic()-begun>1800:raise TimeoutError(f'{task} exceeded its 30-minute limit')
                try:
                    state=json.loads((output/'worker_progress.json').read_text(encoding='utf-8'))
                    if state!=previous:progress(state['fraction'],state['stage']);previous=state
                except (OSError,ValueError,KeyError):pass
                time.sleep(.25)
        finally:
            if process.poll() is None:_terminate_worker(process)
            _write_json(output/f'telemetry_{task}.json',{'device':'cpu','elapsed_seconds':round(time.monotonic()-begun,2)})
    if process.returncode:
        failure=json.loads(error_path.read_text(encoding='utf-8')) if error_path.exists() else {}
        raise RuntimeError(f'{task.title()} failed: '+failure.get('error','See the local worker log.'))


def prepare_video(video, output, progress):
    _run_cpu_stage('inspect',video,output,progress)
    return json.loads((output/'video_info.json').read_text(encoding='utf-8'))


def ocr_analysis(video, output, progress):
    _run_cpu_stage('ocr',video,output,progress)
    return json.loads((output/'ocr.json').read_text(encoding='utf-8'))


def _inspect_worker(video, output):
    from moviepy import VideoFileClip
    from analyze_video import inspect_video
    with VideoFileClip(str(video)) as clip:
        if not clip.duration or not 0 < clip.duration <= MAX_DURATION:
            raise ValueError('Please upload a video between 0 and 600 seconds long.')
        if clip.w*clip.h>3840*2160:
            raise ValueError('Please upload video at 4K resolution or below for this compact profile.')
    inspect_video(video,output)
    with (output/'video_metrics.csv').open(encoding='utf-8',newline='') as stream:
        measurements=[{key:float(value) for key,value in row.items()} for row in csv.DictReader(stream)]
    _charts(measurements,output)


def run_analysis(video: Path, output: Path, budget_mb: int, vision: bool,
                 progress: Callable[[int, str], None] = lambda value, stage: None) -> dict:
    require_memory()
    from studio_report import build_report, render_pdf
    output = Path(output).resolve()
    video = Path(video).resolve()
    output.mkdir(parents=True, exist_ok=True)
    system = get_system_info()
    budget_mb = budget_mb or system['max_budget_mb']
    if not 1024 <= budget_mb <= system["max_budget_mb"]:
        raise ValueError("GPU target exceeds the detected maximum with desktop reserve, or is below 1024 MiB.")
    if not system["cuda_ready"] or not system["gpu"]["available"]:
        raise RuntimeError("A working NVIDIA GPU is required. CPU model fallback is disabled.")
    progress(5, "Measuring video, audio, and visual changes")
    prepared = output / "video_info.json"
    metrics_file = output / "video_metrics.csv"
    if prepared.exists() and metrics_file.exists() and (output / "charts.png").exists():
        info = json.loads(prepared.read_text(encoding="utf-8"))
        progress(14, "Restored completed video measurements")
    else:
        info = prepare_video(video, output, lambda f,s:progress(5+int(f*9),s))
    name = video.name
    try:
        name = json.loads((output / "upload_info.json").read_text(encoding="utf-8"))["original_name"]
    except (OSError, ValueError, KeyError):
        pass
    info["name"] = Path(name.replace("\\", "/")).name
    info.pop("video", None)
    _write_json(output / "video_info.json", info)
    with (output / "video_metrics.csv").open(encoding="utf-8", newline="") as stream:
        measurements = [{key: float(value) for key, value in row.items()} for row in csv.DictReader(stream)]
    # Use the same sample times as inspect_video; one resized image per forward pass.
    scenes = [{"time_seconds": i * max(0, info["duration_seconds"] - .1) / 11,
               "frame_file": f"frames/frame_{i:02d}.jpg", "caption": "Sampled video frame"} for i in range(12)]
    _write_json(output / "scene_manifest.json", scenes)
    warnings, models, devices = [], [], []
    transcript_file = output / "transcript.json"
    ocr_file = output / "ocr.json"
    transcript = json.loads(transcript_file.read_text(encoding="utf-8")) if transcript_file.exists() else None
    ocr = json.loads(ocr_file.read_text(encoding="utf-8")) if ocr_file.exists() else None
    emotion = None
    peak = system["gpu"]["used_mb"]
    device = "cuda"
    tasks = (["speech"] if info["has_audio"] else []) + (["vision"] if vision else [])
    for task in tasks:
        if task == "speech" and transcript is not None:
            progress(40, "Restored completed transcription")
            models.append(f"{transcript.get('model', 'Faster Whisper medium')} / CUDA / {transcript['precision']}")
            devices.append("cuda")
            continue
        if task == "vision" and (output / "scenes.json").exists():
            captions = json.loads((output / "scenes.json").read_text(encoding="utf-8"))
            scenes = captions["scenes"]
            progress(57, "Restored completed frame descriptions")
            models.append(f"BLIP base / CUDA / {captions['precision']}")
            devices.append("cuda")
            continue
        if task == "vision" and ocr is None:
            progress(41,"Reading original on-screen text locally")
            ocr=ocr_analysis(video,output,lambda f,s:progress(41+int(f*6),s))
        # OCR says what text appeared, not whether the footage is engaging or
        # visually clear. Always describe the evenly spaced source frames too.
        if task == "emotion" and (not transcript or not transcript.get("segments") or transcript.get("language") != "en"):
            warnings.append("English-language emotion classification needs a recognized English transcript; this stage was skipped.")
            continue
        start, end = {"speech": (15, 40), "emotion": (41, 45), "vision": (47, 57)}[task]
        progress(start, f"Starting {task} analysis on {device.upper()}")
        stage_pause(progress, start)
        ok, observed_peak, reason = _run_worker(task, video, output, device, budget_mb, progress, start, end)
        peak = max(peak, observed_peak)
        used_device = device
        if not ok:
            raise RuntimeError(reason + " Analysis stopped; no CPU fallback was started.")
        devices.append(used_device)
        if task == "speech":
            transcript = json.loads((output / "transcript.json").read_text(encoding="utf-8"))
            models.append(f"{transcript.get('model', 'Faster Whisper medium')} / {used_device.upper()} / {transcript['precision']}")
        elif task == "emotion":
            emotion = json.loads((output / "emotion.json").read_text(encoding="utf-8"))
            models.append(f"Emotion English DistilRoBERTa / {used_device.upper()}")
        else:
            captions = json.loads((output / "scenes.json").read_text(encoding="utf-8"))
            scenes = captions["scenes"]
            models.append(f"BLIP base / {used_device.upper()} / {captions['precision']}")
    if not info["has_audio"]:
        warnings.append("No audio stream was detected, so speech and audio measurements are omitted.")
    if ocr is None:
        ocr=ocr_analysis(video,output,lambda f,s:progress(52+int(f*6),s))
    if not vision:
        warnings.append("Frame descriptions were disabled. Sampled images are still included.")
    if not (output / "transcript.json").exists():
        _transcript_files(transcript or {"language": None, "segments": []}, output)
    processing = {
        "device": "cuda" if devices and all(d == "cuda" for d in devices) else "mixed" if "cuda" in devices else "cpu",
        "gpu_name": system["gpu"]["name"], "budget_mb": budget_mb, "peak_gpu_mb": peak,
        "peak_gpu_scope": "total", "models": models, "warnings": warnings, "brain_inference": False,
        "memory_policy": "Speech/captions/review on GPU, CPU OCR between stages; one model worker at a time; review reuses GPU prompt context and adjusts work size to temperature. Automatic maximum total GPU target with 512 MiB desktop reserve and 256 MiB margin; pause at 75 C until 72 C; stop active inference at 82 C. A fresh idle cooling heartbeat may continue briefly up to 83 C. 1.5 GB free RAM to start, 768 MB runtime reserve. Sampled guards, not hard system-wide caps.",
    }
    progress(58, "Preparing transcript evidence for detailed review")
    report = build_report(info, measurements, transcript, scenes, processing)
    report["ocr"] = ocr
    from studio_av_signals import voice_from_video, visual_observations
    voice_file = output / "voice_signals.json"
    if voice_file.exists():
        voice = json.loads(voice_file.read_text(encoding="utf-8"))
    elif not info["has_audio"]:
        voice = {"available": False, "sources": [], "note": "No audio stream."}
    else:
        voice = voice_from_video(video)
        _write_json(voice_file, voice)
    visual = visual_observations(output, scenes, info["duration_seconds"])
    _write_json(output / "visual_signals.json", visual)
    report["voice"] = voice
    report["visual"] = visual
    from studio_review import settings
    report["review_context"] = settings(output)
    if (output / "brand_context.json").exists():
        report["brand_context"] = json.loads((output / "brand_context.json").read_text(encoding="utf-8"))
    _write_json(output / "review_input.json", report)
    if (transcript and transcript.get("segments")) or ocr.get("sources"):
        progress(60, "Starting semantic creative review")
        stage_pause(progress, 60)
        review_device = "cuda"
        ok, review_peak, reason = _run_worker("review", video, output, review_device, budget_mb, progress, 60, 89)
        peak = max(peak, review_peak)
        if ok:
            report["review"] = json.loads((output / "review.json").read_text(encoding="utf-8"))
            report["processing"]["models"].append(f"Qwen3-4B-Instruct-2507 Q4_K_M / {review_device.upper()}")
            devices.append(review_device)
        else:
            raise RuntimeError(reason + " Review stopped; no CPU fallback was started.")
    report["processing"]["peak_gpu_mb"] = peak
    report["processing"]["device"] = "mixed" if len(set(devices)) > 1 else (devices[0] if devices else "none")
    return export_report(report, video, output, progress)


def resume_analysis(video, output, budget_mb, vision, progress):
    """Reuse the saved transcript/frame evidence for a failed review/export."""
    require_memory()
    source = output / "review_input.json"
    if not source.exists():
        return run_analysis(video, output, budget_mb, vision, progress)
    report = json.loads(source.read_text(encoding="utf-8"))
    stage_pause(progress, 60, "Resuming saved review sections")
    ok, peak, reason = _run_worker("review", video, output, "cuda", budget_mb, progress, 60, 89)
    if not ok:
        raise RuntimeError(reason + " Review stopped; completed sections are saved.")
    report["review"] = json.loads((output / "review.json").read_text(encoding="utf-8"))
    report["processing"]["peak_gpu_mb"] = max(peak, report["processing"].get("peak_gpu_mb", 0))
    report["processing"]["models"].append("Qwen3-4B-Instruct-2507 Q4_K_M / CUDA")
    report["processing"]["device"] = "cuda"
    report["processing"]["budget_mb"] = budget_mb or get_system_info()['max_budget_mb']
    return export_report(report, video, output, progress)


def export_report(report, video, output, progress):
    from studio_report import render_pdf
    from studio_brief import build_brief, create_clips
    from studio_screenshots import create_screenshots
    report["brief"] = build_brief(report)
    from studio_evaluation import build_evaluation
    report["evaluation"] = build_evaluation(report)
    _write_json(output/'evaluation.json',report['evaluation'])
    progress(92, "Preparing playable review clips")
    create_clips(video, output, report["brief"])
    progress(94, "Capturing screenshots for the PDF")
    create_screenshots(video, output, report)
    report["title"] = "Detailed multilingual creative review"
    report["limitations"] = [text for text in report.get("limitations", []) if not text.startswith("No measured or predicted brain")]
    report["limitations"].insert(0, "AI creative scores are unvalidated editorial assessments, not virality probabilities. A target score is an editing goal; upload the edited video to assess it. Regional-language transcription and suggested wording require a fluent reviewer.")
    _write_json(output / "report.json", report)
    progress(95, "Creating the downloadable PDF")
    render_pdf(report, output)
    progress(100, "Report ready")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["worker", "analyze"])
    parser.add_argument("task", nargs="?", choices=["inspect", "ocr", "speech", "vision", "emotion", "review", "review_probe"])
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument("--budget-mb", type=int, default=0, help="0 selects the detected maximum with desktop reserve")
    parser.add_argument("--no-vision", action="store_true")
    args = parser.parse_args()
    if args.mode == "worker":
        try:
            if args.task == "inspect":
                _inspect_worker(args.video,args.output)
            elif args.task == "ocr":
                from studio_ocr import run_ocr
                run_ocr(args.video,args.output,lambda f,s:_write_json(args.output/'worker_progress.json',{'fraction':f,'stage':s}))
            elif args.task == "speech":
                _speech_worker(args.video, args.output, args.device, args.budget_mb)
            elif args.task == "vision":
                _vision_worker(args.output, args.device, args.budget_mb)
            elif args.task == "emotion":
                _emotion_worker(args.output, args.device, args.budget_mb)
            elif args.task in {"review", "review_probe"}:
                from studio_review import semantic_worker
                semantic_worker(args.output, args.device, args.budget_mb, probe=args.task == "review_probe")
            else:
                parser.error("A worker task is required")
        except Exception as exc:
            _write_json(args.output / f"worker_{args.task}_error.json", {"error": str(exc), "type": type(exc).__name__})
            raise
    else:
        run_analysis(args.video, args.output, args.budget_mb, not args.no_vision,
                     lambda value, stage: print(f"{value}% {stage}", flush=True))


if __name__ == "__main__":
    main()


def score_draft_script(script_text, brief, duration):
    """Pre-publication API gate; no local model or GPU stage."""
    from studio_evaluation import score_draft_script as score
    return score(script_text, brief, duration)


def generate_viral_script_pipeline(request,complete,save,progress,save_draft=None):
    """Linear actor -> mechanical critic -> editor. Never regenerate or re-grade.

    Deterministic checks prevent unsafe final/alternate text from being exported;
    they do not create a quality score or cause another model call.
    """
    from studio_script_writer import (validate_product_identity,compact_brief,system_prompt,
        validate_final_script,final_script_issues,reference_cards,final_script_guidance,creator_closing_issues)
    from studio_persona_lookup import retrieve_personas
    from studio_evaluation import critique_algorithmic_draft,sterile_cleanup_sequence
    from studio_editor import edit_script_and_hooks,compose_script
    brief=request['brief']
    validate_product_identity(brief)
    context=compact_brief(brief)
    # Retrieve only matching creator voices rather than inserting the whole desk.
    available=reference_cards(brief)
    priority={'creator-emotion','creator-share','creator-brand-bridge','creator-payoff'}
    cards=([c for c in available if c['id'] in priority]+[c for c in available if c['id'] not in priority])[:6]
    context.update(persona_references=retrieve_personas(brief),creator_direction=final_script_guidance(brief),creator_references=cards)
    for key in ('selected_hook','revision_notes','previous_script'):
        if request.get(key):context[key]=request[key]
    master=system_prompt(brief)
    prompt=('Write one algorithmic draft.' if getattr(complete,'system_prompt',None)==master else master)
    prompt+='\nBRIEF: '+json.dumps(context,ensure_ascii=False)
    candidate=None;critique=None;body='';hooks=[];issues=[];stages=[];stage_error=None
    try:
        progress(.08,'Actor: drafting one script')
        began=time.monotonic()
        draft_tokens=12000 if brief['content_duration']=='long' else 2500
        raw=complete(prompt,draft_tokens,'Draft 1')
        try:candidate=validate_final_script(raw)
        except ValueError:
            reject=getattr(complete,'reject',None)
            if callable(reject):reject(prompt,draft_tokens,'Draft 1')
            raise
        stages.append(dict(stage='actor',elapsed_seconds=round(time.monotonic()-began,3)))
        if save_draft:save_draft(candidate)
        progress(.36,'Critic: checking four algorithmic pillars')
        began=time.monotonic()
        critique=critique_algorithmic_draft(candidate['final_script'],brief,complete)
        stages.append(dict(stage='critic',elapsed_seconds=round(time.monotonic()-began,3)))
        progress(.62,'Editor: applying critique and creating three A/B hooks')
        began=time.monotonic()
        body,hooks=edit_script_and_hooks(candidate['final_script'],critique,brief,complete,request.get('revision_notes',''))
        stages.append(dict(stage='editor',elapsed_seconds=round(time.monotonic()-began,3)))
        for hook in hooks:
            variant=compose_script(hook['text'],body)
            flags=final_script_issues({'final_script':variant},brief)
            flags.extend(creator_closing_issues(variant,brief))
            if sterile_cleanup_sequence(variant):flags.append('Weave cleanup into conversational speech instead of bare commands.')
            hook['issues']=list(dict.fromkeys(flags))
            hook['validated']=not flags
            issues.extend(hook['label']+': '+flag for flag in flags)
        if issues:
            reject_last=getattr(complete,'reject_last',None)
            if callable(reject_last):reject_last('Editor and A/B hooks')
        candidate={'final_script':compose_script(hooks[0]['text'],body)}
        if save_draft:save_draft(candidate)
    except (ValueError,RuntimeError) as exc:
        stage_error=exc
        issues.append('Actor-critic stage unavailable: '+str(exc)[:500])
    if candidate is None:
        raise ValueError('Actor produced no usable script. No completed draft is available. '+str(stage_error)[:500]) from stage_error
    approved=not issues and len(hooks)==3
    assessment={'score':None,'critique':'One draft, one mechanical critique and one editor pass completed.' if approved else '; '.join(issues),
        'criteria':[],'blockers':list(dict.fromkeys(issues)),'unsupported_claims':[],
        'method':'Single-pass actor-critic editing plus deterministic safety checks; no predicted virality or final model grade.'}
    model=getattr(complete,'model','selected writer')
    if not isinstance(model,str):model='selected writer'
    result={'pipeline_version':'actor-critic-v1','pipeline':{'kind':'actor_critic','draft_model':model,'analysis_model':model,
                'editor_model':model,'stages':stages,'model_calls_completed':len(stages)},
        'final_script':candidate['final_script'],'script_body':body,'ab_hooks':hooks,'selected_hook_kind':'problem',
        'mechanical_critique':critique,'best':{'script':candidate,'assessment':assessment},'brief':brief,
        'evaluation':None,'approved':approved,'target_met':approved,'quality_status':'ready' if approved else 'needs_review',
        'stop_reason':'single_pass_complete' if approved else 'deterministic_checks_failed','history':[],'gate_history':[],
        'reference_ids':[c['id'] for c in cards],
        'revision_notes':request.get('revision_notes',''),'parent_script_id':request.get('parent_script_id')}
    save(result)
    progress(1,'Script and three hooks ready' if approved else 'Draft retained; review the flagged issues')
    return result


def extract_audit_frame(video, timestamp, destination):
    import imageio_ffmpeg
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-nostdin', '-y', '-v', 'error',
        '-i', str(video), '-ss', str(timestamp), '-frames:v', '1',
        '-vf', 'scale=640:640:force_original_aspect_ratio=decrease', str(destination)],
        capture_output=True, check=True, timeout=30,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if not destination.is_file():
        raise ValueError('No video frame exists at the cited timestamp.')
    return destination


def _run_observation_cognitive_audit(video, output, visual_frames, progress, brief=None):
    """One audio/simulation pass; below 70, exactly one independently checked rewrite."""
    import imageio_ffmpeg
    from studio_av_signals import transcribe_pacing, corrected_transcript_pacing
    from studio_virality import simulate_cognitive_response
    from studio_script_writer import system_prompt, FORMATS, validate_final_script, claim_issues
    from studio_script_team import chat_json, MODEL, nvidia_token
    from studio_decision_pdf import generate_audit_pdf
    output = Path(output)
    reader = imageio_ffmpeg.read_frames(str(video))
    try:
        info = next(reader)
    finally:
        reader.close()
    duration = info.get('duration', 0)
    if not 0 < duration <= 900:
        raise ValueError('Cognitive review supports videos up to 15 minutes.')
    # Reject unsupported visual times before giving evidence to the simulator.
    discarded_frames=sum(not 0 <= f['timestamp'] < duration for f in visual_frames)
    visual_frames=[f for f in visual_frames if 0 <= f['timestamp'] < duration]
    if not visual_frames:
        raise ValueError('Visual evidence is missing or outside the uploaded video.')
    progress(45, 'Extracting audio and Whisper word timestamps')
    try:
        try:
            saved_input=json.loads((output / 'review_input.json').read_text(encoding='utf-8'))
            corrected=saved_input.get('transcript',{})
        except (OSError,ValueError,AttributeError):
            corrected={}
        if corrected.get('manually_corrected') is True:
            pacing=corrected_transcript_pacing(corrected,duration)
        else:
            pacing = transcribe_pacing(video, output, (brief or {}).get('language', 'auto'))
    except Exception as exc:
        pacing = {'available': False, 'wpm': None, 'duration_seconds': duration,
                  'words': [], 'text': '', 'dead_air': [], 'note': 'Audio transcription unavailable: ' + type(exc).__name__}
    _write_json(output / 'transcript.json', pacing)
    (output / 'transcript.txt').write_text(pacing['text'], encoding='utf-8')
    progress(65, 'Cloud simulator is combining visual evidence, transcript and pacing')
    cognitive = simulate_cognitive_response(visual_frames, pacing['text'], pacing, brief)
    result = {'cognitive': cognitive, 'pacing': pacing, 'audit': {'triggered': False},
              'evidence_warnings': ([f'{discarded_frames} out-of-range visual timestamps were excluded.'] if discarded_frames else [])}
    _write_json(output / 'cognitive_audit.json', result)
    if cognitive['attention_retention_score'] >= 70:
        return result
    progress(80, 'Attention estimate below 70: one script rewrite and PDF audit')
    kind = 'short' if duration <= 40 else 'mid' if duration <= 90 else 'long'
    context = dict(brief or {}, content_duration=kind)
    # Observed transcript is not evidence that the product claims within it are true.
    context.setdefault('topic', 'Rewrite of the uploaded creator video')
    context.setdefault('facts', 'No independently verified product facts supplied. Do not add efficacy claims.')
    audit = {'triggered': True, 'rewrite_attempts': 1, 'rewrite_approved': False, 'final_script': ''}
    result['audit'] = audit
    _write_json(output / 'cognitive_audit.json', result)
    try:
        prompt = json.dumps({'brief': context, 'original_transcript': pacing['text'],
                             'psychological_critique': cognitive['psychological_critique']}, ensure_ascii=False)
        raw, _ = chat_json(nvidia_token(), MODEL, system_prompt(context) +
                           ' Rewrite once from the critique. Transcript claims are unverified; rely only on brief facts.', prompt,
                           12000 if kind == 'long' else 2500, .8)
        candidate = validate_final_script(raw)
        audit['final_script'] = candidate['final_script']
        _write_json(output / 'cognitive_audit.json', result)
        score = score_draft_script(candidate['final_script'], context, kind)
        import re
        spoken = re.sub(r'\[[^\]]*\]', '', candidate['final_script'])
        minimum, maximum = FORMATS[kind][:2]
        audit['evaluation'] = score
        blockers = claim_issues(spoken, context)
        if not minimum <= len(spoken.split()) <= maximum:
            blockers.append(f'Expected {minimum}-{maximum} spoken words.')
        if re.search(r"\b(in this video|let['\u2019]s dive in|without further ado)\b", spoken, re.I):
            blockers.append('Remove filler phrases.')
        if kind == 'short' and (len(re.split(r'[.!?\n]', spoken, maxsplit=1)[0].split()) >= 12 or '?' in spoken or '\uff1f' in spoken):
            blockers.append('Short opening must be under 12 words without a question.')
        if kind == 'mid':
            sentences = 0
            cues = 0
            for part in re.split(r'(\[[^\]]+\])', candidate['final_script']):
                if part.startswith('['):
                    cues += 1
                    if sentences != 3:
                        blockers.append('Place a cue after every three sentences.')
                    sentences = 0
                else:
                    sentences += len(re.findall(r'[.!?\u0964](?:\s|$)', part))
            if not cues or sentences > 3:
                blockers.append('Mid script is missing required pacing cues.')
        if kind == 'long' and not 3 <= len(re.findall(r'\[SECTION\s+\d+\s*:', candidate['final_script'], re.I)) <= 5:
            blockers.append('Long script needs three to five inline sections.')
        audit['blockers'] = list(dict.fromkeys(blockers))
        audit['rewrite_approved'] = (score['has_cta'] and not score['invented_experience']
            and score['overall_score'] >= 80 and not blockers)
    except Exception as exc:
        audit['rewrite_error'] = 'Rewrite or independent scoring unavailable: ' + type(exc).__name__
    screenshots = []
    for index, failure in enumerate(cognitive['failure_timestamps']):
        try:
            path = extract_audit_frame(video, failure['timestamp'], output / 'frames' / f'frame_{index}.jpg')
            screenshots.append({'path': str(path), 'caption': f"{failure['timestamp']:.2f}s: {failure['reason']}"})
        except (OSError, ValueError, subprocess.SubprocessError):
            audit.setdefault('warnings', []).append('A cited screenshot could not be extracted.')
    try:
        pdf_critique = cognitive['psychological_critique']
        if audit.get('evaluation'):
            pdf_critique += ('\n\nRewrite text review: ' + ('APPROVED' if audit['rewrite_approved'] else 'NOT APPROVED')
                + f" ({audit['evaluation']['overall_score']}/100). " + audit['evaluation']['critique'])
        if audit.get('rewrite_error'):
            pdf_critique += '\n\n' + audit['rewrite_error']
        generate_audit_pdf(pacing['text'], audit['final_script'], pdf_critique, screenshots, output / 'audit.pdf')
        audit['pdf_file'] = 'audit.pdf'
    except Exception as exc:
        audit['pdf_error'] = 'Audit PDF unavailable: ' + type(exc).__name__
    result['audit'] = audit
    _write_json(output / 'cognitive_audit.json', result)
    return result


def run_cognitive_audit(video,output,visual_frames,progress,brief=None):
    """Unified pixel/transcript/WPM simulation after parallel media extraction."""
    if visual_frames and not any(frame.get('path') for frame in visual_frames):
        # Previously saved observation-only evidence remains reviewable.
        return _run_observation_cognitive_audit(video,output,visual_frames,progress,brief)
    import asyncio
    import imageio_ffmpeg
    from studio_av_signals import extract_media_parallel
    from studio_virality import simulate_cognitive_response,DEFAULT_COGNITIVE_MODEL
    from studio_decision_pdf import generate_audit_pdf
    output=Path(output)
    reader=imageio_ffmpeg.read_frames(str(video))
    try:info=next(reader)
    finally:reader.close()
    duration=info.get('duration',0)
    if not 0<duration<=900:raise ValueError('Cognitive review supports clips up to 15 minutes.')
    try:
        corrected=json.loads((output/'review_input.json').read_text(encoding='utf-8')).get('transcript',{})
    except (OSError,ValueError,AttributeError):corrected={}
    progress(15,'Extracting video frames and Whisper speech evidence in parallel')
    media=asyncio.run(extract_media_parallel(video,output,duration,(brief or {}).get('language','auto'),corrected))
    pacing=media['pacing']
    _write_json(output/'transcript.json',pacing)
    (output/'transcript.txt').write_text(pacing['text'],encoding='utf-8')
    if not media['frames']:raise ValueError('No actual visual frames were extracted; no cognitive score assigned.')
    progress(45,'Nemotron is reviewing pixels, transcript, word timings and WPM')
    cognitive=simulate_cognitive_response(media['frames'],pacing['text'],pacing,brief,
        progress=lambda stage:progress(45,'Cognitive simulation: '+stage))
    result={'cognitive':cognitive,'pacing':pacing,'audit':{'triggered':False},
            'visual_frames':cognitive.get('visual_observations',[]),
            'extraction_seconds':media['extraction_seconds'],'evidence_warnings':media['warnings']}
    _write_json(output/'cognitive_audit.json',result)
    if cognitive['attention_retention_score']>=70:return result
    progress(72,'Attention below 70: actor-critic revision and three-page PDF audit')
    from studio_script_writer import brief_values
    from studio_script_team import chat_json
    from studio_script_nvidia import nvidia_token
    from studio_evaluation import CRITIC_SYSTEM
    from studio_editor import EDITOR_SYSTEM
    context=dict(brief or {})
    context.setdefault('topic','Creator video revision')
    context.setdefault('facts','No verified product efficacy or experience supplied. Describe only the supplied evidence.')
    context.update(content_duration='short' if duration<=40 else 'mid' if duration<=90 else 'long',writer_backend='fast')
    audit={'triggered':True,'rewrite_attempts':1,'rewrite_approved':False,'final_script':''}
    result['audit']=audit
    _write_json(output/'cognitive_audit.json',result)
    try:
        from studio_script_writer import system_prompt
        context=brief_values(context)
        if (brief or {}).get('brand_context'):context['brand_context']=brief['brand_context']
        request={'brief':context,'revision_notes':cognitive['psychological_critique'],
                 'previous_script':{'final_script':pacing['text']}}
        def complete(prompt,tokens,label):
            from studio_script_team import draft_reasoning_effort
            system=CRITIC_SYSTEM if label.startswith('Internal critique') else EDITOR_SYSTEM if label.startswith('Editor') else system_prompt(context)
            def preview(content):pass
            preview.status=lambda message:progress(80,label+': '+message)
            return chat_json(nvidia_token('COGNITIVE_API_KEY') or nvidia_token('GEMMA_API_KEY') or nvidia_token(),DEFAULT_COGNITIVE_MODEL,
                             system,prompt,tokens,0 if label.startswith('Internal critique') else .7,preview,
                             reasoning_effort=draft_reasoning_effort(tokens,label))[0]
        complete.model=DEFAULT_COGNITIVE_MODEL
        complete.stage_systems=True
        revision=generate_viral_script_pipeline(request,complete,lambda value:_write_json(output/'audit_script_result.json',value),lambda *args:None)
        audit.update(final_script=revision['final_script'],rewrite_approved=revision['approved'],
                     blockers=revision['best']['assessment']['blockers'],ab_hooks=revision['ab_hooks'],
                     pipeline=revision['pipeline'],mechanical_critique=revision['mechanical_critique'])
    except (ValueError,RuntimeError) as exc:
        audit['rewrite_error']='Actor-critic revision unavailable: '+str(exc)[:400]
    screenshots=[]
    for index,failure in enumerate(cognitive['failure_timestamps']):
        try:
            path=extract_audit_frame(video,failure['timestamp'],output/'frames'/f'frame_{index}.jpg')
            screenshots.append({'path':str(path),'caption':f"{failure['timestamp']:.2f}s: {failure['reason']}"})
        except (OSError,ValueError,subprocess.SubprocessError):
            audit.setdefault('warnings',[]).append('A flagged frame could not be extracted.')
    try:
        critique=cognitive['psychological_critique']+'\n\nRevision: '+('Safety checks passed.' if audit['rewrite_approved'] else 'Needs review.')
        if audit.get('blockers'):critique+='\nRevision checks: '+'; '.join(audit['blockers'])[:1000]
        if audit.get('rewrite_error'):critique+=' '+audit['rewrite_error']
        generate_audit_pdf(pacing['text'],audit['final_script'],critique,screenshots,output/'audit.pdf')
        audit['pdf_file']='audit.pdf'
    except Exception as exc:
        audit['pdf_error']='Audit PDF unavailable: '+type(exc).__name__
    _write_json(output/'cognitive_audit.json',result)
    return result
