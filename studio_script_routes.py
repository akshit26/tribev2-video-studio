"""Script writer API sharing Studio's exclusive GPU execution slot."""
import json
import uuid
import time
from typing import Annotated

from fastapi import Body, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, HTMLResponse

import studio_script_writer as writer


def install(server):
    app = server.app

    def directory(script_id):
        if not server.JOB_ID.fullmatch(script_id):
            raise HTTPException(404, "Script not found.")
        return server.RESULTS_DIR / "_scripts" / script_id

    def read(script_id):
        path = directory(script_id)
        try:
            state = json.loads((path / "state.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise HTTPException(404, "Script not found.") from None
        with server._lock:
            if state["status"] in {"queued", "running"} and server._active_job != script_id:
                state.update(status="failed", stage="Interrupted by server restart", error="Saved drafts are preserved. Start a new revision to continue.")
        for name, key in [("hooks.json", "hook_options"), ("script_result.json", "result")]:
            try:
                state[key] = json.loads((path / name).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        if "result" not in state and (path / "script_draft.json").exists():
            try:
                draft = json.loads((path / "script_draft.json").read_text(encoding="utf-8"))
                state["result"] = {"brief": state["brief"], "best": {"script": draft, "assessment": {
                    "score": None, "criteria": [], "unsupported_claims": [], "blockers": draft.get("missing_proof", []),
                    "method": "Saved draft; no valid automated score is available."}}, "history": [],
                    "target": writer.TARGET, "target_met": False, "stop_reason": "review_unavailable", "selected_hook": None}
            except (OSError, ValueError):
                pass
        # Live preview stays explicitly unscored and never replaces saved text.
        try:
            live_path=path / "script_live.json"
            draft_path=path / "script_draft.json"
            if live_path.exists():
                state["live_draft"]=json.loads(live_path.read_text(encoding="utf-8"))
            if draft_path.exists() and (not live_path.exists() or draft_path.stat().st_mtime>=live_path.stat().st_mtime):
                draft=json.loads(draft_path.read_text(encoding="utf-8"))
                state["live_draft"]={"paragraphs":[s["spoken"] for s in draft["scenes"]],"validated":True,"reviewed":False}
            request=json.loads((path / "review_input.json").read_text(encoding="utf-8"))["script_request"]
            state["revision_notes"]=request.get("revision_notes","")
            state["parent_script_id"]=request.get("parent_script_id")
            if state["status"]=="failed" and "result" not in state and request.get("previous_script"):
                original=request["previous_script"]
                state["result"]={"brief":state["brief"],"best":{"script":original,"assessment":{"score":None,"criteria":[],"unsupported_claims":[],"blockers":[],"method":"Original draft retained; requested changes did not complete."}},"history":[],"target_met":False,"stop_reason":"requested_changes_not_completed","selected_hook":request.get("selected_hook"),"revision_notes":request.get("revision_notes","")}
        except (OSError,ValueError,KeyError,TypeError):
            pass
        if "result" in state:
            state["result"] = writer.recheck_saved_result(state["result"],state["brief"])
        try:
            state["timing"] = json.loads((path / "review_profile.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        return state

    def persist(path, state):
        from studio_pipeline import _write_json
        _write_json(path / "state.json", state)

    def process(script_id, request):
        path = directory(script_id)
        begun = time.monotonic()
        state = {"id": script_id, "status": "running", "stage": "Starting hosted writer" if request["brief"].get("writer_backend") in {"huggingface", "nvidia"} else "Starting local writer", "progress": 1, "brief": request["brief"]}
        try:
            persist(path, state)
            def progress(percent, stage):
                state.update(progress=max(state["progress"], percent), stage=stage, elapsed_seconds=round(time.monotonic()-begun, 1))
                persist(path, state)
            if request["brief"].get("writer_backend", "local") == "huggingface":
                from studio_script_hf import run_hf_writer
                run_hf_writer(path,request,progress)
            elif request["brief"].get("writer_backend") == "nvidia":
                from studio_script_nvidia import run_nvidia_writer
                run_nvidia_writer(path, request, progress)
            else:
                from studio_pipeline import _run_worker, stage_pause
                stage_pause(progress, 1, "Waiting for the GPU to be ready")
                ok, _, reason = _run_worker("review", path / "unused.mp4", path, "cuda", 4096, progress, 1, 99)
                if not ok:
                    raise RuntimeError(reason)
            state.update(status="completed", progress=100, stage="Hook options ready" if request["mode"] == "hooks" else "Script revision finished")
            if request["mode"] == "hooks":
                result = json.loads((path / "hooks.json").read_text(encoding="utf-8")) if (path / "hooks.json").exists() else {}
                if result.get("review_status") in {"needs_review", "unavailable"}:
                    state.update(stage="Hooks saved — review the flagged options", warning=result.get("warning"))
        except Exception as exc:
            state.update(status="failed", error=server._safe_error(exc), stage="Writer stopped; any completed drafts are saved")
        finally:
            try:
                state["elapsed_seconds"] = round(time.monotonic()-begun, 1)
                persist(path, state)
            finally:
                with server._lock:
                    if server._active_job == script_id:
                        server._active_job = None

    @app.get("/writer")
    def page():
        return FileResponse(server.ROOT / "web/writer.html")

    @app.get("/writer.js")
    def javascript():
        return FileResponse(server.ROOT / "web/writer.js", media_type="text/javascript")

    @app.get("/writer.css")
    def stylesheet():
        return FileResponse(server.ROOT / "web/writer.css", media_type="text/css")

    @app.get("/api/scripts/engines")
    def engines():
        from studio_script_hf import configuration
        return configuration()

    @app.get("/api/scripts/personas")
    def personas():
        return {"personas": writer.personas()}

    @app.get("/api/scripts/library")
    def library():
        return writer.library()

    @app.get("/api/scripts/experiments")
    def experiments():
        path = server.RESULTS_DIR / "_scripts" / "experiments.json"
        with server._lock:
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    @app.post("/api/scripts/experiments", status_code=201)
    def record_experiment(values: Annotated[dict, Body()]):
        try:
            row = {k: writer.text(values.get(k), limit) for k, limit in [("title", 160), ("platform", 80), ("hypothesis", 500), ("observations", 1500)]}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        row.update(id=uuid.uuid4().hex, created_at=server._now(), evidence_type="user observation; not verified or causal")
        with server._lock:
            rows = experiments()
            if len(rows) >= 200:
                raise HTTPException(422, "Experiment library is limited to 200 entries.")
            from studio_pipeline import _write_json
            path = server.RESULTS_DIR / "_scripts" / "experiments.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            _write_json(path, rows + [row])
        return row

    @app.get("/api/scripts")
    def listing():
        rows = []
        for p in (server.RESULTS_DIR / "_scripts").glob("*/state.json"):
            try:
                row = read(p.parent.name)
                rows.append({k: row[k] for k in ("id", "status", "brief", "stage")})
            except (HTTPException, OSError, ValueError, KeyError):
                continue
        return rows

    @app.post("/api/scripts", status_code=202)
    def create(values: Annotated[dict, Body()]):
        from studio_pipeline import _write_json
        try:
            brief = writer.brief_values(values.get("brief"))
            brief["generation_seed"] = uuid.uuid4().int % 2147483647
            from studio_script_hf import validate_configuration
            validate_configuration(brief)
            mode = values.get("mode", "hooks")
            if mode not in {"hooks", "script"}:
                raise ValueError("Choose hooks or script.")
            hook = values.get("selected_hook")
            if hook is not None:
                if not isinstance(hook, dict):
                    raise ValueError("Choose a valid hook.")
                hook = {k: writer.text(hook.get(k), 350) for k in ("angle", "spoken", "payoff")}
                hook.update(visual="", overlay="")
                for key in ("concept", "why_stop", "creative_route"):
                    if values["selected_hook"].get(key):
                        hook[key] = writer.text(values["selected_hook"][key], 350)
            if brief["brand_id"]:
                from studio_brands import read_brand
                brand = read_brand(server.RESULTS_DIR, brief["brand_id"])
                brief["brand_context"] = {"name": brand["name"], "documents": {
                    k: v.get("text", "")[:1000] for k, v in brand.get("documents", {}).items()}}
            if brief["source_job_id"]:
                job = server._load_job(brief["source_job_id"])
                if job["status"] != "completed":
                    raise ValueError("Finish the source video analysis first.")
                if brief["brand_id"] and job.get("brand_id") and job["brand_id"] != brief["brand_id"]:
                    raise ValueError("The source video belongs to a different brand.")
                source = json.loads((server._job_dir(brief["source_job_id"]) / "report.json").read_text(encoding="utf-8"))
                brief["source_review"] = json.dumps(source.get("brief", {}), ensure_ascii=False)[:1200]
            if values.get("use_experiments"):
                brief["experiment_notes"] = [{"hypothesis": r["hypothesis"][:250], "observations": r["observations"][:500],
                                               "evidence_type": r["evidence_type"]} for r in experiments()[-2:]]
            previous = values.get("previous_script")
            if previous is not None:
                previous = writer.validate_script(previous, brief)
            raw_notes=values.get("revision_notes", "")
            revision_notes = writer.text(raw_notes,1200) if raw_notes != "" else ""
            if revision_notes and (mode!="script" or previous is None):
                raise ValueError("Requested changes need an existing script draft.")
            parent_script_id=values.get("parent_script_id")
            if parent_script_id is not None:
                if not isinstance(parent_script_id,str) or not server.JOB_ID.fullmatch(parent_script_id):
                    raise ValueError("Choose a valid original script.")
                read(parent_script_id)
            scene_index = values.get("scene_index")
            if scene_index is not None and (type(scene_index) is not int or previous is None or not 0 <= scene_index < len(previous["scenes"])):
                raise ValueError("Choose an existing scene to regenerate.")
            if len(json.dumps(brief, ensure_ascii=False)) > 6500:
                raise ValueError("Brief and references are too long for the local model. Shorten the facts or deselect experiment notes.")
        except (ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
            raise HTTPException(422, str(exc)) from None
        request = {"mode": mode, "brief": brief, "selected_hook": hook, "previous_script": previous, "scene_index": scene_index, "revision_notes":revision_notes,"parent_script_id":parent_script_id}
        script_id = uuid.uuid4().hex
        path = directory(script_id)
        with server._lock:
            if server._active_job is not None:
                raise HTTPException(409, "Studio is busy. Wait for the active video or script job to finish.")
            if request["brief"].get("writer_backend", "local") == "local":
                server.require_memory()
            path.mkdir(parents=True)
            persist(path, {"id": script_id, "status": "queued", "progress": 0, "stage": "Queued", "brief": brief,"revision_notes":revision_notes,"parent_script_id":parent_script_id})
            _write_json(path / "review_input.json", {"script_request": request})
            server._active_job = script_id
            try:
                server._executor.submit(process, script_id, request)
            except Exception:
                server._active_job = None
                raise
        return read(script_id)

    @app.get("/api/scripts/{script_id}")
    def detail(script_id: str):
        return read(script_id)

    @app.post("/api/scripts/{script_id}/retry", status_code=202)
    def retry(script_id: str, values: Annotated[dict | None, Body()] = None):
        from studio_pipeline import _write_json
        path = directory(script_id)
        with server._lock:
            state = read(script_id)
            if server._active_job is not None:
                raise HTTPException(409, "Studio is busy. Wait for the active job to finish.")
            flagged = state.get("hook_options", {}).get("review_status") in {"needs_review", "unavailable"}
            if state["status"] != "failed" and not (state["status"] == "completed" and flagged):
                raise HTTPException(409, "Only stopped jobs or hooks needing review can be retried.")
            try:
                request = json.loads((path / "review_input.json").read_text(encoding="utf-8"))["script_request"]
            except (OSError, ValueError, KeyError):
                raise HTTPException(422, "Saved generation input is unavailable. Start from the brief instead.") from None
            if values and values.get("writer_backend") == "local":
                choice=values.get("local_model","auto")
                from studio_script_local import resolve_local_model
                try:
                    resolve_local_model({"local_model":choice})
                except ValueError as exc:
                    raise HTTPException(422,str(exc)) from None
                request["brief"].update(writer_backend="local",local_model=choice,hf_credits_allowed=False)
                _write_json(path / "review_input.json", {"script_request":request})
            elif values and values.get("writer_backend") is not None:
                raise HTTPException(422,"Retry can switch to local only. Start a new brief to change hosted settings.")
            if request["brief"].get("writer_backend", "local") == "local":
                server.require_memory()
            from studio_script_hf import validate_configuration
            try:
                validate_configuration(request["brief"])
            except ValueError as exc:
                raise HTTPException(422,str(exc)) from None
            # Keep completion checkpoints and saved drafts. Matching prompts
            # resume; version/signature changes invalidate incompatible output.
            _write_json(path / "state.json", {"id": script_id, "status": "queued", "progress": 0,
                                                "stage": "Resuming saved generation", "brief": request["brief"]})
            server._active_job = script_id
            try:
                server._executor.submit(process, script_id, request)
            except Exception:
                server._active_job = None
                raise
        return read(script_id)

    @app.put("/api/scripts/{script_id}/draft")
    def save_draft(script_id: str, values: Annotated[dict, Body()]):
        state = read(script_id)
        if state["status"] not in {"completed", "failed"}:
            raise HTTPException(409, "Wait for generation to finish before editing.")
        if "result" not in state:
            raise HTTPException(409, "Generate a script first.")
        try:
            draft = writer.validate_script(values, state["brief"])
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise HTTPException(422, str(exc)) from None
        from studio_pipeline import _write_json
        with server._lock:
            _write_json(directory(script_id) / "edited_script.json", draft)
        return {"saved": True, "score_status": "Edited draft is unscored. Generate a new revision to assess changes."}

    @app.get("/api/scripts/{script_id}/draft")
    def get_draft(script_id: str):
        read(script_id)
        path = directory(script_id) / "edited_script.json"
        if not path.exists():
            raise HTTPException(404, "No edited draft saved.")
        return json.loads(path.read_text(encoding="utf-8"))

    @app.get("/api/scripts/{script_id}/export")
    def export(script_id: str, format: str = "txt"):
        state = read(script_id)
        if "result" not in state:
            raise HTTPException(409, "No completed draft is available yet.")
        result = state["result"]
        edited = directory(script_id) / "edited_script.json"
        if edited.exists():
            result["best"]["script"] = json.loads(edited.read_text(encoding="utf-8"))
            result["best"]["assessment"].update(score="Unscored edited draft", method="Manually edited; previous automated score does not apply.")
        content = writer.export_text(result)
        if format == "print":
            import html
            return HTMLResponse('<!doctype html><html><meta charset="utf-8"><title>Script export</title><style>body{font:16px/1.6 system-ui;max-width:850px;margin:40px auto}pre{white-space:pre-wrap;font:inherit}@media print{button{display:none}}</style><button onclick="window.print()">Print / Save as PDF</button><pre>' + html.escape(content) + '</pre></html>')
        if format != "txt":
            raise HTTPException(422, "Choose txt or print.")
        return PlainTextResponse(content, headers={"Content-Disposition": 'attachment; filename="video-script.txt"'})
