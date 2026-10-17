import math
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from studio_av_signals import decode_pcm, voice_observations


class AudioEvidenceTests(unittest.TestCase):
    def test_ffmpeg_decodes_varying_waveform_and_voice_spans(self):
        # Regression: MoviePy previously supplied a repeated constant sample
        # for a real video, making vocal delivery measurements meaningless.
        rate = 16000
        seconds = 2
        t = np.arange(rate * seconds) / rate
        signal = .2 * np.sin(2 * math.pi * 180 * t)
        signal[rate:] *= .2
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "voice.wav"
            with wave.open(str(path), "wb") as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(rate)
                out.writeframes((signal * 32767).astype("<i2").tobytes())
            decoded = decode_pcm(path)
        self.assertGreater(float(decoded.std()), .02)
        self.assertGreater(float(decoded[:rate].std()), float(decoded[rate:].std()) * 4)
        evidence = voice_observations(decoded, seconds_per_span=1)
        self.assertEqual([row["id"] for row in evidence["sources"]], ["A1", "A2"])
        self.assertNotEqual(evidence["sources"][0]["median_level_dbfs"],
                            evidence["sources"][1]["median_level_dbfs"])
