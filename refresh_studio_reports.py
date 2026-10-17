"""Refresh completed semantic reports with estimates and embedded screenshots.

Run while Studio is stopped. Original PDFs/JSON are retained once as backups.
No transcription or creative-model inference is repeated.
"""
import json
from pathlib import Path
import shutil
import sys
import argparse

from studio_estimate import apply_estimate
from studio_pipeline import _write_json
from studio_review import transcript_quality, validate_review
from studio_review_output import render_detailed_pdf
from studio_screenshots import create_screenshots, screenshot_path

ROOT = Path(__file__).resolve().parent

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids", nargs="*")
    parser.add_argument("--reuse-screenshots", action="store_true")
    parser.add_argument("--revalidate", action="store_true", help="Revalidate saved model JSON without generating new text")
    args = parser.parse_args()
    for job_file in sorted((ROOT / "results/studio").glob("*/job.json")):
        if args.ids and job_file.parent.name not in args.ids:
            continue
        job = json.loads(job_file.read_text(encoding="utf-8"))
        directory = job_file.parent
        if job.get("status") != "completed" or not (directory / "report.json").exists():
            continue
        report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
        if not report.get("review", {}).get("available"):
            continue
        for name in ("report.json", "report.pdf", "job.json"):
            backup = directory / (name + ".before-estimate")
            if (directory / name).exists() and not backup.exists():
                shutil.copy2(directory / name, backup)
        if args.revalidate:
            raw = json.loads((directory / "review_raw.json").read_text(encoding="utf-8"))
            validated = validate_review(raw, report)
            old_frames = {(e["start"], e["end"]): e.get("screenshots", []) for e in report["review"]["edits"]}
            for edit in validated["edits"]:
                edit["screenshots"] = old_frames.get((edit["start"], edit["end"]), [])
            report["review"].update(validated)
        apply_estimate(report["review"], report)
        if report["review"].get("brand_review"):
            from studio_brand_review import apply_brand_score
            apply_brand_score(report["review"])
        report["review"]["transcript_quality"] = transcript_quality(report)
        report["brief"].update(overall_score=report["review"]["overall_score"],
                               score_note=report["review"]["score_note"])
        video = next((p for p in directory.glob("input.*") if p.suffix.lower() in {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}), None)
        if video is None:
            raise FileNotFoundError(f"Source video missing in {directory}")
        items = report["review"]["edits"] + report["brief"]["clips"]
        ready = all(item.get("screenshots") and all(screenshot_path(f, directory) for f in item["screenshots"]) for item in items)
        if not args.reuse_screenshots or not ready:
            create_screenshots(video, directory, report)
        render_detailed_pdf(report, directory)
        _write_json(directory / "report.json", report)
        job["report"] = report
        _write_json(job_file, job)
        frames = [f for e in report["review"]["edits"] + report["brief"]["clips"] for f in e.get("screenshots", [])]
        print(json.dumps({"job": job["id"], "score": report["review"]["overall_score"],
                          "frames": len(frames), "failed_frames": sum("error" in f for f in frames)}), flush=True)
