"""API regression checks; no video models, network, or GPU are needed."""
from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import studio_server as server


class StudioServerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.results = Path(self.directory.name)
        self.patchers = [
            patch.object(server, "require_memory"),
            patch.object(server, "get_system_info", return_value={"max_budget_mb":5632,"default_budget_mb":5632}),
            patch.object(server, "RESULTS_DIR", self.results),
            patch.object(server, "_jobs", {}),
            patch.object(server, "_active_job", None),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.client = TestClient(server.app, base_url="http://127.0.0.1:8765")

    def tearDown(self):
        self.client.close()
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.directory.cleanup()

    def upload(self, filename="example.mp4", content=b"test video", **data):
        return self.client.post("/api/jobs", files={"video": (filename, content, "video/mp4")}, data=data)

    def wait_for_job(self, job_id):
        end = time.monotonic() + 5
        while time.monotonic() < end:
            job = self.client.get(f"/api/jobs/{job_id}").json()
            if job["status"] in {"completed", "failed"}:
                # The final manifest is published immediately before releasing the slot.
                with server._lock:
                    if server._active_job is None:
                        return job
            time.sleep(0.01)
        self.fail("Worker did not finish in five seconds")

    def test_complete_report_downloads_and_private_input(self):
        def analyze(video, output, budget_mb, vision, progress):
            self.assertEqual(video.read_bytes(), b"test video")
            self.assertEqual(budget_mb, 5632)
            self.assertTrue(vision)
            self.assertEqual(json.loads((output / "upload_info.json").read_text())["original_name"], "example.mp4")
            progress(45, "Testing analysis")
            (output / "report.pdf").write_bytes(b"%PDF-1.4 test")
            (output / "frames").mkdir()
            (output / "frames" / "frame_01.jpg").write_bytes(b"jpg")
            (output / "clips").mkdir()
            (output / "clips" / "clip_00.mp4").write_bytes(b"0123456789")
            return {"summary": "A test report", "processing": {"peak_gpu_mb": 1200}}

        with patch.object(server, "run_analysis", side_effect=analyze):
            response = self.upload()
            self.assertEqual(response.status_code, 202)
            job_id = response.json()["id"]
            job = self.wait_for_job(job_id)
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["progress"], 100)
        self.assertEqual(job["gpu_peak_mb"], 1200)
        self.assertEqual(self.client.get(job["report_url"]).json()["summary"], "A test report")
        pdf = self.client.get(job["pdf_url"])
        self.assertEqual(pdf.content, b"%PDF-1.4 test")
        self.assertIn("attachment", pdf.headers["content-disposition"])
        self.assertEqual(self.client.get(job["files_url"] + "frames/frame_01.jpg").status_code, 200)
        clip = self.client.get(job["files_url"] + "clips/clip_00.mp4", headers={"Range": "bytes=2-5"})
        self.assertEqual(clip.status_code, 206)
        self.assertEqual(clip.content, b"2345")
        self.assertEqual(clip.headers["content-type"], "video/mp4")
        self.assertNotIn("attachment", clip.headers.get("content-disposition", ""))
        self.assertEqual(self.client.get(job["files_url"] + "clips/input.mp4").status_code, 404)
        for name in ["input.mp4", "upload_info.json", "job.json", ".env", "../.env", "frames/../../.env"]:
            self.assertEqual(self.client.get(job["files_url"] + name).status_code, 404)
        # Reports remain accessible when the in-memory job cache is empty.
        with server._lock:
            server._jobs.clear()
        self.assertEqual(self.client.get(job["report_url"]).json()["summary"], "A test report")

    def test_only_one_gpu_job_can_run(self):
        started = threading.Event()
        release = threading.Event()

        def analyze(**kwargs):
            started.set()
            if not release.wait(5):
                raise RuntimeError("Test timed out")
            return {"summary": "done"}

        with patch.object(server, "run_analysis", side_effect=analyze) as mock:
            job_id = self.upload().json()["id"]
            try:
                self.assertTrue(started.wait(3))
                self.assertEqual(self.upload().status_code, 409)
                self.assertEqual(self.client.get(f"/api/jobs/{job_id}/report").status_code, 409)
                self.assertEqual(mock.call_count, 1)
            finally:
                release.set()
                self.wait_for_job(job_id)

    def test_rejects_invalid_upload_and_memory_budget(self):
        with patch.object(server, "run_analysis") as mock:
            self.assertEqual(self.upload("script.py").status_code, 415)
            self.assertEqual(self.upload(content=b"").status_code, 400)
            self.assertEqual(self.upload(budget_mb="1023").status_code, 422)
            self.assertEqual(self.upload(budget_mb="8192").status_code, 422)
            self.assertEqual(self.upload(budget_mb="262145").status_code, 422)
            with patch.object(server, "MAX_UPLOAD_BYTES", 4):
                self.assertEqual(self.upload(content=b"12345").status_code, 413)
            self.assertIsNone(server._active_job)
            mock.assert_not_called()

    def test_rejects_remote_hosts_and_cross_origin_upload(self):
        self.assertEqual(self.client.get("/", headers={"host": "evil.example"}).status_code, 403)
        for headers in [{"Origin": "https://evil.example"}, {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"}]:
            response = self.client.post("/api/jobs", files={"video": ("x.mp4", b"x")}, headers=headers)
            self.assertEqual(response.status_code, 403)
        self.assertIsNone(server._active_job)

    def test_failed_job_exposes_error_without_credentials(self):
        with patch.object(server, "run_analysis", side_effect=RuntimeError("Download failed hf_FAKESECRET123")):
            job_id = self.upload().json()["id"]
            job = self.wait_for_job(job_id)
        self.assertEqual(job["status"], "failed")
        self.assertIn("[redacted token]", job["error"])
        self.assertNotIn("FAKESECRET", job["error"])
        self.assertIsNone(server._active_job)

    def test_interrupted_job_is_marked_failed_on_restart(self):
        job_id = "a" * 32
        directory = self.results / job_id
        directory.mkdir()
        (directory / "job.json").write_text(json.dumps({"id": job_id, "status": "running", "progress": 50}))
        job = self.client.get(f"/api/jobs/{job_id}").json()
        self.assertEqual(job["status"], "failed")
        self.assertIn("restarted", job["error"])
        self.assertEqual(self.client.get("/api/jobs/not-a-job").status_code, 404)

    def test_system_reports_busy_and_upload_limits(self):
        with patch.object(server, "get_system_info", return_value={"cuda_available": True}):
            info = self.client.get("/api/system").json()
        self.assertTrue(info["cuda_available"])
        self.assertFalse(info["busy"])
        self.assertEqual(info["upload_limit_mb"], 250)

    def test_low_ram_rejects_upload_without_starting_analysis(self):
        with patch.object(server, "require_memory", side_effect=server.ResourcePressureError("Low RAM")), \
                patch.object(server, "run_analysis") as analyze:
            response = self.upload()
        self.assertEqual(response.status_code, 503)
        self.assertIsNone(server._active_job)
        analyze.assert_not_called()

    def test_failed_job_can_resume_saved_upload_without_new_analysis(self):
        job_id = "b" * 32
        directory = self.results / job_id
        directory.mkdir()
        (directory / "input.mp4").write_bytes(b"saved upload")
        (directory / "job.json").write_text(json.dumps({"id": job_id, "status": "failed", "vision": True}))
        with patch.object(server, "resume_analysis", return_value={"summary": "Recovered"}) as resume, \
                patch.object(server, "run_analysis") as fresh:
            self.assertEqual(self.client.post(f"/api/jobs/{job_id}/retry").status_code, 202)
            self.assertEqual(self.wait_for_job(job_id)["status"], "completed")
        resume.assert_called_once()
        fresh.assert_not_called()
        self.assertEqual(self.client.post(f"/api/jobs/{job_id}/retry").status_code, 409)

    def test_correcting_transcript_preserves_times_and_reuses_video(self):
        job_id = "c" * 32
        directory = self.results / job_id
        directory.mkdir()
        (directory / "input.mp4").write_bytes(b"saved video")
        (directory / "job.json").write_text(json.dumps({"id": job_id, "status": "completed", "vision": True}))
        original = {"video": {"duration_seconds": 12}, "metrics": {}, "transcript": {"language": "te", "segments": [
            {"start": 2, "end": 8, "text": "Incorrect", "words": [{"word": "Incorrect", "probability": .2}]}]}}
        (directory / "review_input.json").write_text(json.dumps(original))
        endpoint = f"/api/jobs/{job_id}/correct-transcript"
        self.assertEqual(self.client.post(endpoint, json={"texts": []}).status_code, 422)
        with patch.object(server, "resume_analysis", return_value={"summary": "Corrected review"}) as resume:
            result = self.client.post(endpoint, json={"texts": ["మీ నీళ్ల సీసా"]})
            self.assertEqual(result.status_code, 202)
            self.wait_for_job(job_id)
        resume.assert_called_once()
        corrected = json.loads((directory / "review_input.json").read_text(encoding="utf-8"))
        segment = corrected["transcript"]["segments"][0]
        self.assertEqual((segment["start"], segment["end"]), (2, 8))
        self.assertEqual(segment["words"], [])
        self.assertEqual(segment["text"], "మీ నీళ్ల సీసా")
        self.assertTrue(corrected["transcript"]["manually_corrected"])
        self.assertEqual(json.loads((directory / "review_input_original.json").read_text())["transcript"]["segments"][0]["text"], "Incorrect")


if __name__ == "__main__":
    unittest.main()
