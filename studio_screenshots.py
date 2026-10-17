"""Small, sequential source-frame previews for portable PDF reports."""
import base64
from pathlib import Path


def screenshot_command(executable, video, destination, timestamp):
    return [executable, "-hide_banner", "-loglevel", "error", "-y",
            "-hwaccel", "cuda", "-hwaccel_output_format", "cuda",
            "-ss", str(timestamp), "-i", str(video), "-map", "0:v:0",
            "-an", "-sn", "-dn", "-frames:v", "1",
            "-vf", "scale_cuda=w='min(640,iw)':h='min(640,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2:format=nv12,hwdownload,format=nv12",
            "-c:v", "mjpeg", "-q:v", "3", "-threads", "1", "-update", "1", str(destination)]


def create_screenshots(video: Path, output: Path, report: dict) -> None:
    import imageio_ffmpeg
    from studio_video import run_gpu_render

    directory = output / "screenshots"
    directory.mkdir(parents=True, exist_ok=True)
    duration = float(report["video"]["duration_seconds"])
    frame = 1 / max(1, float(report["video"].get("fps") or 30))
    cache = {}

    def capture(timestamp, label):
        timestamp = round(max(0, min(timestamp, duration - frame)), 3)
        if timestamp not in cache:
            relative = f"screenshots/frame_{len(cache):03d}.jpg"
            destination = output / relative
            result = {"time_seconds": timestamp, "file": relative}
            try:
                run_gpu_render(screenshot_command(imageio_ffmpeg.get_ffmpeg_exe(), video,
                                                  destination, timestamp),
                               directory / f"frame_{len(cache):03d}.log", timeout=30)
                if not destination.is_file() or not destination.stat().st_size:
                    raise RuntimeError("No source frame was returned")
            except (OSError, RuntimeError) as exc:
                destination.unlink(missing_ok=True)
                result = {"time_seconds": timestamp, "error": str(exc)}
            cache[timestamp] = result
        return dict(cache[timestamp], label=label)

    for edit in report.get("review", {}).get("edits", []):
        start, end = float(edit["start"]), float(edit["end"])
        edit["screenshots"] = [capture(start, "Start of edit range")]
        if end - start > 2 * frame:
            edit["screenshots"].append(capture(end - frame, "End of edit range"))
    for clip in report.get("brief", {}).get("clips", []):
        clip["screenshots"] = [capture((clip["start"] + clip["end"]) / 2, "Clip preview")]


def screenshot_path(frame: dict, directory: Path):
    """Read only generated preview assets inside this report's directory."""
    if not frame.get("file"):
        return None
    bases = [(directory / folder).resolve() for folder in ("screenshots", "ocr_frames")]
    candidate = (directory / frame["file"]).resolve()
    if (not any(candidate.is_relative_to(base) for base in bases) or candidate.suffix.lower() != ".jpg"
            or not candidate.is_file() or candidate.stat().st_size > 2_000_000):
        return None
    return candidate


def screenshot_html(frames: list, directory: Path) -> str:
    import html
    figures = []
    for frame in frames:
        caption = html.escape(f'{frame.get("label", "Source frame")} — near {frame["time_seconds"]:.2f}s')
        path = screenshot_path(frame, directory)
        if path:
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            figures.append(f'<figure><img src="data:image/jpeg;base64,{data}" alt="{caption}"><figcaption>{caption}</figcaption></figure>')
        else:
            figures.append(f'<figure><figcaption>{caption}: screenshot unavailable; check the original video.</figcaption></figure>')
    return '<div class="screenshots">' + ''.join(figures) + '</div>' if figures else ''
