"""Sequential NVIDIA video rendering, guarded like the model workers."""
import subprocess
import time

from studio_resources import GPU_BUDGET_MB, GPU_GUARD_MB, GPU_STOP_C, RESERVE_MB, require_memory


def clip_command(executable, video, destination, start, duration):
    return [executable, "-hide_banner", "-loglevel", "error", "-y",
            "-hwaccel", "cuda", "-hwaccel_output_format", "cuda",
            "-ss", str(start), "-i", str(video), "-t", str(duration),
            "-map", "0:v:0", "-map", "0:a:0?", "-sn", "-dn", "-map_metadata", "-1",
            "-vf", "scale_cuda=w='min(640,iw)':h='min(640,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2:format=nv12",
            "-c:v", "h264_nvenc", "-preset", "p2", "-tune", "hq", "-rc", "vbr", "-cq", "25", "-b:v", "0",
            "-rc-lookahead", "0", "-bf", "0", "-c:a", "aac", "-b:a", "96k", "-threads", "2",
            "-movflags", "+faststart", str(destination)]


def run_gpu_render(command, log_path, timeout=90):
    from studio_pipeline import gpu_info, stage_pause, _terminate_worker
    # The short NVENC export uses a dedicated video engine, not LLM bursts.
    # Retain its original preflight threshold and the live 82 C stop guard.
    stage_pause(lambda *_: None, 0, pause_at=76, resume_at=74)
    require_memory(RESERVE_MB)
    before = gpu_info()
    if before["used_mb"] > GPU_BUDGET_MB - 1536:
        raise RuntimeError("GPU is busy; not enough headroom for video rendering")
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                                   | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
        try:
            while process.poll() is None:
                require_memory(RESERVE_MB)
                info = gpu_info()
                if (not info["available"] or info["used_mb"] > GPU_BUDGET_MB - GPU_GUARD_MB
                        or info.get("temperature_c", GPU_STOP_C) >= GPU_STOP_C):
                    raise RuntimeError("GPU rendering stopped by the memory/temperature guard")
                if time.monotonic() - started > timeout:
                    raise TimeoutError("GPU video rendering timed out")
                time.sleep(.25)
            if process.returncode != 0:
                raise RuntimeError("NVIDIA video rendering failed; see " + log_path.name)
        finally:
            if process.poll() is None:
                _terminate_worker(process)
