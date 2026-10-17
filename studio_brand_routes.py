"""Register brand endpoints on the local Studio app."""
import json
from pathlib import Path
from typing import Annotated
from fastapi import Body, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
import studio_brands as brands


def install(server):
    app = server.app

    @app.get("/brand.js")
    def script():
        return FileResponse(server.ROOT / "web/brand.js", media_type="text/javascript")

    def get(brand_id):
        try:
            return brands.read_brand(server.RESULTS_DIR, brand_id)
        except (OSError, ValueError):
            raise HTTPException(404, "Brand not found.") from None

    @app.get("/api/brands")
    def listing():
        rows = []
        for path in (server.RESULTS_DIR / "_brands").glob("*/profile.json"):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
                rows.append({k: row[k] for k in ("id", "name", "version")})
            except (OSError, ValueError, KeyError):
                continue
        return sorted(rows, key=lambda r: r["name"].casefold())

    @app.post("/api/brands", status_code=201)
    def create(values: Annotated[dict, Body()]):
        try:
            with server._lock:
                return brands.new_brand(server.RESULTS_DIR, values.get("name"))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get("/api/brands/{brand_id}")
    def detail(brand_id: str):
        profile = get(brand_id)
        return dict(profile, calibration=brands.calibration(profile))

    @app.post("/api/brands/{brand_id}/documents/{kind}")
    async def document(brand_id: str, kind: str, file: Annotated[UploadFile | None, File()] = None,
                       text: Annotated[str, Form(max_length=brands.MAX_TEXT)] = ""):
        if kind not in {"guidelines", "product_brief"}:
            raise HTTPException(422, "Choose guidelines or product_brief.")
        get(brand_id)
        try:
            if file and text.strip():
                raise ValueError("Choose a file or pasted text for this document, not both.")
            if file:
                content = await file.read(brands.MAX_DOCUMENT_BYTES + 1)
                extracted = await run_in_threadpool(brands.extract_document, file.filename or "", content)
                name = Path(file.filename or "Document").name
            else:
                extracted = text.strip()
                if not extracted:
                    raise ValueError("Choose a document or paste its text.")
                name = "Pasted " + kind.replace("_", " ")
            with server._lock:
                profile = get(brand_id)
                profile["documents"][kind] = {"name": name, "text": extracted, "characters": len(extracted)}
                return brands.save_brand(server.RESULTS_DIR, profile)
        except Exception as exc:
            if isinstance(exc, HTTPException):
                raise
            raise HTTPException(422, "Document could not be read: " + server._safe_error(exc)) from None
        finally:
            if file:
                await file.close()

    @app.delete("/api/brands/{brand_id}/documents/{kind}")
    def remove_document(brand_id: str, kind: str):
        with server._lock:
            profile = get(brand_id)
            profile["documents"].pop(kind, None)
            return brands.save_brand(server.RESULTS_DIR, profile)

    @app.post("/api/brands/{brand_id}/references")
    def reference(brand_id: str, values: Annotated[dict, Body()]):
        job_id = str(values.get("job_id", ""))
        job = server._load_job(job_id)
        if job["status"] != "completed":
            raise HTTPException(409, "Finish the reference analysis first.")
        if job.get("brand_id") and job["brand_id"] != brand_id:
            raise HTTPException(422, "This video belongs to a different brand.")
        get(brand_id)
        try:
            with server._lock:
                return brands.register_reference(server.RESULTS_DIR, brand_id, job_id,
                                                  brands.outcome_values(values.get("outcomes", {})))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.delete("/api/brands/{brand_id}/references/{job_id}")
    def remove_reference(brand_id: str, job_id: str):
        with server._lock:
            profile = get(brand_id)
            profile["references"] = [r for r in profile["references"] if r["job_id"] != job_id]
            return brands.save_brand(server.RESULTS_DIR, profile)

    @app.post("/api/jobs/{job_id}/feedback")
    def feedback(job_id: str, values: Annotated[dict, Body()]):
        job = server._load_job(job_id)
        if job["status"] != "completed" or not job.get("brand_id"):
            raise HTTPException(409, "Feedback learning needs a completed video associated with a brand.")
        report = json.loads((server._job_dir(job_id) / "report.json").read_text(encoding="utf-8"))
        try:
            outcomes = brands.outcome_values(values)
            if not outcomes["notes"] and not any(k in outcomes for k in ("team_rating", "views", "retention_percent", "conversions", "spend")):
                raise ValueError("Add a rating, result or feedback note.")
            with server._lock:
                profile = brands.save_feedback(server.RESULTS_DIR, job["brand_id"], job_id,
                                               report, outcomes, job.get("purpose", "candidate"), job.get("video_hash"))
            return {"saved": True, "calibration": brands.calibration(profile), "feedback": outcomes}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get("/api/jobs/{job_id}/feedback")
    def get_feedback(job_id: str):
        job = server._load_job(job_id)
        if not job.get("brand_id"):
            return {"enabled": False}
        profile = get(job["brand_id"])
        row = next((r for r in profile.get("feedback", []) if r["job_id"] == job_id), {})
        return {"enabled": True, "brand": profile["name"], "feedback": row,
                "calibration": brands.calibration(profile)}
