"""Local video studio: one analysis job at a time, private input files.

Run with ``.venv\\Scripts\\python studio_server.py`` and open
http://127.0.0.1:8765. Model execution lives in studio_pipeline.py.
"""
from __future__ import annotations

import json
import hashlib
import logging
import os
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlsplit

from studio_resources import ResourcePressureError, limit_cpu_threads, require_memory

limit_cpu_threads()

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, Body
from fastapi.responses import FileResponse, JSONResponse


ROOT = Path(__file__).resolve().parent
RESULTS_DIR = ROOT / "results" / "studio"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
VIDEO_EXTENSIONS = {".mp4"}
PUBLIC_FILES = {
    "report.pdf", "report.json", "audit.pdf", "cognitive_audit.json", "transcript.txt", "transcript.json",
    "subtitles.srt", "video_metrics.csv", "video_info.json", "charts.png", "evaluation.json", "ocr.json",
}
JOB_ID = re.compile(r"^[0-9a-f]{32}$")
FRAME_FILE = re.compile(r"^(?:frames|ocr_frames)/frame_[0-9]+\.jpg$")
CLIP_FILE = re.compile(r"^clips/clip_[0-9]{2}\.mp4$")
TERMINAL_STATES = {"completed", "failed"}

app = FastAPI(title="Creator Video Studio", docs_url=None, redoc_url=None)
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="video-analysis")
_lock = threading.RLock()
_jobs: dict[str, dict[str, Any]] = {}
_active_job: str | None = None
_logger = logging.getLogger("studio")


def get_system_info() -> dict:
    from studio_script_nvidia import nvidia_token
    return {"review_backend":"nvidia", "review_configured":bool(nvidia_token('GEMMA_API_KEY') or nvidia_token()),
            "max_budget_mb":4096, "default_budget_mb":4096, "cuda_ready":False, "gpu":{"available":False}}



def run_analysis(**kwargs: Any) -> dict:
    from studio_remote_review import review_video
    return review_video(kwargs['video'], kwargs['output'], kwargs['progress'])


def resume_analysis(**kwargs: Any) -> dict:
    return run_analysis(**kwargs)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_error(exc: Exception) -> str:
    return re.sub(r"(?:hf_[A-Za-z0-9]+|nvapi-[A-Za-z0-9_-]+)", "[redacted token]", str(exc))[:2000]


def _job_dir(job_id: str) -> Path:
    if not JOB_ID.fullmatch(job_id):
        raise HTTPException(404, "Job not found.")
    return RESULTS_DIR / job_id


