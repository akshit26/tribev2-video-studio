import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import studio_video


class VideoTests(unittest.TestCase):
    def test_video_path_uses_hardware_decode_scale_and_encode(self):
        command = studio_video.clip_command("ffmpeg", "input.mov", "clip.mp4", 0, 5)
        self.assertEqual(command[command.index("-hwaccel") + 1], "cuda")
        self.assertEqual(command[command.index("-hwaccel_output_format") + 1], "cuda")
        self.assertIn("scale_cuda", command[command.index("-vf") + 1])
        self.assertEqual(command[command.index("-c:v") + 1], "h264_nvenc")
        self.assertNotIn("libx264", command)

    def test_gpu_guard_terminates_renderer(self):
        info = {"available": True, "used_mb": 0, "temperature_c": 60}
        process = Mock(pid=999, returncode=None)
        process.poll.return_value = None
        with tempfile.TemporaryDirectory() as tmp, \
                patch("studio_pipeline.stage_pause"), patch("studio_video.require_memory"), \
                patch("studio_pipeline.gpu_info", side_effect=[info, dict(info, used_mb=4000)]), \
                patch("studio_video.subprocess.Popen", return_value=process), \
                patch("studio_pipeline._terminate_worker") as stop:
            with self.assertRaisesRegex(RuntimeError, "guard"):
                studio_video.run_gpu_render(["ffmpeg"], Path(tmp) / "render.log")
        stop.assert_called_once_with(process)
