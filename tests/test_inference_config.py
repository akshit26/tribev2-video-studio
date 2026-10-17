"""Regression checks that do not download or allocate model weights."""
import tempfile
import unittest
from pathlib import Path, PureWindowsPath
from unittest.mock import patch

import yaml

from tribev2.demo_utils import TribeModel, _CheckpointConfigLoader


class ConfigTests(unittest.TestCase):
    def test_released_yaml_path_on_windows(self):
        value = yaml.load("p: !!python/object/apply:pathlib.PosixPath [/, checkpoint, cache]\nt: !!python/tuple [1, 2]", Loader=_CheckpointConfigLoader)
        self.assertEqual(value["p"], str(Path("/", "checkpoint", "cache")))
        self.assertEqual(value["t"], (1, 2))

    def test_other_python_yaml_tags_rejected(self):
        with self.assertRaises(yaml.constructor.ConstructorError):
            yaml.load("!!python/object/apply:builtins.str [hello]", Loader=_CheckpointConfigLoader)

    def test_hub_id_and_cpu_devices(self):
        config = {"infra": {"folder": "/training", "workdir": None}, "data": {
            "study": {"infra_timelines": {}}, "neuro": {"infra": {}},
            "text_feature": {"device": "cuda"}, "audio_feature": {"device": "cuda"},
            "video_feature": {"image": {"device": "cuda"}},
            "image_feature": {"infra": {}, "image": {"device": "cuda"}}}}
        class Captured(Exception):
            pass
        seen = {}
        def capture(**kwargs):
            seen.update(kwargs)
            raise Captured
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.yaml"
            config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
            ckpt_path = Path(directory) / "best.ckpt"
            with patch("huggingface_hub.hf_hub_download", side_effect=[str(config_path), str(ckpt_path)]) as download:
                with self.assertRaises(Captured):
                    TribeModel.from_pretrained.__func__(capture, PureWindowsPath("facebook/tribev2"), device="cpu")
            self.assertEqual(download.call_args_list[0].args, ("facebook/tribev2", "config.yaml"))
            self.assertEqual(seen["checkpoint_path"], str(ckpt_path))
            self.assertEqual(seen["data"]["text_feature"]["device"], "cpu")
            self.assertEqual(seen["data"]["audio_feature"]["device"], "cpu")
            self.assertEqual(seen["data"]["video_feature"]["image"]["device"], "cpu")


if __name__ == "__main__":
    unittest.main()