def _persist_job(job: dict[str, Any]) -> None:
    directory = _job_dir(job["id"])
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / "job.json.tmp"
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(job, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(directory / "job.json")


def _update_job(job_id: str, **changes: Any) -> None:
    with _lock:
        _jobs[job_id].update(changes, updated_at=_now())
        _persist_job(_jobs[job_id])


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    result = dict(job)
    job_url = f"/api/jobs/{job['id']}"
    result["report_url"] = job_url + "/report"
    result["pdf_url"] = job_url + "/files/report.pdf"
    result["files_url"] = job_url + "/files/"
    return result


def _load_job(job_id: str) -> dict[str, Any]:
    directory = _job_dir(job_id)
    with _lock:
        if job_id not in _jobs:
            try:
                job = json.loads((directory / "job.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raise HTTPException(404, "Job not found.") from None
            if not isinstance(job, dict) or job.get("id") != job_id:
                raise HTTPException(404, "Job not found.")
            # Old worker threads cannot survive a server restart.
            if job.get("status") not in TERMINAL_STATES:
                job.update(status="failed", stage="Analysis interrupted", error=
                           "The server restarted before this analysis finished. Use Resume saved analysis to reuse the saved upload and evidence.",
                           updated_at=_now())
                _persist_job(job)
            _jobs[job_id] = job
        return _public_job(_jobs[job_id])


def _process_job(job_id: str, video: Path, budget_mb: int, vision: bool, resume: bool = False) -> None:
    global _active_job
    try:
        _update_job(job_id, status="running", progress=1, stage="Starting analysis", budget_mb=budget_mb)

        def progress(percent: int, stage: str) -> None:
            _update_job(job_id, progress=max(1, min(99, int(percent))), stage=str(stage))

        analyze = resume_analysis if resume else run_analysis
        report = analyze(video=video, output=_job_dir(job_id), budget_mb=0, vision=True, progress=progress)
        info_path = _job_dir(job_id) / "upload_info.json"
        info = json.loads(info_path.read_text(encoding="utf-8")) if info_path.exists() else {}
        if info.get("purpose") == "reference" and info.get("brand_id"):
            from studio_brands import register_reference
            with _lock:
                register_reference(RESULTS_DIR, info["brand_id"], job_id, info.get("outcomes", {}))
        # Keep the endpoint available even if a future pipeline only returns JSON.
        report_file = _job_dir(job_id) / "report.json"
        if not report_file.exists():
            report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        _update_job(job_id, status="completed", progress=100, stage="Report ready", report=report,
                    gpu_peak_mb=report.get("processing", {}).get("peak_gpu_mb"), completed_at=_now())
    except Exception as exc:
        error = _safe_error(exc) or type(exc).__name__
        _logger.error("Analysis %s failed: %s", job_id, error)
        _update_job(job_id, status="failed", stage="Analysis failed", error=error)
    finally:
        with _lock:
            if _active_job == job_id:
                _active_job = None


def _submit_job(job_id: str, *arguments) -> None:
    """A failed executor submission must release the slot and retain the upload."""
    global _active_job
    try:
        _executor.submit(_process_job,job_id,*arguments)
    except Exception as exc:
        with _lock:
            _update_job(job_id,status='failed',stage='Could not start analysis',error=_safe_error(exc))
            if _active_job==job_id:
                _active_job=None
        raise HTTPException(503,'Could not start analysis. Your upload is saved; retry when ready.') from None


@app.middleware("http")
async def local_requests_only(request: Request, call_next):
    # Prevent a remote webpage from submitting jobs to a localhost GPU service.
    host = request.headers.get("host", "")
    try:
        hostname = urlsplit("http://" + host).hostname
    except ValueError:
        hostname = None
    if hostname not in {"localhost", "127.0.0.1", "::1"}:
        return JSONResponse({"detail": "This studio accepts localhost requests only."}, status_code=403)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin and origin != f"{request.url.scheme}://{host}":
            return JSONResponse({"detail": "Cross-origin uploads are not permitted."}, status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Cross-site uploads are not permitted."}, status_code=403)
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                too_large = int(content_length) > MAX_UPLOAD_BYTES + 1024 * 1024
            except ValueError:
                return JSONResponse({"detail": "Invalid content length."}, status_code=400)
            if too_large:
                return JSONResponse({"detail": "Video upload limit is 20 MB."}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def index():
    page = ROOT / "web" / "index.html"
    if not page.is_file():
        raise HTTPException(503, "The studio page is not installed. Check the web/index.html file.")
    return FileResponse(page, media_type="text/html")


@app.get("/api/system")
def system_info():
    info = get_system_info()
    with _lock:
        return {**info, "busy": _active_job is not None, "active_job_id": _active_job,
                "upload_limit_mb": 20, "budget_min_mb": 1024, "budget_max_mb": info.get("max_budget_mb", 4096)}


@app.get("/creative.js")
def creative_script():
    return FileResponse(ROOT / "web" / "creative.js", media_type="text/javascript")


@app.get("/creative.css")
def creative_style():
    return FileResponse(ROOT / "web" / "creative.css", media_type="text/css")


@app.post("/api/jobs", status_code=202)
async def create_job(
    video: Annotated[UploadFile, File()],
    budget_mb: Annotated[int, Form(ge=0, le=262144)] = 0,
    vision: Annotated[bool, Form()] = True,
    language: Annotated[str, Form()] = "auto",
    platform: Annotated[str, Form()] = "general",
    audience: Annotated[str, Form(max_length=300)] = "",
    brand_id: Annotated[str, Form()] = "",
    purpose: Annotated[str, Form()] = "candidate",
    outcomes: Annotated[str, Form(max_length=4000)] = "{}",
):
    global _active_job
    from studio_review import LANGUAGES
    from studio_brands import snapshot, outcome_values, read_brand
    from studio_script_nvidia import nvidia_token
    if not (nvidia_token('GEMMA_API_KEY') or nvidia_token()):
        await video.close()
        raise HTTPException(422, 'Set GEMMA_API_KEY or NVIDIA_API_KEY on the server.')
    budget_mb = 0
    try:
        if purpose not in {"candidate", "reference"} or (purpose == "reference" and not brand_id):
            raise ValueError("Reference videos need a saved brand.")
        feedback_values = outcome_values(json.loads(outcomes))
        brand_snapshot = snapshot(RESULTS_DIR, brand_id) if brand_id and purpose == "candidate" else None
        if brand_id and purpose == "reference" and len(read_brand(RESULTS_DIR, brand_id)["references"]) >= 5:
            raise ValueError("This brand already has 5 references. Remove one first.")
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        await video.close()
        raise HTTPException(422, str(exc)) from None
    if language not in LANGUAGES or platform not in {"general", "instagram", "youtube", "facebook"}:
        await video.close()
        raise HTTPException(422, "Choose a supported language and platform.")
    extension = Path(video.filename or "").suffix.lower()
    if extension not in VIDEO_EXTENSIONS:
        await video.close()
        raise HTTPException(415, "Choose an MP4 up to 20 MB for NVIDIA review.")
    job_id = uuid.uuid4().hex
    with _lock:
        busy = _active_job is not None
        if not busy:
            _active_job = job_id
            _jobs[job_id] = {"id": job_id, "status": "uploading", "progress": 0,
                             "brand_id": brand_id, "purpose": purpose,
                             "stage": "Saving video", "budget_mb": budget_mb, "vision": vision,
                             "filename": Path(video.filename or "video").name,
                             "created_at": _now(), "updated_at": _now(), "error": None}
    if busy:
        await video.close()
        raise HTTPException(409, "Another video is being analyzed. Wait for its report before uploading again.")
    upload_saved=False
    try:
        directory = _job_dir(job_id)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "upload_info.json").write_text(
            json.dumps({"original_name": _jobs[job_id]["filename"], "language": language,
                        "platform": platform, "audience": audience, "brand_id": brand_id,
                        "purpose": purpose, "outcomes": feedback_values}, ensure_ascii=False),
            encoding="utf-8",
        )
        if brand_snapshot:
            from studio_remote_review import write_json as _write_json
            _write_json(directory / "brand_context.json", brand_snapshot)
        destination = directory / ("input" + extension)
        size = 0
        digest = hashlib.sha256()
        with destination.open("wb") as uploaded:
            while chunk := await video.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "Video upload limit is 20 MB.")
                uploaded.write(chunk)
                digest.update(chunk)
        if not size:
            raise HTTPException(400, "The uploaded video is empty.")
        upload_info = json.loads((directory / "upload_info.json").read_text(encoding="utf-8"))
        upload_info["video_hash"] = digest.hexdigest()
        from studio_remote_review import write_json as _write_json
        _write_json(directory / "upload_info.json", upload_info)
        if brand_snapshot:
            _write_json(directory / "brand_context.json", snapshot(RESULTS_DIR, brand_id, exclude_fingerprint=digest.hexdigest()))
        _update_job(job_id, status="queued", stage="Preparing analysis", upload_bytes=size, video_hash=digest.hexdigest())
        upload_saved=True
        _submit_job(job_id, destination, budget_mb, vision)
        return _load_job(job_id)
    except Exception as exc:
        error = str(exc.detail) if isinstance(exc, HTTPException) else _safe_error(exc)
        _update_job(job_id, status="failed", stage="Upload failed", error=error)
        with _lock:
            if _active_job == job_id:
                _active_job = None
        # A failed upload is not useful and can otherwise fill the disk on retries.
        if not upload_saved:
            incomplete = _job_dir(job_id) / ("input" + extension)
            incomplete.unlink(missing_ok=True)
        raise
    finally:
        await video.close()


@app.post("/api/jobs/{job_id}/retry", status_code=202)
def retry_job(job_id: str):
    global _active_job
    job = _load_job(job_id)
    directory = _job_dir(job_id)
    video = next((p for p in directory.glob("input.*") if p.suffix.lower() in VIDEO_EXTENSIONS), None)
    if video is None:
        raise HTTPException(400, "The saved upload is unavailable. Upload the video again.")
    with _lock:
        if _active_job is not None or job["status"] != "failed":
            raise HTTPException(409, "Only a failed analysis can be resumed, while Studio is idle.")
        _active_job = job_id
        _update_job(job_id, status="queued", stage="Resuming saved analysis", error=None)
    _submit_job(job_id, video, get_system_info()["default_budget_mb"], bool(job.get("vision", True)), True)
    return _load_job(job_id)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    return _load_job(job_id)


@app.post("/api/jobs/{job_id}/correct-transcript", status_code=202)
def correct_transcript(job_id: str, changes: Annotated[dict, Body()]):
    """Let a fluent reviewer fix ASR before regenerating judgments; retain source times."""
    global _active_job
    job = _load_job(job_id)
    directory = _job_dir(job_id)
    source = directory / "review_input.json"
    if not source.is_file():
        raise HTTPException(409, "Transcript evidence is not ready yet.")
    report = json.loads(source.read_text(encoding="utf-8"))
    segments = report.get("transcript", {}).get("segments", [])
    texts = changes.get("texts")
    if (not isinstance(texts, list) or len(texts) != len(segments) or not texts
            or any(not isinstance(t, str) or not t.strip() or len(t) > 3000 for t in texts)
            or sum(len(t) for t in texts) > 60000):
        raise HTTPException(422, "Supply one non-empty correction per original segment (maximum 3,000 characters each).")
    video = next((p for p in directory.glob("input.*") if p.suffix.lower() in VIDEO_EXTENSIONS), None)
    if video is None:
        raise HTTPException(400, "The saved video is unavailable.")
    try:
        require_memory()
    except ResourcePressureError as exc:
        raise HTTPException(503, str(exc)) from None
    with _lock:
        if _active_job is not None or job["status"] not in TERMINAL_STATES:
            raise HTTPException(409, "Wait for the current analysis to finish before correcting its transcript.")
        from studio_pipeline import _write_json, _transcript_files
        backup = directory / "review_input_original.json"
        if not backup.exists():
            _write_json(backup, report)
        for segment, text in zip(segments, texts):
            segment.update(text=text.strip(), words=[])
        report["transcript"]["manually_corrected"] = True
        report["metrics"]["word_count"] = sum(len(t.split()) for t in texts)
        report["metrics"]["words_per_minute"] = round(report["metrics"]["word_count"] * 60 / max(.1, report["video"]["duration_seconds"]), 1)
        report["metrics"]["low_confidence_word_count"] = 0
        _write_json(source, report)
        _transcript_files(report["transcript"], directory)
        _active_job = job_id
        _update_job(job_id, status="queued", stage="Reviewing corrected transcript", error=None, progress=1)
    _submit_job(job_id, video, get_system_info()["default_budget_mb"], bool(job.get("vision", True)), True)
    return _load_job(job_id)


@app.get("/api/jobs/{job_id}/report")
def get_report(job_id: str):
    job = _load_job(job_id)
    if job["status"] != "completed":
        raise HTTPException(409, "The report is not ready yet.")
    if "report" in job:
        return JSONResponse(job["report"])
    report = _job_dir(job_id) / "report.json"
    if not report.is_file():
        raise HTTPException(404, "Report file not found.")
    return FileResponse(report, media_type="application/json")


@app.get("/api/jobs/{job_id}/video")
def get_review_video(job_id: str):
    _load_job(job_id)
    video = _job_dir(job_id) / 'input.mp4'
    if not video.is_file():
        raise HTTPException(404, 'Original MP4 not found.')
    return FileResponse(video, media_type='video/mp4')


@app.get("/api/jobs/{job_id}/files/{filename:path}")
def get_file(job_id: str, filename: str):
    _load_job(job_id)
    if filename not in PUBLIC_FILES and not FRAME_FILE.fullmatch(filename) and not CLIP_FILE.fullmatch(filename):
        raise HTTPException(404, "Report file not found.")
    directory = _job_dir(job_id).resolve()
    path = (directory / filename).resolve()
    if not path.is_relative_to(directory) or not path.is_file():
        raise HTTPException(404, "Report file not found.")
    download = path.name if path.suffix in {".pdf", ".srt", ".csv", ".txt", ".json"} else None
    return FileResponse(path, filename=download)


import sys
from studio_brand_routes import install as install_brand_routes
install_brand_routes(sys.modules[__name__])
from studio_script_routes import install as install_script_routes
install_script_routes(sys.modules[__name__])

from studio_gemma_routes import install as install_gemma_routes
install_gemma_routes(sys.modules[__name__])

if __name__ == "__main__":
    import uvicorn
    print("Creator Video Studio: http://127.0.0.1:8765", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=8765, proxy_headers=False)
