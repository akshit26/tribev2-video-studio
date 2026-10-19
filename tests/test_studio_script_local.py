"""Local model selection and separation from video-review runtime."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import studio_script_local as local
from studio_review import MODEL, review_command


class LocalWriterTests(unittest.TestCase):
    def test_recommended_prefers_new_writer_and_can_use_compatibility_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);new=root/'new.gguf';old=root/'old.gguf';old.touch()
            choices={'qwen35':('New',new),'qwen3':('Old',old)}
            with patch.object(local,'LOCAL_MODELS',choices):
                self.assertEqual(local.resolve_local_model({})[0],'qwen3')
                new.touch()
                self.assertEqual(local.resolve_local_model({})[0],'qwen35')
                self.assertEqual(local.resolve_local_model({'local_model':'qwen3'})[2],old)
                self.assertTrue(all(row['installed'] for row in local.local_configuration()))

    def test_missing_or_unknown_model_does_not_download_on_generation(self):
        with patch.object(local,'LOCAL_MODELS',{'qwen35':('New',Path('missing-writer-for-test.gguf'))}):
            with self.assertRaisesRegex(ValueError,'prepare_writer'):local.resolve_local_model({'local_model':'qwen35'})
            with self.assertRaises(ValueError):local.resolve_local_model({'local_model':'unknown'})

    def test_hybrid_writer_has_smaller_temperature_aware_bursts(self):
        from studio_review_parts import cool_writer_burst_limits
        self.assertEqual(cool_writer_burst_limits({'temperature_c':60}),(64,16))
        self.assertEqual(cool_writer_burst_limits({'temperature_c':68}),(32,8))
        self.assertEqual(cool_writer_burst_limits({}),(32,8))

    def test_writer_runtime_model_override_keeps_full_gpu_guards(self):
        writer=Path('writer-model.gguf')
        command=review_command(Path('llama-server.exe'),12345,writer)
        self.assertEqual(command[command.index('-m')+1],str(writer))
        self.assertEqual(command[command.index('-ngl')+1],'all')
        self.assertIn('--no-host',command)
        self.assertEqual(command[command.index('--cache-ram')+1],'0')
        normal=review_command(Path('llama-server.exe'),12345)
        self.assertEqual(normal[normal.index('-m')+1],str(MODEL))


if __name__=='__main__':unittest.main()
