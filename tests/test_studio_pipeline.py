"""GPU-only safety and staging regression checks without loading ML libraries."""
from __future__ import annotations

from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import studio_pipeline as pipeline


def gpu(used=600, total=6144, available=True, temperature=65):
    return {"available": available, "name": "Test GPU", "total_mb": total, "used_mb": used, "temperature_c": temperature}


class WorkerMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.output = Path(self.temporary.name)
        self.video = self.output / "input.mp4"
        self.progress = Mock()
        self.memory_patch = patch.object(pipeline, "require_memory")
        self.memory_patch.start()
        self.addCleanup(self.memory_patch.stop)

    def tearDown(self):
        self.temporary.cleanup()

    def worker(self, device="cuda"):
        return pipeline._run_worker("speech", self.video, self.output, device, 4096, self.progress, 20, 58)

    def test_preflight_rejects_crowded_gpu_without_starting_process(self):
        with patch.object(pipeline, "gpu_info", return_value=gpu(2700)), \
                patch.object(pipeline.subprocess, "Popen") as spawn:
            ok, peak, reason = self.worker()
        self.assertFalse(ok)
        self.assertEqual(peak, 2700)
        self.assertIn("before starting", reason)
        spawn.assert_not_called()

    def test_ram_pressure_prevents_model_start(self):
        with patch.object(pipeline, "require_memory", side_effect=pipeline.ResourcePressureError("Low RAM")), \
                patch.object(pipeline.subprocess, "Popen") as spawn:
            with self.assertRaises(pipeline.ResourcePressureError):
                self.worker()
        spawn.assert_not_called()

    def test_ram_watchdog_kills_worker_and_aborts_instead_of_retrying(self):
        process = Mock(pid=4321, returncode=None)
        process.poll.return_value = None
        with patch.object(pipeline, "require_memory", side_effect=[None, pipeline.ResourcePressureError("Low RAM")]), \
                patch.object(pipeline, "gpu_info", return_value=gpu()), \
                patch.object(pipeline.subprocess, "Popen", return_value=process), \
                patch.object(pipeline, "_terminate_worker") as stop:
            with self.assertRaises(pipeline.ResourcePressureError):
                self.worker()
        stop.assert_called_once_with(process)

    def test_preflight_requires_memory_monitoring(self):
        with patch.object(pipeline, "gpu_info", return_value=gpu(0, available=False)), \
                patch.object(pipeline.subprocess, "Popen") as spawn:
            ok, _, reason = self.worker()
        self.assertFalse(ok)
        self.assertTrue(reason)
        spawn.assert_not_called()

    def test_validation_failure_is_not_misreported_as_cuda_failure(self):
        process = Mock(pid=4321, returncode=1)
        process.poll.return_value = 1
        def spawn(*args, **kwargs):
            (self.output / "worker_speech_error.json").write_text(json.dumps({"error": "Invalid review operation"}))
            return process
        with patch.object(pipeline, "gpu_info", return_value=gpu()), \
                patch.object(pipeline.subprocess, "Popen", side_effect=spawn):
            ok, _, reason = self.worker()
        self.assertFalse(ok)
        self.assertIn("Invalid review operation", reason)
        self.assertNotIn("could not run on CUDA", reason)

    def test_watchdog_stops_its_worker_and_preserves_observed_peak(self):
        process = Mock(pid=4321, returncode=None)
        process.poll.return_value = None

        def terminate(owned):
            self.assertIs(owned, process)
            owned.returncode = -9

        with patch.object(pipeline, "gpu_info", side_effect=[gpu(700), gpu(3900)]), \
                patch.object(pipeline.subprocess, "Popen", return_value=process) as spawn, \
                patch.object(pipeline, "_terminate_worker", side_effect=terminate) as terminate_mock:
            ok, peak, reason = self.worker()
        self.assertFalse(ok)
        self.assertEqual(peak, 3900)
        self.assertIn("memory guard", reason)
        terminate_mock.assert_called_once_with(process)
        spawn.assert_called_once()
        self.assertIn("--budget-mb", spawn.call_args.args[0])

    def test_monitor_failure_stops_running_gpu_worker(self):
        process = Mock(pid=4321, returncode=None)
        process.poll.return_value = None

        def terminate(owned):
            owned.returncode = -9

        with patch.object(pipeline, "gpu_info", side_effect=[gpu(700), gpu(0, available=False)]), \
                patch.object(pipeline.subprocess, "Popen", return_value=process), \
                patch.object(pipeline, "_terminate_worker", side_effect=terminate) as terminate_mock:
            ok, peak, reason = self.worker()
        self.assertFalse(ok)
        self.assertEqual(peak, 700)
        self.assertIn("monitoring became unavailable", reason)
        terminate_mock.assert_called_once_with(process)

    def test_cpu_inference_is_rejected_without_spawning(self):
        with patch.object(pipeline.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(ValueError, "GPU-only"):
                self.worker(device="cpu")
        spawn.assert_not_called()

    def test_thermal_guard_stops_running_worker(self):
        process = Mock(pid=4321, returncode=None)
        process.poll.return_value = None
        def stop(owned):
            owned.returncode = -9
        with patch.object(pipeline, "gpu_info", side_effect=[gpu(), gpu(temperature=83)]), \
                patch.object(pipeline.subprocess, "Popen", return_value=process), \
                patch.object(pipeline, "_terminate_worker", side_effect=stop) as terminate:
            ok, _, reason = self.worker()
        self.assertFalse(ok)
        self.assertIn("temperature guard", reason)
        terminate.assert_called_once_with(process)

    def test_warm_gpu_does_not_start_worker(self):
        with patch.object(pipeline, "gpu_info", return_value=gpu(temperature=80)), \
                patch.object(pipeline.subprocess, "Popen") as spawn:
            ok, _, reason = self.worker()
        self.assertFalse(ok)
        self.assertIn("warm", reason)
        spawn.assert_not_called()

    def test_termination_targets_only_owned_process_tree(self):
        process = Mock(pid=4321)
        with patch.object(pipeline.os, "name", "nt"), \
                patch.object(pipeline.subprocess, "run") as taskkill:
            pipeline._terminate_worker(process)
        self.assertEqual(taskkill.call_args.args[0], ["taskkill", "/PID", "4321", "/T", "/F"])
        process.wait.assert_called_once_with(timeout=10)
        process.kill.assert_not_called()

    def test_unresponsive_worker_is_killed_after_termination_timeout(self):
        process = Mock(pid=4321)
        process.wait.side_effect = [subprocess.TimeoutExpired("test-worker", 10), 0]
        with patch.object(pipeline.os, "name", "nt"), patch.object(pipeline.subprocess, "run"):
            pipeline._terminate_worker(process)
        process.kill.assert_called_once()
        self.assertEqual(process.wait.call_count, 2)


class AdaptivePacingTests(unittest.TestCase):
    def test_warm_gpu_cools_with_headroom_before_next_burst(self):
        with patch.object(pipeline, "require_memory"), patch.object(pipeline, "gpu_info", side_effect=[gpu(temperature=79), gpu(temperature=78), gpu(temperature=77)]) as info, \
                patch.object(pipeline.time, "sleep") as sleep:
            pipeline.stage_pause(Mock(), 0)
        self.assertEqual(info.call_count, 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [.5, .5])

    def test_cool_gpu_has_no_artificial_delay(self):
        with patch.object(pipeline, "require_memory"), patch.object(pipeline, "gpu_info", return_value=gpu(temperature=60)), \
                patch.object(pipeline.time, "sleep") as sleep:
            pipeline.stage_pause(Mock(), 0)
        sleep.assert_not_called()

    def test_hot_gpu_waits_before_resuming(self):
        with patch.object(pipeline, "require_memory"), patch.object(pipeline, "gpu_info", side_effect=[gpu(temperature=80), gpu(temperature=77)]), \
                patch.object(pipeline.time, "sleep") as sleep:
            progress = Mock()
            pipeline.stage_pause(progress, 50)
        sleep.assert_called()
        self.assertIn("cooling", progress.call_args.args[1])

    def test_warm_but_safe_gpu_keeps_working(self):
        with patch.object(pipeline, "require_memory"), patch.object(pipeline, "gpu_info", return_value=gpu(temperature=76)), \
                patch.object(pipeline.time, "sleep") as sleep:
            pipeline.stage_pause(Mock(), 0)
        sleep.assert_not_called()


class CpuIsolationTests(unittest.TestCase):
    def test_cpu_stage_is_terminated_on_ram_pressure(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp);process=Mock(pid=4321);process.poll.return_value=None
            with patch.object(pipeline,'require_memory',side_effect=[None,pipeline.ResourcePressureError('Low RAM')]), \
                    patch.object(pipeline.subprocess,'Popen',return_value=process), \
                    patch.object(pipeline,'_terminate_worker') as terminate:
                with self.assertRaises(pipeline.ResourcePressureError):
                    pipeline._run_cpu_stage('ocr',output/'input.mp4',output,Mock())
            terminate.assert_called_once_with(process)

    def test_cpu_stage_releases_before_returning_and_preserves_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp);process=Mock(pid=4321,returncode=1);process.poll.return_value=1
            def spawn(*args,**kwargs):
                (output/'worker_ocr_error.json').write_text(json.dumps({'error':'Unreadable video'}))
                return process
            with patch.object(pipeline,'require_memory'),patch.object(pipeline.subprocess,'Popen',side_effect=spawn):
                with self.assertRaisesRegex(RuntimeError,'Unreadable video'):
                    pipeline._run_cpu_stage('ocr',output/'input.mp4',output,Mock())


class AnalysisFallbackTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.output = Path(self.temporary.name)
        self.video = self.output / "input.mp4"
        self.clip_factory = Mock()
        self.clip_factory.return_value.__enter__ = Mock(return_value=SimpleNamespace(duration=2.0, w=1280, h=720))
        self.clip_factory.return_value.__exit__ = Mock(return_value=False)
        self.info = {"duration_seconds": 2.0, "width": 1280, "height": 720,
                     "fps": 30, "file_bytes": 123, "has_audio": True}

        def inspect(video, output):
            (output / "video_metrics.csv").write_text(
                "time_seconds,brightness_0_255,frame_difference_0_255,audio_rms_dbfs,audio_peak_dbfs\n"
                "0,100,0,-20,-6\n", encoding="utf-8")
            return dict(self.info)

        def report(info, measurements, transcript, scenes, processing):
            return {"video": info, "transcript": transcript or {"segments": []}, "scenes": scenes, "processing": processing, "limitations": []}

        self.inspect = Mock(side_effect=inspect)
        self.render_pdf = Mock()
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(pipeline, "require_memory"))
        self.pause = self.stack.enter_context(patch.object(pipeline, "stage_pause"))
        # These imports happen inside run_analysis; substitute the dependency
        # boundaries so this test suite never imports torch, decodes video, or
        # downloads models.
        self.stack.enter_context(patch.dict("sys.modules", {
            "analyze_video": SimpleNamespace(inspect_video=self.inspect),
            "moviepy": SimpleNamespace(VideoFileClip=self.clip_factory),
            "studio_report": SimpleNamespace(build_report=report, render_pdf=self.render_pdf),
        }))
        self.stack.enter_context(patch.object(pipeline, "get_system_info", return_value={
            "max_budget_mb": 5120, "cuda_ready": True, "gpu": gpu(600),
        }))
        self.stack.enter_context(patch.object(pipeline, "_charts"))
        self.stack.enter_context(patch.object(pipeline, "prepare_video", side_effect=lambda v,o,p:self.inspect(v,o)))
        self.stack.enter_context(patch.object(pipeline, "ocr_analysis", return_value={"sources":[],"available":True}))
        self.stack.enter_context(patch("studio_brief.create_clips"))
        self.stack.enter_context(patch("studio_screenshots.create_screenshots"))
        self.stack.enter_context(patch("studio_av_signals.voice_from_video", return_value={
            "available": True, "sources": [{"id": "A1", "start": 0, "end": 1,
                                             "kind": "audio", "text": "Measured test audio"}],
            "note": "Fixture audio"}))
        self.stack.enter_context(patch("studio_av_signals.visual_observations", return_value={
            "available": True, "sources": [{"id": "V1", "start": 0, "end": 1,
                                             "kind": "visual", "text": "Measured test frame"}],
            "note": "Fixture visual"}))

    def tearDown(self):
        self.stack.close()
        self.temporary.cleanup()

    def analyze(self, budget=4096, vision=True):
        return pipeline.run_analysis(self.video, self.output, budget, vision)

    def write_speech(self):
        transcript = {"language": "en", "precision": "int8", "segments": [
            {"start": 0.0, "end": 1.0, "text": "Test speech", "words": []},
        ]}
        (self.output / "transcript.json").write_text(json.dumps(transcript), encoding="utf-8")

    def write_vision(self):
        (self.output / "scenes.json").write_text(json.dumps({
            "precision": "float16", "scenes": [{"time_seconds": 0, "caption": "A test scene"}],
        }), encoding="utf-8")

    def test_out_of_range_budget_fails_before_video_or_model_work(self):
        with patch.object(pipeline, "_run_worker") as worker:
            for budget in (0, 1023, 4608, 5120, 6144):
                with self.subTest(budget=budget), self.assertRaisesRegex(ValueError, "GPU target"):
                    self.analyze(budget=budget)
            worker.assert_not_called()
        self.clip_factory.assert_not_called()
        self.inspect.assert_not_called()
        self.render_pdf.assert_not_called()

    def test_all_model_stages_run_sequentially_on_gpu_with_pauses(self):
        calls = []
        def worker(task, video, output, device, *args):
            self.assertEqual(device, "cuda")
            calls.append(task)
            if task == "speech":
                self.write_speech()
            elif task == "vision":
                self.write_vision()
            else:
                (output / "review.json").write_text(json.dumps({"available": True, "overall_score": 60,
                    "verdict": "Test", "summary": "Test review", "strengths": [], "edits": [], "score_note": "Test"}))
            return True, 3000, ""
        with patch.object(pipeline, "_run_worker", side_effect=worker):
            report = self.analyze()
        self.assertEqual(calls, ["speech", "vision", "review"])
        self.assertEqual(self.pause.call_count, 3)
        self.assertEqual(report["processing"]["device"], "cuda")
        self.assertEqual(report["processing"]["peak_gpu_mb"], 3000)
        self.render_pdf.assert_called_once()

    def test_gpu_failure_aborts_without_cpu_retry_or_next_model(self):
        with patch.object(pipeline, "_run_worker", return_value=(False, 3900, "GPU guard triggered.")) as worker:
            with self.assertRaisesRegex(RuntimeError, "no CPU fallback"):
                self.analyze()
        self.assertEqual(worker.call_count, 1)
        self.render_pdf.assert_not_called()

    def test_trusted_ocr_does_not_hide_visual_footage(self):
        ocr={"available":True,"sources":[{"id":f"O{i+1}","start":i/10,"end":i/10+.1,
             "text":f"label {i}","confidence":.95,"frame_file":"frames/frame_00.jpg"} for i in range(6)]}
        def worker(task, video, output, device, *args):
            if task == "speech": self.write_speech()
            elif task == "vision": self.write_vision()
            elif task == "review":
                (output / "review.json").write_text(json.dumps({"available":True,"overall_score":60,
                    "verdict":"Test","summary":"Test review","strengths":[],"edits":[],"score_note":"Test"}))
            return True, 3000, ""
        with patch.object(pipeline,"ocr_analysis",return_value=ocr), \
                patch.object(pipeline,"_run_worker",side_effect=worker) as run:
            report=self.analyze()
        self.assertEqual([call.args[0] for call in run.call_args_list],["speech","vision","review"])
        self.assertTrue(report["visual"]["available"])

    def test_retry_reuses_completed_transcription(self):
        self.write_speech()
        def worker(task, video, output, device, *args):
            self.assertEqual(task, "review")
            (output / "review.json").write_text(json.dumps({"available": True, "overall_score": 60,
                "verdict": "Test", "summary": "Test review", "strengths": [], "edits": [], "score_note": "Test"}))
            return True, 3000, ""
        with patch.object(pipeline, "_run_worker", side_effect=worker) as run:
            self.analyze(vision=False)
        self.assertEqual([call.args[0] for call in run.call_args_list], ["review"])

    def test_gpu_unavailable_aborts_before_decoding(self):
        with patch.object(pipeline, "get_system_info", return_value={"max_budget_mb": 4096, "cuda_ready": False, "gpu": gpu(available=False)}):
            with self.assertRaisesRegex(RuntimeError, "NVIDIA GPU"):
                self.analyze()
        self.clip_factory.assert_not_called()

    def test_silent_video_skips_speech_worker(self):
        self.info["has_audio"] = False
        with patch.object(pipeline, "_run_worker") as worker:
            report = self.analyze(vision=False)
        worker.assert_not_called()
        self.assertTrue(any("No audio stream" in warning for warning in report["processing"]["warnings"]))
        self.assertEqual(report["processing"]["models"], [])


if __name__ == "__main__":
    unittest.main()
